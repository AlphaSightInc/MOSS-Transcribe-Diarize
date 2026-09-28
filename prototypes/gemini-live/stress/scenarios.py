"""Paced public-audio stress scenarios through the unchanged Account Live HTTP API.

Run one: python prototypes/gemini-live/stress/scenarios.py --scenario stop-early
  --launch-stub --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/stress-stop-early
Use --base-url https://127.0.0.1:18524 against an already running Gemini stack.
--seconds N is a plumbing smoke override, not a full-duration stress qualification.
"""
from __future__ import annotations

import argparse
import array
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError

import numpy as np
import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/e2e"))
sys.path.insert(0, str(ROOT / "tests/e2e"))
# The installed site-packages "tests" package masks this repo's namespace directory.
import verify_demo_lanes  # noqa: E402
sys.modules["tests.e2e.verify_demo_lanes"] = verify_demo_lanes
from corpus import clips  # noqa: E402
from gemini_common import read_wav  # noqa: E402
from run import candidate_manifest, stop_process, dom_rows  # noqa: E402
from tap_proxy import TapProxy  # noqa: E402
from tests.e2e.verify_demo_lanes import Client  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64")
FAULTS = {
    "http_429": "rest", "http_500": "rest", "http_503": "rest",
    "latency_fixed": "rest", "latency_heavy_tail": "rest", "connection_reset": "rest",
    "response_truncate": "rest", "malformed_json": "rest", "stall": "rest",
    "ws_close_1011": "ws", "ws_close_1007": "ws", "ws_goaway": "ws",
    "ws_connection_reset": "ws", "ws_stall": "ws", "google_down": "all",
}
SILENCE_RMS = 1e-4
SAMPLE_RATE = 16000


def percentile(values: list[float], fraction: float):
    if not values:
        return "UNMEASURED"
    values = sorted(values)
    pos = (len(values) - 1) * fraction
    lo, hi = math.floor(pos), math.ceil(pos)
    return round(values[lo] + (values[hi] - values[lo]) * (pos - lo), 3)


def engine_metrics(diagnostics: dict | None) -> dict | str:
    if not isinstance(diagnostics, dict):
        return "UNMEASURED"
    calls = diagnostics.get("calls_by_kind") or {}
    anomalies = diagnostics.get("timing_anomalies") or {}
    total = sum(calls.values())
    return {"calls_by_kind": calls, "calls_total": total,
            "errors_by_code": diagnostics.get("errors_by_code") or {},
            "retries_by_code": diagnostics.get("retries_by_code") or {},
            "timing_anomalies": anomalies,
            "clamped_per_call": round(anomalies.get("clamped", 0) / total, 6) if total else "UNMEASURED",
            "dropped_per_call": round(anomalies.get("dropped", 0) / total, 6) if total else "UNMEASURED",
            "audio_seconds_sent": diagnostics.get("audio_seconds_sent", "UNMEASURED"),
            "cost_usd": diagnostics.get("cost_usd", "UNMEASURED"),
            "degraded_path_activations": diagnostics.get("degraded_path_activations", "UNMEASURED"),
            "window_lag_seconds": diagnostics.get("window_lag_seconds", "UNMEASURED"),
            "preview_lag_seconds": diagnostics.get("preview_lag_seconds", "UNMEASURED")}


