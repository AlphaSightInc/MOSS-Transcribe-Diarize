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


@dataclass(frozen=True, slots=True)
class ArbiterSnapshot:
    batch: int
    live_canonical: int
    live_provisional: int


class InferenceArbiter:
    """Priority gate for batch, canonical live, and provisional live inference."""

    BATCH = "batch"
    LIVE_CANONICAL = "live_canonical"
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
        self._live_provisional: OrderedDict[str, ArbiterWorkItem] = OrderedDict()

    def submit_batch(self, *, key: str, payload: Any) -> ArbiterAdmission:
        self._ensure_room(self._batch, self.max_batch_items, "batch queue is full.")
        item = self._item(self.BATCH, key, payload)
        self._batch.append(item)
        return ArbiterAdmission(True, item.id)

    def submit_live_canonical(self, *, key: str, payload: Any) -> ArbiterAdmission:
        self._ensure_room(self._live_canonical, self.max_live_canonical_items, "live canonical queue is full.")
        item = self._item(self.LIVE_CANONICAL, key, payload)
        self._live_canonical.append(item)
        return ArbiterAdmission(True, item.id)

    def submit_live_provisional(self, *, coalesce_key: str, payload: Any) -> ArbiterAdmission:
        previous = self._live_provisional.pop(coalesce_key, None)
        if previous is None and len(self._live_provisional) >= self.max_live_provisional_items:
            return ArbiterAdmission(False, None, reason="live provisional queue suppressed")
        item = self._item(self.LIVE_PROVISIONAL, coalesce_key, payload)
        self._live_provisional[coalesce_key] = item
        return ArbiterAdmission(True, item.id, replaced_item_id=None if previous is None else previous.id)

    def next_work(self) -> ArbiterWorkItem | None:
        if self._batch:
            return self._batch.popleft()
        if self._live_canonical:
            return self._live_canonical.popleft()
        if self._live_provisional:
            _, item = self._live_provisional.popitem(last=False)
            return item
        return None

    def snapshot(self) -> ArbiterSnapshot:
        return ArbiterSnapshot(
            batch=len(self._batch),
            live_canonical=len(self._live_canonical),
            live_provisional=len(self._live_provisional),
        )

    def _item(self, kind: str, key: str, payload: Any) -> ArbiterWorkItem:
        if not key:
            raise ValueError("arbiter work key must be non-empty.")
        item = ArbiterWorkItem(self._next_id, kind, key, payload)
        self._next_id += 1
        return item

    @staticmethod
    def _ensure_room(queue: deque[ArbiterWorkItem], limit: int | None, message: str) -> None:
        if limit is not None and len(queue) >= limit:
            raise InferenceArbiterBackpressure(message)


def _validate_capacity(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative when provided.")
