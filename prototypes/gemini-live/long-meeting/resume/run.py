"""Offline real-route measurement. No production writes, provider construction or keys.

Run from worktree root: ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/long-meeting/resume/run.py
"""
import asyncio
import base64
import json
import math
import struct
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/phase2"), str(ROOT / "tests/gemini"), str(ROOT / "tests")]
from fastapi.testclient import TestClient
from test_owner_bound_live_meeting import provision, make_app, session, heartbeat
from test_gemini_live_runtime import descriptor
from test_live_helper_failure import FakeTimer
from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiLiveRuntime, ScriptedGeminiEngine, GeminiRolling, GeminiBase, GeminiSegment,
)
from protocol import ResumeProtocol

EV = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume")
RATE, NS, N, M = 16000, 1000000000, 4, 4
SETTINGS = {"transcription": {"vendor": "gemini", "model": "gemini-3.5-transcribe", "api_key": "offline-prototype-stub"}, "cleanup_after_stop": False}


class Clock:
    def __init__(self): self.now = 10 * NS
    def __call__(self): return self.now


class OfflineEngine(ScriptedGeminiEngine):
    def __init__(self, publish):
        super().__init__(publish, batches=[], terminal=())
        self.audio_blocks = []
    def push_audio(self, start_sample, pcm16):
        count = len(pcm16) // 2
        values = struct.unpack(f"<{count}h", pcm16)
        self._publish(GeminiBase(start_sample + count, ()))
        rows = ()
        if any(values):
            self.audio_blocks.append([start_sample, start_sample + count])
            rows = (GeminiSegment(start_sample, start_sample + count, "synthetic audible block", "speaker-0001"),)
        self._publish(GeminiRolling(start_sample, start_sample + count, rows))
    async def drain_tail(self, deadline): return True


def build_app(directory):
    directory.mkdir(parents=True, exist_ok=False)
    database = directory / "meeting.sqlite"
    cookies = asyncio.run(provision(database))
    engines = []
    def runtime():
        d = descriptor(tape_bytes=16 * 1024 * 1024)
        d = replace(d, frame_samples=8000, bounds=replace(d.bounds, max_retained_samples=960000, max_events=1024))
        def factory(_sid, publish, _usage, _settings):
            e = OfflineEngine(publish); engines.append(e); return e
        return GeminiLiveRuntime(descriptor=d, engine_factory=factory, tape_storage_root=directory / "tapes")
    return make_app(database, lease_seconds=120, live_runtime_factory=runtime), cookies, engines


def hb(instance, sequence=0, epoch=0):
    value = heartbeat(sequence)
    value["instance_id"] = instance
    for lane in value["lanes"].values(): lane["device_epoch"] = epoch
    return value


def frame(lane, sequence, start, epoch=0, discontinuity=False):
    count = RATE // 2
    pcm = b"\0\0" * count if lane == "microphone" else struct.pack(f"<{count}h", *(
        int(6000 * math.sin(2 * math.pi * 440 * i / RATE)) for i in range(count)))
    return {"lane": lane, "sequence": sequence, "capture_timestamp_ns": int(start * NS),
        "capture_end_timestamp_ns": int((start + .5) * NS), "device_epoch": epoch,
        "sample_count": count, "sample_rate": RATE, "silent": lane == "microphone",
        "discontinuity": discontinuity, "pcm_base64": base64.b64encode(pcm).decode()}


def wait_meeting(client, sid, status):
    for _ in range(100):
        value = client.get(f"/api/meetings/{sid}").json()
        if value["status"] == status: return value
        time.sleep(.02)
    raise AssertionError(value)


