"""R4-10 pre-terminal rerun receipt harness.

The only authorised command for this preparation slice is::

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/preterm-rerun/run.py \
    --plan-only --out evidence/round4/preterm/plan.json

``--run`` is reserved for the frozen, budgeted R4-10 pass.  It starts the
production app through ``stack.py``, retains every required layer, and refuses
to dispatch when the audited D27 reference/cut is not present or the budget is
too small.  It never falls back to the historical reference.
"""
from __future__ import annotations

import argparse
import array
import base64
import json
import math
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.lane_word_oracle import distance, words
from tests.e2e.verify_demo_lanes import (  # Production corpus/cut seam, read only.
    DEFAULT_MIC_GAIN,
    MICROPHONE_VOICE,
    SHARED_TAB_VOICE,
    Client,
)
from tools.qualify.run import MEASURED_REQUEST_RATE, MEASURED_REQUEST_RATE_UNIT


ARMS = (
    ("alternation", "system"),
    ("alternation", "microphone"),
    ("overlap", "system"),
    ("overlap", "microphone"),
)
PROPOSAL = ROOT / "evidence/round4/overlap/reference-correction-proposal.json"


def _read_row(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"reference has no rows: {path}")
    # The production acceptance seam deliberately selects the first source interval.
    # Retain that selection instead of claiming the corpus is a one-row file.
    return rows[0]


def corrected_references() -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Read the run-time fixture; never inject the proposal as a replacement."""
    proposal = json.loads(PROPOSAL.read_text())["proposals"]
    actual = {
        "system": _read_row(SHARED_TAB_VOICE.with_name("reference.jsonl")),
        "microphone": json.loads(
            (ROOT / "tests/e2e/fixtures/lane-microphone-reference.json").read_text()
        ),
    }
    wanted = {
        "system": proposal["alternation_system_29s"],
        "microphone": proposal["keyu_microphone_0_25_source_corpus"],
    }
    missing = [
        lane
        for lane in wanted
        if (actual[lane].get("start"), actual[lane].get("end"), words(actual[lane].get("text", "")))
        != (wanted[lane]["start"], wanted[lane]["end"], words(wanted[lane]["text"]))
    ]
    return actual, missing


def cut_geometry(references: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The exact PCM intervals fed to the live-frame route."""
    lanes = {}
    for lane, source in (("system", SHARED_TAB_VOICE), ("microphone", MICROPHONE_VOICE)):
        row = references[lane]
        with wave.open(str(source)) as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
                raise ValueError(f"unsupported corpus PCM geometry: {source}")
            start = round(float(row["start"]) * 16000)
            end = round(float(row["end"]) * 16000)
            if not 0 <= start < end <= audio.getnframes():
                raise ValueError(f"reference interval is outside corpus audio: {lane}")
        lanes[lane] = {
            "source": str(source), "sample_rate": 16000, "start_sample": start,
            "end_sample": end, "sample_count": end - start,
            "seconds": (end - start) / 16000,
            "microphone_gain": DEFAULT_MIC_GAIN if lane == "microphone" else 1.0,
        }
    return {"schema": "moss-r4-preterm-cut-geometry.v1", "lanes": lanes}


def plan() -> dict[str, Any]:
    references, missing = corrected_references()
    geometry = cut_geometry(references)
    arms = []
    for case, lane in ARMS:
        seconds = geometry["lanes"][lane]["seconds"]
        estimate = math.ceil(seconds * MEASURED_REQUEST_RATE)
        arms.append({
            "case": case, "lane": lane, "lane_seconds": seconds,
            "lanes_per_session": 2,
            "measured_request_rate": MEASURED_REQUEST_RATE,
            "measured_request_rate_unit": MEASURED_REQUEST_RATE_UNIT,
            "planned_requests": estimate,
            "calculation": f"ceil({seconds:g} lane_seconds * {MEASURED_REQUEST_RATE:g} {MEASURED_REQUEST_RATE_UNIT})",
        })
    return {
        "schema": "moss-r4-preterm-plan.v1",
        "population": {"cases": ["alternation", "overlap"], "arms": arms,
                       "lane_seconds": sum(a["lane_seconds"] for a in arms)},
        "planned_requests": sum(a["planned_requests"] for a in arms),
        "corrected_reference": {"status": "READY" if not missing else "MISSING", "missing_lanes": missing},
        "cut_geometry": geometry,
    }


