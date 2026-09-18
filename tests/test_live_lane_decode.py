from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from moss_transcribe_diarize.app.live_adapters import (
    InferenceTranscript,
    LiveProviderTransientError,
)
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
    LiveSpeakerEvidence,
)
from moss_transcribe_diarize.app.live_lane_decode import (
    decode_refinement,
    finalize_lanes,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    EffectiveTranscriptSegment,
    LiveSession,
    LiveIdentitySnapshot,
    TextRevisionProposal,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape, CompleteMixedTapeUnavailable
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    TerminalDecodePlan,
    TerminalTranscriptFinalizer,
)

RATE = 16000


class Speech:
    def observe(self, *, frame, start_sample, end_sample):
        return (SpeechObservation(start_sample, end_sample, True),)


class Evidence:
    """Equal voices deliberately match EVERY existing speaker: lane scope must prevent it."""

    def score(self, *, segments, base_snapshot, **kwargs):
        return tuple(
            LiveSpeakerEvidence(s.speaker, canonical, 1.0)
            for s in segments
            for canonical in base_snapshot.canonical_speakers
        )

    def revision_reader(self):
        return Evidence()


def identity():
    return BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(16, 0.35, 0.1),
        evidence_provider=Evidence(),
        lane_factory=identity,
    )


class Decoder:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def transcribe_pcm(self, *, span, pcm):
        marker = pcm[0]
        self.calls.append(marker)
        if marker == self.fail:
            raise LiveProviderTransientError("injected")
        return InferenceTranscript(
            f"[0][S01]lane {marker}[{span.sample_count/RATE}]", elapsed_sec=0.1
        )


def make(decoder=None, *, capacity=640000, rolling=False):
    session = LiveSession(max_retained_samples=320000)
    arbiter = InferenceArbiter()
    decoder = decoder or Decoder()
    c = LiveCoordinator(
        session_key="lane-test",
        session=session,
        endpoint_policy=EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1, min_silence_samples=1, hard_cap_samples=40000
            )
        ),
        speech_provider=Speech(),
        decoder=decoder,
        identity_preparer=identity(),
        arbiter=arbiter,
        tape_capacity_bytes=capacity,
        rolling_decoder=decoder if rolling else None,
    )
    return c, decoder, session, arbiter


def frame(seq=0, count=40000, system=1, mic=2, silent=False):
    return AudioFrame(
        seq,
        bytes([7]) * count * 2,
        count,
        lane_pcm=(
            ("system", bytes([system]) * count * 2),
            ("microphone", bytes([mic]) * count * 2),
        ),
        lane_silent=(("system", False), ("microphone", silent)),
    )


def commit(c, arbiter):
    item = arbiter.next_work()
    work = c.capture_work_item(item)
    prepared = c.prepare_work_item(work)
    result = c.submit_prepared_work(prepared)
    return prepared, result


@pytest.mark.parametrize("mic,silent", [(0, False), (2, True)])
def test_zero_and_declared_silent_never_decode_or_birth(mic, silent):
    c, decoder, session, arbiter = make()
    c.accept_frame(frame(mic=mic, silent=silent))
    _, result = commit(c, arbiter)
    assert result.submitted
    assert decoder.calls == [1]
    assert {s.source_lane for s in session.snapshot().effective_transcript} == {
        "system"
    }
    assert session.snapshot().identity_snapshot.canonical_speakers == ("speaker-0001",)


def test_same_voice_two_namespaces_stable_across_spans_and_global_allocator():
    c, decoder, session, arbiter = make()
    for seq in range(2):
        c.accept_frame(frame(seq))
        assert commit(c, arbiter)[1].submitted
    surface = session.snapshot().effective_transcript
    assert decoder.calls == [1, 2, 1, 2]
    assert session.snapshot().identity_snapshot.canonical_speakers == (
        "speaker-0001",
        "speaker-0002",
    )
    assert [(s.source_lane, s.canonical_speaker) for s in surface] == [
        ("system", "speaker-0001"),
        ("microphone", "speaker-0002"),
    ] * 2