def jsonl(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def clone_client(base: str, jar: dict) -> Client:
    client = Client(base, ssl._create_unverified_context())
    client._jar = dict(jar)
    return client


def audio_specs(scenario: str, override: float | None) -> list[dict]:
    def pcm(clip):
        return read_wav(clip.audio).astype(np.int16)

    def complete_five_minute():
        wanted = ("lex_bill_ackman", "lex_keyu_jin", "lex_javier_milei")
        available = {c.clip_id.rsplit(":", 1)[-1]: c for c in clips("bench5m")}
        if any(name not in available for name in wanted):
            raise RuntimeError("complete lex 5-minute public fixtures unavailable")
        return [available[name] for name in wanted]

    if scenario == "long60":
        source = clips("long30m")
        if len(source) < 2:
            raise RuntimeError("long30m public corpus lacks two clips")
        system = np.concatenate([pcm(source[0]), pcm(source[1])])
        result = [{"name": "long60", "system": system, "mic": None,
                   "source_ids": [source[0].clip_id, source[1].clip_id]}]
    elif scenario == "concurrent2":
        source = complete_five_minute()
        result = [{"name": f"concurrent_{i+1}", "system": pcm(source[i]), "mic": None,
                   "source_ids": [source[i].clip_id]}
                  for i in range(2)]
    elif scenario in ("silence10", "music5"):
        seconds = 600 if scenario == "silence10" else 300
        if scenario == "silence10":
            system = np.zeros(seconds * SAMPLE_RATE, dtype=np.int16)
        else:
            # Generated chord sequence, bounded below clipping; no external audio.
            t = np.arange(seconds * SAMPLE_RATE, dtype=np.float64) / SAMPLE_RATE
            notes = np.array([261.63, 329.63, 392.00, 293.66])
            freq = notes[(t.astype(np.int32) // 2) % len(notes)]
            system = (5500 * np.sin(2 * np.pi * freq * t) +
                      1800 * np.sin(4 * np.pi * freq * t)).astype(np.int16)
        result = [{"name": scenario, "system": system, "mic": None,
                   "source_ids": ["generated:" + scenario]}]
    elif scenario == "overlap":
        source = complete_five_minute()
        a, b = pcm(source[0]), pcm(source[1])
        count = min(len(a), len(b))
        a_rms = math.sqrt(float(np.mean(a[:count].astype(np.float64) ** 2)))
        b_rms = math.sqrt(float(np.mean(b[:count].astype(np.float64) ** 2)))
        if a_rms == 0 or b_rms == 0:
            raise RuntimeError("overlap source RMS is zero")
        result = [{"name": label,
                   "system": np.clip(a[:count].astype(np.float64) + a_rms / b_rms * gain * b[:count],
                                     -32768, 32767).astype(np.int16), "mic": None,
                   "source_ids": [source[0].clip_id, source[1].clip_id],
                   "input_ratio_db": db}
                  for label, db, gain in (("overlap_0db", 0, 1.0),
                                          ("overlap_minus10db", -10, 10 ** (-10 / 20)))]
    elif scenario == "manyspk":
        source = next((c for c in clips("synth") if c.true_speakers == 6), None)
        if source is None:
            raise RuntimeError("public synthetic K=6 fixture unavailable")
        result = [{"name": "manyspk_k6", "system": pcm(source), "mic": None,
                   "source_ids": [source.clip_id]}]
    else:
        source = complete_five_minute() if scenario.startswith("faults-") or scenario == "abort-mid" else clips("accept6")
        if not source:
            raise RuntimeError("public corpus unavailable")
        selected = source[0]
        result = [{"name": scenario, "system": pcm(selected), "mic": None,
                   "source_ids": [selected.clip_id]}]

    for spec in result:
        duration = len(spec["system"]) / SAMPLE_RATE
        if scenario == "stop-early":
            duration = min(duration, 5)
        if scenario == "abort-mid":
            duration = min(duration, 150)
        if override is not None:
            duration = min(duration, override)
        spec["duration_s"] = duration
    return result


@contextmanager
def local_stub_stack(out: Path):
    """Isolated no-GPU MOSS loopback stack, using owned 18524-18526 ports."""
    with tempfile.TemporaryDirectory(prefix="p64-stress-", dir=os.environ.get("TMPDIR")) as root_name:
        scratch = Path(root_name)
        manifest = scratch / "provider-manifest.json"
        candidate_manifest(manifest)
        cert, key = scratch / "cert.pem", scratch / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT),
                   MOSS_TEST_REAL_SQLITE="1")
        stub = stack = proxy = None
        try:
            stub_log = (scratch / "stub.log").open("wb")
            stub = subprocess.Popen([sys.executable, str(ROOT / "prototypes/gemini-live/e2e/loopback_vllm_stub.py"),
                                     "--port", "18526", "--out", str(scratch / "stub")],
                                    env=env, stdout=stub_log, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            time.sleep(.5)
            if stub.poll() is not None:
                raise RuntimeError("loopback stub startup failed")
            proxy = TapProxy(port=18525, upstream_port=18526, budget=2000,
                             out=out / "decoder-tap.jsonl")
            proxy.start()
            stack_log = (scratch / "stack.log").open("wb")
            stack = subprocess.Popen([sys.executable, str(ROOT / "prototypes/gemini-live/e2e/local_stack.py"),
                                      "--state", str(scratch / "state"), "--cert", str(cert),
                                      "--key", str(key), "--port", "18524", "--manifest", str(manifest),
                                      "--vllm-base-url", "http://127.0.0.1:18525/v1",
                                      "--max-requests", "2000", "--draft-lane-seconds", "1.0"],
                                     cwd=ROOT, env=env, stdout=stack_log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            base = "https://127.0.0.1:18524"
            for _ in range(120):
                if stack.poll() is not None:
                    break
                try:
                    Client(base, ssl._create_unverified_context()).call("POST", "/api/workspace/bootstrap")
                    break
                except Exception:
                    time.sleep(.5)
            else:
                raise RuntimeError("stub stack startup timeout")
            if stack.poll() is not None:
                raise RuntimeError("stub stack failed: " + (scratch / "stack.log").read_text()[-1000:])
            yield base, stack.pid
        finally:
            stop_process(stack)
            if proxy is not None:
                proxy.close()
            stop_process(stub)
            if 'stack_log' in locals(): stack_log.close()
            if 'stub_log' in locals(): stub_log.close()


def process_watch(pid: int | None, out: Path, stop: threading.Event, state: dict) -> None:
    if pid is None:
        state["status"] = "UNMEASURED"
        return
    while not stop.is_set():
        try:
            ps = subprocess.check_output(["ps", "-o", "rss=", "-o", "%cpu=", "-p", str(pid)],
                                         text=True).strip().split()
            fd_lines = subprocess.check_output(["lsof", "-n", "-p", str(pid)],
                                               text=True, stderr=subprocess.DEVNULL).splitlines()
            row = {"monotonic_ns": time.monotonic_ns(), "rss_kib": int(ps[0]),
                   "cpu_percent": float(ps[1]), "open_fds": max(0, len(fd_lines) - 1)}
            jsonl(out, row)
            state["samples"] = state.get("samples", 0) + 1
            for key in ("rss_kib", "cpu_percent", "open_fds"):
                state["max_" + key] = max(state.get("max_" + key, 0), row[key])
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            state["error_type"] = type(exc).__name__
            break
        stop.wait(5)


def dom_watch(base: str, jar: dict, meeting: str, out: Path, stop: threading.Event,
              ready: threading.Event, state: dict) -> None:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True,
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            context = browser.new_context(ignore_https_errors=True)
            try:
                context.add_cookies([{"name": k, "value": v, "url": base, "secure": True}
                                     for k, v in jar.items()])
                page = context.new_page()
                page.goto(base, wait_until="domcontentloaded")
                page.locator('[data-boot="ready"]').wait_for(timeout=30000)
                page.evaluate("id => document.dispatchEvent(new CustomEvent('moss:observe-live-meeting', {detail:{meetingId:id}}))", meeting)
                ready.set()
                first_text, first_label = {}, {}
                while not stop.is_set():
                    start_ns = state.get("audio_start_ns")
                    rows = dom_rows(page)
                    elapsed = (time.monotonic_ns() - start_ns) / 1e9 if start_ns else None
                    ui_status = page.locator(".top-status").text_content() or ""
                    jsonl(out, {"monotonic_ns": time.monotonic_ns(),
                                "audio_s": round(elapsed, 2) if elapsed is not None else "UNMEASURED",
                                "rows": len(rows), "named_labels": len({r.get("label") for r in rows
                                    if r.get("label") and not r.get("uncertain")}),
                                "uncertain_rows": sum(bool(r.get("uncertain")) for r in rows),
                                "ui_status": ui_status.strip()})
                    state["samples"] = state.get("samples", 0) + 1
                    state["last_ui_status"] = ui_status.strip()
                    if elapsed is not None:
                        for row in rows:
                            label_ok = (row.get("label") and not row.get("uncertain") and
                                        row.get("speaker_id") not in (None, "S00"))
                            for segment in row.get("segments") or [row]:
                                if not (segment.get("text") or "").strip():
                                    continue
                                try:
                                    a, b = float(segment["start"]), float(segment["end"])
                                except (ValueError, TypeError, KeyError):
                                    continue
                                for second in range(max(0, math.floor(a)), math.ceil(b)):
                                    if a < second + 1 and b > second:
                                        delay = max(0, elapsed - second - 1)
                                        first_text.setdefault(second, delay)
                                        if label_ok:
                                            first_label.setdefault(second, delay)
                    stop.wait(1)
                state["first_text"] = first_text
                state["first_label"] = first_label
            finally:
                context.close()
                browser.close()
    except Exception as exc:
        state["error_type"] = type(exc).__name__
        ready.set()


def poll_watch(base: str, jar: dict, meeting: str, out: Path, stop: threading.Event,
               state: dict) -> None:
    client = clone_client(base, jar)
    cursor = -1
    while not stop.is_set():
        try:
            start = time.monotonic()
            envelope = client.call("GET", f"/api/live/sessions/{meeting}/snapshot")
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            payload = envelope.get("snapshot") or {}
            session = payload.get("session") or {}
            engine = engine_metrics(payload.get("engine_diagnostics"))
            jsonl(out / "poll.jsonl", {"monotonic_ns": time.monotonic_ns(),
                "latency_ms": elapsed_ms, "snapshot_bytes": len(json.dumps(envelope).encode()),
                "pending_work_items": payload.get("pending_work_items"),
                "session_status": session.get("status"),
                "finalization_status": session.get("finalization_status"),
                "accepted_samples": session.get("accepted_samples"),
                "engine": engine})
            state["polls"] = state.get("polls", 0) + 1
            state["max_pending"] = max(state.get("max_pending", 0),
                                       payload.get("pending_work_items") or 0)
            state["max_snapshot_bytes"] = max(state.get("max_snapshot_bytes", 0),
                                              len(json.dumps(envelope).encode()))
            state.setdefault("poll_latency_ms", []).append(elapsed_ms)
            events = client.call("GET", f"/api/live/sessions/{meeting}/events?since_seq={cursor}").get("events", [])
            for event in events:
                seq = int(event["seq"])
                if seq < cursor:
                    continue
                kind = event.get("kind", "")
                jsonl(out / "events.jsonl", {"monotonic_ns": time.monotonic_ns(),
                                               "seq": seq, "kind": kind})
                if "reconnect" in kind.lower() or "goaway" in kind.lower():
                    state["reconnect_events"] = state.get("reconnect_events", 0) + 1
                cursor = seq + 1
        except Exception as exc:
            state["error_type"] = type(exc).__name__
            break
        stop.wait(1)


def frame_payload(lane: str, pcm: bytes, sequence: int, size: int, epoch: int) -> dict:
    offset = sequence * size * 2
    chunk = pcm[offset:offset + size * 2].ljust(size * 2, b"\0")
    values = array.array("h")
    values.frombytes(chunk)
    rms = math.sqrt(sum(v * v for v in values) / len(values)) / 32768
    start_ns = round(sequence * size / SAMPLE_RATE * 1e9)
    end_ns = round((sequence + 1) * size / SAMPLE_RATE * 1e9)
    return {"lane": lane, "sequence": sequence,
            "capture_timestamp_ns": start_ns, "capture_end_timestamp_ns": end_ns,
            "device_epoch": epoch, "pcm_base64": base64.b64encode(chunk).decode(),
            "sample_count": size, "sample_rate": SAMPLE_RATE,
            "silent": rms < SILENCE_RMS, "discontinuity": False}


def run_session(base: str, jar: dict, meeting: str, descriptor: dict, spec: dict,
                out: Path, barrier: threading.Barrier | None = None,
                abort: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    client = clone_client(base, jar)
    lane_clients = [clone_client(base, jar), clone_client(base, jar)]
    system = spec["system"].tobytes()
    mic = spec["mic"].tobytes() if spec["mic"] is not None else b""
    size = int(descriptor["frame_samples"])
    frame_seconds = size / SAMPLE_RATE
    frames = math.ceil(spec["duration_s"] / frame_seconds)
    epoch = time.time_ns()
    watch_stop = threading.Event()
    dom_ready = threading.Event()
    dom_state, poll_state = {}, {}
    dom_thread = threading.Thread(target=dom_watch,
        args=(base, jar, meeting, out / "dom-samples.jsonl", watch_stop, dom_ready, dom_state), daemon=True)
    poll_thread = threading.Thread(target=poll_watch,
        args=(base, jar, meeting, out, watch_stop, poll_state), daemon=True)
    dom_thread.start()
    poll_thread.start()
    result = {"meeting_id": meeting, "name": spec["name"], "planned_audio_s": spec["duration_s"],
              "source_ids": spec.get("source_ids", "UNMEASURED"),
              "input_ratio_db": spec.get("input_ratio_db", "NOT_APPLICABLE"),
              "frames_planned": frames, "frames_accepted_per_lane": {"system": 0, "microphone": 0},
              "frame_errors": [], "finalization_status": "UNMEASURED"}
    try:
        if not dom_ready.wait(35) or dom_state.get("error_type"):
            raise RuntimeError("browser DOM observer did not start")
        if barrier is not None:
            barrier.wait(timeout=40)
        start = time.monotonic()
        dom_state["audio_start_ns"] = time.monotonic_ns()
        (out / "audio-start.json").write_text(json.dumps({"monotonic_ns": dom_state["audio_start_ns"]}) + "\n")
        max_lag = 0.0
        with ThreadPoolExecutor(max_workers=2) as pool:
            for sequence in range(frames):
                scheduled = start + sequence * frame_seconds
                time.sleep(max(0, scheduled - time.monotonic()))
                health = dict(state="capturing", device_epoch=epoch, dropped_frames=0,
                              discontinuities=0, failure_code=None)
                client.call("POST", f"/api/live/sessions/{meeting}/heartbeat", {
                    "schema": "moss-live-helper-health.v1", "instance_id": "p64-stress",
                    "sequence": sequence, "sent_monotonic_ns": time.monotonic_ns(),
                    "helper_version": "p64-stress", "state": "capturing",
                    "lanes": {"system": health, "microphone": dict(health)}})
                futures = [pool.submit(lane_clients[i].call, "POST",
                    f"/api/live/sessions/{meeting}/frames",
                    frame_payload(lane, audio, sequence, size, epoch))
                    for i, (lane, audio) in enumerate((("system", system), ("microphone", mic)))]
                for i, future in enumerate(futures):
                    lane = ("system", "microphone")[i]
                    try:
                        future.result()
                        result["frames_accepted_per_lane"][lane] += 1
                    except Exception as exc:
                        result["frame_errors"].append({"sequence": sequence, "lane": lane,
                                                       "error_type": type(exc).__name__})
                if result["frame_errors"]:
                    break
                max_lag = max(max_lag, time.monotonic() - scheduled)
        result["max_sender_lag_s"] = round(max_lag, 3)
        result["sent_audio_s"] = result["frames_accepted_per_lane"]["system"] * frame_seconds
        result["terminal_action"] = "abort" if abort else "stop"
        action_start = time.monotonic()
        if abort:
            client.call("POST", f"/api/live/sessions/{meeting}/abort", {"reason": "stress_abort_mid"})
        else:
            client.call("POST", f"/api/live/sessions/{meeting}/stop", {"deadline": 30})
        terminal = None
        start_wait = time.monotonic()
        for _ in range(90):
            terminal = client.call("GET", f"/api/live/sessions/{meeting}/snapshot")
            session = ((terminal.get("snapshot") or {}).get("session") or {})
            if session.get("finalization_status") in ("final", "failed", "unavailable") or \
               session.get("status") in ("aborted", "failed"):
                break
            time.sleep(.5)
        result["post_action_wait_s"] = round(time.monotonic() - start_wait, 3)
        result["action_to_terminal_s"] = round(time.monotonic() - action_start, 3)
        (out / "final-snapshot.json").write_text(json.dumps(terminal, ensure_ascii=False) + "\n")
        session = ((terminal.get("snapshot") or {}).get("session") or {}) if terminal else {}
        result["finalization_status"] = session.get("finalization_status", "UNMEASURED")
        result["session_status"] = session.get("status", "UNMEASURED")
        result["engine"] = engine_metrics((terminal.get("snapshot") or {}).get("engine_diagnostics"))
        saved = None
        for _ in range(30):
            try:
                saved = client.call("GET", f"/api/meetings/{meeting}")
                break
            except HTTPError:
                time.sleep(.5)
        if saved:
            (out / "saved-meeting.json").write_text(json.dumps(saved, ensure_ascii=False) + "\n")
        audio = (saved or {}).get("audio") or {}
        result["saved_status"] = (saved or {}).get("status", "UNMEASURED")
        result["audio_state"] = audio.get("state", "UNMEASURED")
        result["retained_mp3_duration_s"] = (audio.get("duration_ms") / 1000
                                               if isinstance(audio.get("duration_ms"), (int, float))
                                               else "UNMEASURED")
        result["audio_duration_gap_s"] = (round(result["retained_mp3_duration_s"] - result["sent_audio_s"], 3)
                                          if isinstance(result["retained_mp3_duration_s"], (int, float))
                                          else "UNMEASURED")
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:240]
        try:
            client.call("POST", f"/api/live/sessions/{meeting}/abort", {"reason": "stress_harness_cleanup"})
        except Exception:
            pass
    finally:
        watch_stop.set()
        dom_thread.join(timeout=15)
        poll_thread.join(timeout=10)
        result["dom_samples"] = dom_state.get("samples", 0)
        result["dom_error_type"] = dom_state.get("error_type")
        result["last_ui_status"] = dom_state.get("last_ui_status", "UNMEASURED")
        result["polls"] = poll_state.get("polls", 0)
        result["poll_error_type"] = poll_state.get("error_type")
        result["max_pending_work_items"] = poll_state.get("max_pending", "UNMEASURED")
        result["max_snapshot_bytes"] = poll_state.get("max_snapshot_bytes", "UNMEASURED")
        result["poll_latency_ms"] = {"p50": percentile(poll_state.get("poll_latency_ms", []), .5),
                                     "p90": percentile(poll_state.get("poll_latency_ms", []), .9)}
        result["reconnect_events"] = poll_state.get("reconnect_events", 0)
        result["first_text_latency_s"] = {
            "p50": percentile(list(dom_state.get("first_text", {}).values()), .5),
            "p90": percentile(list(dom_state.get("first_text", {}).values()), .9),
            "audio_seconds_observed": len(dom_state.get("first_text", {}))}
        result["label_latency_s"] = {
            "p50": percentile(list(dom_state.get("first_label", {}).values()), .5),
            "p90": percentile(list(dom_state.get("first_label", {}).values()), .9),
            "audio_seconds_observed": len(dom_state.get("first_label", {}))}
        for kind in ("first_text", "first_label"):
            values = dom_state.get(kind, {})
            result[kind + "_latency_by_minute"] = {
                str(minute): {"p50": percentile([v for sec, v in values.items() if sec // 60 == minute], .5),
                              "p90": percentile([v for sec, v in values.items() if sec // 60 == minute], .9),
                              "audio_seconds_observed": sum(sec // 60 == minute for sec in values)}
                for minute in range(math.ceil(spec["duration_s"] / 60))}
        (out / "session-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def expectations(scenario: str, sessions: list[dict], descriptor: dict,
                 server_alive: bool, process: dict, third: dict | None,
                 fault_count: int | str, smoke: bool, words_source: str) -> dict:
    frame_complete = all(not s["frame_errors"] and s["frames_accepted_per_lane"]["system"] == s["frames_planned"]
                         and s["frames_accepted_per_lane"]["microphone"] == s["frames_planned"] for s in sessions)
    limit = (descriptor.get("bounds") or {}).get("max_queue_depth")
    queue = (all(isinstance(s["max_pending_work_items"], int) and s["max_pending_work_items"] <= limit
                 for s in sessions) if isinstance(limit, int) else "UNMEASURED")
    audio_complete = all(isinstance(s.get("audio_duration_gap_s"), (float, int))
                         and abs(s["audio_duration_gap_s"]) <= 1.0 for s in sessions)
    terminal = all((s["finalization_status"] in ("final", "failed", "unavailable")
                    if s.get("terminal_action") == "stop" else s["session_status"] == "aborted")
                   and s["session_status"] in ("closed", "aborted", "failed") for s in sessions)
    visible = all(s["dom_samples"] > 0 and s["last_ui_status"] != "UNMEASURED" for s in sessions)
    checks = {"server_alive": server_alive, "all_frames_accepted": frame_complete,
              "queue_bounded_in_samples": queue, "retained_audio_matches_1s_tolerance": audio_complete,
              "terminal_after_action": terminal, "visible_status": visible,
              "process_sampled": process.get("samples", 0) > 0 if process.get("status") != "UNMEASURED" else "UNMEASURED"}
    if scenario != "abort-mid":
        checks["stop_terminal_within_35s"] = all(isinstance(s.get("action_to_terminal_s"), (float, int))
                                                 and s["action_to_terminal_s"] <= 35 for s in sessions)
    if scenario == "concurrent2":
        checks["third_rejected_capacity_409"] = bool(third and third.get("status") == 409 and
                                                      third.get("code") == "live_capacity_full")
    if scenario.startswith("faults-"):
        checks["fault_injected"] = fault_count > 0 if isinstance(fault_count, int) else "UNMEASURED"
    if scenario == "abort-mid":
        checks["abort_visible"] = all(s["session_status"] == "aborted" for s in sessions)
    verdict = ("PLUMBING_PASS" if smoke else "PASS") if all(v is True for v in checks.values()) else "FAIL"
    if scenario.startswith("faults-ws_") and words_source == "batch" and fault_count == 0:
        verdict = "PENDING_WORDS_SOURCE" if all(v is True for k, v in checks.items()
                                                  if k != "fault_injected") else "FAIL"
    return {"verdict": verdict, "checks": checks,
            "scope": "short plumbing smoke, not full scenario" if smoke else "full named scenario",
            "words_source": words_source}


def run(args) -> dict:
    scenario = args.scenario
    specs = audio_specs(scenario, args.seconds)
    base = args.base_url
    client = Client(base, ssl._create_unverified_context())
    client.call("POST", "/api/workspace/bootstrap")
    descriptor = client.call("GET", "/api/live/descriptor")["descriptor"]
    fault_count = "UNMEASURED"
    if scenario.startswith("faults-"):
        fault = scenario.removeprefix("faults-")
        if fault == "google_down":
            if not args.proxy_url:
                raise RuntimeError("google_down requires --proxy-url and proxy --down")
            try:
                httpx.get(args.proxy_url + "/__fault/status", verify=False, timeout=2)
                raise RuntimeError("google_down requires proxy --down with port unbound")
            except httpx.ConnectError:
                fault_count = 1
        else:
            if not args.proxy_url:
                raise RuntimeError("fault scenario requires --proxy-url")
            transport = FAULTS[fault]
            wire_fault = "connection_reset" if fault == "ws_connection_reset" else \
                         "stall" if fault == "ws_stall" else fault
            plan = {"schedule": [{"transport": transport, "ordinal": 1,
                                  "fault": wire_fault, "seconds": args.fault_seconds}], "seed": 7}
            response = httpx.post(args.proxy_url + "/__fault/plan", json=plan,
                                  verify=False, timeout=5)
            response.raise_for_status()
    created = []
    third = None
    process_state = {}
    monitor_stop = threading.Event()
    monitor = threading.Thread(target=process_watch,
        args=(args.server_pid, args.out / "process-samples.jsonl", monitor_stop, process_state), daemon=True)
    monitor.start()
    try:
        for spec in specs:
            response = client.call("POST", "/api/live/sessions",
                                   {"source_revision": descriptor["source_revision"]})
            created.append((response.get("id") or response["session_id"], spec))
        if scenario == "concurrent2":
            try:
                client.call("POST", "/api/live/sessions",
                            {"source_revision": descriptor["source_revision"]})
                third = {"status": 201, "code": None}
            except HTTPError as exc:
                try:
                    detail = json.loads(exc.read()).get("detail") or {}
                except ValueError:
                    detail = {}
                third = {"status": exc.code, "code": detail.get("code")}
        barrier = threading.Barrier(2) if scenario == "concurrent2" else None
        with ThreadPoolExecutor(max_workers=len(created)) as pool:
            futures = [pool.submit(run_session, base, client._jar, meeting, descriptor, spec,
                                   args.out / spec["name"], barrier, scenario == "abort-mid")
                       for meeting, spec in created]
            sessions = [future.result() for future in futures]
        try:
            client.call("GET", "/api/live/descriptor")
            server_alive = True
        except Exception:
            server_alive = False
        if scenario.startswith("faults-") and args.proxy_url and scenario != "faults-google_down":
            response = httpx.get(args.proxy_url + "/__fault/status", verify=False, timeout=5)
            fault_count = sum(response.json().get("injected", {}).values())
        checks = expectations(scenario, sessions, descriptor, server_alive,
                              process_state, third, fault_count, args.seconds is not None,
                              args.words_source)
        engines = [s.get("engine", "UNMEASURED") for s in sessions]
        measured_engines = all(isinstance(e, dict) for e in engines)
        if not args.launch_stub:
            checks["checks"]["engine_diagnostics_visible"] = measured_engines
            if not measured_engines:
                checks["verdict"] = "FAIL"
        total_calls = sum(e["calls_total"] for e in engines) if measured_engines else 0
        anomalies = ({"clamped": sum(e["timing_anomalies"].get("clamped", 0) for e in engines),
                      "dropped": sum(e["timing_anomalies"].get("dropped", 0) for e in engines)}
                     if measured_engines else "UNMEASURED")
        if scenario == "faults-google_down":
            errors = sum(sum(e["errors_by_code"].values()) for e in engines) if measured_engines else None
            checks["checks"]["provider_error_observed"] = errors > 0 if errors is not None else "UNMEASURED"
            if checks["checks"]["provider_error_observed"] is not True:
                checks["verdict"] = "FAIL"
        return {"scenario": scenario, "status": checks["verdict"],
                "expectations": checks, "sessions": sessions, "third_create": third,
                "fault_injections": fault_count, "process": process_state,
                "queue_limit": (descriptor.get("bounds") or {}).get("max_queue_depth"),
                "gemini_cost_usd": round(sum(e["cost_usd"] for e in engines), 6) if measured_engines else "UNMEASURED",
                "gemini_calls": total_calls if measured_engines else "UNMEASURED",
                "gemini_errors": sum(sum(e["errors_by_code"].values()) for e in engines) if measured_engines else "UNMEASURED",
                "retries": sum(sum(e["retries_by_code"].values()) for e in engines) if measured_engines else "UNMEASURED",
                "timing_anomalies": anomalies,
                "timing_anomalies_per_call": ({"clamped": round(anomalies["clamped"] / total_calls, 6),
                                               "dropped": round(anomalies["dropped"] / total_calls, 6)}
                                              if measured_engines and total_calls else "UNMEASURED"),
                "degraded_path_activations": (sum(e["degraded_path_activations"] for e in engines)
                                              if measured_engines else "UNMEASURED")}
    finally:
        monitor_stop.set()
        monitor.join(timeout=10)
        # Cleanup any meeting left active by a failed scenario.
        for meeting, _ in created:
            try:
                snapshot = client.call("GET", f"/api/live/sessions/{meeting}/snapshot")
                status = ((snapshot.get("snapshot") or {}).get("session") or {}).get("status")
                if status == "active":
                    client.call("POST", f"/api/live/sessions/{meeting}/abort",
                                {"reason": "stress_cleanup"})
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True,
                        choices=["long60", "concurrent2", "silence10", "music5", "overlap",
                                 "manyspk", "stop-early", "abort-mid"] +
                                ["faults-" + name for name in FAULTS])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--base-url")
    source.add_argument("--launch-stub", action="store_true")
    parser.add_argument("--proxy-url", help="local HTTPS fault proxy control URL for faults-* scenarios")
    parser.add_argument("--server-pid", type=int, help="local stack PID for RSS/CPU/fd samples")
    parser.add_argument("--fault-seconds", type=float, default=3)
    parser.add_argument("--words-source", choices=["batch", "live"], default="batch",
                        help="selected product word source; WS faults become mandatory with live")
    parser.add_argument("--seconds", type=float, help="short plumbing smoke override")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or EVIDENCE not in args.out.resolve().parents:
        parser.error("--out must be a new directory under evidence/P64")
    if args.base_url and not args.base_url.startswith("https://127.0.0.1:1852"):
        parser.error("local HTTPS URL in assigned 18520-18529 range required")
    if args.proxy_url and not args.proxy_url.startswith("https://127.0.0.1:1852"):
        parser.error("local HTTPS proxy in assigned range required")
    if args.seconds is not None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    args.out.mkdir(parents=True)
    result = {"scenario": args.scenario, "status": "INCOMPLETE"}
    try:
        if args.launch_stub:
            with local_stub_stack(args.out) as (base, pid):
                args.base_url, args.server_pid = base, pid
                result = run(args)
        else:
            result = run(args)
    except Exception as exc:
        result = {"scenario": args.scenario, "status": "HARNESS_ERROR",
                  "error_type": type(exc).__name__, "error": str(exc)[:400]}
    (args.out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if result["status"] not in ("PASS", "PLUMBING_PASS", "PENDING_WORDS_SOURCE"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
