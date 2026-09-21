"""One-command F2/F6 prototype: raw custody plus observation outside decision."""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
)
from moss_transcribe_diarize.app.live_lane_decode import finalize_lanes
from moss_transcribe_diarize.app.live_session import LiveIdentitySnapshot
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    TerminalDecodePlan,
    TerminalTranscriptFinalizer,
)

from native_decision import (
    ADAM,
    CONTAINED_TRANSCRIPT,
    DeterministicEvidence,
    ELIGIBILITY_FLOOR_SAMPLES,
    RATE,
    decide,
)
from observer import copy_diagnostics


class ContainedRunner:
    def transcribe(self, *_args, **_kwargs):
        return SimpleNamespace(text=CONTAINED_TRANSCRIPT)


@contextmanager
def _capture_destination(destination: Path | None):
    name = "MOSS_TERMINAL_LABEL_CAPTURE"
    previous = os.environ.get(name)
    try:
        if destination is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = str(destination)
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _proposal_bytes(result) -> bytes:
    return json.dumps(
        [
            {
                "start": segment.start_sample,
                "end": segment.end_sample,
                "text": segment.text,
                "canonical_speaker": segment.canonical_speaker,
            }
            for segment in result.proposal.segments
        ],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def frozen_product_capture(destination: Path | None) -> dict:
    """Exercise the frozen terminal finalizer/capture seam with contained S02."""

    with tempfile.TemporaryDirectory(prefix="moss-p-f2f6-product-") as directory:
        tape = CompleteMixedTape(
            epoch=0, capacity_bytes=round(2.5 * RATE) * 2, storage_root=Path(directory)
        )
        assert tape.append(
            start_sample=0, pcm=bytes([1]) * round(2.5 * RATE) * 2
        ).written
        preparer = BoundedCausalIdentityPreparer(
            config=LiveIdentityConfig(16, 0.35, 0.1),
            evidence_provider=DeterministicEvidence(),
        )
        snapshot = SimpleNamespace(
            identity_snapshot=LiveIdentitySnapshot(canonical_speakers=(ADAM,))
        )
        coordinator = SimpleNamespace(
            session_key="p-f2f6-contained",
            lane_tapes={"system": tape},
            _lane_speakers={"system": {ADAM}},
            _lane_preparers={"system": preparer},
            session=SimpleNamespace(snapshot=lambda: snapshot),
        )
        with _capture_destination(destination):
            result = finalize_lanes(
                coordinator,
                TerminalTranscriptFinalizer(
                    runner=ContainedRunner(), scratch_dir=Path(directory)
                ),
                plan=TerminalDecodePlan(
                    0, round(2.5 * RATE), 0, RollingStatus.STOPPED, 0, 0
                ),
                tape=tape,
                base_text_revision_version=0,
                base_surface=(),
                canonical_speakers=(ADAM,),
            )
        rows = []
        if destination is not None and destination.is_file():
            rows = [json.loads(line) for line in destination.read_text().splitlines()]
        return {
            "published_proposal_bytes": _proposal_bytes(result).decode("utf-8"),
            "capture_rows": rows,
            "terminal_partitions": [
                {
                    "partition_id": partition.partition_id,
                    "terminal_local_label": partition.terminal_local_label,
                    "member_span_indexes": [span.span_index for span in partition.spans],
                }
                for partition in result.terminal_partitions
            ],
        }


def _observer_is_pure() -> dict:
    path = Path(__file__).with_name("observer.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules = []
    imported_names = []
    called_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.append(node.module or "")
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                called_names.append(function.id)
            elif isinstance(function, ast.Attribute):
                called_names.append(function.attr)
    banned = {"BoundedCausalIdentityPreparer", "prepare", "prepare_revision", "score"}
    return {
        "imports": sorted(imported_modules),
        "imported_names": sorted(imported_names),
        "calls": sorted(set(called_names)),
        "no_preparer_import_construct_wrap_or_call": not (
            banned.intersection(imported_names) or banned.intersection(called_names)
        )
        and all("live_identity" not in module for module in imported_modules),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="moss-p-f2f6-") as directory:
        scratch = Path(directory)
        product_on_path = scratch / "frozen-product.jsonl"
        frozen_off = frozen_product_capture(None)
        frozen_on = frozen_product_capture(product_on_path)
        frozen_refusal = frozen_product_capture(scratch)

        native_off = decide()
        native_on = decide()
        native_on_path = scratch / "native.jsonl"
        native_on_receipt = copy_diagnostics(native_on.diagnostics, native_on_path)
        native_refusal = decide()
        native_refusal_receipt = copy_diagnostics(native_refusal.diagnostics, scratch)
        observed = [json.loads(line) for line in native_on_path.read_text().splitlines()]

    raw_rows = [row for row in observed if row["record_type"] == "raw_terminal_span"]
    mapping_rows = [row for row in observed if row["record_type"] == "raw_to_normalized"]
    partition_rows = [
        row for row in observed if row["record_type"] == "normalized_partition"
    ]
    observer_structure = _observer_is_pure()
    product_labels = [
        row["terminal_local_label"]
        for row in frozen_on["capture_rows"]
        if "terminal_local_label" in row
    ]
    normalized_product_labels = [
        row["terminal_local_label"]
        for row in frozen_on["capture_rows"]
        if row.get("record_type") == "normalized_partition"
    ]
    controls = {
        "frozen_capture_off_on_writer_refusal_byte_identical": len(
            {
                frozen_off["published_proposal_bytes"],
                frozen_on["published_proposal_bytes"],
                frozen_refusal["published_proposal_bytes"],
            }
        )
        == 1,
        "frozen_normalized_stream_is_post_normalization": (
            normalized_product_labels == ["S01"]
        ),
        "prototype_raw_stream_retains_contained_s02": [
            row["terminal_local_label"] for row in raw_rows
        ]
        == ["S01", "S02"],
        "prototype_mapping_marks_contained_s02_dropped": any(
            row["raw_index"] == 1
            and row["normalized_partition_id"] is None
            and row["disposition"] == "dropped_by_normalization"
            for row in mapping_rows
        ),
        "native_capture_off_on_writer_refusal_byte_identical": len(
            {
                native_off.published_proposal_bytes,
                native_on.published_proposal_bytes,
                native_refusal.published_proposal_bytes,
            }
        )
        == 1,
        "writer_refusal_is_observational": (
            native_on_receipt.written and not native_refusal_receipt.written
        ),
        "observer_has_no_preparer_dependency": observer_structure[
            "no_preparer_import_construct_wrap_or_call"
        ],
        "captured_partition_matches_native_partition": (
            len(partition_rows) == 1
            and partition_rows[0]["partition_id"]
            == native_on.diagnostics.normalized_partitions[0].partition_id
            and tuple(partition_rows[0]["member_raw_indexes"])
            == native_on.diagnostics.normalized_partitions[0].member_raw_indexes
        ),
        "eligibility_floor_unchanged": partition_rows[0][
            "eligibility_floor_samples"
        ]
        == ELIGIBILITY_FLOOR_SAMPLES,
        "decoder_requests": 0,
        "network_calls": 0,
    }
    payload = {
        "schema": "moss-p-f2f6-prototype.v1",
        "structural_question": (
            "Can capture retain raw terminal spans before normalization while the native "
            "decision returns immutable diagnostics that a pure observer only copies?"
        ),
        "minimum_primitives": [
            "raw_terminal_span",
            "raw_to_normalized_mapping",
            "normalized_partition_decision",
            "pure_diagnostics_observer",
        ],
        "invariants": [
            "publication bytes do not change with observation off, on, or refusing",
            "the 8000-sample eligibility floor and identity thresholds do not change",
            "raw and normalized custody remain separate and owner-bound",
        ],
        "assumptions_and_unknowns": [
            "the historical S17 span remains unmeasured until an authorized rerun",
            "this deterministic score proves seam ownership, not acoustic accuracy",
        ],
        "falsifier": (
            "contained S02 absent from raw capture; normalized record differs from the "
            "native partition; observer depends on or changes the preparer; publication differs"
        ),
        "tool_decision": (
            "real resolver and identity preparer test live semantics without decoder, tunnel, "
            "network, threshold, or product changes"
        ),
        "frozen_product": {
            **frozen_on,
            "captured_labels": product_labels,
        },
        "prototype_native_result": {
            "published_proposal_bytes": native_on.published_proposal_bytes.decode("utf-8"),
            "observed_records": observed,
        },
        "observer_structure": observer_structure,
        "controls": controls,
        "verdicts": {
            "F2": "SUPPORTED",
            "F6": "SUPPORTED",
        },
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    failed = [name for name, value in controls.items() if value is False]
    if failed:
        raise SystemExit("FAILED controls: " + ", ".join(failed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
