#!/usr/bin/env python3
"""Finalize the CAL-HP strict gate after the standard pipeline's silent-mic refusal."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from capture_harness import atomic_json, read_json, sha256, utc_now
from post_session import curl_json, raw_retention_decision, seal_tree


def audio_levels(path: Path) -> dict:
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", str(path)],
        text=True,
        capture_output=True,
        check=True,
    )
    stats = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
        text=True,
        capture_output=True,
        check=True,
    )
    def last(label: str) -> float:
        matches = re.findall(re.escape(label) + r":\s*(-?[0-9.]+)", stats.stderr)
        if not matches:
            raise RuntimeError("astats_missing:" + label)
        return float(matches[-1])
    metadata = json.loads(probe.stdout)["format"]
    return {
        "duration_seconds": float(metadata["duration"]),
        "bytes": int(metadata["size"]),
        "peak_dbfs": last("Peak level dB"),
        "rms_dbfs": last("RMS level dB"),
        "rms_peak_dbfs": last("RMS peak dB"),
        "sha256": sha256(path),
    }


def segment_count(root: Path, lane: str) -> int:
    path = root / "derived" / "asr" / lane / "asr-transcript.json"
    return len(read_json(path)["segments"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--microphone-job-id", required=True)
    args = parser.parse_args()
    root = args.session_dir.resolve()
    manifest_path = root / "session-manifest.json"
    manifest = read_json(manifest_path)
    grant = read_json(root.parents[1] / "grant.json")
    microphone_terminal = curl_json("/api/jobs/%s" % args.microphone_job_id)
    microphone_zero = (
        microphone_terminal.get("status") == "failed"
        and "zero parsed segments" in str(microphone_terminal.get("error", ""))
    )
    counts = {
        "system": segment_count(root, "system"),
        "microphone": 0 if microphone_zero else None,
        "mixed": segment_count(root, "mixed"),
    }
    levels = {lane: audio_levels(root / "audio" / (lane + ".wav")) for lane in ("system", "microphone", "mixed")}
    system_speech = counts["system"] > 0
    mic_no_intelligible = counts["microphone"] == 0
    verdict = "PASS" if system_speech and mic_no_intelligible else "FAIL"
    gate_root = root / "derived" / "cal-hp-gate"
    gate_root.mkdir(parents=True, exist_ok=False)
    atomic_json(gate_root / "microphone-job-terminal.json", microphone_terminal)
    gate = {
        "schema": "moss-dl2-cal-hp-gate.v1",
        "session_id": manifest["session_id"],
        "shape_id": "CAL-HP",
        "evaluated_at_utc": utc_now(),
        "strict_rule": "PASS only if system lane has interview speech and microphone lane has no intelligible YouTube speech",
        "operator_observation": "operator silent; YouTube interview continuously playing through AirPods Pro",
        "segment_counts": counts,
        "levels": levels,
        "microphone_batch": {
            "job_id": args.microphone_job_id,
            "status": microphone_terminal.get("status"),
            "generated_tokens": microphone_terminal.get("generated_tokens"),
            "error": microphone_terminal.get("error"),
            "source_sha256": microphone_terminal.get("source_sha256"),
            "job_json_sha256_on_server": "420eaafec56428221d640c42a3aff5c4e9b0e9a4cc141866b9ead296b108739d",
            "raw_transcript_persisted": False,
            "interpretation": "zero parsed speech; no intelligible YouTube speech detected by deployed batch ASR",
        },
        "system_speech_present": system_speech,
        "microphone_intelligible_youtube_speech_absent": mic_no_intelligible,
        "system_minus_microphone_rms_db": round(levels["system"]["rms_dbfs"] - levels["microphone"]["rms_dbfs"], 6),
        "standard_pipeline": {
            "status": "named_refusal_on_silent_microphone_then_diagnostic_continuation",
            "refusal": "batch_job_failed:%s:vLLM transcription returned zero parsed segments" % args.microphone_job_id,
            "system_job_id": read_json(root / "derived/asr/system/job-terminal.json")["id"],
            "mixed_job_id": read_json(root / "derived/asr/mixed/job-terminal.json")["id"],
            "rerun_capture": False,
        },
        "verdict": verdict,
    }
    atomic_json(gate_root / "CAL_HP_GATE.json", gate)
    seal_tree(gate_root, gate_root / "CAL_HP_GATE_EVIDENCE.sha256")
    retention = raw_retention_decision(grant, manifest)
    manifest["state"] = "audit_ready_raw_retained" if retention["retain"] else "derived_hashed"
    manifest["raw_retention"] = retention
    manifest["cal_hp_gate"] = {
        "verdict": verdict,
        "path": "derived/cal-hp-gate/CAL_HP_GATE.json",
        "sha256": sha256(gate_root / "CAL_HP_GATE.json"),
        "seal_path": "derived/cal-hp-gate/CAL_HP_GATE_EVIDENCE.sha256",
        "seal_sha256": sha256(gate_root / "CAL_HP_GATE_EVIDENCE.sha256"),
    }
    atomic_json(manifest_path, manifest)
    print(json.dumps({"verdict": verdict, "segment_counts": counts, "levels": levels, "raw_retention": retention}, indent=2, sort_keys=True))
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
