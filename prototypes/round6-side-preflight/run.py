#!/usr/bin/env python3
"""THROWAWAY: fail-closed side-instance predicate preflight.

One command prints the complete current feasibility state; no service is started.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from moss_transcribe_diarize import phase2_acceptance_external as external
from moss_transcribe_diarize import phase2_acceptance_setup as setup
from moss_transcribe_diarize import phase2_acceptance_summary as summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--staged", action="store_true", help="package is installed outside the SHA-matched checkout")
    args = parser.parse_args()
    repo = args.repo.resolve()
    lines = {
        "repo": str(repo),
        "package": str(Path(external.__file__).resolve()),
        "setup": str(Path(setup.__file__).resolve()),
        "summary": str(Path(summary.__file__).resolve()),
        "same_checkout": repo in Path(external.__file__).resolve().parents,
        "production_bootstrap": hasattr(setup, "_bootstrap"),
        "production_campaign": hasattr(external, "FixedAccountCampaign"),
        "target_methods": [
            name for name in (
                "browser_final_summary", "excess_admission_overload", "quality_corpus"
            ) if hasattr(external.FixedAccountCampaign, name)
        ],
        "side_unit_supported": False,
        "g9_prerequisite_needed": False,
        "driver_prepares_g9": False,
        "quality_single_pass_supported": False,
    }
    source = (repo / "moss_transcribe_diarize/phase2_acceptance_external.py").read_text()
    quality = source.split("    def quality_corpus(", 1)[1].split("    def two_session_capacity(", 1)[0]
    load = source.split("    def _run_live_load(", 1)[1].split("    def _", 1)[0]
    lines["side_unit_supported"] = (
        "web_pid = _unit_pid(web_unit)" in load
        and '"server_log": self._journal_window(web_unit)' in load
        and 'vllm_pid = _unit_pid("moss-vllm.service")' in load
    )
    lines["g9_prerequisite_needed"] = "_summary_voiceprint_meeting" in (
        repo / "moss_transcribe_diarize/phase2_acceptance_summary.py"
    ).read_text()
    lines["driver_prepares_g9"] = "_prepare_g9(campaign)" in (
        Path(__file__).with_name("driver.py")
    ).read_text()
    lines["quality_single_pass_supported"] = "for pass_number in (1, 2):" not in quality
    print(json.dumps(lines, indent=2, sort_keys=True))
    return 0 if all((lines["same_checkout"] or args.staged,
                     lines["side_unit_supported"], lines["driver_prepares_g9"])) else 2


if __name__ == "__main__":
    raise SystemExit(main())
