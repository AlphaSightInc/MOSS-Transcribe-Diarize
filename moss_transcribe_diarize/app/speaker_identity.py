from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scipy.optimize import linear_sum_assignment

from moss_transcribe_diarize.transcript_parser import TranscriptSegment


NodeKey = tuple[int, str]
Interval = tuple[float, float]


@dataclass(frozen=True, slots=True)
class IdentityResolverConfig:
    min_overlap_support_seconds: float = 2.0
    min_overlap_dice: float = 0.75
    mutual_margin_seconds: float = 1.0
    tier_b_enabled: bool = False


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    relabeled_results: list[list[TranscriptSegment]]
    summary: dict[str, Any]
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _WindowBundle:
    index: int
    start: float
    end: float
    own_start: float
    own_end: float
    segments: list[TranscriptSegment]


class _UnionFind:
    def __init__(self, nodes: list[NodeKey]):
        self.parent = {node: node for node in nodes}

    def find(self, node: NodeKey) -> NodeKey:
        parent = self.parent[node]
        if parent != node:
            parent = self.find(parent)
            self.parent[node] = parent
        return parent

    def union(self, left: NodeKey, right: NodeKey) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root


class IdentityResolver:
    def __init__(self, *, config: IdentityResolverConfig | None = None, tier_b_encoder: Any = None):
        self.config = config or IdentityResolverConfig()
        self.tier_b_encoder = tier_b_encoder

    def resolve(
        self,
        windows: list[Any],
        local_results: list[list[TranscriptSegment]],
        *,
        window_audio_paths: list[str] | list[Any],
    ) -> IdentityResolution:
        del window_audio_paths
        bundles = _bundle_windows(windows, local_results)
        nodes = _nodes_for(bundles)
        union = _UnionFind(nodes)
        node_intervals = _node_intervals(bundles)
        boundaries: list[dict[str, Any]] = []
        accepted_edges = 0

        for left, right in zip(bundles, bundles[1:], strict=False):
            boundary, accepted = self._resolve_boundary(left, right, node_intervals, union)
            accepted_edges += accepted
            if boundary["edges"]:
                boundaries.append(boundary)

        components = _components(nodes, union)
        tier_b = self._tier_b_diagnostics(components)
        canonical = _canonical_labels(bundles, components, union)
        relabeled = _relabeled_results(bundles, canonical)

        summary = {
            "schema_version": 2,
            "accepted_edges": accepted_edges,
            "tier_a_accepted": accepted_edges,
            "tier_b_status": tier_b["status"],
            "tier_b_accepted": 0,
        }
        diagnostics = {
            "schema_version": 2,
            "config": {
                "min_overlap_support_seconds": self.config.min_overlap_support_seconds,
                "min_overlap_dice": self.config.min_overlap_dice,
                "mutual_margin_seconds": self.config.mutual_margin_seconds,
                "tier_b_enabled": self.config.tier_b_enabled,
            },
            "boundaries": boundaries,
            "tier_b": tier_b,
        }
        return IdentityResolution(relabeled_results=relabeled, summary=summary, diagnostics=diagnostics)

    def _resolve_boundary(
        self,
        left: _WindowBundle,
        right: _WindowBundle,
        node_intervals: dict[NodeKey, list[Interval]],
        union: _UnionFind,
    ) -> tuple[dict[str, Any], int]:
        left_nodes = sorted({(left.index, segment.speaker) for segment in left.segments})
        right_nodes = sorted({(right.index, segment.speaker) for segment in right.segments})
        boundary = {"left_window": left.index, "right_window": right.index, "edges": []}
        if not left_nodes or not right_nodes:
            for node in right_nodes:
                boundary["edges"].append(_edge(None, node, "unmatched_birth_or_return"))
            return boundary, 0

        support: list[list[float]] = []
        dice: list[list[float]] = []
        overlap = (max(left.start, right.start), min(left.end, right.end))
        for left_node in left_nodes:
            support_row: list[float] = []
            dice_row: list[float] = []
            for right_node in right_nodes:
                left_clipped = _clip_intervals(node_intervals[left_node], overlap)
                right_clipped = _clip_intervals(node_intervals[right_node], overlap)
                intersection = _intersection_seconds(left_clipped, right_clipped)
                denominator = _interval_seconds(left_clipped) + _interval_seconds(right_clipped)
                support_row.append(intersection)
                dice_row.append(0.0 if denominator <= 0 else (2.0 * intersection) / denominator)
            support.append(support_row)
            dice.append(dice_row)

        row_indexes, col_indexes = linear_sum_assignment([[-score for score in row] for row in dice])
        accepted = 0
        matched_right: set[NodeKey] = set()
        for row_index, col_index in sorted(zip(row_indexes, col_indexes, strict=True), key=lambda item: right_nodes[item[1]]):
            left_node = left_nodes[row_index]
            right_node = right_nodes[col_index]
            reason = self._tier_a_reason(row_index, col_index, support, dice)
            if reason == "accepted_overlap" and _would_violate_cannot_link(union, left_node, right_node):
                reason = "cannot_link_conflict"
            boundary["edges"].append(_edge(left_node, right_node, reason))
            if reason == "accepted_overlap":
                matched_right.add(right_node)
                union.union(left_node, right_node)
                accepted += 1

        for node in right_nodes:
            if node not in matched_right:
                boundary["edges"].append(_edge(None, node, "unmatched_birth_or_return"))
        boundary["edges"].sort(key=lambda item: (item["right"] or "", item["left"] or "", item["reason"]))
        return boundary, accepted

    def _tier_a_reason(
        self,
        row_index: int,
        col_index: int,
        support: list[list[float]],
        dice: list[list[float]],
    ) -> str:
        assigned_support = support[row_index][col_index]
        assigned_dice = dice[row_index][col_index]
        if assigned_support < self.config.min_overlap_support_seconds:
            return "low_support"

        row_alternatives = [
            value for index, value in enumerate(support[row_index]) if index != col_index
        ]
        column_alternatives = [
            row[col_index] for index, row in enumerate(support) if index != row_index
        ]
        runner_up = max(row_alternatives + column_alternatives, default=0.0)
        if assigned_support - runner_up < self.config.mutual_margin_seconds:
            return "low_margin"
        if assigned_dice < self.config.min_overlap_dice:
            return "low_dice"
        return "accepted_overlap"

    def _tier_b_diagnostics(self, components: list[list[NodeKey]]) -> dict[str, Any]:
        if not self.config.tier_b_enabled:
            return {"status": "disabled", "proposals": []}
        if self.tier_b_encoder is None:
            return {
                "status": "unavailable",
                "proposals": [{"reason": "tier_b_unavailable"}],
            }

        proposals: list[dict[str, Any]] = []
        for index, left in enumerate(components):
            for right in components[index + 1 :]:
                if _component_windows(left) & _component_windows(right):
                    proposals.append(
                        {
                            "left": _format_component(left),
                            "right": _format_component(right),
                            "reason": "cannot_link_conflict",
                        }
                    )
        return {"status": "available", "provider": getattr(self.tier_b_encoder, "descriptor", {}), "proposals": proposals}


