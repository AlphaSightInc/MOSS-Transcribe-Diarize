from __future__ import annotations

from dataclasses import replace

from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalResult,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
)


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


def test_prepared_canonical_publishes_transcript_and_identity_snapshot_atomically():
    session = LiveSession(max_retained_samples=4000, hard_cap_samples=4000)
    ack = session.accept_frame(frame(0, 4000))
    span = session._frozen_spans[ack.frozen_span_ids[0]]
    result = prepared_result(span, session.snapshot().identity_snapshot)

    assert session.submit_prepared_canonical(result) is True

    snapshot = session.snapshot()
    assert snapshot.accounted_samples == 4000
    assert snapshot.identity_snapshot == result.identity_preparation.proposed_snapshot
    assert snapshot.committed[0].transcript == result.transcript
    assert snapshot.committed[0].identity_snapshot_version == snapshot.identity_snapshot.version
    assert snapshot.pending_span_ids == ()


def test_prepared_canonical_rejects_invalid_preparations_without_mutation():
    session = LiveSession(max_retained_samples=8000, hard_cap_samples=4000)
    ack = session.accept_frame(frame(0, 8000))
    first = session._frozen_spans[ack.frozen_span_ids[0]]
    second = session._frozen_spans[ack.frozen_span_ids[1]]
    base = session.snapshot().identity_snapshot

    out_of_order = prepared_result(second, base)
    before = session.snapshot()
    assert session.submit_prepared_canonical(out_of_order) is False
    assert session.snapshot() == before

    mismatched = prepared_result(first, base)
    mismatched = replace(mismatched, end_sample=first.end_sample - 1)
    assert session.submit_prepared_canonical(mismatched) is False
    assert session.snapshot() == before

    ambiguous = prepared_result(first, base, status="abstain", reason="ambiguous identity")
    assert session.submit_prepared_canonical(ambiguous) is False
    assert session.snapshot() == before

    failed = prepared_result(first, base, status="failed", reason="identity provider failed")
    assert session.submit_prepared_canonical(failed) is False
    assert session.snapshot() == before

    accepted_first = prepared_result(first, base)
    assert session.submit_prepared_canonical(accepted_first) is True
    after_first = session.snapshot()

    stale_second = prepared_result(second, base)
    assert session.submit_prepared_canonical(stale_second) is False
    assert session.snapshot() == after_first
