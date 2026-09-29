"""The scorecard must not charge metered output again as estimated output."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


CASES = (
    "mono_javier_intro_50s", "interview_bill_ackman_60s", "interview_keyu_jin_60s",
    "interview_adam_frank_180s", "discussion_jamie_dimon_180s", "discussion_rtfl_90s",
)


@pytest.mark.parametrize("has_metered_output", [True, False])
def test_scorecard_separates_metered_output_from_output_estimate(tmp_path: Path, has_metered_output):
    root = Path(__file__).resolve().parents[2]
    quality = tmp_path / "quality"
    rows, diagnostics = [], []
    for number in (1, 2):
        for case_id in CASES:
            rows.append({"case_id": case_id, "pass": number, "duration_seconds": 60,
                         "metrics": {"settled": {"der": .05}}})
            # Review F3 example: $0.002 metered input + $0.0012 metered output.
            usage = {"cost_usd": .0032, "output_cost_estimate_usd": .002}
            if has_metered_output:
                usage["metered_output_usd"] = .0012
            diagnostics.append({"case_id": case_id, "pass": number,
                                "engine_settings": {"speaker_window": "balanced", "cleanup_after_stop": False},
                                "engine_diagnostics": usage})
            manifest = quality / f"pass-{number}" / case_id / "replay-manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"descriptor": {"provider_name": "gemini-3.5-transcribe"}}))
    (quality / "content-free-metrics.json").write_text(json.dumps({"per_case": rows}))
    (quality / "engine-diagnostics.json").write_text(json.dumps({"cases": diagnostics}))
    output = tmp_path / "scorecard"
    subprocess.run([sys.executable, str(root / "prototypes/gemini-live/harness/round2_scorecard.py"),
                    "--quality", str(quality), "--out", str(output)], cwd=root, check=True,
                   capture_output=True, text=True)
    cost = json.loads((output / "scorecard.json").read_text())["gates"]["COST"]
    markdown = (output / "scorecard.md").read_text()
    assert cost["meeting_hours"] == pytest.approx(.2)
    assert cost["metered_usd"] == pytest.approx(.0384)
    assert cost["output_estimate_usd"] == pytest.approx(.024)
    if has_metered_output:
        assert cost["metered_input_usd"] == pytest.approx(.024)
        assert cost["metered_output_usd"] == pytest.approx(.0144)
        assert cost["with_output_estimate_usd_per_meeting_hour"] == pytest.approx(.24)
        assert cost["metered_output_status"] == "MEASURED"
        assert "Missing metered-output fields treated as $0: 0/12 cases." in markdown
    else:
        assert cost["metered_output_usd"] == 0
        assert cost["metered_output_status"] == "ASSUMED_ZERO"
        assert cost["with_output_estimate_usd_per_meeting_hour"] == pytest.approx(.312)
        assert "Missing metered-output fields treated as $0: 12/12 cases." in markdown

    (quality / "engine-diagnostics.json").unlink()
    output_without_meter = tmp_path / "scorecard-without-meter"
    subprocess.run([sys.executable, str(root / "prototypes/gemini-live/harness/round2_scorecard.py"),
                    "--quality", str(quality), "--out", str(output_without_meter)], cwd=root, check=True,
                   capture_output=True, text=True)
    without_meter = json.loads((output_without_meter / "scorecard.json").read_text())["gates"]["COST"]
    assert without_meter["status"] == "UNMEASURED"
    assert without_meter["with_output_estimate_usd_per_meeting_hour"] is None