def _bundle_windows(windows: list[Any], local_results: list[list[TranscriptSegment]]) -> list[_WindowBundle]:
    if len(windows) != len(local_results):
        raise ValueError("windows and local_results must have the same length.")
    pairs = sorted(zip(windows, local_results, strict=True), key=lambda item: item[0].index)
    return [
        _WindowBundle(
            index=int(window.index),
            start=float(window.start),
            end=float(window.end),
            own_start=float(window.own_start),
            own_end=float(window.own_end),
            segments=list(segments),
        )
        for window, segments in pairs
    ]


def _nodes_for(bundles: list[_WindowBundle]) -> list[NodeKey]:
    return sorted({(bundle.index, segment.speaker) for bundle in bundles for segment in bundle.segments})


def _node_intervals(bundles: list[_WindowBundle]) -> dict[NodeKey, list[Interval]]:
    intervals: dict[NodeKey, list[Interval]] = {}
    for bundle in bundles:
        for segment in bundle.segments:
            key = (bundle.index, segment.speaker)
            intervals.setdefault(key, []).append((bundle.start + float(segment.start), bundle.start + float(segment.end)))
    return {key: _merge_intervals(value) for key, value in intervals.items()}


def _clip_intervals(intervals: list[Interval], bounds: Interval) -> list[Interval]:
    start, end = bounds
    if end <= start:
        return []
    clipped = [(max(item_start, start), min(item_end, end)) for item_start, item_end in intervals]
    return _merge_intervals([(item_start, item_end) for item_start, item_end in clipped if item_end > item_start])