def _segments(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, dict):
        document = document.get("segments") or document.get("parsed_segments") or []
    if not isinstance(document, list):
        raise ValueError("receipt transcript must be a segment list or a {segments: [...]} object")
    return [dict(row) for row in document if isinstance(row, dict)]


def _layer_words(document: Any, lane: str) -> list[str]:
    return words(" ".join(
        str(row.get("text", "")) for row in _segments(document)
        if row.get("source_lane", lane) == lane
    ))


def _raw_words(document: dict[str, Any]) -> list[str]:
    parts = []
    for window in document.get("windows", []):
        response = window.get("response", window)
        if isinstance(response, dict):
            parts.append(str(response.get("text", "")))
    return words(" ".join(parts))


def _alignment(reference: list[str], hypothesis: list[str]) -> list[dict[str, Any]]:
    """Stable backtrace, asserted below against production ``distance``."""
    costs = [[0] * (len(hypothesis) + 1) for _ in range(len(reference) + 1)]
    parents: list[list[tuple[int, int, str] | None]] = [
        [None] * (len(hypothesis) + 1) for _ in range(len(reference) + 1)
    ]
    for i in range(1, len(reference) + 1):
        costs[i][0], parents[i][0] = i, (i - 1, 0, "omission")
    for j in range(1, len(hypothesis) + 1):
        costs[0][j], parents[0][j] = j, (0, j - 1, "addition")
    for i, left in enumerate(reference, 1):
        for j, right in enumerate(hypothesis, 1):
            if left == right:
                costs[i][j], parents[i][j] = costs[i - 1][j - 1], (i - 1, j - 1, "match")
            else:
                options = ((costs[i - 1][j - 1] + 1, i - 1, j - 1, "substitution"),
                           (costs[i - 1][j] + 1, i - 1, j, "omission"),
                           (costs[i][j - 1] + 1, i, j - 1, "addition"))
                _, previous_i, previous_j, operation = min(options)
                costs[i][j], parents[i][j] = min(options)[0], (previous_i, previous_j, operation)
    result = []
    i, j = len(reference), len(hypothesis)
    while i or j:
        previous_i, previous_j, operation = parents[i][j]  # type: ignore[misc]
        result.append({"operation": operation,
                       "reference_index": i - 1 if i != previous_i else None,
                       "hypothesis_index": j - 1 if j != previous_j else None,
                       "reference_word": reference[i - 1] if i != previous_i else None,
                       "hypothesis_word": hypothesis[j - 1] if j != previous_j else None})
        i, j = previous_i, previous_j
    return list(reversed(result))


def score_layers(*, reference: dict[str, Any], raw: dict[str, Any], canonical: Any,
                 published: Any, lane: str, paths: dict[str, str], reference_audit: dict[tuple, str] | None = None) -> list[dict[str, Any]]:
    """Classify every final edit at its first evidenced layer, or refuse the receipt."""
    reference_words, raw_words = words(reference["text"]), _raw_words(raw)
    canonical_words, published_words = _layer_words(canonical, lane), _layer_words(published, lane)
    production = distance(reference_words, published_words)
    operations = _alignment(reference_words, published_words)
    if sum(item["operation"] != "match" for item in operations) != sum(production[k] for k in ("substitutions", "omissions", "additions")):
        raise AssertionError("backtrace no longer reproduces production scorer")
    raw_signatures = {(x["operation"], x["reference_word"], x["hypothesis_word"])
                      for x in _alignment(reference_words, raw_words) if x["operation"] != "match"}
    canonical_signatures = {(x["operation"], x["reference_word"], x["hypothesis_word"])
                            for x in _alignment(reference_words, canonical_words) if x["operation"] != "match"}
    audit = reference_audit or {}
    rows = []
    for edit_index, edit in enumerate((x for x in operations if x["operation"] != "match"), 1):
        signature = (edit["operation"], edit["reference_word"], edit["hypothesis_word"])
        if signature in audit:
            label, evidence = audit[signature], paths["reference"]
        elif signature in raw_signatures:
            label, evidence = "a", paths["raw"]
        elif signature in canonical_signatures:
            label, evidence = "b", paths["canonical"]
        elif canonical_words != published_words:
            label, evidence = "c", paths["published"]
        else:
            raise ValueError(f"unattributable edit: {edit}; receipt falsified")
        rows.append({**edit, "edit_index": edit_index, "class": label, "evidence": evidence})
    return rows


