from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

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
    tier_b_min_segment_seconds: float = 2.0
    tier_b_max_segments_per_node: int = 3
    tier_b_similarity: float = 0.70
    tier_b_margin: float = 0.20


@dataclass(frozen=True, slots=True)
class TierBAssetSpec:
    provider: str = "wespeaker_resnet152_lm"
    revision: str = "4adba1525a6c9d5fff74b6df43a6ec97a86c4112"
    state_sha256: str = "b0446afc11bb51b0eb79559b60508e967310980cf1a5580804473104024239bc"
    embedding_dimension: int = 256
    frontend_version: str = "pytorch-offline-trial"


@dataclass(frozen=True, slots=True)
class TierBPreflight:
    available: bool
    reason: str | None
    descriptor: dict[str, Any]


class TierBEmbedder(Protocol):
    descriptor: dict[str, Any]

    def preflight(self) -> TierBPreflight:
        ...

    def embed(self, wav_path: str | Path, intervals: list[tuple[float, float]]) -> list[float]:
        ...


PINNED_TIER_B_ASSET_SPEC = TierBAssetSpec()


def tier_b_provider_manifest(
    spec: TierBAssetSpec | None = None,
    *,
    device: str = "cpu",
) -> dict[str, Any]:
    manifest_spec = spec or PINNED_TIER_B_ASSET_SPEC
    return {
        "provider": manifest_spec.provider,
        "revision": manifest_spec.revision,
        "state_sha256": manifest_spec.state_sha256,
        "embedding_dimension": manifest_spec.embedding_dimension,
        "frontend_version": manifest_spec.frontend_version,
        "device": device,
    }