def test_one_lane_failure_keeps_other_lane_and_names_failure():
    c, decoder, session, arbiter = make(Decoder(fail=1))
    c.accept_frame(frame())
    prepared, result = commit(c, arbiter)
    assert result.submitted and decoder.calls == [1, 1, 2]
    assert prepared.lane_failures == (("system", "LiveProviderTransientError"),)
    assert {s.source_lane for s in session.snapshot().effective_transcript} == {
        "microphone"
    }


def test_refused_preparation_does_not_claim_speaker_ownership():
    c, decoder, session, arbiter = make()
    c.accept_frame(frame())
    prepared = c.prepare_work_item(c.capture_work_item(arbiter.next_work()))
    assert c._lane_speakers == {}
    invalid = replace(
        prepared, preparation=replace(prepared.preparation, base_snapshot_version=99)
    )
    assert not c.submit_prepared_work(invalid).submitted
    assert c._lane_speakers == {}


def test_lane_tapes_are_bounded_retain_committed_audio_and_release():
    c, decoder, session, arbiter = make(capacity=80000)
    c.accept_frame(frame())
    commit(c, arbiter)
    assert all(
        t.read(end_sample=40000) == bytes([marker]) * 80000
        for marker, t in zip((1, 2), c.lane_tapes.values())
    )
    c.accept_frame(frame(1))
    assert (
        sum(
            t.accounting(through_sample=80000).retained_bytes
            for t in (c.tape, *c.lane_tapes.values())
        )
        == 3 * 80000
    )
    for tape in c.lane_tapes.values():
        with pytest.raises(CompleteMixedTapeUnavailable):
            tape.read(end_sample=80000)
    c.release_tape()
    assert all(
        t.accounting(through_sample=80000).retained_bytes == 0
        for t in (c.tape, *c.lane_tapes.values())
    )


@pytest.mark.parametrize("change", ["length", "lane", "silent"])
def test_invalid_aligned_frame_refused_before_admission(change):
    c, _, session, _ = make()
    f = frame()
    if change == "length":
        f = replace(f, lane_pcm=(("system", b"x"), ("microphone", b"x")))
    if change == "lane":
        f = replace(f, lane_pcm=(("system", f.pcm), ("other", f.pcm)))
    if change == "silent":
        f = replace(f, lane_silent=(("system", "false"), ("microphone", True)))
    with pytest.raises(ValueError):
        c.accept_frame(f)
    assert session.snapshot().accepted_samples == 0


def test_cross_lane_overlap_legal_same_lane_overlap_refused():
    c, _, session, arbiter = make()
    c.accept_frame(frame())
    commit(c, arbiter)
    segments = session.snapshot().effective_transcript
    proposal = TextRevisionProposal(
        epoch=session.epoch,
        base_text_revision_version=0,
        source="rolling",
        start_sample=0,
        end_sample=40000,
        segments=segments,
        revision_lanes=("system", "microphone"),
    )
    bad = replace(
        proposal, segments=(segments[0], replace(segments[1], source_lane="system"))
    )
    assert session.apply_text_revision(bad).refusal == "segments_out_of_order"
    assert session.apply_text_revision(proposal).applied


def test_failed_rolling_lane_keeps_full_cross_boundary_segment_while_other_advances():
    c, _, session, arbiter = make()
    c.accept_frame(frame())
    commit(c, arbiter)
    prior = next(
        s for s in session.snapshot().effective_transcript if s.source_lane == "system"
    )
    revised = EffectiveTranscriptSegment(
        0, 16000, "new mic", None, "rolling", "microphone"
    )
    proposal = TextRevisionProposal(
        session.epoch,
        0,
        "rolling",
        0,
        16000,
        (revised,),
        revision_lanes=("microphone",),
    )
    assert session.apply_text_revision(proposal).applied
    assert prior in session.snapshot().effective_transcript
    proposal = replace(
        proposal,
        base_text_revision_version=1,
        start_sample=16000,
        end_sample=40000,
        segments=(
            replace(revised, start_sample=16000, end_sample=40000, text="mic next"),
        ),
    )
    assert session.apply_text_revision(proposal).applied
    assert prior in session.snapshot().effective_transcript
    assert (
        sum(
            s.source_lane == "microphone"
            for s in session.snapshot().effective_transcript
        )
        == 2
    )


