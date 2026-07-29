from __future__ import annotations

from dataclasses import replace

import pytest

from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalResult,
    CanonicalSubmission,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
)
from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
    LiveSpeakerEvidence,
)


def _refused(refusal: str) -> CanonicalSubmission:
    return CanonicalSubmission(submitted=False, refusal=refusal)


def frame(sequence: int, samples: int) -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=b"\0" * samples * 2, sample_count=samples)


def transcript(samples: int, text: str = "ok") -> str:
    return f"[0][S01]{text}[{samples / LIVE_SAMPLE_RATE:g}]"


def prepared_result(span, base: LiveIdentitySnapshot, *, status: str = "prepared", reason: str | None = None):
    text = transcript(span.sample_count)
    proposed = LiveIdentitySnapshot(
        version=base.version + 1,
        canonical_speakers=("speaker-a",),
        diagnostics=(("span_id", str(span.id)),),
    )
    preparation = LiveIdentityPreparation(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        base_snapshot_version=base.version,
        proposed_snapshot=proposed,
        relabeled_transcript=text,
        status=status,
        reason=reason,
    )
    return CanonicalResult(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=text,
        identity_preparation=preparation,
    )


class StaticEvidence:
    def __init__(self, *evidence: LiveSpeakerEvidence):
        self.evidence = evidence

    def score(self, **kwargs):
        del kwargs
        return self.evidence


class MeasuredEvidence(StaticEvidence):
    """A provider that also reports how much speech it embedded, as the real one does.

    `StaticEvidence` deliberately does not: a stack with no album has no admission gate and
    must birth exactly as it always did. This subclass is the other half of that seam, so the
    two behaviours are both covered by a double rather than only by the deployed bundle.
    """

    def __init__(self, *evidence: LiveSpeakerEvidence, embedded: dict[str, float], floor: float = 1.0):
        super().__init__(*evidence)
        self.embedded = embedded
        self.floor = floor

    def birth_deferrals(self, *, span_id: int, candidates):
        del span_id
        return tuple(
            (local, self.embedded.get(local, 0.0))
            for local in candidates
            if self.embedded.get(local, 0.0) < self.floor
        )


def identity_config() -> LiveIdentityConfig:
    return LiveIdentityConfig(max_speakers=3, min_match_score=0.8, min_match_margin=0.1)


def test_prepared_canonical_publishes_transcript_and_identity_snapshot_atomically():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    result = prepared_result(span, session.snapshot().identity_snapshot)

    assert session.submit_prepared_canonical(result) == CanonicalSubmission(submitted=True)

    snapshot = session.snapshot()
    assert snapshot.accounted_samples == 4000
    assert snapshot.identity_snapshot == result.identity_preparation.proposed_snapshot
    assert snapshot.committed[0].transcript == result.transcript
    assert snapshot.committed[0].identity_snapshot_version == snapshot.identity_snapshot.version
    assert snapshot.pending_span_ids == ()


def test_prepared_canonical_rejects_invalid_preparations_without_mutation():
    """Each refusal leaves the session untouched *and* names the condition that refused.

    These five conditions used to be one bare `False`, so the runtime reported them with a
    single code and a reader outside the process could not tell a stale preparation from a
    span submitted out of order -- the gap that cost H4d a host-side probe.
    """
    session = LiveSession(max_retained_samples=8000)
    session.accept_frame(frame(0, 8000))
    first = session.freeze_until(4000, reason="hard_cap")
    second = session.freeze_until(8000, reason="hard_cap")
    base = session.snapshot().identity_snapshot

    out_of_order = prepared_result(second, base)
    before = session.snapshot()
    assert session.submit_prepared_canonical(out_of_order) == _refused("span_out_of_order")
    assert session.snapshot() == before

    mismatched = prepared_result(first, base)
    mismatched = replace(mismatched, end_sample=first.end_sample - 1)
    assert session.submit_prepared_canonical(mismatched) == _refused("span_sample_mismatch")
    assert session.snapshot() == before

    ambiguous = prepared_result(first, base, status="abstain", reason="ambiguous identity")
    assert session.submit_prepared_canonical(ambiguous) == _refused("identity_preparation_not_prepared")
    assert session.snapshot() == before

    failed = prepared_result(first, base, status="failed", reason="identity provider failed")
    assert session.submit_prepared_canonical(failed) == _refused("identity_preparation_not_prepared")
    assert session.snapshot() == before

    accepted_first = prepared_result(first, base)
    assert session.submit_prepared_canonical(accepted_first).submitted is True
    after_first = session.snapshot()

    stale_second = prepared_result(second, base)
    assert session.submit_prepared_canonical(stale_second) == _refused("identity_preparation_stale_base_version")
    assert session.snapshot() == after_first


