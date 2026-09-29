"""Run Q-FILE through a loopback Gemini Account server; see README.md."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import quote
import wave

import httpx


PYTHON = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python")
DEFAULT_MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
ACCEPT6_BOUND = 0.110
LONG60_BOUND = 0.06
# TerminalTranscriber defaults at this pinned source: 900 s chunks / 30 s overlap.
TERMINAL_CHUNK_SAMPLES = 900 * 16000
TERMINAL_OVERLAP_SAMPLES = 30 * 16000
# Gemini 3.5 Transcribe standard list-price estimates, USD per audio minute.
TRANSCRIBE_INPUT_USD_PER_MINUTE = 0.003
TRANSCRIBE_OUTPUT_USD_PER_MINUTE = 0.002


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_sha(worktree: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=worktree, text=True).strip()


def corpus_and_scorers(worktree: Path):
    sys.path.insert(0, str(worktree))
    sys.path.insert(0, str(worktree / "prototypes/gemini-live/common"))
    sys.path.insert(0, str(worktree / "prototypes/gemini-live/harness"))
    from corpus import clips
    from h1_offline import score_case
    from score import score
    return clips, score_case, score


def selected_clips(clips, cases: list[str]):
    population = [*clips("accept6"), *clips("long60")]
    if len(population) != 7 or len(clips("accept6")) != 6 or len(clips("long60")) != 1:
        raise ValueError("Q-FILE requires six accept6 clips and one long60 clip")
    by_id = {clip.clip_id: clip for clip in population}
    unknown = sorted(set(cases) - by_id.keys())
    if unknown:
        raise ValueError(f"unregistered Q-FILE case: {unknown}")
    selected = [by_id[name] for name in cases] if cases else population
    if len({clip.clip_id for clip in selected}) != len(selected):
        raise ValueError("duplicate Q-FILE case")
    for clip in selected:
        if not clip.audio.is_file() or clip.reference is None or not clip.reference.is_file():
            raise ValueError(f"missing public audio or reference for {clip.clip_id}")
        with wave.open(str(clip.audio), "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                raise ValueError(f"Q-FILE audio must be 16 kHz mono PCM16: {clip.clip_id}")
    return selected


def check_scorers(selected, score_case, score):
    accept = next((clip for clip in selected if clip.tier == "accept6"), None)
    long = next((clip for clip in selected if clip.tier == "long60"), None)
    if accept is not None:
        score_case(accept.clip_id, immediate=[], settled=[], final=[])
    if long is not None:
        score(long.reference_segments(), [])


def make_certificate(state: Path) -> tuple[Path, Path]:
    cert, key = state / "cert.pem", state / "key.pem"
    if cert.exists() and key.exists():
        return cert, key
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1",
        "-subj", "/CN=localhost",
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return cert, key


def launch_server(worktree: Path, state: Path, manifest: Path, port: int):
    cert, key = make_certificate(state)
    log = (state / "server.log").open("w")
    env = dict(os.environ)
    env.pop("GEMINI_API_KEY", None)
    env.update(MOSS_OPEN_WORKSPACE="1", PYTHONDONTWRITEBYTECODE="1")
    command = [
        str(PYTHON), "-m", "moss_transcribe_diarize.app.phase2_web_cli",
        "--database", str(state / "phase2.sqlite"),
        "--control-socket", str(state / "control.sock"),
        "--tls-certfile", str(cert), "--tls-keyfile", str(key),
        "--file-work-root", str(state / "file-work"),
        "--meeting-audio-root", str(state / "meeting-audio"),
        "--live-provider-manifest", str(manifest),
        "--live-helper-lease-seconds", "30", "--live-engine", "gemini",
        "--host", "127.0.0.1", "--port", str(port),
    ]
    process = subprocess.Popen(command, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT)
    log.close()
    return process


def await_server(client: httpx.Client, process: subprocess.Popen, seconds: float = 90) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Gemini server exited during startup ({process.returncode})")
        try:
            if client.get("/api/auth/session", timeout=3).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.5)
    raise TimeoutError("Gemini server did not become ready")


def pick_speaker(rows: list[dict]) -> tuple[str | None, float]:
    duration: dict[str, float] = {}
    for row in rows:
        speaker = row.get("speaker_entity_id") or row.get("speaker")
        if not isinstance(speaker, str) or speaker in {"", "S00", "Speaker TBD"}:
            continue
        duration[speaker] = duration.get(speaker, 0.0) + max(0.0, float(row["end"]) - float(row["start"]))
    return (max(duration, key=duration.get), max(duration.values())) if duration else (None, 0.0)


def terminal_cost_estimate(audio_path: Path) -> dict:
    """Estimate one terminal pass from its voiced 900/30 chunk schedule."""
    from moss_transcribe_diarize.app.gemini_lane_engine import WebRtcSpeechDetector

    voiced_audio = WebRtcSpeechDetector()
    chunks = []
    sent_samples = 0
    with wave.open(str(audio_path), "rb") as audio:
        end = audio.getnframes()
        start = 0
        while start < end:
            stop = min(end, start + TERMINAL_CHUNK_SAMPLES)
            audio.setpos(start)
            sent = voiced_audio(audio.readframes(stop - start))
            chunks.append({"start_seconds": start / 16000, "end_seconds": stop / 16000,
                           "sent_estimate": sent})
            if sent:
                sent_samples += stop - start
            if stop == end:
                break
            start = stop - TERMINAL_OVERLAP_SAMPLES
    sent_seconds = sent_samples / 16000
    input_usd = sent_seconds / 60 * TRANSCRIBE_INPUT_USD_PER_MINUTE
    output_usd = sent_seconds / 60 * TRANSCRIBE_OUTPUT_USD_PER_MINUTE
    return {
        "status": "ESTIMATE", "basis": "one_voiced_terminal_pass_no_retries",
        "model": "gemini-3.5-transcribe", "chunks": chunks,
        "audio_seconds_sent_estimate": sent_seconds,
        "input_usd_per_minute": TRANSCRIBE_INPUT_USD_PER_MINUTE,
        "output_usd_per_minute": TRANSCRIBE_OUTPUT_USD_PER_MINUTE,
        "input_usd": round(input_usd, 9), "output_usd": round(output_usd, 9),
        "total_usd": round(input_usd + output_usd, 9),
    }


def run_clip(client: httpx.Client, clip, score_case, score, wait_seconds: float) -> dict:
    started = time.monotonic()
    result = {
        "case_id": clip.clip_id, "tier": clip.tier, "audio_seconds": None,
        "audio_bytes": clip.audio.stat().st_size, "meeting_id": None,
        "meeting_status": None, "transcript_rows": None, "speaker_count": None,
        "scorer": "h1_offline.score_case.final" if clip.tier == "accept6" else "common.score",
        "metrics": None, "transcription_wall_seconds": None, "wall_seconds": None,
        "enrollment": None, "named_speaker_seconds": None, "voiceprint_id_present": None,
        "engine_diagnostics": None, "usage_cost_usd": None, "usage_cost_status": "UNMEASURED",
        "cost_estimate": None,
        "failure": None,
    }
    with wave.open(str(clip.audio), "rb") as audio:
        result["audio_seconds"] = audio.getnframes() / audio.getframerate()
    try:
        admission = client.post("/api/meetings/file/admission", json={"file_bytes": result["audio_bytes"]})
        admission.raise_for_status()
        if admission.status_code != 204:
            raise RuntimeError("File admission returned unexpected status")
        with clip.audio.open("rb") as audio:
            upload = client.post("/api/meetings/file", files={"file": (clip.audio.name, audio, "audio/wav")},
                                 timeout=180)
        upload.raise_for_status()
        if upload.status_code != 201:
            raise RuntimeError("File upload returned unexpected status")
        result["meeting_id"] = upload.json()["id"]
        deadline = time.monotonic() + wait_seconds
        while True:
            response = client.get(f"/api/meetings/{quote(result['meeting_id'], safe='')}")
            response.raise_for_status()
            meeting = response.json()
            result["meeting_status"] = meeting["status"]
            if meeting["status"] != "active":
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("File Meeting completion deadline expired")
            time.sleep(2)
        result["transcription_wall_seconds"] = round(time.monotonic() - started, 3)
        if meeting["status"] != "completed":
            result["failure"] = {"type": "meeting_outcome", "code": meeting.get("failure_code"),
                                 "reason": meeting.get("failure_reason")}
            return result
        result["cost_estimate"] = terminal_cost_estimate(clip.audio)
        rows = (meeting.get("transcript") or {}).get("segments") or []
        result["transcript_rows"] = len(rows)
        result["speaker_count"] = len({row["speaker"] for row in rows if row.get("speaker") not in (None, "S00")})
        if clip.tier == "accept6":
            result["metrics"] = score_case(clip.clip_id, immediate=[], settled=[], final=rows)["metrics"]["final"]
        else:
            result["metrics"] = score(clip.reference_segments(), rows)
        diagnostics = meeting.get("engine_diagnostics")
        if isinstance(diagnostics, dict):
            result["engine_diagnostics"] = diagnostics
            if isinstance(diagnostics.get("cost_usd"), (int, float)):
                result["usage_cost_usd"] = diagnostics["cost_usd"]
                result["usage_cost_status"] = "MEASURED"
        speaker, seconds = pick_speaker(rows)
        result["named_speaker_seconds"] = round(seconds, 3)
        if speaker is None:
            result["failure"] = {"type": "no_named_speaker"}
            return result
        named = client.put(
            f"/api/meetings/{quote(result['meeting_id'], safe='')}/speakers/{quote(speaker, safe='')}/name",
            json={"label": f"QFILE {clip.clip_id}", "save_voiceprint": True},
            timeout=min(wait_seconds, 900),
        )
        named.raise_for_status()
        result["enrollment"] = named.json().get("enrollment")
        result["voiceprint_id_present"] = bool(named.json().get("voiceprint_id"))
        if result["enrollment"] != "enrolled" or not result["voiceprint_id_present"]:
            result["failure"] = {"type": "enrollment_unavailable"}
    except Exception as exc:
        result["failure"] = {"type": type(exc).__name__,
                             "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None,
                             "detail": str(exc)[:300]}
    finally:
        result["wall_seconds"] = round(time.monotonic() - started, 3)
    return result


def aggregate(selected: list[str], results: list[dict]) -> dict:
    by_id = {row["case_id"]: row for row in results}
    full = len(selected) == 7 and len(by_id) == 7
    accept = [row for row in results if row["tier"] == "accept6" and row["metrics"] is not None]
    long = next((row for row in results if row["tier"] == "long60"), None)
    macro = (sum(row["metrics"]["der"] for row in accept) / 6) if len(accept) == 6 else None
    long_der = None if long is None or long["metrics"] is None else long["metrics"]["der"]
    all_enrolled = len(results) == 7 and all(row["enrollment"] == "enrolled" for row in results)
    gate = "UNMEASURED"
    if full:
        gate = ("PASS" if macro is not None and macro <= ACCEPT6_BOUND
                and long_der is not None and long_der <= LONG60_BOUND
                and all_enrolled and all(row["failure"] is None for row in results) else "FAIL")
    return {"selected": len(selected), "completed": sum(row["meeting_status"] == "completed" for row in results),
            "accept6_scored": len(accept), "accept6_der_macro": macro, "accept6_der_bound": ACCEPT6_BOUND,
            "long60_der": long_der, "long60_der_bound": LONG60_BOUND,
            "enrolled": sum(row["enrollment"] == "enrolled" for row in results),
            "measured_cost_usd": sum(row["usage_cost_usd"] or 0 for row in results),
            "unmeasured_cost_cases": sum(row["usage_cost_status"] == "UNMEASURED" for row in results),
            "estimated_cost_usd": round(sum((row.get("cost_estimate") or {}).get("total_usd", 0)
                                            for row in results), 9),
            "estimated_cost_cases": sum(row.get("cost_estimate") is not None for row in results),
            "qfile_gate": gate}


def save(path: Path, report: dict) -> None:
    report["updated_at_utc"] = now_utc()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--expect-sha", required=True)
    parser.add_argument("--out", type=Path, required=True, help="Destination qfile.json")
    parser.add_argument("--case", action="append", default=[], help="Registered case ID; omit for all seven")
    parser.add_argument("--port", type=int, default=18730)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--wait-seconds", type=float, default=1800)
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    state_value = os.environ.get("MOSS_GEMINI_STATE")
    if not state_value:
        parser.error("MOSS_GEMINI_STATE must name an absolute scratch directory")
    state = Path(state_value)
    if not state.is_absolute() or not 18730 <= args.port <= 18739 or args.wait_seconds <= 0:
        parser.error("use an absolute MOSS_GEMINI_STATE, port 18730-18739, and positive wait")
    if len(os.fsencode(state / "control.sock")) >= 104:
        parser.error("MOSS_GEMINI_STATE is too long for the host control socket")
    if not PYTHON.is_file() or not args.manifest.is_file() or not (worktree / ".env.local").is_file():
        parser.error("Python, pinned manifest, or worktree .env.local is missing")
    sha = source_sha(worktree)
    if sha != args.expect_sha:
        parser.error(f"worktree HEAD {sha} differs from --expect-sha")
    clips, score_case, score = corpus_and_scorers(worktree)
    selected = selected_clips(clips, args.case)
    check_scorers(selected, score_case, score)
    state.mkdir(parents=True, exist_ok=True)
    state.chmod(0o700)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            parser.error(f"port {args.port} is already occupied")
    report = {"schema": "moss.qfile.v1", "worktree": str(worktree), "source_sha": sha,
              "selection": [clip.clip_id for clip in selected], "started_at_utc": now_utc(),
              "updated_at_utc": None, "server_port": args.port,
              "cases": [], "aggregate": aggregate([clip.clip_id for clip in selected], []),
              "run_failure": None}
    process = None
    try:
        process = launch_server(worktree, state, args.manifest, args.port)
        with httpx.Client(base_url=f"https://127.0.0.1:{args.port}", verify=False, timeout=30) as client:
            await_server(client, process)
            for clip in selected:
                case = run_clip(client, clip, score_case, score, args.wait_seconds)
                report["cases"].append(case)
                report["aggregate"] = aggregate(report["selection"], report["cases"])
                save(args.out, report)
                print(f"{clip.clip_id}: {case['meeting_status']} DER={None if case['metrics'] is None else case['metrics']['der']} enrollment={case['enrollment']} wall={case['wall_seconds']}s", flush=True)
    except Exception as exc:
        report["run_failure"] = {"type": type(exc).__name__, "detail": str(exc)[:300]}
        save(args.out, report)
        raise
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    print(f"qfile={args.out} gate={report['aggregate']['qfile_gate']}", flush=True)
    return 0 if all(row["failure"] is None for row in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