def _merge_intervals(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _intersection_seconds(left: list[Interval], right: list[Interval]) -> float:
    total = 0.0
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        start = max(left[left_index][0], right[right_index][0])
        end = min(left[left_index][1], right[right_index][1])
        total += max(0.0, end - start)
        if left[left_index][1] < right[right_index][1]:
            left_index += 1
        else:
            right_index += 1
    return total


def _interval_seconds(intervals: list[Interval]) -> float:
    return sum(end - start for start, end in intervals)


def _components(nodes: list[NodeKey], union: _UnionFind) -> list[list[NodeKey]]:
    groups: dict[NodeKey, list[NodeKey]] = {}
    for node in nodes:
        groups.setdefault(union.find(node), []).append(node)
    return [sorted(group) for _, group in sorted(groups.items())]


def _would_violate_cannot_link(union: _UnionFind, left: NodeKey, right: NodeKey) -> bool:
    left_root = union.find(left)
    right_root = union.find(right)
    if left_root == right_root:
        return False
    windows_by_root: dict[NodeKey, set[int]] = {}
    for node in union.parent:
        windows_by_root.setdefault(union.find(node), set()).add(node[0])
    return bool(windows_by_root[left_root] & windows_by_root[right_root])


def _canonical_labels(
    bundles: list[_WindowBundle],
    components: list[list[NodeKey]],
    union: _UnionFind,
) -> dict[NodeKey, str]:
    component_order = []
    for component in components:
        component_order.append((_component_first_owned_timestamp(bundles, component), component))
    component_order.sort(key=lambda item: (item[0], item[1]))

    labels: dict[NodeKey, str] = {}
    for index, (_, component) in enumerate(component_order, start=1):
        label = f"S{index:02d}"
        for node in component:
            labels[node] = label
    return {node: labels[union.find(node)] if union.find(node) in labels else labels[node] for node in union.parent}


def _component_first_owned_timestamp(bundles: list[_WindowBundle], component: list[NodeKey]) -> tuple[int, float]:
    bundle_by_index = {bundle.index: bundle for bundle in bundles}
    component_set = set(component)
    owned: list[float] = []
    fallback: list[float] = []
    for bundle in bundles:
        for segment in bundle.segments:
            if (bundle.index, segment.speaker) not in component_set:
                continue
            absolute_start = bundle.start + float(segment.start)
            absolute_end = bundle.start + float(segment.end)
            midpoint = (absolute_start + absolute_end) / 2.0
            fallback.append(absolute_start)
            upper_owned = midpoint < bundle.own_end or bundle.index == max(bundle_by_index)
            if midpoint >= bundle.own_start and upper_owned:
                owned.append(absolute_start)
    candidates = owned or fallback
    return (0, min(owned)) if owned else (1, min(candidates) if candidates else float("inf"))


def _relabeled_results(bundles: list[_WindowBundle], canonical: dict[NodeKey, str]) -> list[list[TranscriptSegment]]:
    relabeled: list[list[TranscriptSegment]] = []
    for bundle in bundles:
        window_segments: list[TranscriptSegment] = []
        for segment in bundle.segments:
            window_segments.append(
                TranscriptSegment(
                    start=segment.start,
                    end=segment.end,
                    speaker=canonical[(bundle.index, segment.speaker)],
                    text=segment.text,
                )
            )
        relabeled.append(window_segments)
    return relabeled


def _edge(left: NodeKey | None, right: NodeKey | None, reason: str) -> dict[str, Any]:
    return {
        "left": None if left is None else _format_node(left),
        "right": None if right is None else _format_node(right),
        "reason": reason,
    }


def _format_node(node: NodeKey) -> str:
    return f"{node[0]}:{node[1]}"


def _format_component(component: list[NodeKey]) -> list[str]:
    return [_format_node(node) for node in component]


def _component_windows(component: list[NodeKey]) -> set[int]:
    return {node[0] for node in component}


__all__ = ["IdentityResolution", "IdentityResolver", "IdentityResolverConfig"]