def test_a_refused_canonical_submission_cannot_be_built_without_naming_itself():
    """The invariant that keeps the silent refusal unwritable.

    A future `return CanonicalSubmission(submitted=False)` -- the shape every one of the
    refusals above used to have -- raises here rather than reaching an operator as an
    unexplained stop.
    """
    with pytest.raises(ValueError, match="must name its refusal"):
        CanonicalSubmission(submitted=False)
    with pytest.raises(ValueError, match="has no refusal"):
        CanonicalSubmission(submitted=True, refusal="span_out_of_order")


def test_bounded_identity_births_session_speakers_without_committing_raw_labels():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    preparer = BoundedCausalIdentityPreparer(config=identity_config())

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S03]first[0.1][0.2][S01]second[0.25]",
        base_snapshot=session.snapshot().identity_snapshot,
    )

    assert preparation.status == "prepared"
    assert preparation.proposed_snapshot.canonical_speakers == ("speaker-0001", "speaker-0002")
    assert "S03" not in preparation.proposed_snapshot.canonical_speakers
    assert preparation.relabeled_transcript == "[0][S01]first[0.1][0.2][S02]second[0.25]"


def test_a_birth_cannot_be_minted_from_a_span_the_encoder_was_never_asked_about():
    """Candidate 55, at the seam that mints a speaker.

    The defect this refuses: 14 of one certification run's 16 canonical speakers were born
    from spans where no segment cleared the evidence floor, so no vector was ever computed.
    The album has nothing to enrol, the speaker is a capacity slot no later span can match
    against, and sixteen of them for two voices exhausts identity inside the first minute.

    A local speaker the encoder was never asked about reports **0.0 s**, which is why the
    assertion is on the seconds and not merely on absence. The words are still published --
    identity answers *who*, never *whether* -- and the snapshot still advances, because the
    span was prepared: it simply established nobody.
    """

    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=MeasuredEvidence(embedded={}),
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S01]Hi.[0.1]",
        base_snapshot=session.snapshot().identity_snapshot,
    )

    assert preparation.status == "prepared"
    assert preparation.proposed_snapshot.canonical_speakers == ()
    assert preparation.proposed_snapshot.version == 1
    assert preparation.relabeled_transcript == "[0][S00]Hi.[0.1]"
    assert ("deferred_births", "S01=0.000") in preparation.proposed_snapshot.diagnostics


def test_a_deferred_birth_costs_its_own_speaker_a_label_and_nobody_elses():
    """Deferral is per speaker; an abstain for the whole span would be a worse answer.

    One voice carries a second of speech and one carries a fragment. Refusing the whole span
    would drop a label the session had every reason to write, so the fragment publishes `S00`
    beside the other speaker's `S01` -- the same mixed state a retrospective sweep is already
    written to accept (`revise_labels` exempts `S00` from its collision rule).
    """

    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=MeasuredEvidence(embedded={"S01": 1.4, "S02": 0.5}),
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S01]a real turn[0.1][0.2][S02]yeah[0.25]",
        base_snapshot=session.snapshot().identity_snapshot,
    )

    assert preparation.status == "prepared"
    assert preparation.proposed_snapshot.canonical_speakers == ("speaker-0001",)
    assert preparation.relabeled_transcript == "[0][S01]a real turn[0.1][0.2][S00]yeah[0.25]"
    assert ("deferred_births", "S02=0.500") in preparation.proposed_snapshot.diagnostics
    assert ("assignments", "S01->speaker-0001") in preparation.proposed_snapshot.diagnostics


def test_the_birth_floor_never_stops_a_short_span_from_being_labelled():
    """ADR-0002's asymmetry, asserted from the birth side: matching is not enrollment.

    The same fragment that may not *become* a speaker may still be *recognised* as one. If the
    floor were applied to matching too, every backchannel in a meeting would go unlabelled --
    which is the opposite of what candidate 55 is for.
    """

    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    base = LiveIdentitySnapshot(version=1, canonical_speakers=("speaker-0001",))
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=MeasuredEvidence(
            LiveSpeakerEvidence("S01", "speaker-0001", 0.95),
            embedded={"S01": 0.12},
        ),
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S01]mm hm[0.1]",
        base_snapshot=base,
    )

    assert preparation.status == "prepared"
    assert preparation.relabeled_transcript == "[0][S01]mm hm[0.1]"
    assert ("deferred_births", "") in preparation.proposed_snapshot.diagnostics


