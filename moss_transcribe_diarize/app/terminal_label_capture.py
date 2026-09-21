"""Opt-in observation of terminal-local partition identity outcomes.

This module is deliberately outside the terminal decision path.  It only copies the
native ``TerminalPartitionDecision`` records after finalization has settled.  A
capture or writer failure is ignored so the ordinary published proposal still wins.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


ENVIRONMENT_VARIABLE = "MOSS_TERMINAL_LABEL_CAPTURE"


def capture_from_environment() -> "TerminalLabelCapture | None":
    """Return an explicit sink, or nothing on the ordinary product path."""

    destination = os.environ.get(ENVIRONMENT_VARIABLE)
    return TerminalLabelCapture(Path(destination)) if destination else None


@dataclass(frozen=True, slots=True)
class _ProbeObservation:
    minimum_samples: int | None
    score_by_canonical: dict[str, float]
    margin: float | None


class _EvidenceObserver:
    """Transparent revision-reader wrapper that only copies its returned evidence."""

    def __init__(self, provider: Any, capture: "TerminalLabelCapture", partition_id: str):
        self._provider = provider
        self._capture = capture
        self._partition_id = partition_id
        self.min_segment_samples = getattr(provider, "min_segment_samples", None)

    def score(self, **kwargs):
        evidence = tuple(self._provider.score(**kwargs))
        try:
            self._capture.observe_evidence(
                partition_id=self._partition_id,
                evidence=evidence,
                minimum_samples=self.min_segment_samples,
            )
        except Exception:
            pass
        return evidence

    def birth_deferrals(self, **kwargs):
        method = getattr(self._provider, "birth_deferrals", None)
        return () if method is None else method(**kwargs)


class TerminalLabelCapture:
    """Copy native partition decisions and existing aggregate score evidence to JSONL."""

    def __init__(self, destination: Path):
        self.destination = destination
        self._lock = Lock()
        self._evidence: dict[str, _ProbeObservation] = {}

    def prepare_revision(
        self,
        *,
        owner: Any,
        partition_id: str,
        **kwargs,
    ) -> Any:
        """Run the existing revision reader through a score-copying wrapper."""

        from .live_identity import BoundedCausalIdentityPreparer

        provider = owner.evidence_provider
        revision_reader = getattr(provider, "revision_reader", None)
        if revision_reader is not None:
            provider = revision_reader()
        observed = _EvidenceObserver(provider, self, partition_id)
        return BoundedCausalIdentityPreparer(
            config=owner.config, evidence_provider=observed
        ).prepare(**kwargs)

    def observe_evidence(
        self,
        *,
        partition_id: str,
        evidence: tuple[Any, ...],
        minimum_samples: int | None,
    ) -> None:
        """Retain the raw returned scores for the product partition that requested them."""

        score_by_canonical = {
            str(item.canonical_speaker): float(item.score) for item in evidence
        }
        ranked = sorted(score_by_canonical.values(), reverse=True)
        margin = None if not ranked else ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
        with self._lock:
            self._evidence[partition_id] = _ProbeObservation(
                minimum_samples=(
                    None if minimum_samples is None else int(minimum_samples)
                ),
                score_by_canonical=score_by_canonical,
                margin=margin,
            )

    def record_partitions(self, partitions: tuple[Any, ...]) -> None:
        """Append rows copied from native finalization records; never affect publication."""

        try:
            with self._lock:
                rows = []
                for partition in partitions:
                    evidence = self._evidence.get(partition.partition_id)
                    floor = partition.minimum_samples
                    for span in partition.spans:
                        samples = span.source_end - span.source_start
                        rows.append(
                            {
                                "span_index": span.span_index,
                                "source_start": span.source_start,
                                "source_end": span.source_end,
                                "samples": samples,
                                "terminal_local_label": partition.terminal_local_label,
                                "partition_id": partition.partition_id,
                                "eligible": None if floor is None else samples >= floor,
                                "score_by_canonical": (
                                    {} if evidence is None else evidence.score_by_canonical
                                ),
                                "margin": None if evidence is None else evidence.margin,
                                "decision": partition.decision,
                                "published_identity": span.published_identity,
                            }
                        )
                self.destination.parent.mkdir(parents=True, exist_ok=True)
                with self.destination.open("a", encoding="utf-8") as output:
                    for row in rows:
                        output.write(
                            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
                        )
        except Exception:
            pass
