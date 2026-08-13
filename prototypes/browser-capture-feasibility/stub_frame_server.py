#!/usr/bin/env python3
"""PROTOTYPE — throwaway stub server for the browser capture pipeline harness.

Run:  python3 prototypes/browser-capture-feasibility/stub_frame_server.py
Then open http://127.0.0.1:8899/ in Chrome.

Serves the capture page + worklet, accepts v2-shaped JSON frames, and exposes
GET /verdict with a full analysis (sequence integrity, PCM16 decode, per-lane
dominant tone via Goertzel, capture-clock spacing, arrival cadence split by
tab visibility). Stdlib only. State in memory. No persistence.
"""
from __future__ import annotations

import base64
import json
import math
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 8899
SAMPLE_RATE = 16_000
# Deliberately differs from the historical 8k/16k frame sizes so browser
# evidence fails if the page falls back to either old frame-size constant.
FRAME_SAMPLES = 3_200
MAX_FRAME_SAMPLES = 6_400
DESCRIPTOR = {
    "descriptor": {
        "sample_rate": SAMPLE_RATE,
        "frame_samples": FRAME_SAMPLES,
        "bounds": {"max_frame_samples": MAX_FRAME_SAMPLES},
    },
    "negotiation": {"selected_protocol_version": 2},
}
STUB_CAPTURE_BEARER = "prototype-stub-capture-bearer"
STUB_SESSION_ID = "prototype-stub-session"
FRAME_KEYS = frozenset(
    {
        "lane",
        "sequence",
        "capture_timestamp_ns",
        "device_epoch",
        "pcm_base64",
        "sample_count",
        "sample_rate",
        "silent",
        "discontinuity",
    }
)
TONE_PAGE = """<!doctype html><meta charset=utf-8><title>997 Hz tone</title>
<body style="font:16px system-ui;padding:2rem">
<h1>997 Hz test tone</h1><button id=b style="font-size:1.5rem">Play tone</button>
<script>document.getElementById('b').onclick=async()=>{const c=new AudioContext();
const o=c.createOscillator();o.frequency.value=997;const g=c.createGain();g.gain.value=0.3;
o.connect(g).connect(c.destination);o.start();await c.resume();
document.body.style.background='#cfc';document.title='997 Hz PLAYING'};</script>"""

STATE_LOCK = threading.Lock()
STATE: dict = {
    "session_creates": 0,
    "lanes": {},
    "telemetry": {},
    "frame_rejections": [],
    "phases": [],
    "probes": [],
    "started_wall": time.time(),
}


def lane_state(lane: str) -> dict:
    return STATE["lanes"].setdefault(
        lane,
        {
            "frames": 0,
            "sequences": [],
            "sample_counts": {},
            "sample_rates": {},
            "epochs": {},
            "silent_frames": 0,
            "discontinuities": 0,
            "pcm_min": 0,
            "pcm_max": 0,
            "rms": [],
            "goertzel_997": [],
            "goertzel_440": [],
            "ts_ns": [],
            "arrival_wall": [],
            "frame_key_sets": {},
            "decode_errors": [],
        },
    )


def goertzel_ratio(samples: list[float], freq: float, rate: float) -> float:
    w = 2.0 * math.pi * freq / rate
    cw = 2.0 * math.cos(w)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + cw * s1 - s2
        s2, s1 = s1, s0
    power = s1 * s1 + s2 * s2 - cw * s1 * s2
    total = sum(x * x for x in samples) or 1e-12
    return power / (total * len(samples) / 2.0)


