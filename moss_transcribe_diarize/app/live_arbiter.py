from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any


class InferenceArbiterBackpressure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ArbiterAdmission:
    accepted: bool
    item_id: int | None
    reason: str | None = None
    replaced_item_id: int | None = None


@dataclass(frozen=True, slots=True)
class ArbiterWorkItem:
    id: int
    kind: str
    key: str
    payload: Any
    weight: int = 1


@dataclass(frozen=True, slots=True)
class ArbiterSnapshot:
    """Queue depths, per kind. Depths only -- never lifetime counters.

    Every refinement the arbiter drops is already reported to the caller that submitted it:
    a coalesced one comes back as `replaced_item_id`, a suppressed one as `accepted=False`
    with a reason. Counting them a second time here would be a second bookkeeping of the
    same fact, and the two would eventually disagree. `live_refinement_running` is the one
    thing a caller cannot see from its own admission results, so it is here.
    """

    batch: int
    live_canonical: int
    live_provisional: int
    live_refinement: int = 0
    live_refinement_running: int = 0


class InferenceArbiter:
    """Priority gate for batch, canonical live, rolling refinement, and provisional inference.

    The live ordering is plan §6 M5's, and it is the whole reason the rolling witness may
    share one GPU with the base path::

        unresolved short canonical work > newest rolling refinement > provisional-only work

    A rolling window is a 10-second decode; a canonical span is at most 2.5 seconds and a
    listener is waiting on it. Putting refinement above canonical would let the second
    listener delay the first, which plan §10.6 forbids outright ("rolling must never build an
    unbounded queue or delay unresolved short canonical work"). Putting it below provisional
    would starve it, because provisional work is regenerated on every frame.
    """

    BATCH = "batch"
    LIVE_CANONICAL = "live_canonical"
    LIVE_REFINEMENT = "live_refinement"
    LIVE_PROVISIONAL = "live_provisional"

    def __init__(
        self,
        *,
        max_batch_items: int | None = None,
        max_live_canonical_items: int | None = None,
        max_live_provisional_items: int = 1,
    ):
        _validate_capacity("max_batch_items", max_batch_items)
        _validate_capacity("max_live_canonical_items", max_live_canonical_items)
        _validate_capacity("max_live_provisional_items", max_live_provisional_items)
        self.max_batch_items = max_batch_items
        self.max_live_canonical_items = max_live_canonical_items
        self.max_live_provisional_items = max_live_provisional_items
        self._next_id = 0
        self._batch: deque[ArbiterWorkItem] = deque()
        self._live_canonical: deque[ArbiterWorkItem] = deque()
        self._live_canonical_weight = 0
        self._live_refinement: OrderedDict[str, ArbiterWorkItem] = OrderedDict()
        self._running_refinements: dict[str, int] = {}
        self._live_provisional: OrderedDict[str, ArbiterWorkItem] = OrderedDict()

    def submit_batch(self, *, key: str, payload: Any) -> ArbiterAdmission:
        self._ensure_room(self._batch, self.max_batch_items, "batch queue is full.")
        item = self._item(self.BATCH, key, payload)
        self._batch.append(item)
        return ArbiterAdmission(True, item.id)

    def submit_live_canonical(self, *, key: str, payload: Any, weight: int = 1) -> ArbiterAdmission:
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise ValueError("live canonical weight must be a positive integer.")
        if (
            self.max_live_canonical_items is not None
            and self._live_canonical_weight + weight > self.max_live_canonical_items
        ):
            raise InferenceArbiterBackpressure("live canonical queue is full.")
        item = self._item(self.LIVE_CANONICAL, key, payload, weight=weight)
        self._live_canonical.append(item)
        self._live_canonical_weight += weight
        return ArbiterAdmission(True, item.id)

    def submit_live_refinement(self, *, coalesce_key: str, payload: Any) -> ArbiterAdmission:
        """Admit one rolling witness for `coalesce_key`, or say why it was not admitted.

        Plan §6 M5 allows **one queued or running rolling witness per session**, and the key
        is what carries the session (`rolling:<epoch>`, emitted by the converger). That rule
        splits into the two answers this method can give:

        - a witness is *queued* for this key -- the newer one replaces it. Nothing has been
          spent on the older request, and the newer window covers audio the older one does
          not, so keeping the stale one would decode yesterday's audio first.
        - a witness is *running* for this key -- the newer one is refused. Replacing it would
          mean cancelling a MOSS request that is already burning GPU, which plan §6 M5
          forbids; the converger's next `observe_base` will re-plan the window anyway.

        No capacity knob: the per-key rule *is* the bound. One arbiter serves one session in
        the runtime, so this queue's depth is one, and a shared arbiter's depth is exactly
        the number of sessions with a pending witness -- which is the number that should be
        scheduled, not a number to refuse.
        """

        if coalesce_key in self._running_refinements:
            return ArbiterAdmission(False, None, reason="live refinement already running")
        item = self._item(self.LIVE_REFINEMENT, coalesce_key, payload)
        previous = self._live_refinement.pop(coalesce_key, None)
        self._live_refinement[coalesce_key] = item
        return ArbiterAdmission(True, item.id, replaced_item_id=None if previous is None else previous.id)

    def release_live_refinement(self, *, item_id: int) -> bool:
        """Report that a dispatched witness is no longer running, so the next may be admitted.

        Called wherever the decode result is handed back, whatever the outcome: a refusal, a
        failed window and a good proposal all end the same request. `False` means this id was
        not the running witness -- a completion that arrived after the session moved on --
        and is not an error, but it is also not a licence to skip the call: the key stays
        blocked until its own release arrives, which is what `live_refinement_running` in the
        snapshot exists to make visible.
        """

        key = next(
            (k for k, running_id in self._running_refinements.items() if running_id == item_id),
            None,
        )
        if key is None:
            return False
        del self._running_refinements[key]
        return True

    def submit_live_provisional(self, *, coalesce_key: str, payload: Any) -> ArbiterAdmission:
        previous = self._live_provisional.pop(coalesce_key, None)
        if previous is None and len(self._live_provisional) >= self.max_live_provisional_items:
            return ArbiterAdmission(False, None, reason="live provisional queue suppressed")
        item = self._item(self.LIVE_PROVISIONAL, coalesce_key, payload)
        self._live_provisional[coalesce_key] = item
        return ArbiterAdmission(True, item.id, replaced_item_id=None if previous is None else previous.id)

    def next_work(self) -> ArbiterWorkItem | None:
        """The highest-priority admitted item, or `None`.

        Dispatching a refinement also *marks it running*, which is the only side effect any
        of these four branches has. It belongs here rather than at the caller because the
        moment a witness leaves this queue is the moment it stops being replaceable, and a
        caller that forgot to say so would let a second witness for the same session start.
        `release_live_refinement` is the other half.
        """

        if self._batch:
            return self._batch.popleft()
        if self._live_canonical:
            item = self._live_canonical.popleft()
            self._live_canonical_weight -= item.weight
            return item
        if self._live_refinement:
            _, item = self._live_refinement.popitem(last=False)
            self._running_refinements[item.key] = item.id
            return item
        if self._live_provisional:
            _, item = self._live_provisional.popitem(last=False)
            return item
        return None

    def snapshot(self) -> ArbiterSnapshot:
        return ArbiterSnapshot(
            batch=len(self._batch),
            live_canonical=self._live_canonical_weight,
            live_provisional=len(self._live_provisional),
            live_refinement=len(self._live_refinement),
            live_refinement_running=len(self._running_refinements),
        )

    def _item(self, kind: str, key: str, payload: Any, *, weight: int = 1) -> ArbiterWorkItem:
        if not key:
            raise ValueError("arbiter work key must be non-empty.")
        item = ArbiterWorkItem(self._next_id, kind, key, payload, weight)
        self._next_id += 1
        return item

    @staticmethod
    def _ensure_room(queue: deque[ArbiterWorkItem], limit: int | None, message: str) -> None:
        if limit is not None and len(queue) >= limit:
            raise InferenceArbiterBackpressure(message)


def _validate_capacity(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative when provided.")