def run_cell(mode, gap, directory, continuation=M):
    app, cookies, engines = build_app(directory)
    clock, timer = Clock(), FakeTimer()
    protocol = ResumeProtocol(app, mode, clock) if mode != "baseline" else None
    record = {"mode": mode, "gap_seconds": gap, "continuation_seconds": continuation, "events": []}
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, cookies["a"])
        st = app.state
        st.live_helper_presence._monotonic_ns = clock
        st.live_helper_failures._monotonic_ns = clock
        st.live_helper_failures._timer = timer
        sid = client.post("/api/live/sessions", json={"engine_settings": SETTINGS}).json()["id"]
        base = f"/api/live/sessions/{sid}"
        old = {"X-Moss-Capture-Instance": "page-original"}
        new = {"X-Moss-Capture-Instance": "page-new"}
        def event(label, response):
            record["events"].append({"action": label, "status": response.status_code,
                "body": response.json()})
            return response
        event("initial heartbeat", client.post(base + "/heartbeat", json=hb("page-original"), headers=old))
        origin = clock.now
        for i in range(N * 2):
            clock.now = origin + int((i + 1) * .5 * NS)
            for lane in ("system", "microphone"):
                r = client.post(base + "/frames", json=frame(lane, i, i * .5), headers=old)
                assert r.status_code == 200, r.text
        event("last original heartbeat", client.post(base + "/heartbeat", json=hb("page-original", 1), headers=old))
        event("name speaker", client.put(f"/api/meetings/{sid}/speakers/speaker-0001/name", json={"label": "Alex"}))
        record["before"] = client.get(base + "/snapshot").json()
        record["before_engine_id"] = id(engines[0])
        clock.now += gap * NS
        if gap >= 120:
            client.portal.call(timer.scheduled[-1][1].fire)
            record["expired"] = wait_meeting(client, sid, "interrupted")
        if mode == "baseline":
            takeover = event("new heartbeat", client.post(base + "/heartbeat", json=hb("page-new"), headers=new))
            event("reset frame", client.post(base + "/frames", json=frame("system", N * 2, 0), headers=new))
            if gap < 120:
                event("stop baseline", client.post(base + "/stop", json={"deadline": 10}, headers=old))
            record["resume_status"] = takeover.status_code
            return record
        if mode == "S1":
            takeover = event("takeover heartbeat", client.post(base + "/heartbeat", json=hb("page-new"),
                headers={**new, "X-Moss-Takeover": "1"}))
            state = protocol.state(sid) if takeover.status_code == 200 else None
            record["S1_state_source"] = "prototype-private read; NOT returned by heartbeat route"
        else:
            # Origin cookie, not just account, remains necessary.
            session(client, cookies["b"])
            event("different browser/account resume", client.post(base + "/resume", headers=new,
                json={"expected_instance_id": "page-original", "heartbeat": hb("page-new")}))
            session(client, cookies["a"])
            takeover = event("resume", client.post(base + "/resume", headers=new,
                json={"expected_instance_id": "page-original", "heartbeat": hb("page-new")}))
            state = takeover.json() if takeover.status_code == 200 else None
        record["resume_status"] = takeover.status_code
        if state is None:
            record["final_status"] = wait_meeting(client, sid, "interrupted")["status"]
            record["frames_accepted_after_resume"] = 0
            record["archives"] = [p.name for p in (directory / "meetings/sub-a" / sid).glob("*.mp3")]
            return record
        record["adopted"] = state
        # An awakened old page uses the correct next sequence/time: without fencing
        # it can submit new audio, not merely replay a previous acknowledgement.
        event("old heartbeat", client.post(base + "/heartbeat", headers=old, json=hb("page-original", 2)))
        event("old next frame", client.post(base + "/frames", headers=old,
            json=frame("system", N * 2, N + gap, 0)))
        if mode == "S2":
            for operation in ("stop", "abort"):
                event("old " + operation, client.post(base + "/" + operation, headers=old,
                    json={"deadline": 1} if operation == "stop" else {"reason": "old page"}))
            event("stale repeat takeover", client.post(base + "/resume", headers=old,
                json={"expected_instance_id": "page-original", "heartbeat": hb("page-original", 2)}))
        sequences = {k: v["next_sequence"] for k, v in state["lanes"].items()}
        if mode == "S1": sequences["system"] += 1  # old writer really consumed it
        accepted, max_retained, first = 0, 0, set(sequences)
        first_live_resumed_at = None
        for i in range(continuation * 2):
            start = N + gap + i * .5
            clock.now = origin + int((start + .5) * NS)
            for lane in sequences:
                r = client.post(base + "/frames", headers=new,
                    json=frame(lane, sequences[lane], start, 1, lane in first))
                if r.status_code == 200:
                    sequences[lane] += 1; accepted += 1; first.discard(lane)
                else:
                    event("new frame failed", r)
                    break
            snap = client.get(base + "/snapshot").json()
            max_retained = max(max_retained, *(v["retained_samples"] for v in snap["v2_session"]["lanes"].values()))
            if first_live_resumed_at is None and any(
                row["start_sample"] >= (N + gap) * RATE for row in snap["snapshot"]["session"]["effective_transcript"]):
                first_live_resumed_at = (i + 1) * .5
        record["live_after"] = client.get(base + "/snapshot").json()
        before_stop = st.phase2_live.audio_stages.path("sub-a", sid)
        record["stage_bytes_before_stop"] = before_stop.stat().st_size
        stop = event("new stop", client.post(base + "/stop", headers=new, json={"deadline": 20}))
        meeting = wait_meeting(client, sid, "completed") if stop.status_code == 200 else client.get(f"/api/meetings/{sid}").json()
        record.update(final_status=meeting["status"], meeting=meeting,
            frames_accepted_after_resume=accepted, max_retained_samples=max_retained,
            first_live_resumed_row_after_seconds=first_live_resumed_at,
            same_engine=id(engines[0]) == record["before_engine_id"], engine_count=len(engines))
        record["final_snapshot"] = client.get(base + "/snapshot").json()
        paths = list((directory / "meetings/sub-a" / sid).glob("*.mp3"))
        record["archives"] = [p.name for p in paths]
        if paths:
            pcm = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(paths[0]), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"])
            record["decoded_mp3_seconds"] = len(pcm) / 2 / RATE
            values = struct.unpack(f"<{len(pcm)//2}h", pcm)
            # Exclude 100 ms codec boundary smearing at each edge.
            gap_values = values[int((N + .1) * RATE):int((N + gap - .1) * RATE)]
            record["gap_interior_max_amplitude"] = max(map(abs, gap_values), default=0)
            record["gap_interior_seconds"] = len(gap_values) / RATE
        record["full_state_after_stop"] = {
            "capture_writer": protocol.writers[sid], "anchor_ns": protocol.anchors.get(sid),
            "last_capture_ends": protocol.last_ends[sid], "clock_now_ns": clock.now,
            "lease_released": sid not in st.live_helper_failures._sessions,
            "mixed_engine_audio_blocks": engines[0].audio_blocks,
        }
    return record


def main():
    run_dir = EV / ("runs-" + time.strftime("%Y%m%d-%H%M%S"))
    run_dir.mkdir(parents=True)
    cells = [("baseline", 5, M), ("S1", 90, M), *(("S2", g, M) for g in (5, 30, 90, 119, 125)),
             ("S2", 119, 45)]
    results = []
    for mode, gap, continuation in cells:
        name = f"{mode}-{gap}-continue{continuation}"
        value = run_cell(mode, gap, run_dir / name, continuation)
        results.append(value)
        (run_dir / f"{name}.json").write_text(json.dumps(value, indent=2))
        print(json.dumps(value, indent=2), flush=True)
    (run_dir / "matrix.json").write_text(json.dumps(results, indent=2))
    (EV / "LATEST.txt").write_text(str(run_dir) + "\n")
    print("EVIDENCE", run_dir, flush=True)


if __name__ == "__main__": main()