class Runner:
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []

    def transcribe(self, path, **kwargs):
        with wave.open(str(path)) as f:
            marker = f.readframes(1)[0]
        self.calls.append(marker)
        if marker == self.fail:
            raise RuntimeError("injected")
        return SimpleNamespace(text="[0][S01]refined words[2.5]")


@pytest.mark.parametrize("fail", [None, 1, 2])
def test_terminal_lane_decode_and_failure_preserves_committed_lane(
    fail, tmp_path
):
    c, _, session, arbiter = make()
    c.accept_frame(frame())
    commit(c, arbiter)
    before = session.snapshot().effective_transcript
    runner = Runner(fail)
    finalizer = TerminalTranscriptFinalizer(runner=runner, scratch_dir=tmp_path)
    plan = TerminalDecodePlan(
        epoch=session.epoch,
        end_sample=40000,
        rolling_through_sample=0,
        rolling_status=RollingStatus.STOPPED,
        windows_completed=0,
        windows_failed=0,
    )
    result = finalize_lanes(
        c,
        finalizer,
        plan=plan,
        tape=c.tape,
        base_text_revision_version=0,
        base_surface=before,
        canonical_speakers=session.snapshot().identity_snapshot.canonical_speakers,
    )
    assert sorted(runner.calls) == [1, 2]
    assert session.apply_text_revision(result.proposal).applied
    after = session.snapshot().effective_transcript
    assert {s.canonical_speaker for s in after} == {"speaker-0001", "speaker-0002"}
    if fail:
        lane = "system" if fail == 1 else "microphone"
        assert next(s for s in after if s.source_lane == lane) == next(
            s for s in before if s.source_lane == lane
        )
        assert result.accounting.reason == "lane_terminal_failed:" + lane


@pytest.mark.parametrize("same_voice", [False, True])
def test_terminal_overlap_uses_own_lane_without_acoustic_probes(tmp_path, monkeypatch, same_voice):
    import moss_transcribe_diarize.app.live_lane_decode as lanes

    c, _, session, arbiter = make()
    c.accept_frame(frame(mic=1 if same_voice else 2))
    commit(c, arbiter)
    snapshot = session.snapshot()
    calls = []
    original = lanes.revision_segments

    def recorded(*args):
        calls.append(args[1])
        return original(*args)

    monkeypatch.setattr(lanes, "revision_segments", recorded)
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=Runner(None), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(session.epoch, 40000, 0, RollingStatus.STOPPED, 0, 0),
        tape=c.tape, base_text_revision_version=0,
        base_surface=snapshot.effective_transcript,
        canonical_speakers=snapshot.identity_snapshot.canonical_speakers,
    )
    assert calls == []
    assert {(s.source_lane, s.canonical_speaker) for s in result.proposal.segments} == {
        ("system", "speaker-0001"), ("microphone", "speaker-0002")}
    assert session.apply_text_revision(result.proposal).applied


