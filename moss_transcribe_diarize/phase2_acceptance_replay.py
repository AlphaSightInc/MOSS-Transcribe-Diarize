"""Account-cookie HTTP Adapter for the retained Live replay evaluator."""

from __future__ import annotations

import asyncio
import base64
import json
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .app.live_session import AudioFrame, LIVE_SAMPLE_RATE
from .app.live_service_runtime import LiveServiceEvent, LiveServiceFrameResult, LiveServiceSnapshot
from .live_service_replay import (
    ServiceReplayIdentityCommitFailure,
    ServiceReplayProviderConfigFailure,
    ServiceReplayTransportFailure,
    _descriptor_from_dict,
    _event_from_dict,
    _frame_ack_from_dict,
    _snapshot_from_dict,
)


# Matches ControlPanel.stopCapture -> CaptureClient.stop(5), in seconds, not a timestamp.
ACCEPTANCE_STOP_DEADLINE_SECONDS = 5.0

SESSION_COOKIE = "__Host-moss_session"
HELPER_SCHEMA = "moss-live-helper-health.v1"


class AccountReplayTransportFailure(ServiceReplayTransportFailure):
    """A retryable Account transport refusal with its HTTP class retained."""

    def __init__(self, message: str, *, http_status: int | None):
        super().__init__(message)
        self.http_status = http_status


# Measurement clients own helper presence even while waiting for unrelated work.
HELPER_HEARTBEAT_INTERVAL_SECONDS = 5.0
HELPER_HEARTBEAT_TIMEOUT_SECONDS = 5.0


class AcceptanceHelperLease:
    """One serialized heartbeat stream, independent of blocking measurement requests."""

    def __init__(self, post):
        self._post = post
        self._sequence = 0
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: Exception | None = None

    def start(self) -> None:
        self.send()
        self._thread = threading.Thread(target=self._run, name="acceptance-helper", daemon=True)
        self._thread.start()

    def send(self) -> None:
        with self._lock:
            if self._closed.is_set():
                if self.last_error is not None:
                    raise self.last_error
                return
            lane = {"state": "capturing", "device_epoch": 0, "dropped_frames": 0,
                    "discontinuities": 0, "failure_code": None}
            # Reserve the sequence before I/O: an ambiguous response may already be
            # admitted. Presence accepts monotonic gaps, never reused sequences with
            # changed timestamps. Frames retain their separate byte-identical retry rule.
            sequence = self._sequence
            self._sequence += 1
            self._post({"schema": HELPER_SCHEMA, "instance_id": "phase2-acceptance-replay",
                        "sequence": sequence, "sent_monotonic_ns": time.monotonic_ns(),
                        "helper_version": "phase2-acceptance.v1", "state": "capturing",
                        "lanes": {"system": dict(lane), "microphone": dict(lane)}})
            self.last_error = None

    def _run(self) -> None:
        while not self._closed.wait(HELPER_HEARTBEAT_INTERVAL_SECONDS):
            try:
                self.send()
            except ServiceReplayIdentityCommitFailure as exc:
                # Revoked authority or an already-terminal session is not recreated.
                self.last_error = exc
                self._closed.set()
            except Exception as exc:
                self.last_error = exc

    def close(self) -> None:
        self._closed.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=HELPER_HEARTBEAT_TIMEOUT_SECONDS + 1)


