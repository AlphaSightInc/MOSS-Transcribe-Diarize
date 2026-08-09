#!/usr/bin/env python3
"""Append already-committed system prefix windows so S05 ASR covers the whole card."""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from capture_harness import HarnessRefusal, atomic_json, read_json, sha256, utc_now
from post_session import bleed_rate_for_packet, render_html, seal_tree, triangulate

_PARSER_PATH = Path(__file__).resolve().parents[3] / "moss_transcribe_diarize" / "transcript_parser.py"
_PARSER_SPEC = importlib.util.spec_from_file_location("moss_transcript_parser_standalone", _PARSER_PATH)
if _PARSER_SPEC is None or _PARSER_SPEC.loader is None:
    raise RuntimeError("Could not load production transcript parser")
_PARSER = importlib.util.module_from_spec(_PARSER_SPEC)
sys.modules[_PARSER_SPEC.name] = _PARSER
_PARSER_SPEC.loader.exec_module(_PARSER)
parse_transcript = _PARSER.parse_transcript


HOST = "gyauo@ga0-alienware-rtx4070ti.local"


def fetch_record(root: str, name: str, expected_sha: str) -> bytes:
    remote = f"{root}/windows/{name}"
    script = "set -euo pipefail\nsha256sum %s\nbase64 -w0 %s\nprintf '\\n'\n" % (remote, remote)
    completed = subprocess.run(
        ["ssh", HOST, "wsl.exe -d Ubuntu -- bash -s"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise HarnessRefusal("s05_prefix_fetch_failed:" + completed.stderr.strip())
    lines = completed.stdout.splitlines()
    if len(lines) != 2 or lines[0].split()[0] != expected_sha:
        raise HarnessRefusal("s05_prefix_remote_hash_mismatch:" + name)
    payload = base64.b64decode(lines[1], validate=True)
    import hashlib
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        raise HarnessRefusal("s05_prefix_local_hash_mismatch:" + name)
    return payload


def parsed_owned(record: dict[str, Any], lower: float, upper: float) -> list[dict[str, Any]]:
    start = float(record["plan"]["start_us"]) / 1_000_000.0
    output = []
    for segment in parse_transcript(record["raw_result"]["text"]):
        left, right = start + float(segment.start), start + float(segment.end)
        midpoint = (left + right) / 2.0
        if lower <= midpoint < upper:
            output.append({"start": round(left, 6), "end": round(right, 6), "speaker": segment.speaker, "text": segment.text})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    session = args.session_dir.resolve()
    plan = read_json(args.plan)
    manifest_path = session / "session-manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("session_id") != plan.get("session_id") or manifest.get("state") != "audit_ready_raw_retained":
        raise HarnessRefusal("s05_prefix_session_state_refused")
    source = session / "derived"
    archive = session / "derived-recovery-v1-system-through-360"
    if not source.is_dir() or archive.exists():
        raise HarnessRefusal("s05_prefix_source_missing_or_archived")
    source.rename(archive)
    shutil.copytree(archive, source)
    old_seal = source / "DERIVED_EVIDENCE.sha256"
    old_seal.unlink()

    raw_root = source / "recovery" / "system-prefix-records"
    raw_root.mkdir()
    supplement = []
    for item in plan["records"]:
        payload = fetch_record(plan["read_only_checkpoint_root"], item["name"], item["sha256"])
        path = raw_root / item["name"]
        path.write_bytes(payload)
        record = json.loads(payload)
        lower, upper = map(float, item["keep_midpoint_tape_seconds"])
        owned = parsed_owned(record, lower, upper)
        if not owned:
            raise HarnessRefusal("s05_prefix_owned_segments_empty:" + item["name"])
        supplement.extend(owned)
    atomic_json(source / "recovery" / "system-prefix-supplement-plan.json", plan)

    transcript_path = source / "asr/system/asr-transcript.json"
    transcript = read_json(transcript_path)
    base_segments = [item for item in transcript["segments"] if (float(item["start"]) + float(item["end"])) / 2.0 < 360.0]
    combined = base_segments + supplement
    combined.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    for index, item in enumerate(combined, 1):
        item["id"] = f"seg_{index:04d}"
    atomic_json(transcript_path, {"segments": combined})
    (source / "asr/system/asr-text.txt").write_text(" ".join(item["text"].strip() for item in combined if item["text"].strip()) + "\n", encoding="utf-8")
    terminal_path = source / "asr/system/job-terminal.json"
    terminal = read_json(terminal_path)
    terminal["prefix_supplement"] = {
        "source_job_id": plan["source_job_id"],
        "record_count": len(plan["records"]),
        "added_segment_count": len(supplement),
        "inference_rerun": False,
        "plan_sha256": sha256(args.plan),
    }
    atomic_json(terminal_path, terminal)

    packet = source / "audit-packet"
    rows = triangulate(source / "asr")
    bleed = bleed_rate_for_packet(manifest)
    atomic_json(packet / "audit-rows.json", {"schema": "moss-dl2-audit-rows.v1", "session_id": manifest["session_id"], "bleed_rate": bleed, "rows": rows})
    (packet / "audit-rows.html").write_text(render_html(rows, manifest["session_id"], bleed), encoding="utf-8")
    provenance_path = source / "provenance.json"
    provenance = read_json(provenance_path)
    provenance["system_prefix_supplement"] = {
        "plan_path": "derived/recovery/system-prefix-supplement-plan.json",
        "plan_sha256": sha256(args.plan),
        "source_job_id": plan["source_job_id"],
        "added_segment_count": len(supplement),
        "inference_rerun": False,
        "completed_at_utc": utc_now(),
    }
    provenance["audit_row_count"] = len(rows)
    provenance["target_listen_row_count"] = sum(bool(row["target_listen"]) for row in rows)
    for record in provenance["tracks"]:
        if record["track"] == "system":
            record["segment_count"] = len(combined)
            record["transcript_sha256"] = sha256(transcript_path)
            record["text_sha256"] = sha256(source / "asr/system/asr-text.txt")
            record["terminal_sha256"] = sha256(terminal_path)
    atomic_json(provenance_path, provenance)
    seal_path = source / "DERIVED_EVIDENCE_V2.sha256"
    seal_tree(source, seal_path)

    manifest.setdefault("derived_history", []).append({
        "reason": "system transcript covered tape 60-360 before reuse of already-committed full-track prefix records",
        "path": archive.name,
        "seal_path": archive.name + "/DERIVED_EVIDENCE.sha256",
        "seal_sha256": sha256(archive / "DERIVED_EVIDENCE.sha256"),
    })
    manifest["derived"].update({
        "provenance_sha256": sha256(provenance_path),
        "audit_rows_sha256": sha256(packet / "audit-rows.json"),
        "audit_html_sha256": sha256(packet / "audit-rows.html"),
        "seal_path": "derived/DERIVED_EVIDENCE_V2.sha256",
        "seal_sha256": sha256(seal_path),
    })
    manifest["system_prefix_supplement"] = {
        "plan_path": "../../../s05-system-prefix-supplement.json",
        "plan_sha256": sha256(args.plan),
        "source_job_id": plan["source_job_id"],
        "added_segment_count": len(supplement),
        "inference_rerun": False,
    }
    atomic_json(manifest_path, manifest)
    print(json.dumps({"ok": True, "added_segments": len(supplement), "system_segments": len(combined), "audit_rows": len(rows), "seal_sha256": sha256(seal_path)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
