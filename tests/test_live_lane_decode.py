from dataclasses import replace
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
    TextRevisionProposal,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTapeUnavailable
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
def test_terminal_serial_lane_decode_and_failure_preserves_committed_lane(
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
    assert runner.calls == [1, 2]
    assert session.apply_text_revision(result.proposal).applied
    after = session.snapshot().effective_transcript
    assert {s.canonical_speaker for s in after} == {"speaker-0001", "speaker-0002"}
    if fail:
        lane = "system" if fail == 1 else "microphone"
        assert next(s for s in after if s.source_lane == lane) == next(
            s for s in before if s.source_lane == lane
        )
        assert result.accounting.reason == "lane_terminal_failed:" + lane


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