def test_a_provider_that_cannot_report_embedded_speech_births_exactly_as_before():
    """The capability is asked for by name, so a stack without it is unchanged.

    `NoLiveSpeakerEvidence`, the pre-ADR-0002 overwrite policy and every hand-built double
    have no album and therefore no admission gate. Applying a floor they do not state would
    silence every label in those configurations rather than fix a fragmentation they cannot
    have.
    """

    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=StaticEvidence(),
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S01]Hi.[0.1]",
        base_snapshot=session.snapshot().identity_snapshot,
    )

    assert preparation.status == "prepared"
    assert preparation.proposed_snapshot.canonical_speakers == ("speaker-0001",)
    assert preparation.relabeled_transcript == "[0][S01]Hi.[0.1]"


def test_a_provider_that_raises_asking_about_births_fails_the_span_and_not_the_meeting():
    """The live path's terminal-failure policy, applied to the seam this change adds.

    A `failed` preparation publishes the span's words unattributed and the meeting continues;
    only a session that genuinely cannot continue may be terminal. The reason names the
    exception class, because a typed refusal that discards the one word naming it is what
    forced a host-side probe to be built in the first place.
    """

    class Exploding(StaticEvidence):
        def birth_deferrals(self, **kwargs):
            del kwargs
            raise LookupError("no pending vectors")

    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=Exploding(),
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S01]Hi.[0.1]",
        base_snapshot=session.snapshot().identity_snapshot,
    )

    assert preparation.status == "failed"
    assert preparation.reason == "birth_evidence_failed:LookupError"


def test_bounded_identity_uses_exact_one_to_one_existing_assignment():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    base = LiveIdentitySnapshot(version=2, canonical_speakers=("speaker-0001", "speaker-0002"))
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=StaticEvidence(
            LiveSpeakerEvidence("S02", "speaker-0001", 0.97),
            LiveSpeakerEvidence("S02", "speaker-0002", 0.40),
            LiveSpeakerEvidence("S01", "speaker-0001", 0.35),
            LiveSpeakerEvidence("S01", "speaker-0002", 0.96),
        ),
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S02]returning first[0.1][0.2][S01]returning second[0.25]",
        base_snapshot=base,
    )

    assert preparation.status == "prepared"
    assert preparation.proposed_snapshot.version == 3
    assert preparation.proposed_snapshot.canonical_speakers == base.canonical_speakers
    assert preparation.relabeled_transcript == "[0][S01]returning first[0.1][0.2][S02]returning second[0.25]"


def test_bounded_identity_abstains_on_same_span_cannot_link_conflict_without_mutation():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    base = LiveIdentitySnapshot(version=1, canonical_speakers=("speaker-0001",))
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config(),
        evidence_provider=StaticEvidence(
            LiveSpeakerEvidence("S01", "speaker-0001", 0.95),
            LiveSpeakerEvidence("S02", "speaker-0001", 0.94),
        ),
    )
    before = session.snapshot()

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S01]one[0.1][0.2][S02]two[0.25]",
        base_snapshot=base,
    )
    result = CanonicalResult(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=preparation.relabeled_transcript,
        identity_preparation=preparation,
    )

    assert preparation.status == "abstain"
    assert preparation.reason == "same_span_cannot_link_conflict"
    assert session.submit_prepared_canonical(result) == _refused("identity_preparation_not_prepared")
    assert session.snapshot() == before


def test_bounded_identity_abstains_when_new_speaker_would_exceed_capacity():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    base = LiveIdentitySnapshot(version=1, canonical_speakers=("speaker-0001",))
    preparer = BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(max_speakers=1, min_match_score=0.8, min_match_margin=0.1)
    )

    preparation = preparer.prepare(
        span=span,
        pcm=frame(0, 4000).pcm,
        transcript="[0][S02]new voice[0.1]",
        base_snapshot=base,
    )

    assert preparation.status == "abstain"
    assert preparation.reason == "speaker_capacity_exceeded"


def test_bounded_identity_fails_on_pcm_span_mismatch():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    preparer = BoundedCausalIdentityPreparer(config=identity_config())

    preparation = preparer.prepare(
        span=span,
        pcm=b"\0",
        transcript="[0][S01]bad pcm[0.1]",
        base_snapshot=session.snapshot().identity_snapshot,
    )

    assert preparation.status == "failed"
    assert preparation.reason == "pcm_span_mismatch"
