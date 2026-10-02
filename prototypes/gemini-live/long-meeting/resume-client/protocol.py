"""Throwaway candidate at real Phase2 route seams; never imported by product.

S1 deliberately measures heartbeat replacement without frame fencing/state return.
S2 serializes takeover and capture mutations, with compare-and-swap page identity.
Private state reads here identify the small public accessors a product change needs.
"""
import asyncio
import json
from collections import defaultdict

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from moss_transcribe_diarize.app.live_helper_presence import HelperHeartbeat


class ResumeProtocol:
    def __init__(self, app, mode, clock):
        self.app, self.mode, self.clock = app, mode, clock
        self.writers = {}
        self.receipts = {}
        self.interruptions = defaultdict(list)
        self.last_takeover = {}
        self.anchors = {}
        self.last_ends = defaultdict(dict)
        self.locks = defaultdict(asyncio.Lock)
        app.middleware("http")(self.capture_mutation)
        app.post("/api/live/sessions/{session_id}/resume")(self.resume)

    def state(self, sid):
        st = self.app.state
        session = st.live_v2_sessions.get(sid)
        mixer = st.live_v2_mixers.get(sid)
        return {
            "session_id": sid,
            "descriptor": self.app.state.phase2_live.runtime.descriptor.to_dict(),
            "instance_id": self.writers[sid],
            "lanes": {
                lane.value: {
                    **value.to_dict(),
                    "last_capture_end_timestamp_ns": self.last_ends[sid].get(lane.value, 0),
                    "resume_device_epoch": (value.current_device_epoch or 0) + 1,
                }
                for lane, value in session.snapshot().lanes.items()
            },
            "capture_now_ns": max(
                self.clock() - self.anchors.get(sid, self.clock()),
                max(self.last_ends[sid].values(), default=0),
                mixer._cursor_ns or 0,
            ),
            "mixed_cursor_ns": mixer._cursor_ns,
            "mixed_samples": st.phase2_live.runtime.snapshot(sid).session.accepted_samples,
            "lease_remaining_ns": st.live_helper_failures._sessions[sid].deadline_monotonic_ns - self.clock(),
            "heartbeat_next_sequence": st.live_helper_presence.snapshot(sid).sequence + 1,
            "heartbeat_next_monotonic_ns": st.live_helper_presence.snapshot(sid).sent_monotonic_ns + 1,
        }

    async def takeover(self, request, sid, body):
        st = self.app.state
        # "heartbeat" uses the existing strict origin-sign-in mutation authority.
        authority = await st.live_transport_control._adapter.authorize(request, "heartbeat", sid)
        st.live_transport_control._adapter.validate_mutation(authority)
        lease = st.live_helper_failures._sessions.get(sid)
        if lease is None or self.clock() >= lease.deadline_monotonic_ns:
            raise HTTPException(409, {"code": "resume_lease_expired"})
        if self.mode == "S2":
            pair = (body["expected_instance_id"], body["instance_id"])
            if self.last_takeover.get(sid) == pair and self.writers.get(sid) == pair[1]:
                return self.state(sid)  # Lost response retry: no second takeover/renewal.
            if pair[0] is not None and pair[0] != self.writers.get(sid):
                raise HTTPException(409, {"code": "capture_writer_mismatch"})
        if body["automatic"] and self.clock() - self.receipts.get(sid, 0) < 3_000_000_000:
            raise HTTPException(409, {"code": "capture_page_alive"})
        presence = st.live_helper_presence.snapshot(sid)
        old_sent = presence.sent_monotonic_ns
        heartbeat = {"schema": "moss-live-helper-health.v1", "instance_id": body["instance_id"],
            "helper_version": "offline-protocol", "state": "capturing",
            "lanes": {lane: {"state": "capturing", "device_epoch": 0, "dropped_frames": 0,
                "discontinuities": 0, "failure_code": None} for lane in ("system", "microphone")}}

        heartbeat["sequence"] = presence.sequence + 1
        heartbeat["sent_monotonic_ns"] = old_sent + 1
        parsed = HelperHeartbeat.from_dict(heartbeat)
        # Preserve global heartbeat ordering; switching page permits its clock to restart.
        st.live_helper_presence.release(sid)
        current = st.live_helper_presence.observe(sid, parsed)
        await st.live_helper_failures.observe(sid, current)
        self.writers[sid] = heartbeat["instance_id"]
        if self.mode == "S2": self.last_takeover[sid] = pair
        self.interruptions[sid].append({"start_sample": st.phase2_live.runtime.snapshot(sid).session.accepted_samples, "end_sample": None})
        return self.state(sid)

    async def resume(self, session_id: str, request: Request):
        async with self.locks[session_id]:
            try:
                return await self.takeover(request, session_id, await request.json())
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc

    async def capture_mutation(self, request, call_next):
        parts = request.url.path.split("/")
        if request.method == "GET" and ((len(parts) == 6 and parts[-1] == "snapshot") or (len(parts) == 4 and parts[2] == "meetings")):
            sid = parts[-2] if parts[-1] == "snapshot" else parts[-1]
            response = await call_next(request)
            if self.interruptions.get(sid) and response.status_code == 200:
                raw = b"".join([chunk async for chunk in response.body_iterator])
                value = json.loads(raw)
                if parts[-1] == "snapshot": value["interruptions"] = self.interruptions[sid]
                elif value.get("transcript") is not None: value["transcript"]["interruptions"] = self.interruptions[sid]
                return JSONResponse(value)
            return response
        if len(parts) != 6 or parts[1:4] != ["api", "live", "sessions"] or request.method != "POST":
            return await call_next(request)
        sid, operation = parts[4:]
        if operation not in {"frames", "heartbeat", "stop", "abort"}:
            return await call_next(request)
        async with self.locks[sid]:
            writer = request.headers.get("X-Moss-Capture-Instance")
            if self.mode == "S2":
                try:
                    authority = await self.app.state.live_transport_control._adapter.authorize(
                        request, "frame" if operation == "frames" else operation, sid)
                    self.app.state.live_transport_control._adapter.validate_mutation(authority)
                except HTTPException as exc:
                    return JSONResponse({"detail": exc.detail}, exc.status_code)
            if self.mode == "S2" and sid in self.writers and writer != self.writers[sid]:
                return JSONResponse({"detail": "capture replaced; view meeting", "code": "capture_replaced"}, 409)
            body = await request.json() if operation in {"heartbeat", "frames"} else None
            if False:
                try:
                    await self.takeover(request, sid, {"heartbeat": body})
                except HTTPException as exc:
                    return JSONResponse({"detail": exc.detail}, exc.status_code)
                return JSONResponse({"helper_presence": self.app.state.live_helper_presence.snapshot(sid).to_dict()})
            if operation == "heartbeat" and self.mode == "S2" and body["instance_id"] != writer:
                return JSONResponse({"detail": "heartbeat page/header mismatch"}, 409)
            response = await call_next(request)
            if response.status_code == 200 and operation == "heartbeat":
                self.writers.setdefault(sid, body["instance_id"])
                self.receipts[sid] = self.clock()
            if response.status_code == 200 and operation == "frames":
                self.last_ends[sid][body["lane"]] = max(
                    self.last_ends[sid].get(body["lane"], 0), body["capture_end_timestamp_ns"])
                if self.interruptions.get(sid) and self.interruptions[sid][-1]["end_sample"] is None:
                    gap = self.interruptions[sid][-1]
                    gap["end_sample"] = max(gap["start_sample"], int(body["capture_timestamp_ns"] * 16000 / 1e9))
                # Synthetic driver aligns receipt with capture end. Browser transport
                # latency remains an explicitly unmeasured accuracy term.
                self.anchors.setdefault(sid, self.clock() - body["capture_end_timestamp_ns"])
            return response