def ingest_frame(body: dict) -> tuple[int, dict]:
    actual_keys = set(body)
    if actual_keys != FRAME_KEYS:
        missing = sorted(FRAME_KEYS - actual_keys)
        unknown = sorted(actual_keys - FRAME_KEYS)
        rejection = {"missing": missing, "unknown": unknown}
        with STATE_LOCK:
            STATE["frame_rejections"].append(rejection)
        return 400, {"error": "invalid frame fields", **rejection}
    lane = body.get("lane")
    if lane not in ("system", "microphone"):
        return 400, {"error": f"bad lane {lane!r}"}
    raw = base64.b64decode(body["pcm_base64"])
    n = len(raw) // 2
    ints = struct.unpack(f"<{n}h", raw)
    floats = [v / 32768.0 for v in ints]
    rms = math.sqrt(sum(x * x for x in floats) / max(1, n))
    with STATE_LOCK:
        st = lane_state(lane)
        st["frames"] += 1
        st["sequences"].append(body.get("sequence"))
        st["sample_counts"][str(body.get("sample_count"))] = st["sample_counts"].get(str(body.get("sample_count")), 0) + 1
        st["sample_rates"][str(body.get("sample_rate"))] = st["sample_rates"].get(str(body.get("sample_rate")), 0) + 1
        st["epochs"][str(body.get("device_epoch"))] = st["epochs"].get(str(body.get("device_epoch")), 0) + 1
        st["silent_frames"] += 1 if body.get("silent") else 0
        st["discontinuities"] += 1 if body.get("discontinuity") else 0
        st["pcm_min"] = min(st["pcm_min"], min(ints)) if ints else st["pcm_min"]
        st["pcm_max"] = max(st["pcm_max"], max(ints)) if ints else st["pcm_max"]
        st["rms"].append(round(rms, 5))
        st["goertzel_997"].append(round(goertzel_ratio(floats, 997.0, SAMPLE_RATE), 4))
        st["goertzel_440"].append(round(goertzel_ratio(floats, 440.0, SAMPLE_RATE), 4))
        st["ts_ns"].append(int(body.get("capture_timestamp_ns", -1)))
        st["arrival_wall"].append(time.time())
        key_set = ",".join(sorted(actual_keys))
        st["frame_key_sets"][key_set] = st["frame_key_sets"].get(key_set, 0) + 1
        if n != body.get("sample_count"):
            st["decode_errors"].append(f"decoded {n} != declared {body.get('sample_count')}")
    return 200, {"accepted": True, "lane": lane, "sequence": body.get("sequence")}


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = min(len(sorted_vals) - 1, max(0, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def analyze() -> dict:
    with STATE_LOCK:
        snap = json.loads(json.dumps(STATE))  # deep copy of plain data
    out = {
        "phases": snap["phases"],
        "probes": snap["probes"],
        "frame_contract": {
            "expected_keys": sorted(FRAME_KEYS),
            "rejections": snap["frame_rejections"],
        },
        "lanes": {},
        "checks": {},
    }
    for lane, st in snap["lanes"].items():
        seqs = [s for s in st["sequences"] if s is not None]
        gaps = sum(1 for a, b in zip(seqs, seqs[1:]) if b != a + 1)
        ts = st["ts_ns"]
        ts_deltas = sorted(b - a for a, b in zip(ts, ts[1:]))
        arr = st["arrival_wall"]
        telemetry = snap["telemetry"].get(lane, {})
        visibility = [telemetry.get(str(sequence), {}).get("client_visibility", "?") for sequence in seqs]
        arr_deltas = list(zip(visibility[1:], (b - a for a, b in zip(arr, arr[1:]))))
        by_vis: dict[str, list[float]] = {}
        for vis, d in arr_deltas:
            by_vis.setdefault(vis, []).append(d)
        cadence = {
            vis: {
                "n": len(ds),
                "p50_ms": round(percentile(sorted(ds), 0.5) * 1e3, 1),
                "p95_ms": round(percentile(sorted(ds), 0.95) * 1e3, 1),
                "max_ms": round(max(ds) * 1e3, 1),
            }
            for vis, ds in by_vis.items()
        }
        g997 = st["goertzel_997"]
        g440 = st["goertzel_440"]
        out["lanes"][lane] = {
            "frames": st["frames"],
            "seq_first_last": [seqs[0], seqs[-1]] if seqs else None,
            "seq_gaps": gaps,
            "sample_counts": st["sample_counts"],
            "sample_rates": st["sample_rates"],
            "epochs": st["epochs"],
            "silent_frames": st["silent_frames"],
            "pcm_range": [st["pcm_min"], st["pcm_max"]],
            "rms_mean": round(sum(st["rms"]) / len(st["rms"]), 4) if st["rms"] else None,
            "goertzel_997_mean": round(sum(g997) / len(g997), 4) if g997 else None,
            "goertzel_440_mean": round(sum(g440) / len(g440), 4) if g440 else None,
            "ts_delta_ns_min_max": [ts_deltas[0], ts_deltas[-1]] if ts_deltas else None,
            "arrival_cadence_by_visibility": cadence,
            "frame_key_sets": st["frame_key_sets"],
            "out_of_band_telemetry_frames": len(telemetry),
            "decode_errors": st["decode_errors"][:5],
        }
    lanes = out["lanes"]
    sys_l, mic_l = lanes.get("system"), lanes.get("microphone")
    checks = out["checks"]
    checks["both_lanes_present"] = bool(sys_l and mic_l)
    if sys_l and mic_l:
        checks["no_seq_gaps"] = sys_l["seq_gaps"] == 0 and mic_l["seq_gaps"] == 0
        checks["all_frames_match_descriptor"] = (
            set(sys_l["sample_counts"]) == {str(FRAME_SAMPLES)} == set(mic_l["sample_counts"])
            and set(sys_l["sample_rates"]) == {str(SAMPLE_RATE)} == set(mic_l["sample_rates"])
        )
        # A descriptor-selected frame can put 997 Hz between DFT bins, so use a
        # dominance test rather than an absolute-purity threshold.
        checks["system_is_997hz"] = (sys_l["goertzel_997_mean"] or 0) > 0.25 and (
            (sys_l["goertzel_997_mean"] or 0) > 10 * (sys_l["goertzel_440_mean"] or 0)
        )
        checks["microphone_is_440hz"] = (mic_l["goertzel_440_mean"] or 0) > 0.5 and (
            (mic_l["goertzel_440_mean"] or 0) > 10 * (mic_l["goertzel_997_mean"] or 0)
        )
        checks["sine_amplitude_sane"] = all(
            l["rms_mean"] and 0.25 < l["rms_mean"] < 0.45 for l in (sys_l, mic_l)
        )
        expected_delta_ns = FRAME_SAMPLES * 1_000_000_000 // SAMPLE_RATE
        checks["capture_clock_matches_descriptor"] = all(
            l["ts_delta_ns_min_max"] == [expected_delta_ns, expected_delta_ns] for l in (sys_l, mic_l)
        )
        expected_key_set = ",".join(sorted(FRAME_KEYS))
        checks["exact_nine_frame_keys"] = all(
            set(l["frame_key_sets"]) == {expected_key_set} for l in (sys_l, mic_l)
        )
        checks["out_of_band_telemetry_complete"] = all(
            l["out_of_band_telemetry_frames"] == l["frames"] for l in (sys_l, mic_l)
        )
        hidden = [l["arrival_cadence_by_visibility"].get("hidden") for l in (sys_l, mic_l)]
        checks["hidden_tab_cadence_ok"] = all(h and h["p95_ms"] < 1500 for h in hidden) if all(hidden) else "no hidden phase measured"
        checks["no_decode_errors"] = not sys_l["decode_errors"] and not mic_l["decode_errors"]
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, (HERE / "capture_pipeline_page.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/framer_worklet.js":
            self._send(200, (HERE / "framer_worklet.js").read_bytes(), "text/javascript; charset=utf-8")
        elif path == "/tone":
            self._send(200, TONE_PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/prototype/verdict":
            self._send(200, json.dumps(analyze(), indent=2).encode(), "application/json")
        elif path == "/prototype/bootstrap":
            self._send(200, json.dumps({"capture_bearer": STUB_CAPTURE_BEARER}).encode(), "application/json")
        elif path == "/api/live/descriptor":
            self._send(200, json.dumps(DESCRIPTOR).encode(), "application/json")
        else:
            self._send(404, b"{}", "application/json")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, b'{"error":"bad json"}', "application/json")
        if self.path == "/api/live/sessions":
            if self.headers.get("Authorization") != f"Bearer {STUB_CAPTURE_BEARER}":
                return self._send(401, b'{"error":"missing bearer"}', "application/json")
            with STATE_LOCK:
                STATE["session_creates"] += 1
            response = {
                "id": STUB_SESSION_ID,
                "view_token": "prototype-stub-view-bearer",
                "descriptor": DESCRIPTOR["descriptor"],
            }
            return self._send(200, json.dumps(response).encode(), "application/json")
        if self.path == f"/api/live/sessions/{STUB_SESSION_ID}/frames":
            if self.headers.get("Authorization") != f"Bearer {STUB_CAPTURE_BEARER}":
                return self._send(401, b'{"error":"missing bearer"}', "application/json")
            code, resp = ingest_frame(body)
            return self._send(code, json.dumps(resp).encode(), "application/json")
        if self.path == "/prototype/telemetry":
            lane = body.get("lane")
            sequence = body.get("sequence")
            if lane not in ("system", "microphone") or not isinstance(sequence, int):
                return self._send(400, b'{"error":"bad telemetry identity"}', "application/json")
            with STATE_LOCK:
                STATE["telemetry"].setdefault(lane, {})[str(sequence)] = body
            return self._send(200, b"{}", "application/json")
        if self.path == "/prototype/phase":
            with STATE_LOCK:
                STATE["phases"].append({"t": round(time.time() - STATE["started_wall"], 2), **body})
            return self._send(200, b"{}", "application/json")
        if self.path == "/prototype/probes":
            with STATE_LOCK:
                STATE["probes"] = body.get("probes", [])
            return self._send(200, b"{}", "application/json")
        if self.path == "/prototype/reset":
            # Echo the verdict being discarded so a mis-ordered reset (after a run,
            # before reading /verdict) cannot silently destroy the evidence.
            prior = analyze()
            with STATE_LOCK:
                STATE["lanes"].clear()
                STATE["telemetry"].clear()
                STATE["frame_rejections"].clear()
                STATE["phases"].clear()
                STATE["started_wall"] = time.time()
            return self._send(200, json.dumps({"reset": True, "cleared": prior}).encode(), "application/json")
        return self._send(404, b"{}", "application/json")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"PROTOTYPE stub listening on http://127.0.0.1:{PORT}/  (Ctrl-C to stop)")
    server.serve_forever()
