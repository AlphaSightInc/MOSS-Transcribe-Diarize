"""Pure canonical lifecycle evidence reduction shared by measurement and qualification."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


def prestop_inference_projection(
    events: Sequence[Mapping[str, Any]],
    *,
    accepted_audio_seconds: float,
) -> dict[str, int | float]:
    """Reduce pre-Stop canonical and rolling compute over accepted audio."""

    def payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
        nested = event.get("payload")
        return nested if isinstance(nested, Mapping) else event

    def item_identity(event: Mapping[str, Any]) -> tuple[str, int]:
        session_id = event.get("session_id")
        item_id = payload(event).get("item_id")
        if not isinstance(session_id, str) or not session_id or not isinstance(item_id, int):
            raise ValueError("inference event lacks session-scoped item identity")
        return session_id, item_id

    if not math.isfinite(accepted_audio_seconds) or accepted_audio_seconds <= 0:
        raise ValueError("accepted audio duration is invalid")
    stop_items = {
        item_identity(event)
        for event in events
        if event.get("kind") == "canonical_queued"
        and payload(event).get("reason") == "stop"
    }
    rolling_admission_events = [
        item_identity(event)
        for event in events
        if event.get("kind") == "rolling_decode_queued"
        and payload(event).get("admitted") is True
    ]
    rolling_admitted = set(rolling_admission_events)
    if len(rolling_admitted) != len(rolling_admission_events):
        raise ValueError("rolling item was admitted more than once")
    canonical_decode_seconds = 0.0
    rolling_decode_seconds = 0.0
    canonical_processed_items = 0
    rolling_completed_items: set[tuple[str, int]] = set()
    for event in events:
        kind = event.get("kind")
        if kind not in {"canonical_processed", "rolling_decode_completed"}:
            continue
        item = payload(event)
        identity = item_identity(event)
        if kind == "canonical_processed" and identity in stop_items:
            continue
        if kind == "canonical_processed":
            try:
                decode = float(item["canonical_decode_elapsed_sec"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("canonical processed event lacks inference timing") from exc
            if not math.isfinite(decode) or decode < 0:
                raise ValueError("canonical processed inference timing is invalid")
            canonical_decode_seconds += decode
            canonical_processed_items += 1
            continue
        if identity not in rolling_admitted or identity in rolling_completed_items:
            raise ValueError("rolling completion lacks one admitted session-scoped item")
        rolling_completed_items.add(identity)
        if item.get("outcome") == "not_awaited":
            # A window the session was no longer waiting for by the time the pump reached it.
            # The coordinator refuses to decode one (`capture_refinement_item`), so there is
            # no inference to project and no measurement to read -- every field this branch
            # would otherwise check is null by construction, because no decode happened. It
            # is counted as completed, because the §7.4 property this reduction enforces is
            # that every *admitted* window ends, and skipped as compute, which is what this
            # reduction measures. The ordinary producer of one is a meeting whose Stop ended
            # rolling while a window sat in the queue; that window is post-Stop by
            # definition, exactly like the canonical tail `stop_items` already excludes.
            continue
        if item.get("outcome") not in {"applied", "refused", "no_proposal"}:
            raise ValueError("rolling completion has a non-healthy terminal outcome")
        if item.get("decode_failure") is not None:
            raise ValueError("rolling completion reports a decode failure")
        for counter in ("windows_failed", "stale_completions"):
            value = item.get(counter)
            if not isinstance(value, int) or isinstance(value, bool) or value != 0:
                raise ValueError(f"rolling completion has invalid {counter}")
        if "rolling_decode_elapsed_sec" not in item:
            raise ValueError("rolling completion lacks inference timing")
        elapsed = item["rolling_decode_elapsed_sec"]
        if elapsed is None:
            raise ValueError("rolling completion did not measure inference timing")
        try:
            rolling_decode = float(elapsed)
        except (TypeError, ValueError) as exc:
            raise ValueError("rolling completion inference timing is invalid") from exc
        if not math.isfinite(rolling_decode) or rolling_decode < 0:
            raise ValueError("rolling completion inference timing is invalid")
        rolling_decode_seconds += rolling_decode
    if canonical_processed_items == 0 or not rolling_admitted:
        raise ValueError("pre-Stop inference evidence is absent")
    if rolling_completed_items != rolling_admitted:
        raise ValueError("rolling admitted/completed accounting is incomplete")
    total_decode_seconds = canonical_decode_seconds + rolling_decode_seconds
    return {
        "canonical_processed_items": canonical_processed_items,
        "rolling_completed_items": len(rolling_completed_items),
        "stop_items": len(stop_items),
        "canonical_decode_seconds": canonical_decode_seconds,
        "rolling_decode_seconds": rolling_decode_seconds,
        "decode_seconds": total_decode_seconds,
        "accepted_audio_seconds": accepted_audio_seconds,
        "rtf": total_decode_seconds / accepted_audio_seconds,
    }


def canonical_lifecycle_fairness(
    events: Sequence[Mapping[str, Any]],
    session_ids: set[str],
    *,
    maximum_skew: int,
) -> dict[str, Any]:
    """Measure pairwise dispatch skew only while two sessions are jointly ready."""

    queued_items = {session_id: set() for session_id in session_ids}
    started_items = {session_id: set() for session_id in session_ids}
    pair_counts: dict[tuple[str, str], dict[str, int]] = {}
    maximum_observed_skew = 0
    contended_pair_dispatch_observations = 0
    lifecycle_counts = {
        kind: 0
        for kind in ("canonical_queued", "canonical_started", "canonical_processed")
    }
    errors: list[str] = []

    def active_pairs() -> set[tuple[str, str]]:
        ready = sorted(
            session_id for session_id, items in queued_items.items() if items
        )
        return {
            (left, right)
            for index, left in enumerate(ready)
            for right in ready[index + 1 :]
        }

    def reconcile_pairs() -> None:
        active = active_pairs()
        for pair in tuple(pair_counts):
            if pair not in active:
                del pair_counts[pair]
        for pair in active:
            pair_counts.setdefault(pair, {pair[0]: 0, pair[1]: 0})

    for index, event in enumerate(events):
        session_id = event.get("session_id")
        kind = event.get("kind")
        payload = event.get("payload")
        if session_id not in session_ids:
            continue
        if kind not in lifecycle_counts:
            errors.append(
                f"event {index} has unsupported canonical lifecycle kind {kind!r}"
            )
            continue
        lifecycle_counts[kind] += 1
        if not isinstance(payload, dict) or not isinstance(payload.get("item_id"), int):
            errors.append(f"event {index} lacks an integer canonical item_id")
            continue
        item_id = payload["item_id"]
        if kind == "canonical_queued":
            if item_id in queued_items[session_id] or item_id in started_items[session_id]:
                errors.append(
                    f"event {index} queues duplicate item {session_id}/{item_id}"
                )
                continue
            queued_items[session_id].add(item_id)
            reconcile_pairs()
            continue
        if kind == "canonical_started":
            reconcile_pairs()
            if item_id not in queued_items[session_id]:
                errors.append(
                    f"event {index} starts unqueued item {session_id}/{item_id}"
                )
                continue
            for pair, counts in pair_counts.items():
                if session_id not in pair:
                    continue
                contended_pair_dispatch_observations += 1
                counts[session_id] += 1
                maximum_observed_skew = max(
                    maximum_observed_skew,
                    abs(counts[pair[0]] - counts[pair[1]]),
                )
            queued_items[session_id].remove(item_id)
            started_items[session_id].add(item_id)
            reconcile_pairs()
            continue
        if item_id not in started_items[session_id]:
            errors.append(
                f"event {index} processes unstarted item {session_id}/{item_id}"
            )

    for kind, count in lifecycle_counts.items():
        if count == 0:
            errors.append(f"lifecycle evidence has no {kind} events")
    if errors:
        applicability = "invalid"
        passes: bool | None = False
    elif contended_pair_dispatch_observations == 0:
        applicability = "not_applicable"
        passes = None
    else:
        applicability = "measured"
        passes = maximum_observed_skew <= maximum_skew
    return {
        "method": "pairwise dispatch skew over each continuous jointly-ready interval",
        "lifecycle_event_counts": lifecycle_counts,
        "contended_pair_dispatch_observations": contended_pair_dispatch_observations,
        "maximum_contended_pair_dispatch_skew": maximum_observed_skew,
        "fairness_gate": maximum_skew,
        "applicability": applicability,
        "errors": errors,
        "passes": passes,
    }