@pytest.mark.parametrize("abstain", [False, True])
def test_terminal_acoustic_fallback_only_reads_uncovered_lane_segment(tmp_path, monkeypatch, abstain):
    import moss_transcribe_diarize.app.live_lane_decode as lanes

    c, _, session, arbiter = make()
    for sequence in range(2):
        c.accept_frame(frame(sequence))
        commit(c, arbiter)
    snapshot = session.snapshot()
    prepare_revision = BoundedCausalIdentityPreparer.prepare_revision

    def possibly_abstain(self, **kwargs):
        preparation = prepare_revision(self, **kwargs)
        # Inject the preparer's legitimate abstention outcome; the lane adapter
        # must preserve words and ignore the otherwise successful relabeling.
        return replace(preparation, status="abstain") if abstain else preparation

    monkeypatch.setattr(BoundedCausalIdentityPreparer, "prepare_revision", possibly_abstain)
    # The system surface lacks a later interval; microphone evidence at the same
    # time must neither cover it nor provide its speaker identity.
    base = tuple(s for s in snapshot.effective_transcript
                 if s.source_lane == "microphone" or s.end_sample <= 40000)
    calls = []
    original = lanes.revision_segments

    def recorded(c, lane, span, pcm, text, authority):
        calls.append((lane, span.start_sample, span.end_sample, len(pcm), pcm[0]))
        return original(c, lane, span, pcm, text, authority)

    class GapRunner:
        def transcribe(self, *args, **kwargs):
            return SimpleNamespace(text="[0][S01]covered words[2.5][3][S01]new words[5]")

    monkeypatch.setattr(lanes, "revision_segments", recorded)
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=GapRunner(), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(session.epoch, 80000, 0, RollingStatus.STOPPED, 0, 0),
        tape=c.tape, base_text_revision_version=0, base_surface=base,
        canonical_speakers=snapshot.identity_snapshot.canonical_speakers,
    )
    assert calls == [("system", 48000, 80000, 64000, 1)]
    assert [(s.source_lane, s.start_sample, s.end_sample, s.text, s.canonical_speaker)
            for s in result.proposal.segments] == [
        ("system", 0, 40000, "covered words", "speaker-0001"),
        ("microphone", 0, 40000, "covered words", "speaker-0002"),
        ("system", 48000, 80000, "new words", None if abstain else "speaker-0001"),
        ("microphone", 48000, 80000, "new words", "speaker-0002"),
    ]
    assert session.apply_text_revision(result.proposal).applied
    assert session.snapshot().effective_transcript == result.proposal.segments