def _identity_contract(config: IdentityResolverConfig, tier_b_preflight: TierBPreflight) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "config": {
            "tier_a": {
                "min_overlap_support_seconds": config.min_overlap_support_seconds,
                "min_overlap_dice": config.min_overlap_dice,
                "mutual_margin_seconds": config.mutual_margin_seconds,
            },
            "tier_b": {
                "enabled": config.tier_b_enabled,
                "min_segment_seconds": config.tier_b_min_segment_seconds,
                "max_segments_per_node": config.tier_b_max_segments_per_node,
                "similarity": config.tier_b_similarity,
                "margin": config.tier_b_margin,
            },
        },
        "provider": dict(tier_b_preflight.descriptor),
        "availability": {
            "available": bool(config.tier_b_enabled and tier_b_preflight.available),
            "reason": tier_b_preflight.reason,
        },
    }


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
    audio_path: Path | None


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
        self._tier_b_static_preflight = self._build_tier_b_static_preflight()
        self._contract = _identity_contract(self.config, self._tier_b_static_preflight)

    def contract(self) -> dict[str, Any]:
        return deepcopy(self._contract)

    def resolve(
        self,
        windows: list[Any],
        local_results: list[list[TranscriptSegment]],
        *,
        window_audio_paths: list[str] | list[Any],
    ) -> IdentityResolution:
        bundles = _bundle_windows(windows, local_results, window_audio_paths)
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
        tier_b, tier_b_accepted = self._resolve_tier_b(bundles, components, union)
        if tier_b_accepted:
            components = _components(nodes, union)
        canonical = _canonical_labels(bundles, components, union)
        relabeled = _relabeled_results(bundles, canonical)

        diagnostics = {
            "schema_version": 2,
            "config": self.contract()["config"],
            "contract": self.contract(),
            "boundaries": boundaries,
            "tier_b": tier_b,
        }
        observability = _summary_observability(diagnostics, components)
        summary = {
            "schema_version": 2,
            "accepted_edges": accepted_edges,
            "tier_a_accepted": accepted_edges,
            "tier_b_status": tier_b["status"],
            "tier_b_accepted": tier_b_accepted,
            **observability,
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

    def _resolve_tier_b(
        self,
        bundles: list[_WindowBundle],
        components: list[list[NodeKey]],
        union: _UnionFind,
    ) -> tuple[dict[str, Any], int]:
        if not self.config.tier_b_enabled:
            return {"status": "disabled", "proposals": []}, 0

        preflight = self._tier_b_static_preflight
        if not preflight.available:
            return (
                {
                    "status": "unavailable",
                    "provider": preflight.descriptor,
                    "unavailable_reason": preflight.reason,
                    "proposals": [{"reason": "tier_b_unavailable"}],
                },
                0,
            )

        evidence, candidates = _tier_b_evidence(bundles, components, self.config)
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
        for component in evidence:
            if component["selected_interval_count"] == 0:
                proposals.append(
                    {
                        "component": component["component"],
                        "reason": "tier_b_insufficient_audio",
                    }
                )

        centroid_by_index: dict[int, list[float]] = {}
        for index, candidate in enumerate(candidates):
            if candidate["selected_interval_count"] == 0:
                continue
            if candidate["audio_path"] is None:
                proposals.append(
                    {
                        "component": candidate["component"],
                        "reason": "tier_b_insufficient_audio",
                    }
                )
                continue
            try:
                centroid = self._tier_b_centroid(candidate["audio_path"], candidate["local_intervals"])
            except Exception as exc:
                proposals.append(
                    {
                        "component": candidate["component"],
                        "reason": "tier_b_embedding_failed",
                        "detail": exc.__class__.__name__,
                    }
                )
                continue
            if centroid is None:
                proposals.append(
                    {
                        "component": candidate["component"],
                        "reason": "tier_b_mixture_or_invalid_embedding",
                    }
                )
                continue
            centroid_by_index[index] = centroid

        pair_scores: dict[tuple[int, int], float] = {}
        for left_index in sorted(centroid_by_index):
            for right_index in sorted(centroid_by_index):
                if right_index <= left_index:
                    continue
                try:
                    pair_scores[(left_index, right_index)] = _cosine(
                        centroid_by_index[left_index],
                        centroid_by_index[right_index],
                    )
                except ValueError:
                    proposals.append(
                        {
                            "left": candidates[left_index]["component"],
                            "right": candidates[right_index]["component"],
                            "reason": "tier_b_embedding_failed",
                            "detail": "dimension_mismatch",
                        }
                    )

        accepted = 0
        for (left_index, right_index), similarity in sorted(
            pair_scores.items(),
            key=lambda item: (-item[1], candidates[item[0][0]]["component"], candidates[item[0][1]]["component"]),
        ):
            left = candidates[left_index]
            right = candidates[right_index]
            proposal = {
                "left": left["component"],
                "right": right["component"],
                "similarity": round(similarity, 6),
            }
            if _component_windows(left["nodes"]) & _component_windows(right["nodes"]):
                proposals.append(proposal | {"reason": "cannot_link_conflict"})
                continue
            if similarity < self.config.tier_b_similarity:
                proposals.append(proposal | {"reason": "low_similarity"})
                continue
            margin = min(
                similarity - _tier_b_runner_up(pair_scores, left_index, right_index),
                similarity - _tier_b_runner_up(pair_scores, right_index, left_index),
            )
            proposal["margin"] = round(margin, 6)
            if margin < self.config.tier_b_margin:
                proposals.append(proposal | {"reason": "low_margin"})
                continue
            left_node = left["nodes"][0]
            right_node = right["nodes"][0]
            if _would_violate_cannot_link(union, left_node, right_node):
                proposals.append(proposal | {"reason": "cannot_link_conflict"})
                continue
            union.union(left_node, right_node)
            accepted += 1
            proposals.append(proposal | {"reason": "accepted_similarity"})

        return {
            "status": "available",
            "provider": preflight.descriptor,
            "evidence": evidence,
            "proposals": proposals,
        }, accepted

    def _tier_b_centroid(self, audio_path: Path, intervals: list[Interval]) -> list[float] | None:
        vectors: list[list[float]] = []
        for interval in intervals:
            vector = self.tier_b_encoder.embed(audio_path, [interval])
            normalized = _normalized_vector(vector)
            if normalized is None:
                return None
            vectors.append(normalized)
        if not vectors:
            return None
        centroid = [sum(values) / len(vectors) for values in zip(*vectors, strict=True)]
        return _normalized_vector(centroid)

    def _build_tier_b_static_preflight(self) -> TierBPreflight:
        descriptor = dict(getattr(self.tier_b_encoder, "descriptor", {}) or {})
        if not self.config.tier_b_enabled:
            return TierBPreflight(
                available=False,
                reason="disabled",
                descriptor=descriptor or tier_b_provider_manifest(),
            )
        return self._probe_tier_b_preflight()

    def _probe_tier_b_preflight(self) -> TierBPreflight:
        if self.tier_b_encoder is None:
            return TierBPreflight(
                available=False,
                reason="provider_missing",
                descriptor=tier_b_provider_manifest(),
            )

        descriptor = dict(getattr(self.tier_b_encoder, "descriptor", {}) or {})
        preflight = getattr(self.tier_b_encoder, "preflight", None)
        if not callable(preflight):
            return TierBPreflight(available=True, reason=None, descriptor=descriptor)
        try:
            result = preflight()
        except Exception as exc:
            return TierBPreflight(
                available=False,
                reason=getattr(exc, "reason", "provider_exception"),
                descriptor=descriptor,
            )
        if isinstance(result, TierBPreflight):
            return result
        if isinstance(result, dict):
            return TierBPreflight(
                available=bool(result.get("available")),
                reason=result.get("reason"),
                descriptor=dict(result.get("descriptor") or descriptor),
            )
        return TierBPreflight(available=bool(result), reason=None if result else "provider_unavailable", descriptor=descriptor)


class WeSpeakerResNet152LmAdapter:
    def __init__(
        self,
        state_path: str | Path,
        *,
        embedder: Any = None,
        loader: Callable[[], Any] | None = None,
        spec: TierBAssetSpec | None = None,
        device: str = "cpu",
    ):
        self.state_path = Path(state_path)
        self.embedder = embedder
        self._loader = loader
        self._embedder_injected = embedder is not None
        self._loaded_descriptor: dict[str, Any] | None = None
        self._verified_preflight: TierBPreflight | None = None
        self.spec = spec or PINNED_TIER_B_ASSET_SPEC
        self.device = device
        self.descriptor = tier_b_provider_manifest(self.spec, device=self.device)

    def preflight(self, *, fixture_path: str | Path | None = None) -> TierBPreflight:
        if self.device != "cpu":
            return TierBPreflight(False, "device_not_cpu", self.descriptor)
        if not self.state_path.exists():
            return TierBPreflight(False, "asset_missing", self.descriptor)
        actual_sha256 = _sha256_file(self.state_path)
        if actual_sha256 != self.spec.state_sha256:
            return TierBPreflight(False, "asset_hash_mismatch", self.descriptor | {"actual_state_sha256": actual_sha256})
        try:
            embedder = self._get_embedder()
        except ImportError as exc:
            return TierBPreflight(False, "provider_missing", self.descriptor | {"detail": str(exc)})
        except Exception as exc:
            return TierBPreflight(False, "provider_load_failed", self.descriptor | {"detail": exc.__class__.__name__})
        if not callable(getattr(embedder, "embed", None)):
            return TierBPreflight(False, "provider_missing", self.descriptor)
        loaded_descriptor = dict(self._loaded_descriptor or {})
        loaded_failure = _loaded_provider_failure(loaded_descriptor, self.descriptor)
        if loaded_failure is not None:
            return TierBPreflight(
                False,
                loaded_failure,
                self.descriptor | {"loaded_provider": loaded_descriptor},
            )
        if fixture_path is None:
            return self._verified_preflight or TierBPreflight(True, None, self.descriptor)
        result = self._smoke_preflight(embedder, Path(fixture_path))
        if result.available:
            self._verified_preflight = result
        return result

    def embed(self, wav_path: str | Path, intervals: list[tuple[float, float]]) -> list[float]:
        preflight = self.preflight()
        if not preflight.available:
            raise RuntimeError(f"Tier B provider unavailable: {preflight.reason}")
        return list(self._get_embedder().embed(wav_path, intervals))

    def _get_embedder(self) -> Any:
        if self.embedder is None:
            loader = self._loader or (
                lambda: _PyannoteWeSpeakerEmbedder(
                    self.state_path,
                    device=self.device,
                )
            )
            self.embedder = loader()
        if self._loaded_descriptor is None:
            if self._embedder_injected:
                self._loaded_descriptor = dict(self.descriptor)
            else:
                load = getattr(self.embedder, "load", None)
                if not callable(load):
                    raise TypeError("Tier B provider loader must expose load().")
                loaded_descriptor = load()
                if not isinstance(loaded_descriptor, dict):
                    raise TypeError("Tier B provider load() must return a descriptor.")
                self._loaded_descriptor = dict(loaded_descriptor)
        return self.embedder

    def _smoke_preflight(self, embedder: Any, fixture_path: Path) -> TierBPreflight:
        if not fixture_path.exists():
            return TierBPreflight(False, "fixture_missing", self.descriptor)
        cuda_before = _cuda_allocated_bytes()
        try:
            first = _vector_values(embedder.embed(fixture_path, [(0.0, 2.0)]))
            second = _vector_values(embedder.embed(fixture_path, [(0.0, 2.0)]))
        except Exception as exc:
            return TierBPreflight(False, "smoke_embedding_failed", self.descriptor | {"detail": exc.__class__.__name__})
        cuda_after = _cuda_allocated_bytes()
        descriptor = self.descriptor | {
            "smoke": {
                "fixture": str(fixture_path),
                "cuda_allocated_bytes_before": cuda_before,
                "cuda_allocated_bytes_after": cuda_after,
            }
        }
        failure = _embedding_smoke_failure(first, second, self.spec.embedding_dimension, cuda_before, cuda_after)
        if failure is not None:
            return TierBPreflight(False, failure, descriptor)
        return TierBPreflight(True, None, descriptor)


class _PyannoteWeSpeakerEmbedder:
    def __init__(self, state_path: Path, *, device: str):
        self.state_path = state_path
        self.device = device
        self._inference = None

    def load(self) -> dict[str, Any]:
        self._load_inference()
        return tier_b_provider_manifest(device=self.device)

    def embed(self, wav_path: str | Path, intervals: list[tuple[float, float]]) -> list[float]:
        inference = self._load_inference()
        vectors = []
        for start, end in intervals:
            if end <= start:
                continue
            vectors.append(_normalized_vector(inference.crop(str(wav_path), _pyannote_segment(start, end))))
        if not vectors:
            raise ValueError("Tier B embedding intervals are empty.")
        return _mean_unit_vector(vectors)

    def _load_inference(self) -> Any:
        if self._inference is not None:
            return self._inference
        try:
            from pyannote.audio import Inference, Model
        except ImportError as exc:
            raise ImportError("install the speaker-identity optional extra") from exc
        model = Model.from_pretrained(str(self.state_path), map_location=self.device)
        self._inference = Inference(model, window="whole", device=self.device)
        return self._inference


def _pyannote_segment(start: float, end: float) -> Any:
    try:
        from pyannote.core import Segment
    except ImportError as exc:
        raise ImportError("install the speaker-identity optional extra") from exc
    return Segment(float(start), float(end))


def _bundle_windows(
    windows: list[Any],
    local_results: list[list[TranscriptSegment]],
    window_audio_paths: list[str] | list[Any],
) -> list[_WindowBundle]:
    if len(windows) != len(local_results):
        raise ValueError("windows and local_results must have the same length.")
    audio_paths = list(window_audio_paths)
    if audio_paths and len(audio_paths) != len(windows):
        raise ValueError("window_audio_paths must be empty or have the same length as windows.")
    pairs = sorted(
        zip(windows, local_results, audio_paths or [None] * len(windows), strict=True),
        key=lambda item: item[0].index,
    )
    return [
        _WindowBundle(
            index=int(window.index),
            start=float(window.start),
            end=float(window.end),
            own_start=float(window.own_start),
            own_end=float(window.own_end),
            segments=list(segments),
            audio_path=None if audio_path is None else Path(audio_path),
        )
        for window, segments, audio_path in pairs
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


def _tier_b_evidence(
    bundles: list[_WindowBundle],
    components: list[list[NodeKey]],
    config: IdentityResolverConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    unresolved_components = [component for component in components if len(component) == 1]
    evidence: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for component in unresolved_components:
        node_entries = []
        local_intervals: list[Interval] = []
        audio_path: Path | None = None
        for node in component:
            node_entry, node_audio_path, node_local_intervals = _tier_b_node_evidence(bundles, node, config)
            node_entries.append(node_entry)
            audio_path = node_audio_path if audio_path is None else audio_path
            local_intervals.extend(node_local_intervals)
        evidence.append(
            {
                "component": _format_component(component),
                "selected_interval_count": sum(entry["selected_interval_count"] for entry in node_entries),
                "selected_duration_seconds": round(
                    sum(entry["selected_duration_seconds"] for entry in node_entries),
                    6,
                ),
                "nodes": node_entries,
            }
        )
        candidates.append(
            {
                "component": _format_component(component),
                "nodes": component,
                "audio_path": audio_path,
                "local_intervals": local_intervals,
                "selected_interval_count": sum(entry["selected_interval_count"] for entry in node_entries),
            }
        )
    return evidence, candidates


def _tier_b_node_evidence(
    bundles: list[_WindowBundle],
    node: NodeKey,
    config: IdentityResolverConfig,
) -> tuple[dict[str, Any], Path | None, list[Interval]]:
    candidates: list[dict[str, Any]] = []
    audio_path: Path | None = None
    for bundle in bundles:
        if bundle.index != node[0]:
            continue
        audio_path = bundle.audio_path
        for segment in bundle.segments:
            if segment.speaker != node[1]:
                continue
            absolute_start = bundle.start + float(segment.start)
            absolute_end = bundle.start + float(segment.end)
            local_start = float(segment.start)
            local_end = float(segment.end)
            duration = absolute_end - absolute_start
            if duration < config.tier_b_min_segment_seconds:
                continue
            candidates.append(
                {
                    "window": bundle.index,
                    "start": round(absolute_start, 6),
                    "end": round(absolute_end, 6),
                    "local_start": local_start,
                    "local_end": local_end,
                    "duration_seconds": round(duration, 6),
                }
            )

    selected = sorted(
        candidates,
        key=lambda item: (-item["duration_seconds"], item["start"], item["end"]),
    )[: config.tier_b_max_segments_per_node]
    public_intervals = [
        {
            "window": item["window"],
            "start": item["start"],
            "end": item["end"],
            "duration_seconds": item["duration_seconds"],
        }
        for item in selected
    ]
    local_intervals = [(item["local_start"], item["local_end"]) for item in selected]
    return (
        {
            "node": _format_node(node),
            "selected_interval_count": len(selected),
            "selected_duration_seconds": round(sum(item["duration_seconds"] for item in selected), 6),
            "selected_intervals": public_intervals,
        },
        audio_path,
        local_intervals,
    )


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


def _summary_observability(
    diagnostics: dict[str, Any],
    components: list[list[NodeKey]],
) -> dict[str, int]:
    birth_or_return_reasons = {
        "unmatched_birth_or_return",
        "unresolved_birth_or_return",
    }
    birth_or_return_nodes: set[str] = set()
    false_accepted_edges = 0

    for boundary in diagnostics.get("boundaries", []):
        accepted_left: set[str] = set()
        accepted_right: set[str] = set()
        for edge in boundary.get("edges", []):
            reason = edge.get("reason")
            left = edge.get("left")
            right = edge.get("right")
            if reason in birth_or_return_reasons and right:
                birth_or_return_nodes.add(right)
            if reason != "accepted_overlap":
                continue
            violates = (
                not left
                or not right
                or _node_window(left) == _node_window(right)
                or left in accepted_left
                or right in accepted_right
            )
            false_accepted_edges += int(violates)
            if left:
                accepted_left.add(left)
            if right:
                accepted_right.add(right)

    accepted_components: set[tuple[str, ...]] = set()
    for proposal in diagnostics.get("tier_b", {}).get("proposals", []):
        reason = proposal.get("reason")
        if reason in birth_or_return_reasons:
            for field in ("component", "left", "right"):
                birth_or_return_nodes.update(proposal.get(field) or [])
        if reason != "accepted_similarity":
            continue
        left = tuple(proposal.get("left") or [])
        right = tuple(proposal.get("right") or [])
        violates = (
            not left
            or not right
            or bool({_node_window(node) for node in left} & {_node_window(node) for node in right})
            or left in accepted_components
            or right in accepted_components
        )
        false_accepted_edges += int(violates)
        if left:
            accepted_components.add(left)
        if right:
            accepted_components.add(right)

    fragmented_recurring_speakers = sum(
        len(component) == 1 and _format_node(component[0]) in birth_or_return_nodes
        for component in components
    )
    return {
        "false_accepted_edges": false_accepted_edges,
        "fragmented_recurring_speakers": fragmented_recurring_speakers,
    }


def _node_window(node: str) -> int:
    return int(node.split(":", 1)[0])


def _normalized_vector(vector: Any) -> list[float] | None:
    values = _vector_values(vector)
    if any(not math.isfinite(value) for value in values):
        return None
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0.0:
        return None
    return [value / norm for value in values]


def _vector_values(vector: Any) -> list[float]:
    return [float(value) for value in vector]


def _mean_unit_vector(vectors: list[list[float] | None]) -> list[float]:
    valid = [vector for vector in vectors if vector is not None]
    if not valid:
        raise ValueError("Tier B embeddings are not finite unit vectors.")
    length = len(valid[0])
    if any(len(vector) != length for vector in valid):
        raise ValueError("Tier B embeddings must have matching dimensions.")
    return _normalized_vector(
        [
            sum(vector[index] for vector in valid) / len(valid)
            for index in range(length)
        ]
    ) or []


def _embedding_smoke_failure(
    first: list[float] | None,
    second: list[float] | None,
    expected_dimension: int,
    cuda_before: int | None,
    cuda_after: int | None,
) -> str | None:
    if first is None or second is None:
        return "smoke_embedding_invalid"
    if len(first) != expected_dimension or len(second) != expected_dimension:
        return "dimension_mismatch"
    if any(not math.isfinite(value) for value in first + second):
        return "smoke_embedding_invalid"
    if abs(math.sqrt(sum(value * value for value in first)) - 1.0) > 1e-6:
        return "smoke_embedding_not_unit_normalized"
    if abs(math.sqrt(sum(value * value for value in second)) - 1.0) > 1e-6:
        return "smoke_embedding_not_unit_normalized"
    if max(first) - min(first) <= 1e-9:
        return "smoke_embedding_constant"
    if any(abs(left - right) > 1e-9 for left, right in zip(first, second, strict=True)):
        return "smoke_embedding_not_deterministic"
    if cuda_before not in (None, 0) or cuda_after not in (None, 0):
        return "cuda_allocated"
    return None


def _loaded_provider_failure(loaded: dict[str, Any], expected: dict[str, Any]) -> str | None:
    for field, reason in (
        ("provider", "provider_mismatch"),
        ("revision", "revision_mismatch"),
        ("state_sha256", "asset_hash_mismatch"),
        ("embedding_dimension", "dimension_mismatch"),
        ("device", "device_not_cpu"),
    ):
        if loaded.get(field) != expected.get(field):
            return reason
    return None


def _cuda_allocated_bytes() -> int | None:
    try:
        import torch
    except ImportError:
        return None
    cuda = getattr(torch, "cuda", None)
    if cuda is None or not callable(getattr(cuda, "memory_allocated", None)):
        return None
    try:
        return int(cuda.memory_allocated())
    except Exception:
        return None


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Tier B embeddings must have matching dimensions.")
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))


def _tier_b_runner_up(pair_scores: dict[tuple[int, int], float], index: int, matched_index: int) -> float:
    alternatives = [
        score
        for pair, score in pair_scores.items()
        if index in pair and matched_index not in pair
    ]
    return max(alternatives, default=0.0)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "IdentityResolution",
    "IdentityResolver",
    "IdentityResolverConfig",
    "PINNED_TIER_B_ASSET_SPEC",
    "TierBAssetSpec",
    "TierBPreflight",
    "WeSpeakerResNet152LmAdapter",
    "tier_b_provider_manifest",
]
