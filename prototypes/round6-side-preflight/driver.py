#!/usr/bin/env python3
"""THROWAWAY: selected production predicates on an isolated side Account app.

The shell guard must first establish that capacity telemetry is side-scoped.
This program retains numeric results only. It never prints cookie contents.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import traceback
from pathlib import Path

import httpx

from moss_transcribe_diarize.phase2_acceptance_external import FixedAccountCampaign
from moss_transcribe_diarize.phase2_acceptance_setup import _bootstrap, _private_once
from moss_transcribe_diarize.phase2_acceptance_replay import ACCEPTANCE_STOP_DEADLINE_SECONDS
from moss_transcribe_diarize.phase2_acceptance import _validate_overload, _validate_quality
from moss_transcribe_diarize.phase2_acceptance_completion import validate_completion_observation


def _metrics(url: str) -> int:
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    values = []
    for line in response.text.splitlines():
        if line.startswith("vllm:request_success_total{") or line.startswith("vllm:request_success_total "):
            values.append(int(float(line.rsplit(" ", 1)[1])))
    if not values:
        raise RuntimeError("request_success_total absent from decoder metrics")
    return sum(values)


def _provision(origin: str, private: Path, config: dict) -> dict:
    private.mkdir(mode=0o700)
    with httpx.Client(base_url=origin, timeout=30, follow_redirects=False) as client:
        owners = set()
        for role in ("a", "b"):
            owner, credential = _bootstrap(client)
            if owner in owners:
                raise RuntimeError("side workspaces merged")
            owners.add(owner)
            cookie = private / f"account-{role}.cookie"
            _private_once(cookie, credential.encode())
            config[f"account_{role}_cookie_file"] = str(cookie)
            config[f"account_{role}_peer_cookie_file"] = str(cookie)
            sentinel = private / f"account-{role}.sentinel"
            _private_once(sentinel, f"moss-side-{role}-{secrets.token_urlsafe(24)}".encode())
            config[f"account_{role}_sentinel_file"] = str(sentinel)
    return config


def _prepare_g9(campaign: FixedAccountCampaign) -> None:
    """Use the production Live seam to create G9's named Wave-2 source."""
    meeting = campaign._new_live_id("a")
    campaign._seed_live_transcript("a", meeting, 0)
    record, _ = campaign.a.json("GET", f"/api/meetings/{meeting}", 200)
    speaker = next(
        row["speaker_entity_id"] for row in record["transcript"]["segments"]
        if row.get("speaker_entity_id")
    )
    campaign.a.json(
        "PUT", f"/api/meetings/{meeting}/speakers/{speaker}/name", 200,
        json={"label": "Qualification speaker"},
    )
    campaign.a.json("POST", f"/api/live/sessions/{meeting}/stop", 200,
                    json={"deadline": ACCEPTANCE_STOP_DEADLINE_SECONDS})
    campaign._summary_voiceprint_meeting = meeting


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    work = args.work.resolve()
    config = json.loads(args.profile.read_text())["measurements"]["deployed"].copy()
    config.update({"https_origin": args.origin, "repo_root": str(args.repo.resolve()),
                   "campaign_work_dir": str(work / "campaign"),
                   "operator_socket": str(work / "control.sock"),
                   "web_unit": "moss-r6-side.service",
                   "vllm_unit": "moss-vllm.service"})
    config = _provision(args.origin, work / "private", config)
    campaign = FixedAccountCampaign(candidate_sha=args.sha, config=config)
    metrics_url = str(config["vllm_metrics_url"])
    summary = {"schema": "side-preflight.v1", "sha": args.sha,
               "origin": args.origin, "quality_passes": 2, "predicates": {}}
    try:
        for name in ("browser_final_summary", "excess_admission_overload", "quality_corpus"):
            before = _metrics(metrics_url)
            row = {"requests_before": before}
            try:
                if name == "browser_final_summary":
                    _prepare_g9(campaign)
                raw = getattr(campaign, name)()
                row["state"] = "executed"
                row["validator_pass"] = (
                    validate_completion_observation(name, raw)
                    if name == "browser_final_summary" else
                    _validate_overload({"raw": raw})
                    if name == "excess_admission_overload" else
                    _validate_quality({"raw": raw})
                )
                if name in {"browser_final_summary", "excess_admission_overload"}:
                    observed = (raw.get("capacity") or {}).get("journal_sources") if name == "browser_final_summary" else raw.get("journal_sources")
                    row["journal_sources"] = observed
                    row["telemetry_scoped"] = (
                        isinstance(observed, list) and len(observed) == 2
                        and all(isinstance(item, dict) for item in observed)
                        and {item.get("unit") for item in observed}
                        == {"moss-r6-side.service", "moss-vllm.service"}
                        and all(item.get("source") == "systemd-user-journal" and
                                item.get("read_succeeded") is True for item in observed)
                    )
                if name == "quality_corpus":
                    row["macro"] = raw.get("macro")
                    row["case_count"] = len(raw.get("per_case", []))
                elif name == "browser_final_summary":
                    row["checks"] = raw.get("checks")
                else:
                    row["sessions"] = raw.get("sessions")
                    row["backpressure"] = raw.get("backpressure_observation")
            except Exception as exc:
                last = traceback.extract_tb(exc.__traceback__)[-1]
                row.update({"state": "failed", "error_type": type(exc).__name__,
                            "error_at": f"{Path(last.filename).name}:{last.lineno}"})
            row["requests_after"] = _metrics(metrics_url)
            row["decoder_requests"] = row["requests_after"] - before
            summary["predicates"][name] = row
            (work / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    finally:
        campaign.close()
    return 0 if all(row["state"] == "executed" and row["validator_pass"] is True
                    and row.get("telemetry_scoped", True) is True
                    for row in summary["predicates"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