@pytest.mark.parametrize("abstain", [False, True])
def test_terminal_extra_local_voice_probes_covered_short_second_voice(tmp_path, monkeypatch, abstain):
    """Three terminal labels compete for two system identities; the third is Lex again."""
    import moss_transcribe_diarize.app.live_lane_decode as lanes

    system = "system"
    speakers = ("speaker-0001", "speaker-0002", "speaker-0003")
    base = tuple(EffectiveTranscriptSegment(
        round(start * RATE), round(end * RATE), "causal", speaker, "causal", lane,
    ) for start, end, speaker, lane in (
        (0, 2.5, speakers[0], system), (2.5, 5, speakers[2], system),
        (5, 5.72, speakers[2], system), (0, 5.72, speakers[1], "microphone"),
    ))
    tape = CompleteMixedTape(epoch=0, capacity_bytes=6 * RATE * 2)
    assert tape.append(start_sample=0, pcm=bytes([7]) * 6 * RATE * 2).written
    calls = []

    class SecondVoiceEvidence(Evidence):
        def revision_reader(self):
            return self

        def score(self, *, span, pcm, **kwargs):
            calls.append((span.start_sample, span.end_sample, len(pcm), pcm[0]))
            # A stronger same-time microphone candidate cannot compete in this lane.
            return tuple(LiveSpeakerEvidence("S01", s, score) for s, score in (
                (speakers[0], .1), (speakers[1], 1.), (speakers[2], .15 if abstain else .9),
            ))

    snapshot = SimpleNamespace(identity_snapshot=LiveIdentitySnapshot(canonical_speakers=speakers))
    c = SimpleNamespace(lane_tapes={system:tape}, _lane_speakers={system:{speakers[0], speakers[2]}},
        _lane_preparers={system:BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, .35, .1), evidence_provider=SecondVoiceEvidence())},
        session=SimpleNamespace(snapshot=lambda: snapshot))

    class SplitLabelRunner:
        def transcribe(self, *args, **kwargs):
            return SimpleNamespace(text="[0][S01]first voice[2.5][2.5][S02]second voice[5][5][S03]short return[5.72]")

    result = lanes.finalize_lanes(c, TerminalTranscriptFinalizer(runner=SplitLabelRunner(), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(0, 6 * RATE, 0, RollingStatus.STOPPED, 0, 0), tape=tape,
        base_text_revision_version=0, base_surface=base, canonical_speakers=speakers)
    assert calls == [(5 * RATE, round(5.72 * RATE), round(.72 * RATE) * 2, 7)]
    assert [(s.text, s.canonical_speaker) for s in result.proposal.segments] == [
        ("first voice", speakers[0]), ("second voice", speakers[2]),
        ("short return", None if abstain else speakers[2]),
    ]
    assert result.accounting.unattributed_segments == int(abstain)
    assert {s.source_lane for s in result.proposal.segments} == {system}


def test_long_single_voice_lane_keeps_all_covered_terminal_words(tmp_path, monkeypatch):
    import moss_transcribe_diarize.app.live_lane_decode as lanes

    seconds = 180
    c, _, session, arbiter = make(capacity=seconds * RATE * 2)
    for sequence in range(seconds * RATE // 40000):
        c.accept_frame(frame(sequence, mic=0))
        assert commit(c, arbiter)[1].submitted
    snapshot = session.snapshot()
    expected = tuple(EffectiveTranscriptSegment(
        start * RATE, (start + 5) * RATE, f"terminal words {start}",
        "speaker-0001", "terminal", "system",
    ) for start in range(0, seconds, 5))

    class LongRunner:
        def transcribe(self, *args, **kwargs):
            return SimpleNamespace(text="".join(
                f"[{s.start_sample / RATE}][S07]{s.text}[{s.end_sample / RATE}]"
                for s in expected))

    probes = []
    original = lanes.revision_segments

    def recorded(*args):
        probes.append(args[1])
        return original(*args)

    monkeypatch.setattr(lanes, "revision_segments", recorded)
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=LongRunner(), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(session.epoch, seconds * RATE, 0, RollingStatus.STOPPED, 0, 0),
        tape=c.tape, base_text_revision_version=0, base_surface=snapshot.effective_transcript,
        canonical_speakers=snapshot.identity_snapshot.canonical_speakers,
    )
    assert probes == []
    assert result.accounting.unattributed_segments == 0
    assert result.proposal.segments == expected
    assert session.apply_text_revision(result.proposal).applied
    assert session.snapshot().effective_transcript == expected


@pytest.mark.parametrize("seconds", [24, 60])
def test_terminal_parity_segment_equality_from_accepted_geometry(tmp_path, monkeypatch, seconds):
    """Replay accepted acoustic row geometry through the production finalizer.

    Synthetic text/causal subdivisions avoid retaining meeting words. Real-input
    equality remains independently measured by the 135-row shadow experiment.
    """
    import moss_transcribe_diarize.app.live_lane_decode as lanes

    fixture = json.loads((Path(__file__).parent / "fixtures/wp12_terminal_parity.json").read_text())
    expected = tuple(EffectiveTranscriptSegment(**row) for row in fixture[str(seconds)])
    speakers = tuple(sorted({s.canonical_speaker for s in expected}))
    base = tuple(replace(s, end_sample=(s.start_sample + s.end_sample) // 2,
                         text="causal evidence", authority="causal") for s in expected)
    tapes = {}
    own = {}
    for marker, lane in enumerate(("system", "microphone"), 1):
        tapes[lane] = CompleteMixedTape(epoch=0, capacity_bytes=seconds * RATE * 2)
        assert tapes[lane].append(start_sample=0, pcm=bytes([marker]) * seconds * RATE * 2).written
        own[lane] = {s.canonical_speaker for s in expected if s.source_lane == lane}
    snapshot = SimpleNamespace(identity_snapshot=LiveIdentitySnapshot(canonical_speakers=speakers))
    c = SimpleNamespace(lane_tapes=tapes, _lane_speakers=own,
                        session=SimpleNamespace(snapshot=lambda: snapshot))

    class ParityRunner:
        def transcribe(self, path, **kwargs):
            with wave.open(str(path)) as audio:
                lane = ("system", "microphone")[audio.readframes(1)[0] - 1]
            # Reversed, lane-local decoder labels deliberately differ from the
            # canonical IDs and collide across lanes.
            labels = {speaker: f"S{i:02d}" for i, speaker in enumerate(sorted(own[lane], reverse=True), 1)}
            return SimpleNamespace(text="".join(
                f"[{s.start_sample / RATE}][{labels[s.canonical_speaker]}]{s.text}[{s.end_sample / RATE}]"
                for s in expected if s.source_lane == lane))

    probes = []

    def unexpected_probe(*args):
        probes.append(args[1])
        return ()

    monkeypatch.setattr(lanes, "revision_segments", unexpected_probe)
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=ParityRunner(), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(0, seconds * RATE, 0, RollingStatus.STOPPED, 0, 0),
        tape=None, base_text_revision_version=0, base_surface=base,
        canonical_speakers=speakers,
    )
    assert probes == []
    assert result.proposal.segments == expected


