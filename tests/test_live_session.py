from __future__ import annotations

import asyncio

import pytest

from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalResult,
    LIVE_SAMPLE_RATE,
    LiveSession,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
)


def frame(sequence: int, samples: int) -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=b"\0" * samples * 2, sample_count=samples)


def transcript(seconds: float, text: str = "ok") -> str:
    return f"[0][S01]{text}[{seconds:g}]"


def result(span, text: str | None = None, *, identity_confirmed: bool = True) -> CanonicalResult:
    return CanonicalResult(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=text if text is not None else transcript(span.sample_count / LIVE_SAMPLE_RATE),
        identity_confirmed=identity_confirmed,
    )


def test_accepts_ordered_16khz_pcm_and_backpressures_before_eviction():
    session = LiveSession(max_retained_samples=4)

    first = session.accept_frame(frame(0, 2))
    second = session.accept_frame(frame(1, 2))

    assert (first.start_sample, first.end_sample) == (0, 2)
    assert (second.start_sample, second.end_sample) == (2, 4)
    assert session.snapshot().accepted_samples == 4
    with pytest.raises(ValueError, match="expected frame sequence 2"):
        session.accept_frame(frame(3, 1))
    with pytest.raises(LiveSessionBackpressure):
        session.accept_frame(frame(2, 1))


def test_hard_cap_freezes_independent_spans_and_publishes_only_in_order():
    session = LiveSession(max_retained_samples=8000, hard_cap_samples=4000)
    session.accept_frame(frame(0, 2000))
    ack = session.accept_frame(frame(1, 6000))

    assert ack.frozen_span_ids == (0, 1)
    first, second = [session._frozen_spans[span_id] for span_id in ack.frozen_span_ids]

    assert session.submit_canonical(result(second, transcript(0.25, "second"))) is True
    blocked = session.snapshot()
    assert blocked.accounted_samples == 0
    assert blocked.pending_span_ids == (0, 1)

    assert session.submit_canonical(result(first, transcript(0.25, "first"))) is True
    published = session.snapshot()
    assert published.accounted_samples == 8000
    assert [commit.span_id for commit in published.committed] == [0, 1]
    assert [commit.transcript for commit in published.committed] == [
        "[0][S01]first[0.25]",
        "[0][S01]second[0.25]",
    ]
    assert published.committed[0].prefix_hash != published.committed[1].prefix_hash
    with pytest.raises(ValueError):
        session.freeze_until(8000, reason="duplicate")


def test_provisional_suffix_is_replace_only_and_stale_generations_are_ignored():
    session = LiveSession(max_retained_samples=4000, hard_cap_samples=4000)
    session.accept_frame(frame(0, 4000))
    epoch, old_generation, start_sample = session.begin_provisional()
    assert session.publish_provisional(
        epoch=epoch,
        generation=old_generation,
        start_sample=start_sample,
        end_sample=4000,
        transcript="old",
    )

    epoch, new_generation, start_sample = session.begin_provisional()
    assert not session.publish_provisional(
        epoch=epoch,
        generation=old_generation,
        start_sample=start_sample,
        end_sample=4000,
        transcript="stale",
    )
    assert session.publish_provisional(
        epoch=epoch,
        generation=new_generation,
        start_sample=start_sample,
        end_sample=4000,
        transcript="new",
    )
    assert session.snapshot().provisional.transcript == "new"

    span = session._frozen_spans[0]
    session.submit_canonical(result(span))
    assert session.snapshot().provisional is None


def test_canonical_validation_fails_closed_and_preserves_unresolved_samples():
    session = LiveSession(max_retained_samples=4000, hard_cap_samples=4000)
    ack = session.accept_frame(frame(0, 4000))
    span = session._frozen_spans[ack.frozen_span_ids[0]]

    with pytest.raises(LiveSessionFailed, match="stable session identity"):
        session.submit_canonical(result(span, identity_confirmed=False))

    snapshot = session.snapshot()
    assert snapshot.status == "failed"
    assert snapshot.accepted_samples == 4000
    assert snapshot.accounted_samples == 0
    assert snapshot.pending_span_ids == (span.id,)
    with pytest.raises(LiveSessionClosed):
        session.accept_frame(frame(1, 1))


def test_stale_epoch_results_are_ignored_after_abort():
    session = LiveSession(max_retained_samples=4000, hard_cap_samples=4000, session_epoch=7)
    ack = session.accept_frame(frame(0, 4000))
    span = session._frozen_spans[ack.frozen_span_ids[0]]

    asyncio.run(session.abort("caller cancelled"))

    stale = CanonicalResult(
        span_id=span.id,
        epoch=span.epoch + 1,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=transcript(0.25),
    )
    assert session.submit_canonical(stale) is False
    assert session.snapshot().status == "aborted"
    with pytest.raises(LiveSessionClosed):
        session.accept_frame(frame(1, 1))


def test_stop_flush_requires_exact_accepted_accounted_equality():
    async def scenario():
        session = LiveSession(max_retained_samples=8)
        session.accept_frame(frame(0, 6))
        with pytest.raises(TimeoutError):
            await session.stop(0.001)

        span = session._frozen_spans[0]
        session.submit_canonical(result(span, transcript(6 / LIVE_SAMPLE_RATE)))
        stopped = await session.stop(0.1)
        assert stopped.status == "closed"
        assert stopped.accepted_samples == stopped.accounted_samples == 6
        assert stopped.retained_samples == 0

    asyncio.run(scenario())