class AccountCookieLiveReplayService:
    """Adapt Account Live HTTP to the existing authority-neutral replay Interface.

    The cookie is read once from a caller-owned mode-0600 file, held only in memory, and never
    appears in object representation, errors, requests paths, or replay artifacts.
    """

    def __init__(self, *, base_url: str, cookie_file: Path, timeout_seconds: float = 10.0):
        if not base_url.startswith("https://"):
            raise ValueError("Account replay requires an https:// origin")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cookie_file.stat().st_mode & 0o777 != 0o600:
            raise ValueError("Account replay cookie file must have mode 0600")
        cookie = cookie_file.read_text(encoding="utf-8").strip()
        if not cookie or "\n" in cookie or "\r" in cookie:
            raise ValueError("Account replay cookie file must contain exactly one value")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = float(timeout_seconds)
        self._cookie = cookie
        self._frame_samples: dict[str, int] = {}
        self._helpers: dict[str, tuple[AcceptanceHelperLease, bool]] = {}
        self.stop_observations: dict[str, dict[str, object]] = {}

    def descriptor(self):
        """Read the authenticated production descriptor without creating a Meeting."""

        return _descriptor_from_dict(self._json("GET", "/api/live/descriptor")["descriptor"])

    def create(self):
        payload = self._json("POST", "/api/live/sessions", {"echo_mode": "speakers"})
        descriptor = _descriptor_from_dict(payload["descriptor"])
        session_id = str(payload["id"])
        self._frame_samples[session_id] = descriptor.frame_samples
        self._start_helper(session_id)
        from .app.live_service_runtime import LiveServiceCreateResult

        return LiveServiceCreateResult(
            session_id=session_id,
            descriptor=descriptor,
            snapshot=_snapshot_from_dict(payload["snapshot"]),
        )

    def attach_existing(self, session_id: str, *, helper: AcceptanceHelperLease | None = None) -> None:
        """Bind local frame geometry to an already owner-created Account Live Meeting."""

        descriptor = self.descriptor()
        self._frame_samples[session_id] = descriptor.frame_samples
        if helper is None:
            self._start_helper(session_id)
        else:
            self._helpers[session_id] = (helper, False)

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        frame_samples = self._frame_samples[session_id]
        timestamp_ns = frame.sequence * frame_samples * 1_000_000_000 // LIVE_SAMPLE_RATE
        system = self._lane_payload(frame, lane="system", timestamp_ns=timestamp_ns, silent=False)
        microphone = self._lane_payload(
            AudioFrame(
                sequence=frame.sequence,
                pcm=b"\0" * len(frame.pcm),
                sample_count=frame.sample_count,
                sample_rate=frame.sample_rate,
            ),
            lane="microphone",
            timestamp_ns=timestamp_ns,
            silent=True,
        )
        system_result = self.accept_lane(session_id, system)
        microphone_result = self.accept_lane(session_id, microphone)
        self._heartbeat(session_id)
        snapshot_payload = self._json(
            "GET", f"/api/live/sessions/{self._quoted(session_id)}/snapshot"
        )["snapshot"]
        queued = tuple(
            int(item)
            for item in (
                list(system_result.get("queued_item_ids", ()))
                + list(microphone_result.get("queued_item_ids", ()))
            )
        )
        return LiveServiceFrameResult(
            ack=_frame_ack_from_dict(system_result["ack"]),
            queued_item_ids=queued,
            snapshot=_snapshot_from_dict(snapshot_payload),
        )

    def accept_lane(
        self, session_id: str, payload: dict[str, object]
    ) -> dict[str, Any]:
        """Submit one exact v2 lane frame so a refused lane can be retried byte-for-byte."""

        return self._json(
            "POST", f"/api/live/sessions/{self._quoted(session_id)}/frames", payload
        )

    def heartbeat(self, session_id: str) -> None:
        self._heartbeat(session_id)

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        query = urllib.parse.urlencode({"since_seq": int(since_seq)})
        payload = self._json(
            "GET", f"/api/live/sessions/{self._quoted(session_id)}/events?{query}"
        )
        return tuple(_event_from_dict(item) for item in payload["events"])

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        query = "" if since_version is None else "?" + urllib.parse.urlencode({"since_version": since_version})
        payload = self._json(
            "GET", f"/api/live/sessions/{self._quoted(session_id)}/snapshot{query}"
        )
        snapshot = payload.get("snapshot")
        return None if snapshot is None else _snapshot_from_dict(snapshot)

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        payload = await asyncio.to_thread(
            self._json,
            "POST",
            f"/api/live/sessions/{self._quoted(session_id)}/stop",
            {"deadline": float(deadline)},
        )
        if payload.get("code") == "stop_in_progress":
            payload = await self._await_stop_publication(session_id)
        self._forget(session_id)
        return _snapshot_from_dict(payload["snapshot"])

    async def _await_stop_publication(self, session_id: str) -> dict[str, Any]:
        # HTTP 202 is an accepted Stop, not a drained session. Reuse this producer's
        # existing request budget for observation; never alter the browser's drain deadline.
        started = time.monotonic()
        end = started + self._timeout_seconds
        observation: dict[str, object] = {
            "session_id": session_id, "initial_code": "stop_in_progress",
            "deadline_seconds": self._timeout_seconds, "polls": 0, "settled": False,
        }
        self.stop_observations[session_id] = observation
        try:
            while True:
                remaining = end - time.monotonic()
                if remaining <= 0:
                    raise AccountReplayTransportFailure(
                        "accepted Stop did not publish terminal state within observation deadline",
                        http_status=202,
                    )
                payload = await asyncio.to_thread(
                    self._json, "GET",
                    f"/api/live/sessions/{self._quoted(session_id)}/snapshot",
                    timeout_seconds=remaining,
                )
                observation["polls"] += 1
                value = payload.get("snapshot")
                if value is not None:
                    snapshot = _snapshot_from_dict(value)
                    status = snapshot.session.status
                    finalization = snapshot.session.finalization_status
                    observation.update(status=status, finalization_status=finalization)
                    if status in {"aborted", "failed"} or (
                        status == "closed" and finalization != "running"
                    ):
                        observation["settled"] = True
                        return payload
                await asyncio.sleep(min(0.25, max(0.0, end - time.monotonic())))
        finally:
            observation["wait_seconds"] = time.monotonic() - started

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        payload = await asyncio.to_thread(
            self._json,
            "POST",
            f"/api/live/sessions/{self._quoted(session_id)}/abort",
            {"reason": reason},
        )
        self._forget(session_id)
        return _snapshot_from_dict(payload["snapshot"])

    def _start_helper(self, session_id: str) -> None:
        helper = AcceptanceHelperLease(lambda payload: self._json(
            "POST", f"/api/live/sessions/{self._quoted(session_id)}/heartbeat", payload,
            timeout_seconds=HELPER_HEARTBEAT_TIMEOUT_SECONDS))
        self._helpers[session_id] = (helper, True)
        helper.start()

    def _heartbeat(self, session_id: str) -> None:
        self._helpers[session_id][0].send()

    def close(self) -> None:
        for session_id in tuple(self._helpers):
            self._forget(session_id)

    @staticmethod
    def _lane_payload(
        frame: AudioFrame, *, lane: str, timestamp_ns: int, silent: bool
    ) -> dict[str, object]:
        return {
            "lane": lane,
            "sequence": frame.sequence,
            "capture_timestamp_ns": timestamp_ns,
            "capture_end_timestamp_ns": timestamp_ns + round(frame.sample_count * 1e9 / frame.sample_rate),
            "device_epoch": 0,
            "pcm_base64": base64.b64encode(frame.pcm).decode("ascii"),
            "sample_count": frame.sample_count,
            "sample_rate": frame.sample_rate,
            "silent": silent,
            "discontinuity": False,
        }

    @staticmethod
    def _quoted(session_id: str) -> str:
        return urllib.parse.quote(session_id, safe="")

    def _forget(self, session_id: str) -> None:
        self._frame_samples.pop(session_id, None)
        helper = self._helpers.pop(session_id, None)
        if helper is not None and helper[1]:
            helper[0].close()

    def _json(
        self, method: str, path: str, payload: dict[str, object] | None = None,
        *, timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json", "Cookie": f"{SESSION_COOKIE}={self._cookie}"}
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self._base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds if timeout_seconds is None else min(self._timeout_seconds, timeout_seconds)) as response:
                envelope = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                response = json.loads(body) if body else {}
            except json.JSONDecodeError:
                response = {}
            detail = response.get("detail") if isinstance(response, dict) else None
            if exc.code == 404 and path == "/api/live/sessions":
                raise ServiceReplayProviderConfigFailure("Account Live routes are disabled") from exc
            if exc.code in (408, 429, 502, 503, 504):
                raise AccountReplayTransportFailure(
                    str(detail or f"HTTP {exc.code}"), http_status=exc.code
                ) from exc
            raise ServiceReplayIdentityCommitFailure(str(detail or f"HTTP {exc.code}")) from exc
        except (OSError, TimeoutError, json.JSONDecodeError) as exc:
            raise AccountReplayTransportFailure(
                f"ambiguous Account HTTP replay result: {type(exc).__name__}",
                http_status=None,
            ) from exc
        if not isinstance(envelope, dict):
            raise ServiceReplayTransportFailure("Account HTTP replay returned a non-object")
        return envelope