def test_legacy_frame_uses_only_mixed_pcm():
    c, decoder, _, arbiter = make()
    c.accept_frame(AudioFrame(0, bytes([7]) * 80000, 40000))
    commit(c, arbiter)
    assert decoder.calls == [7] and c.lane_tapes == {}


@pytest.mark.parametrize("mic", [0, 2])
def test_draft_uses_separate_pcm_skips_zero_and_isolates_failure(mic):
    from tests.phase2.test_draft_lane import runtime, finished

    decoder = Decoder(fail=1)
    r, _, sid = runtime(decoder)
    r.accept_frame(sid, frame(count=1000, mic=mic))
    finished(r)
    assert decoder.calls == ([1] if mic == 0 else [1, 2])
    snapshot = r.snapshot(sid)
    assert snapshot.draft_stats["errors"] == 1
    assert snapshot.session.identity_snapshot.canonical_speakers == ()
    assert (snapshot.draft is not None) == (mic == 2)


def test_zero_rolling_window_advances_without_decoder_and_next_lane_remains_eligible():
    from moss_transcribe_diarize.app.live_transcript_convergence import (
        RollingTranscriptConverger,
    )

    c, decoder, session, arbiter = make(rolling=True)
    # Isolate producer behavior from speech endpointing: real tape + converger.
    c.accept_frame(frame(count=320000, system=0, mic=0))
    converger = RollingTranscriptConverger(epoch=session.epoch)
    converger.accept_pcm(0, bytes(640000))
    request = converger.observe_base(
        SimpleNamespace(
            epoch=session.epoch,
            committed_samples=320000,
            canonical_through_sample=0,
            text_revision_version=0,
        )
    )[0]
    decoded = decode_refinement(c, request)
    assert decoder.calls == [] and decoded.revision_lanes == ("system", "microphone")
    proposal = converger.complete(
        request.id,
        decoded.outcome,
        segments=decoded.lane_segments,
        revision_lanes=decoded.revision_lanes,
    )
    assert proposal is not None and proposal.segments == ()
    assert not c._stopped_refinement_lanes


def test_terminal_zero_lane_never_calls_decoder(tmp_path):
    c, _, session, arbiter = make()
    c.accept_frame(frame(mic=0))
    commit(c, arbiter)
    runner = Runner()
    plan = TerminalDecodePlan(
        epoch=session.epoch,
        end_sample=40000,
        rolling_through_sample=0,
        rolling_status=RollingStatus.STOPPED,
        windows_completed=0,
        windows_failed=0,
    )
    result = finalize_lanes(
        c,
        TerminalTranscriptFinalizer(runner=runner, scratch_dir=tmp_path),
        plan=plan,
        tape=c.tape,
        base_text_revision_version=0,
        base_surface=session.snapshot().effective_transcript,
        canonical_speakers=session.snapshot().identity_snapshot.canonical_speakers,
    )
    assert runner.calls == [1]
    assert {s.source_lane for s in result.proposal.segments} == {"system"}

