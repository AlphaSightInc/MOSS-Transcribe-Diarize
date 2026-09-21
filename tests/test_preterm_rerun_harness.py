"""Offline receipt controls for R4-10's pre-terminal rerun harness."""
from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "prototypes/preterm-rerun/run.py"
SPEC = importlib.util.spec_from_file_location("r4_preterm_harness", HARNESS_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)
EVIDENCE = ROOT / "evidence/round4/overlap"


def _layer(text: str, lane: str) -> list[dict[str, str]]:
    return [{"source_lane": lane, "text": text}]


def _score(reference: dict, text: str, lane: str, audit=None):
    paths = {"raw": f"raw-{lane}.json", "canonical": f"canonical-{lane}.json",
             "published": f"published-{lane}.json", "reference": f"reference-{lane}.jsonl"}
    return harness.score_layers(
        reference=reference,
        raw={"windows": [{"response": {"text": text}}]},
        canonical=_layer(text, lane), published=_layer(text, lane), lane=lane,
        paths=paths, reference_audit=audit,
    )


def test_receipt_scorer_reproduces_retained_final_attributions() -> None:
    retained = json.loads((EVIDENCE / "retained-acceptance-surfaces.json").read_text())
    attribution = json.loads((EVIDENCE / "attribution-alternation.json").read_text())
    system_reference = json.loads((EVIDENCE / "bill-reference-source.jsonl").read_text())
    microphone_reference = json.loads((ROOT / "tests/e2e/fixtures/lane-microphone-reference.json").read_text())
    audit = {
        (row["operation"], row["reference_word"], row["hypothesis_word"]): row["class"]
        for row in attribution["rows"]
        if row["case"] == "alternation" and row["lane"] == "system" and row["class"] == "d"
    }
    alternate_system = _score(system_reference, retained["cases"]["alternation"]["final"]["system"]["text"], "system", audit)
    alternate_microphone = _score(microphone_reference, retained["cases"]["alternation"]["final"]["microphone"]["text"], "microphone")
    overlap_microphone = _score(microphone_reference, retained["cases"]["overlap"]["final"]["microphone"]["text"], "microphone")
    assert Counter(row["class"] for row in alternate_system) == {"a": 2, "d": 7}
    assert Counter(row["class"] for row in alternate_microphone) == {"a": 5}
    assert Counter(row["class"] for row in overlap_microphone) == {"a": 5}
    assert [row["class"] for row in alternate_system + alternate_microphone + overlap_microphone] == [
        row["class"] for row in attribution["rows"]
    ]


def test_plan_only_reports_missing_runtime_corrected_reference_without_dispatch() -> None:
    receipt_plan = harness.plan()
    # This pinned prep clone intentionally predates D27's fixture merge.  A later run reads
    # the fixture then present; it may plan, but must refuse execution while it is absent.
    assert receipt_plan["corrected_reference"] == {"status": "MISSING", "missing_lanes": ["system"]}
    assert receipt_plan["planned_requests"] == 56
    assert [(row["case"], row["lane"], row["planned_requests"]) for row in receipt_plan["population"]["arms"]] == [
        ("alternation", "system", 15), ("alternation", "microphone", 13),
        ("overlap", "system", 15), ("overlap", "microphone", 13),
    ]
