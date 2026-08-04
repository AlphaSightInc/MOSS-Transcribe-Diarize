#!/usr/bin/env python3
"""Diagnosis-only tests for importing superseded three-array caches."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVED_ALPHABET_CACHE = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
)
ACCEPTED_ALPHABET_REFERENCE = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl"
)


class LegacyIngestTest(unittest.TestCase):
    @staticmethod
    def _write_archive(path: Path, rows: np.ndarray) -> None:
        eligible = rows[:, 5] > 0 if rows.ndim == 2 and rows.shape[1] > 5 else np.ones(len(rows), bool)
        vector_indexes = np.where(eligible, np.cumsum(eligible) - 1, -1).astype(np.int64)
        vectors = np.ones((int(np.count_nonzero(eligible)), 2), dtype=np.float32)
        np.savez(path, rows=rows, vec_idx=vector_indexes, vecs=vectors)

    @staticmethod
    def _replay_archived_alphabet(adapted_cache_path: Path) -> dict[str, object]:
        from run_legacy_anchor_fidelity import replay_legacy_case

        config = json.loads((HERE / "l1-control-spec.json").read_text())["production_config"]
        return replay_legacy_case(
            {
                "case_id": "5m-acquired-alphabet",
                "duration_seconds": 300.0,
                "reference_path": str(ACCEPTED_ALPHABET_REFERENCE),
                "split": "validation",
            },
            config,
            archive_path=ARCHIVED_ALPHABET_CACHE,
            adapted_cache_path=adapted_cache_path,
        )

    def test_corrupt_and_truncated_archives_fail_named(self) -> None:
        from legacy_ingest import LegacyIngestError, load_legacy_archive

        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-corrupt-") as temp:
            root = Path(temp)
            valid = root / "valid.npz"
            self._write_archive(
                valid,
                np.asarray([(0, 0, 0.0, 1.0, 1.0, 1)], dtype=np.float64),
            )
            corrupt = root / "corrupt.npz"
            corrupt.write_bytes(b"not-an-npz")
            truncated = root / "truncated.npz"
            payload = valid.read_bytes()
            truncated.write_bytes(payload[: len(payload) // 2])
            for path in (corrupt, truncated):
                with self.subTest(path=path.name):
                    with self.assertRaises(LegacyIngestError) as raised:
                        load_legacy_archive(path)
                    self.assertEqual(raised.exception.code, "legacy_archive_corrupt")

    def test_missing_archive_array_fails_named(self) -> None:
        from legacy_ingest import LegacyIngestError, load_legacy_archive

        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-missing-array-") as temp:
            archive = Path(temp) / "missing-vec-idx.npz"
            np.savez(
                archive,
                rows=np.asarray([(0, 0, 0.0, 1.0, 1.0, 1)], dtype=np.float64),
                vecs=np.ones((1, 2), dtype=np.float32),
            )
            with self.assertRaises(LegacyIngestError) as raised:
                load_legacy_archive(archive)
            self.assertEqual(raised.exception.code, "legacy_archive_missing_field")

    def test_missing_row_field_fails_named(self) -> None:
        from legacy_ingest import LegacyIngestError, load_legacy_archive

        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-missing-row-") as temp:
            archive = Path(temp) / "five-column-rows.npz"
            self._write_archive(
                archive,
                np.asarray([(0, 0, 0.0, 1.0, 1.0)], dtype=np.float64),
            )
            with self.assertRaises(LegacyIngestError) as raised:
                load_legacy_archive(archive)
            self.assertEqual(raised.exception.code, "legacy_row_schema_missing_field")

    def test_legacy_duration_is_reconciled_without_tolerance_change(self) -> None:
        from run_legacy_anchor_fidelity import replay_legacy_case

        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-duration-") as temp:
            root = Path(temp)
            reference = root / "reference.jsonl"
            archive = root / "legacy.npz"
            reference.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "start": 249.837337,
                                "end": 254.117564,
                                "speaker": "Alice",
                                "text": "one",
                            }
                        ),
                        json.dumps(
                            {
                                "start": 254.657593,
                                "end": 256.077668,
                                "speaker": "Alice",
                                "text": "two",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self._write_archive(
                archive,
                np.asarray(
                    [(0, 0, 252.337337, 255.377366, 2.5, 1)],
                    dtype=np.float64,
                ),
            )
            case = {
                "case_id": "tiny-duration-reconciliation",
                "duration_seconds": 256.1,
                "reference_path": str(reference),
                "split": "development",
            }
            config = json.loads((HERE / "l1-control-spec.json").read_text())["production_config"]
            result = replay_legacy_case(
                case,
                config,
                archive_path=archive,
                adapted_cache_path=root / "adapted.npz",
            )
            self.assertLessEqual(
                result["fixture_fidelity"]["max_duration_delta_seconds"],
                1.0 / config["sample_rate"],
            )

    def test_archived_unit_23_span_19_parses_and_reaches_assignment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-unit23-") as temp:
            result = self._replay_archived_alphabet(Path(temp) / "adapted.npz")
        span = next(item for item in result["span_trace"] if item["span_id"] == 19)
        self.assertEqual(span["status"], "prepared")
        self.assertNotEqual(span["diagnostics"].get("reason"), "unparseable_transcript")
        self.assertIsNotNone(result["live_unit_labels"][23])

    def test_all_92_archived_units_render_into_parseable_preparations(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-all92-") as temp:
            result = self._replay_archived_alphabet(Path(temp) / "adapted.npz")
        self.assertEqual(len(result["live_unit_labels"]), 92)
        trace_by_span = {item["span_id"]: item for item in result["span_trace"]}
        with np.load(ARCHIVED_ALPHABET_CACHE, allow_pickle=False) as payload:
            row_spans = payload["rows"][:, 0].astype(np.int64)
        self.assertEqual(len(row_spans), 92)
        for unit_index, span_id in enumerate(row_spans):
            with self.subTest(unit_index=unit_index, span_id=int(span_id)):
                trace = trace_by_span[int(span_id)]
                self.assertNotEqual(trace["diagnostics"].get("reason"), "unparseable_transcript")
                self.assertIn(trace["status"], ("prepared", "abstain"))

    def test_non_monotonic_row_bounds_fail_named(self) -> None:
        from legacy_ingest import LegacyIngestError, load_legacy_archive

        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-order-") as temp:
            archive = Path(temp) / "non-monotonic.npz"
            self._write_archive(
                archive,
                np.asarray(
                    [
                        (0, 0, 1.0, 2.0, 1.0, 1),
                        (1, 0, 0.5, 1.5, 1.0, 1),
                    ],
                    dtype=np.float64,
                ),
            )
            with self.assertRaises(LegacyIngestError) as raised:
                load_legacy_archive(archive)
            self.assertEqual(raised.exception.code, "legacy_row_bounds_non_monotonic")

    def test_span_reason_placeholder_does_not_change_score(self) -> None:
        from run_legacy_anchor_fidelity import replay_legacy_case

        with tempfile.TemporaryDirectory(prefix="moss-l2-legacy-reason-") as temp:
            root = Path(temp)
            reference = root / "reference.jsonl"
            archive = root / "legacy.npz"
            reference.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"start": 0.0, "end": 1.0, "speaker": "Alice", "text": "one"}
                        ),
                        json.dumps(
                            {"start": 1.5, "end": 2.5, "speaker": "Alice", "text": "two"}
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            np.savez(
                archive,
                rows=np.asarray(
                    [(0, 0, 0.0, 1.0, 1.0, 1), (1, 0, 1.5, 2.5, 1.0, 1)],
                    dtype=np.float64,
                ),
                vec_idx=np.asarray([0, 1], dtype=np.int64),
                vecs=np.asarray([(1.0, 0.0), (1.0, 0.0)], dtype=np.float32),
            )
            case = {
                "case_id": "tiny-reason-independence",
                "duration_seconds": 2.5,
                "reference_path": str(reference),
                "split": "development",
            }
            config = json.loads((HERE / "l1-control-spec.json").read_text())["production_config"]
            real = replay_legacy_case(
                case,
                config,
                archive_path=archive,
                adapted_cache_path=root / "real-reason.npz",
                span_reason="end_silence",
            )
            placeholder = replay_legacy_case(
                case,
                config,
                archive_path=archive,
                adapted_cache_path=root / "placeholder-reason.npz",
                span_reason="legacy_unavailable",
            )
            score_fields = (
                "changed_duration_fraction",
                "changed_speaker_seconds",
                "counts",
                "final_unit_labels",
                "live_metrics",
                "live_unit_labels",
                "metrics",
                "revision_trace",
            )
            self.assertEqual(
                {name: real[name] for name in score_fields},
                {name: placeholder[name] for name in score_fields},
            )
            self.assertEqual(real["metrics"]["speaker_accuracy"], 1.0)
            self.assertEqual(
                {item["reason"] for item in real["span_trace"]}, {"end_silence"}
            )
            self.assertEqual(
                {item["reason"] for item in placeholder["span_trace"]},
                {"legacy_unavailable"},
            )


if __name__ == "__main__":
    unittest.main()