@pytest.mark.parametrize('enrolled_lane', ['system', 'microphone'])
def test_lane_commit_preserves_causal_voiceprint_matches_across_lane_namespaces(enrolled_lane):
    from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
    from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
    from moss_transcribe_diarize.app.phase2_voiceprint_match import VoiceprintProfile, match_voiceprint

    class Encoder:
        spec = SimpleNamespace(provider='wespeaker', revision='test', state_sha256='test')
        calls = 0
        def embed(self, *args):
            self.calls += 1
            return (1., 0.)

    encoder = Encoder()
    def factory():
        return BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, .35, .1),
            evidence_provider=WeSpeakerLiveEvidenceProvider(encoder=encoder, album=FingerprintAlbum()),
            lane_factory=factory,
        )
    c, _, session, arbiter = make()
    c.identity_preparer = factory()
    c.accept_frame(frame(system=1 if enrolled_lane == 'system' else 0,
                         mic=2 if enrolled_lane == 'microphone' else 0))
    assert commit(c, arbiter)[1].submitted
    album = c.journal_observations()
    assert len(album) == 1
    profile = VoiceprintProfile('enrolled', 'Alex', album[0].embedder_id, album[0].centroid)

    c, _, session, arbiter = make()
    c.identity_preparer = factory()
    for sequence in range(2):
        c.accept_frame(frame(sequence))
        assert commit(c, arbiter)[1].submitted
        observed = c.match_observations()
        assert {o.speaker_label for o in observed} == {'speaker-0001', 'speaker-0002'}
        assert all(match_voiceprint(o, (profile,)) == profile for o in observed)
        assert c.match_observations() == observed
        assert len(c.journal_observations()) == 2
    assert encoder.calls == 5  # Recognition must not re-embed.


def test_thirty_minute_lane_buffers_plateau_and_release_without_losing_words():
    import asyncio

    c, decoder, session, arbiter = make(capacity=9_600_000)
    checkpoints = {}
    for seq in range(720):  # 720 production-sized 2.5-second spans = 30 minutes.
        c.accept_frame(frame(seq))
        assert commit(c, arbiter)[1].submitted
        if seq + 1 in (120, 360, 720):
            checkpoints[seq + 1] = (
                len(session._frames),
                tuple(len(p._slices) for p in (c._pcm, c._analysis_pcm, *c._lane_pcm.values())),
                tuple(t.retained_bytes for t in (c.tape, *c.lane_tapes.values())),
            )
    # Audio working state stops growing at five minutes; transcript history may grow.
    assert checkpoints[120] == checkpoints[360] == checkpoints[720]
    assert checkpoints[720] == (0, (0, 0, 0, 0), (9_600_000,) * 3)
    before = session.snapshot().effective_transcript
    assert len(before) == 1440
    assert len(decoder.calls) == 1440
    asyncio.run(session.stop(1))
    c.release_tape()
    assert all(t.retained_bytes == 0 for t in (c.tape, *c.lane_tapes.values()))
    assert session.snapshot().effective_transcript == before

def test_terminal_jobs_overlap_and_publish_only_after_both_lanes(tmp_path):
    """Two Stop listeners must overlap; each keeps its own captured decoder result."""
    from threading import Barrier, Lock

    c, _, session, arbiter = make()
    c.accept_frame(frame())
    commit(c, arbiter)
    before = session.snapshot().effective_transcript
    barrier = Barrier(2, timeout=2)
    lock = Lock()

    class ConcurrentRunner(Runner):
        peak = 0
        active = 0

        def transcribe(self, path, **kwargs):
            with lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            try:
                barrier.wait()
                assert session.snapshot().effective_transcript == before
                with wave.open(str(path)) as f:
                    marker = f.readframes(1)[0]
                self.calls.append(marker)
                return SimpleNamespace(text=f"[0][S01]terminal lane {marker}[2.5]")
            finally:
                with lock:
                    self.active -= 1

    runner = ConcurrentRunner()
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=runner, scratch_dir=tmp_path),
        plan=TerminalDecodePlan(session.epoch, 40000, 0, RollingStatus.STOPPED, 0, 0),
        tape=c.tape, base_text_revision_version=0, base_surface=before,
        canonical_speakers=session.snapshot().identity_snapshot.canonical_speakers,
    )
    assert runner.peak == 2
    assert sorted(runner.calls) == [1, 2]
    assert session.snapshot().effective_transcript == before
    assert session.apply_text_revision(result.proposal).applied
    assert [(s.source_lane, s.text, s.canonical_speaker)
            for s in session.snapshot().effective_transcript] == [
        ('system', 'terminal lane 1', 'speaker-0001'),
        ('microphone', 'terminal lane 2', 'speaker-0002'),
    ]