def _pcm(path: Path, row: dict[str, Any], gain: float) -> bytes:
    with wave.open(str(path)) as source:
        source.setpos(round(float(row["start"]) * 16000))
        pcm = source.readframes(round((float(row["end"]) - float(row["start"])) * 16000))
    if gain == 1.0:
        return pcm
    samples = array.array("h"); samples.frombytes(pcm)
    for index in range(len(samples)):
        samples[index] = int(samples[index] * gain)
    return samples.tobytes()


def _snapshot_segments(snapshot: dict[str, Any], key: str) -> Any:
    session = (snapshot.get("snapshot") or {}).get("session") or {}
    value = session.get(key)
    if value is None:
        raise ValueError(f"pre-terminal snapshot lacks {key}; receipt falsified")
    return value


def _capture_case(base: str, context: ssl.SSLContext, case: str, references: dict[str, dict[str, Any]]) -> tuple[str, float, dict[str, Any], dict[str, Any]]:
    client = Client(base, context)
    client.call("POST", "/api/workspace/bootstrap")
    descriptor = client.call("GET", "/api/live/descriptor")["descriptor"]
    size, rate = descriptor["frame_samples"], descriptor["sample_rate"]
    if rate != 16000:
        raise ValueError(f"unexpected live sample rate: {rate}")
    input_pcm = {"system": _pcm(SHARED_TAB_VOICE, references["system"], 1.0),
                 "microphone": _pcm(MICROPHONE_VOICE, references["microphone"], DEFAULT_MIC_GAIN)}
    frame_bytes = size * 2
    frames = {lane: math.ceil(len(pcm) / frame_bytes) for lane, pcm in input_pcm.items()}
    offsets = {"system": 0, "microphone": frames["system"] if case == "alternation" else 0}
    total = max(offsets[lane] + frames[lane] for lane in input_pcm)
    created = client.call("POST", "/api/live/sessions", {"source_revision": descriptor["source_revision"]})
    ident = created.get("id") or created.get("session_id")
    if not ident:
        raise ValueError("live create response lacks id")
    epoch, started = time.time_ns(), time.monotonic()
    for sequence in range(total):
        health = {"state": "capturing", "device_epoch": epoch, "dropped_frames": 0,
                  "discontinuities": 0, "failure_code": None}
        client.call("POST", f"/api/live/sessions/{ident}/heartbeat", {"schema": "moss-live-helper-health.v1",
                    "instance_id": "r4-preterm-receipt", "sequence": sequence,
                    "sent_monotonic_ns": time.monotonic_ns(), "helper_version": "r4-10",
                    "state": "capturing", "lanes": {"system": health, "microphone": dict(health)}})
        for lane, pcm in input_pcm.items():
            index = sequence - offsets[lane]
            chunk = pcm[index * frame_bytes:(index + 1) * frame_bytes] if 0 <= index < frames[lane] else b""
            chunk = chunk.ljust(frame_bytes, b"\0")
            client.call("POST", f"/api/live/sessions/{ident}/frames", {"lane": lane, "sequence": sequence,
                        "capture_timestamp_ns": epoch + round(sequence * size / rate * 1e9), "device_epoch": epoch,
                        "pcm_base64": base64.b64encode(chunk).decode(), "sample_count": size, "sample_rate": rate,
                        "silent": not any(chunk), "discontinuity": False})
        # This is the production acceptance timing: a burst would change queue ownership and
        # create a different pre-terminal population from the arm being measured.
        time.sleep(max(0.0, (sequence + 1) * size / rate - (time.monotonic() - started)))
    cutoff, pre = time.monotonic(), client.call("GET", f"/api/live/sessions/{ident}/snapshot")
    # Stop after the frozen pre-terminal snapshot; terminal calls are deliberately excluded by cutoff.
    client.call("POST", f"/api/live/sessions/{ident}/stop", {"deadline": 30})
    return ident, cutoff, pre, {"case": case, "frame_samples": size, "frames": frames, "offsets": offsets,
                                 "total_frames": total, "sample_rate": rate}


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def execute(args: argparse.Namespace, plan_data: dict[str, Any]) -> int:
    if plan_data["corrected_reference"]["status"] != "READY":
        raise SystemExit("REFUSE: corrected reference/cut absent; no decoder request dispatched")
    if args.budget < plan_data["planned_requests"]:
        raise SystemExit(f"REFUSE: budget={args.budget} < planned_requests={plan_data['planned_requests']}; no decoder request dispatched")
    if not args.decoder_base_url:
        raise SystemExit("--decoder-base-url is required with --run")
    if args.out.exists():
        raise SystemExit(f"REFUSE: output already exists: {args.out}")
    args.out.mkdir(parents=True)
    cert, key = args.out / "cert.pem", args.out / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                    "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                    "-keyout", str(key), "-out", str(cert)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stack = [sys.executable, str(Path(__file__).with_name("stack.py")), "--state", str(args.out / "state"),
             "--port", str(args.port), "--cert", str(cert), "--key", str(key), "--model", str(args.model),
             "--manifest", str(args.manifest), "--decoder-base-url", args.decoder_base_url, "--budget", str(args.budget),
             "--raw-events", str(args.out / "raw-events.jsonl")]
    process = subprocess.Popen(stack, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "."})
    context = ssl._create_unverified_context()
    base = f"https://127.0.0.1:{args.port}"
    try:
        for _ in range(120):
            if process.poll() is not None:
                raise RuntimeError("receipt stack exited before readiness")
            try:
                Client(base, context).call("GET", "/api/live/descriptor"); break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("receipt stack did not become ready")
        references, _ = corrected_references()
        for case in ("alternation", "overlap"):
            ident, cutoff, pre, geometry = _capture_case(base, context, case, references)
            events = [json.loads(line) for line in (args.out / "raw-events.jsonl").read_text().splitlines() if line.strip()]
            for _, lane in (arm for arm in ARMS if arm[0] == case):
                arm_dir = args.out / case / lane
                raw = {"schema": "moss-r4-preterm-raw.v1", "case": case, "lane": lane,
                       "windows": [row for row in events if row["session_id"] == ident and row["lane"] == lane and row["monotonic"] <= cutoff]}
                canonical, published = _snapshot_segments(pre, "committed"), _snapshot_segments(pre, "effective_transcript")
                paths = {"raw": f"raw-{lane}.json", "canonical": f"canonical-{lane}.json",
                         "published": f"published-{lane}.json", "reference": f"reference-{lane}.jsonl"}
                _write(arm_dir / paths["raw"], raw); _write(arm_dir / paths["canonical"], canonical)
                _write(arm_dir / paths["published"], published)
                (arm_dir / paths["reference"]).write_text(json.dumps(references[lane]) + "\n")
                _write(arm_dir / "cut-geometry.json", {**plan_data["cut_geometry"], "case": case, "run": geometry})
                _write(arm_dir / "scored-edits.json", score_layers(reference=references[lane], raw=raw, canonical=canonical,
                    published=published, lane=lane, paths=paths))
    finally:
        process.terminate()
        try: process.wait(timeout=20)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--decoder-base-url")
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--port", type=int, default=18344)
    parser.add_argument("--model", type=Path, default=Path.home() / ".cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8")
    parser.add_argument("--manifest", type=Path, default=Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json")
    args = parser.parse_args(argv)
    if args.plan_only == args.run:
        parser.error("choose exactly one of --plan-only or --run")
    plan_data = plan()
    if args.plan_only:
        _write(args.out, plan_data); print(json.dumps(plan_data, indent=2)); return 0
    return execute(args, plan_data)


if __name__ == "__main__":
    raise SystemExit(main())
