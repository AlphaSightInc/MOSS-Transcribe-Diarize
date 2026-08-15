from __future__ import annotations

from moss_transcribe_diarize.app.live_arbiter import (
    InferenceArbiter,
    InferenceArbiterBackpressure,
)


def test_one_frame_batch_is_all_or_nothing_at_the_canonical_capacity_boundary() -> None:
    arbiter = InferenceArbiter(max_live_canonical_items=1)

    admitted = arbiter.submit_live_canonical_batch(
        (("span-1", object()), ("span-2", object()))
    )

    assert [item.item_id for item in admitted] == [0, 1]
    assert arbiter.snapshot().live_canonical == 2
    try:
        arbiter.submit_live_canonical_batch((("span-3", object()), ("span-4", object())))
    except InferenceArbiterBackpressure:
        pass
    else:
        raise AssertionError("a saturated queue accepted another canonical frame batch")
    assert arbiter.snapshot().live_canonical == 2