def test_lane_album_survives_silent_peer_spans_and_matches_returning_voice():
    """Real evidence/album lifecycle: a microphone voice returns after a silent gap."""
    from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
    from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider

    class Encoder:
        spec = SimpleNamespace(provider='wespeaker', revision='test', state_sha256='test')  # WP17 provider contract
        def embed(self, path, intervals):
            return [1.0, 0.0]

    def preparer():
        return BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, 0.35, 0.1),
            evidence_provider=WeSpeakerLiveEvidenceProvider(
                encoder=Encoder(), album=FingerprintAlbum(admission_seconds=2.0),
                birth_min_seconds=1.0, min_segment_samples=8000,
            ), lane_factory=preparer,
        )

    c, _, session, arbiter = make()
    c.identity_preparer = preparer()
    for seq, mic in enumerate((2, 0, 0, 2)):
        c.accept_frame(frame(seq=seq, mic=mic))
        assert commit(c, arbiter)[1].submitted
        provider = c._lane_preparers['microphone'].evidence_provider
        assert provider._album.speakers() == ('speaker-0002',)
        assert provider._album.reference('speaker-0002') is not None
    assert session.snapshot().identity_snapshot.canonical_speakers == (
        'speaker-0001', 'speaker-0002',
    )
    assert {s.canonical_speaker for s in session.snapshot().effective_transcript
            if s.source_lane == 'microphone'} == {'speaker-0002'}


@pytest.mark.parametrize("exhausted", [("system", "microphone"), ("system",), ("microphone",), ()])
def test_terminal_exhausted_lane_keeps_words_and_reports_tape_gaps(tmp_path, exhausted):
    c, _, session, arbiter = make(capacity=80000)
    c.accept_frame(frame())
    commit(c, arbiter)
    for lane, tape in c.lane_tapes.items():
        if lane not in exhausted:
            tape.capacity_bytes = 160000
    c.accept_frame(frame(seq=1))
    commit(c, arbiter)
    before = session.snapshot().effective_transcript
    runner = Runner()
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=runner, scratch_dir=tmp_path),
        plan=TerminalDecodePlan(session.epoch, 80000, 0, RollingStatus.STOPPED, 0, 0),
        tape=c.tape, base_text_revision_version=0, base_surface=before,
        canonical_speakers=session.snapshot().identity_snapshot.canonical_speakers,
    )
    assert result.accounting.tape_gaps == len(exhausted)
    assert len(runner.calls) == 2 - len(exhausted)
    if len(exhausted) == 2:
        assert result.proposal is None
        assert result.accounting.outcome.finalization_status == "unavailable"
    else:
        assert session.apply_text_revision(result.proposal).applied
    after = session.snapshot().effective_transcript
    assert all(s in after for s in before if s.source_lane in exhausted)


def test_terminal_all_zero_lanes_has_named_refusal(tmp_path):
    c, _, session, _ = make()
    c.accept_frame(frame(system=0, mic=0))
    result = finalize_lanes(
        c, TerminalTranscriptFinalizer(runner=Runner(), scratch_dir=tmp_path),
        plan=TerminalDecodePlan(session.epoch, 40000, 0, RollingStatus.STOPPED, 0, 0),
        tape=c.tape, base_text_revision_version=0, base_surface=(), canonical_speakers=(),
    )
    assert result.proposal is None
    assert result.accounting.reason == "all_lanes_zero"
    assert result.accounting.tape_gaps == 0
