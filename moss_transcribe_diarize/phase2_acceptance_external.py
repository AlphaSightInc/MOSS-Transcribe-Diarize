"""Fixed external Account/HTTP/UDS measurement families.

This is the deployed-observation owner for the Wave-1 driver.  Callers provide only endpoints,
session-cookie files, and immutable input fixtures.  The module chooses every route, mutation,
projection, and success predicate itself; it never consumes a caller-authored observation.
"""

from __future__ import annotations

from .phase2_acceptance_replay import ACCEPTANCE_STOP_DEADLINE_SECONDS

import asyncio
import copy
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
import wave
from urllib.parse import urlsplit
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping
from types import SimpleNamespace

import httpx

from .app.phase2 import SESSION_COOKIE, _settled_transcript
from .app.phase2_audio import MeetingAudioArchive
from .app.phase2_control import Phase2ControlError, request_control
from .app.phase2_operator import render_operator_status, serialize_operator_payload
from .concurrency_evidence import (
    canonical_lifecycle_fairness,
    prestop_inference_projection,
)
from .phase2_acceptance import (
    G1_CROSS_OWNER_MATRIX,
    G1_SENTINEL_SURFACES,
    QUALIFICATION_URL_FIXTURE,
    overload_minimum_frames,
)
from .phase2_acceptance_replay import (
    AccountCookieLiveReplayService,
    AccountReplayTransportFailure,
    AcceptanceHelperLease,
    HELPER_HEARTBEAT_TIMEOUT_SECONDS,
    ServiceReplayIdentityCommitFailure,
)
from .live_service_replay import run_service_replay
from .app.live_session import AudioFrame, LIVE_SAMPLE_RATE
from .app.live_transcript_convergence import ROLLING_STRIDE_SECONDS, ROLLING_WINDOW_SECONDS
from .installed_candidate import validated_candidate_artifacts
from .phase2_acceptance_journal import ServiceJournalWindow, supported_moss_unit
from .evaluation import Segment, calculate_diarization
from .live_speaker_accuracy import load_reference_jsonl


class ExternalMeasurementError(RuntimeError):
    """A fixed measurement ran but did not produce trustworthy product state."""


def _terminal_transcript_matches(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """Compare durable content after the product's terminal speaker presentation."""

    if before.get("transcript_version") != after.get("transcript_version"):
        return False
    document = before.get("transcript")
    if document is None:
        return after.get("transcript") is None
    if not isinstance(document, dict):
        return False
    return _settled_transcript(copy.deepcopy(document)) == after.get("transcript")


class _LoadEventCapture:
    """Drain the bounded product event ring throughout capture, with no silent gaps."""

    def __init__(self):
        self.next_seq = 0
        self.events: list[dict[str, Any]] = []

    def read(self, adapter, session_id):
        for event in adapter.events(session_id, since_seq=self.next_seq):
            if event.seq != self.next_seq:
                raise ExternalMeasurementError(
                    f"live load event gap: expected seq={self.next_seq}, observed={event.seq}"
                )
            self.events.append(event.to_dict())
            self.next_seq += 1


class _CrashRecoveryOps:
    def __init__(self, client):
        self.client = client

    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    def pid(self, unit, timeout):
        return _unit_pid(unit, timeout=timeout)

    def ready(self, timeout):
        # Same authenticated readiness endpoint used by _await_service.
        return self.client.request("GET", "/api/auth/session", timeout=timeout).status_code == 200


def _wait_crash_recovery(ops, unit, old_pid, *, timeout=60.0):
    started = ops.monotonic()
    deadline = started + timeout
    evidence = {"old_pid": old_pid, "new_pid": None, "ready": False,
                "polls": 0, "deadline_seconds": timeout, "last_error_type": None}
    while ops.monotonic() < deadline:
        evidence["polls"] += 1
        try:
            pid = ops.pid(unit, min(1.0, deadline - ops.monotonic()))
            evidence["new_pid"] = pid
            remaining = deadline - ops.monotonic()
            if pid != old_pid and pid > 0 and remaining > 0 and ops.ready(min(1.0, remaining)):
                evidence["ready"] = True
                break
        except (ExternalMeasurementError, subprocess.TimeoutExpired) as exc:
            evidence["last_error_type"] = type(exc).__name__
        ops.sleep(min(0.5, max(0.0, deadline - ops.monotonic())))
    evidence["wait_seconds"] = ops.monotonic() - started
    return evidence


def _recording_mix_pcm(system_pcm: bytes) -> bytes:
    """The replay client sends system audio plus a silent microphone, not mono input.

    Use the production mixer before the archive oracle: recording headroom and
    analysis-only gain are distinct; only frame.pcm is the recording surface.
    """
    from .app.live_lane_contract import LiveLane, LiveV2Frame
    from .app.live_mixer import LiveCompatibilityMixer
    from .app.live_v2_session import LiveV2Session

    count = len(system_pcm) // 2
    source = LiveV2Session(max_retained_samples=count)
    for lane in LiveLane:
        source.accept(LiveV2Frame(
            lane=lane, sequence=0, capture_timestamp_ns=0, device_epoch=0,
            silent=lane == LiveLane.MICROPHONE, discontinuity=False,
            sample_rate=LIVE_SAMPLE_RATE, sample_count=count,
            pcm=system_pcm if lane == LiveLane.SYSTEM else b"\0" * len(system_pcm),
        ))
    runtime = SimpleNamespace(snapshot=lambda _: SimpleNamespace(
        session=SimpleNamespace(next_frame_sequence=0)))
    mixed = LiveCompatibilityMixer(max_output_samples=count)._stage(
        "recording-oracle", source, runtime, final=True
    )
    if mixed is None or mixed.frame.sample_count != count:
        raise ExternalMeasurementError("recording oracle did not cover the accepted prefix")
    return mixed.frame.pcm


class _CampaignBackpressure:
    """Bind one exact refusal, peer advance, and retry to existing campaign sessions."""

    def __init__(self, session_count: int) -> None:
        self._lock = threading.Lock()
        self._refusal_seen = threading.Event()
        self._peer_progress_seen = threading.Event()
        self._state: dict[str, object] = {
            "observed_429": False,
            "peer_progress": False,
            "same_sequence_retry": False,
            "campaign_session_ordinals": list(range(1, session_count + 1)),
            "target_session_ordinal": 1,
            "peer_session_ordinal": 2,
        }

    def accept(
        self,
        index: int,
        adapter: AccountCookieLiveReplayService,
        session_id: str,
        frame: AudioFrame,
    ):
        if index != 0:
            accepted = adapter.accept_frame(session_id, frame)
            if index == 1 and self._refusal_seen.is_set():
                with self._lock:
                    if self._state["peer_progress"] is False:
                        self._state["peer_progress"] = True
                        self._state["peer_progress_sequence"] = frame.sequence
                        self._state["peer_progress_monotonic_ns"] = time.monotonic_ns()
                self._peer_progress_seen.set()
            return accepted.snapshot

        timestamp_ns = (
            frame.sequence * frame.sample_count * 1_000_000_000 // LIVE_SAMPLE_RATE
        )
        for lane, silent, pcm_bytes in (
            ("system", False, frame.pcm),
            ("microphone", True, b"\0" * len(frame.pcm)),
        ):
            payload = AccountCookieLiveReplayService._lane_payload(
                AudioFrame(
                    frame.sequence,
                    pcm_bytes,
                    frame.sample_count,
                    LIVE_SAMPLE_RATE,
                ),
                lane=lane,
                timestamp_ns=timestamp_ns,
                silent=silent,
            )
            refused_here = False
            retry_deadline = time.monotonic() + 30
            while True:
                if refused_here and time.monotonic() >= retry_deadline:
                    with self._lock:
                        self._state["retry_timed_out"] = True
                    raise ExternalMeasurementError(
                        f"two-session refused frame retry timed out: "
                        f"session_id={session_id}, lane={lane}, sequence={frame.sequence}"
                    )
                try:
                    adapter.accept_lane(session_id, payload)
                except AccountReplayTransportFailure as exc:
                    if exc.http_status != 429:
                        raise
                    refused_here = True
                    with self._lock:
                        if self._state["observed_429"] is False:
                            self._state.update(
                                {
                                    "observed_429": True,
                                    "refused_sequence": frame.sequence,
                                    "refused_lane": lane,
                                    "refused_monotonic_ns": time.monotonic_ns(),
                                }
                            )
                    self._refusal_seen.set()
                    if not self._peer_progress_seen.wait(
                        timeout=max(0, retry_deadline - time.monotonic())
                    ):
                        raise ExternalMeasurementError(
                            "eight-session peer made no progress during backpressure"
                        )
                    adapter.heartbeat(session_id)
                    time.sleep(0.25)
                    continue
                if refused_here:
                    with self._lock:
                        if self._state["same_sequence_retry"] is False:
                            self._state["same_sequence_retry"] = True
                            self._state["retry_monotonic_ns"] = time.monotonic_ns()
                break
        adapter.heartbeat(session_id)
        snapshot = adapter.snapshot(session_id)
        if snapshot is None:
            raise ExternalMeasurementError("eight-session target snapshot is absent")
        return snapshot

    def observation(self) -> dict[str, object]:
        with self._lock:
            return dict(self._state)


def _run_admin_status(admin: Path, socket_path: Path, *, json_output: bool):
    """Capture the response this CLI actually renders through a transparent UDS relay.

    Status contains clocks and resource counters: another request is not its oracle.
    The relay forwards the real request and response unchanged, without retaining content.
    """
    from concurrent.futures import ThreadPoolExecutor
    from .app.phase2_control import MAX_CONTROL_LINE_BYTES, MAX_CONTROL_RESPONSE_BYTES

    with tempfile.TemporaryDirectory(prefix="moss-status-", dir="/tmp") as directory:
        proxy = str(Path(directory) / "s")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(proxy)
            listener.listen(1)
            listener.settimeout(30)

            def relay():
                connection, _ = listener.accept()
                with connection, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                    connection.settimeout(30)
                    upstream.settimeout(30)
                    with connection.makefile("rb") as incoming:
                        request = incoming.readline(MAX_CONTROL_LINE_BYTES + 1)
                    if json.loads(request) != {"command": "status"}:
                        raise ExternalMeasurementError("mtd-admin sent a non-status request")
                    upstream.connect(str(socket_path))
                    upstream.sendall(request)
                    with upstream.makefile("rb") as incoming:
                        response = incoming.readline(MAX_CONTROL_RESPONSE_BYTES + 1)
                    if len(response) > MAX_CONTROL_RESPONSE_BYTES or not response.endswith(b"\n"):
                        raise ExternalMeasurementError("operator status response is invalid")
                    connection.sendall(response)
                    envelope = json.loads(response)
                    if envelope.get("ok") is not True:
                        raise ExternalMeasurementError("operator status request failed")
                    return envelope["result"]

            with ThreadPoolExecutor(max_workers=1) as executor:
                captured = executor.submit(relay)
                argv = (str(admin), "--socket", proxy, "status")
                if json_output:
                    argv += ("--json",)
                result = subprocess.run(argv, check=False, capture_output=True, timeout=30)
                return result, captured.result(timeout=30)


def _admin_status_surfaces(
    socket_path: Path,
    forbidden: list[bytes],
) -> dict[str, object]:
    admin = Path(sys.executable).parent / "mtd-admin"
    if not admin.is_file() or not os.access(admin, os.X_OK):
        raise ExternalMeasurementError("installed mtd-admin executable is unavailable")
    human, human_source = _run_admin_status(admin, socket_path, json_output=False)
    machine, machine_source = _run_admin_status(admin, socket_path, json_output=True)
    if human.returncode or machine.returncode:
        raise ExternalMeasurementError("installed mtd-admin status command failed")
    try:
        machine_payload = json.loads(machine.stdout)
        allowlisted = serialize_operator_payload("status", machine_payload)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ExternalMeasurementError("mtd-admin JSON status is invalid") from exc
    expected_projection = serialize_operator_payload("status", machine_source)
    expected_human = (render_operator_status(serialize_operator_payload("status", human_source)) + "\n").encode()
    return {
        "json_exact_projection": allowlisted == expected_projection,
        "human_exact_projection": human.stdout == expected_human,
        "json_stderr_bytes": len(machine.stderr),
        "human_stderr_bytes": len(human.stderr),
        "forbidden_matches": sum(
            human.stdout.count(value) + machine.stdout.count(value)
            for value in forbidden
            if value
        ),
    }


def _mode_600(path: Path, label: str) -> None:
    if path.stat().st_mode & 0o777 != 0o600:
        raise ExternalMeasurementError(f"{label} must be mode 0600")


def _read_cookie(path: Path) -> str:
    _mode_600(path, "Account cookie file")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise ExternalMeasurementError("Account cookie file must contain one value")
    return value


def _owner_state_digest(payload: Mapping[str, object]) -> bytes:
    """Compare exact durable owner state without retaining Account content in evidence."""

    projection = {
        key: payload.get(key)
        for key in (
            "id",
            "mode",
            "status",
            "title",
            "title_source",
            "created_at_ms",
            "updated_at_ms",
            "transcript",
            "audio",
        )
    }
    return hashlib.sha256(
        json.dumps(
            projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).digest()


def _read_revocation_snapshot(database: Path, audio_root: Path, owner: str, meeting_ids: tuple[str, ...]):
    # mode=ro includes committed WAL state. No immutable=1 shortcut or writable store.
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        result = {}
        for meeting_id in meeting_ids:
            row = connection.execute(
                """SELECT m.status, t.version, t.document_json,
                          a.state AS audio_state, a.relative_path, a.byte_count
                   FROM meetings m LEFT JOIN meeting_transcripts t
                     ON t.account_id=m.account_id AND t.meeting_id=m.meeting_id
                   LEFT JOIN meeting_audio a
                     ON a.account_id=m.account_id AND a.meeting_id=m.meeting_id
                   WHERE m.account_id=? AND m.meeting_id=?""", (owner, meeting_id),
            ).fetchone()
            if row is None:
                raise ExternalMeasurementError("Test-owned meeting is absent")
            item = dict(row)
            path = None if item["relative_path"] is None else (audio_root / item["relative_path"]).resolve()
            if path is not None and not path.is_relative_to((audio_root / owner / meeting_id).resolve()):
                raise ExternalMeasurementError("Test audio escaped its meeting directory")
            item["audio_bytes"] = b"" if path is None or not path.is_file() else path.read_bytes()
            decoded = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
                input=item["audio_bytes"], capture_output=True, timeout=30,
            ) if item["audio_bytes"] else None
            item["audio_decodes"] = bool(decoded and decoded.returncode == 0 and decoded.stdout)
            result[meeting_id] = item
        return result
    finally:
        connection.close()



class AccountHttpClient:
    """One Account Sign-in session whose cookie never enters output or exception text."""

    def __init__(self, origin: str, cookie_file: Path):
        if not origin.startswith("https://"):
            raise ExternalMeasurementError("deployed Account measurement requires https://")
        cookie = _read_cookie(cookie_file)
        self._client = httpx.Client(
            base_url=origin.rstrip("/"),
            headers={"Cookie": f"{SESSION_COOKIE}={cookie}"},
            timeout=httpx.Timeout(300.0, connect=15.0),
            follow_redirects=False,
        )

    def request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ExternalMeasurementError(
                f"Account HTTP {method} {path.split('?')[0]} transport failed: {type(exc).__name__}"
            ) from exc

    def json(self, method: str, path: str, expected: int, **kwargs: object) -> tuple[dict[str, Any], httpx.Response]:
        response = self.request(method, path, **kwargs)
        if response.status_code != expected:
            raise ExternalMeasurementError(
                f"Account HTTP {method} {path.split('?')[0]} returned {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalMeasurementError("Account HTTP returned non-JSON") from exc
        if not isinstance(payload, dict):
            raise ExternalMeasurementError("Account HTTP returned non-object")
        return payload, response

    def close(self) -> None:
        self._client.close()


def _control(
    socket_path: Path,
    command: str,
    account_id: str | None = None,
    *,
    meeting_id: str | None = None,
) -> object:
    try:
        return asyncio.run(
            request_control(socket_path, command, account_id, meeting_id=meeting_id)
        )
    except Phase2ControlError as exc:
        raise Phase2ControlError(f"Control {command} at {socket_path}: {exc}") from exc


class FixedAccountCampaign:
    """Share only created IDs across fixed measurement predicates; never share authority."""

    def __init__(
        self,
        *,
        candidate_sha: str,
        config: Mapping[str, object],
    ) -> None:
        self.candidate_sha = candidate_sha
        self.config = config
        self._clients: dict[str, AccountHttpClient] = {}
        self._live: dict[str, str] = {}
        self._live_helpers: dict[str, tuple[str, AcceptanceHelperLease]] = {}
        self._replay_clients: list[AccountCookieLiveReplayService] = []
        self._meetings: dict[str, list[str]] = defaultdict(list)
        self._browser: object | None = None
        self._safe_artifacts: set[Path] = set()

    def _artifact_root(self) -> Path:
        root = Path(self._text("campaign_work_dir")).resolve()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        return root

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root()

    @property
    def safe_artifacts(self) -> tuple[Path, ...]:
        return tuple(sorted(self._safe_artifacts, key=lambda item: item.as_posix()))

    @staticmethod
    def _artifact_relative(relative: str) -> Path:
        path = Path(relative)
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.suffix != ".json"
        ):
            raise ExternalMeasurementError("safe artifact path is invalid")
        return path

    def _artifact_json(self, relative: str, payload: object) -> None:
        relative_path = self._artifact_relative(relative)
        path = self._artifact_root() / relative_path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            view = memoryview(encoded)
            while view:
                view = view[os.write(descriptor, view) :]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._safe_artifacts.add(relative_path)

    @staticmethod
    def _journal_window(unit: str) -> ServiceJournalWindow:
        return ServiceJournalWindow(unit)

    def _text(self, key: str) -> str:
        value = self.config.get(key)
        if not isinstance(value, str) or not value:
            raise ExternalMeasurementError(f"measurement prerequisite absent: {key}")
        return value

    def close(self) -> None:
        for _, helper in self._live_helpers.values():
            helper.close()
        for adapter in self._replay_clients:
            adapter.close()
        for client in self._clients.values():
            client.close()

    @property
    def browser(self):
        if self._browser is None:
            from .phase2_acceptance_browser import BrowserCampaign

            self._browser = BrowserCampaign(
                self.config,
                repo=Path(self._text("repo_root")).resolve(),
                work=Path(self._text("campaign_work_dir")).resolve(),
                register_artifact=self._safe_artifacts.add,
            )
        return self._browser

    def cleanup(self) -> None:
        """Terminalize every reusable probe Meeting before the final zero-work predicate."""

        failures = []
        owned = {meeting_id: owner for owner, meeting_id in self._live.items()}
        owned.update({meeting_id: owner for meeting_id, (owner, _) in self._live_helpers.items()})
        for meeting_id, owner in owned.items():
            client = self.a if owner == "a" else self.b
            response = client.request(
                "POST", f"/api/live/sessions/{meeting_id}/abort", json={}
            )
            durable_status = None
            if response.status_code == 404:
                # A forced restart drops the in-memory session, but its recovered
                # Meeting must be durably terminal before cleanup can count it.
                meeting = client.request("GET", f"/api/meetings/{meeting_id}")
                if meeting.status_code == 200:
                    durable_status = meeting.json().get("status")
            if response.status_code not in {200, 409} and durable_status not in {
                "completed", "interrupted", "failed"
            }:
                failures.append({"session_id": meeting_id, "abort_status": response.status_code,
                                 "durable_status": durable_status})
        self._live.clear()
        for _, helper in self._live_helpers.values():
            helper.close()
        self._live_helpers.clear()
        if failures:
            raise ExternalMeasurementError(f"probe Live cleanup failed: {failures}")

    @property
    def origin(self) -> str:
        return self._text("https_origin")

    @property
    def operator_socket(self) -> Path:
        return Path(self._text("operator_socket")).expanduser()

    def _account(self, name: str) -> AccountHttpClient:
        client = self._clients.get(name)
        if client is None:
            client = AccountHttpClient(
                self.origin, Path(self._text(f"account_{name}_cookie_file")).expanduser()
            )
            self._clients[name] = client
        return client

    @property
    def a(self) -> AccountHttpClient:
        return self._account("a")

    @property
    def b(self) -> AccountHttpClient:
        return self._account("b")

    @property
    def a_peer(self) -> AccountHttpClient:
        return self._account("a_peer")

    @property
    def b_peer(self) -> AccountHttpClient:
        return self._account("b_peer")

    @property
    def revoked_probe(self) -> AccountHttpClient:
        return self._account("revoked_probe")

    def _live_id(self, owner: str) -> str:
        known = self._live.get(owner)
        if known is not None:
            return known
        client = self.a if owner == "a" else self.b
        payload, _ = client.json(
            "POST", "/api/live/sessions", 201, json={"echo_mode": "speakers"}
        )
        meeting_id = payload.get("id")
        if not isinstance(meeting_id, str) or not meeting_id:
            raise ExternalMeasurementError("Live create omitted Meeting ID")
        self._live[owner] = meeting_id
        def heartbeat(payload):
            response = client.request("POST", f"/api/live/sessions/{meeting_id}/heartbeat",
                                      json=payload, timeout=HELPER_HEARTBEAT_TIMEOUT_SECONDS)
            if response.status_code in {401, 403, 404, 409}:
                raise ServiceReplayIdentityCommitFailure(f"helper heartbeat returned HTTP {response.status_code}")
            if response.status_code != 200:
                raise ExternalMeasurementError(f"helper heartbeat returned HTTP {response.status_code}")
        helper = AcceptanceHelperLease(heartbeat)
        self._live_helpers[meeting_id] = (owner, helper)
        helper.start()
        return meeting_id

    def _replay_service(self, **kwargs) -> AccountCookieLiveReplayService:
        adapter = AccountCookieLiveReplayService(**kwargs)
        self._replay_clients.append(adapter)
        return adapter

    def _new_live_id(self, owner: str) -> str:
        self._live.pop(owner, None)
        return self._live_id(owner)

    def installed_candidate_identity(self) -> dict[str, object]:
        manifest_path = Path(self._text("candidate_manifest")).expanduser()
        _mode_600(manifest_path, "candidate manifest")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != "moss-account-candidate.v1"
            or manifest.get("activation_state") != "staged_inert"
        ):
            raise ExternalMeasurementError("candidate manifest is not an object")
        try:
            artifacts = validated_candidate_artifacts(manifest)
        except (OSError, ValueError) as exc:
            raise ExternalMeasurementError("candidate artifact identity is invalid") from exc
        release = artifacts.release
        launcher = artifacts.launchers["mtd-account-web"]
        active_pointer = (
            Path.home() / ".local/share/moss-transcribe-diarize/account-current"
        )
        if (
            not active_pointer.is_symlink()
            or active_pointer.resolve() != release
        ):
            raise ExternalMeasurementError("running Account release does not match the manifest")
        launcher_digests = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in artifacts.launchers.items()
        }
        unit_root = Path.home() / ".config/systemd/user"
        installed_units = {name: unit_root / name for name in artifacts.units}
        if any(
            not installed.is_file() or installed.read_bytes() != artifacts.units[name].read_bytes()
            for name, installed in installed_units.items()
        ):
            raise ExternalMeasurementError("installed service unit differs from the candidate manifest")
        descriptor_payload, response = self.a.json("GET", "/api/live/descriptor", 200)
        descriptor = descriptor_payload.get("descriptor")
        if not isinstance(descriptor, dict):
            raise ExternalMeasurementError("Live descriptor is absent")
        unit = str(self.config.get("web_unit") or "moss-web.service")
        if unit != "moss-web.service":
            raise ExternalMeasurementError("Account web unit must be moss-web.service")
        process = subprocess.run(
            ("systemctl", "--user", "show", unit, "--property", "MainPID", "--value"),
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode:
            raise ExternalMeasurementError("Account web MainPID is unavailable")
        pid = int(process.stdout.strip())
        proc = Path("/proc") / str(pid)
        try:
            cwd = os.readlink(proc / "cwd")
            exe = os.readlink(proc / "exe")
            argv = [
                item.decode("utf-8", "replace")
                for item in (proc / "cmdline").read_bytes().split(b"\0")
                if item
            ]
        except OSError as exc:
            raise ExternalMeasurementError("Account web process identity is unreadable") from exc
        if len(argv) < 4:
            raise ExternalMeasurementError("Account web process is outside the manifested release")
        invoked = Path(argv[0])
        # Resolve the activation directory separately from the interpreter file:
        # different release venvs can symlink to the same base Python executable.
        interpreter = {
            "invoked": argv[0],
            "release_path": str(invoked.parent.resolve() / invoked.name),
            "executable": str(invoked.resolve()),
        }
        if (
            interpreter["release_path"] != str(release / "bin/python")
            or interpreter["executable"] != str((release / "bin/python").resolve())
            or interpreter["executable"] != exe
            or argv[1:4] != ["-I", "-m", "moss_transcribe_diarize.app.phase2_web_cli"]
        ):
            raise ExternalMeasurementError("Account web process is outside the manifested release")
        installed_record = manifest.get("installed_record")
        dependency = manifest.get("dependency_projection")
        config_hashes = descriptor.get("config_hashes")
        url_fixture = self._text("url_fixture")
        if url_fixture != QUALIFICATION_URL_FIXTURE:
            raise ExternalMeasurementError("URL fixture differs from the pinned public input")
        file_fixture = _file_fixture_identity(
            Path(self._text("file_fixture")).expanduser().resolve()
        )
        toolchain = _toolchain_identity(
            Path(self._text("chrome_binary")).expanduser().resolve()
        )
        accelerator = _accelerator_identity(
            _unit_pid(str(self.config.get("vllm_unit") or "moss-vllm.service"))
        )
        tls = _tls_identity(self.origin)
        return {
            "candidate_sha": manifest.get("git_sha"),
            "candidate_tree": manifest.get("git_tree"),
            "uv_lock_sha256": manifest.get("uv_lock_sha256"),
            "fixtures": manifest.get("fixtures"),
            "candidate_header_sha": response.headers.get("X-MOSS-Candidate-SHA"),
            "wheel_record_verified": (
                installed_record.get("record_verified")
                if isinstance(installed_record, dict)
                else False
            ),
            "wheel_record_entries_verified": (
                installed_record.get("record_entries_verified", 0)
                if isinstance(installed_record, dict)
                else 0
            ),
            "wheel_record_projection_sha256": manifest.get(
                "wheel_record_projection_sha256"
            ),
            "dependency_projection_sha256": (
                dependency.get("sha256") if isinstance(dependency, dict) else None
            ),
            "sqlite_runtime": manifest.get("sqlite_runtime"),
            "manifest": {
                "schema": manifest.get("schema"),
                "activation_state": manifest.get("activation_state"),
                "release": str(release),
                "release_launcher": str(launcher),
                "release_launcher_sha256": launcher_digests["mtd-account-web"],
                "release_admin_launcher": str(artifacts.launchers["mtd-admin"]),
                "release_admin_launcher_sha256": launcher_digests["mtd-admin"],
                "release_cutover_launcher": str(
                    artifacts.launchers["mtd-phase2-cutover"]
                ),
                "release_cutover_launcher_sha256": launcher_digests[
                    "mtd-phase2-cutover"
                ],
                "release_vllm_launcher": str(artifacts.launchers["mtd-vllm"]),
                "release_vllm_launcher_sha256": launcher_digests["mtd-vllm"],
                "web_unit_sha256": hashlib.sha256(
                    installed_units["moss-web.service"].read_bytes()
                ).hexdigest(),
                "vllm_unit_sha256": hashlib.sha256(
                    installed_units["moss-vllm.service"].read_bytes()
                ).hexdigest(),
                "installed_units_match_manifest": True,
                "active_pointer_resolves_to_release": True,
            },
            "aiosqlite": self._dependency_version(dependency, "aiosqlite"),
            "process": {"pid": pid, "cwd": cwd, "exe": exe, "argv": argv, "interpreter": interpreter},
            "toolchain": toolchain,
            "accelerator": accelerator,
            "tls": tls,
            "input_fixtures": {
                "file": file_fixture,
                "url": url_fixture,
            },
            "descriptor": {
                "source_revision": descriptor.get("source_revision"),
                "provider_name": descriptor.get("provider_name"),
                "provider_revision": descriptor.get("provider_revision"),
                "provider_manifest_hash": descriptor.get("provider_manifest_hash"),
                "schema_version": descriptor.get("schema_version"),
                "live_protocol_version": descriptor.get("live_protocol_version"),
                "sample_rate": descriptor.get("sample_rate"),
                "frame_samples": descriptor.get("frame_samples"),
                "bounds": descriptor.get("bounds"),
                "config_hashes": config_hashes,
                "combined_config_hash": (
                    config_hashes.get("combined_config_hash")
                    if isinstance(config_hashes, dict)
                    else None
                ),
            },
        }

    @staticmethod
    def _dependency_version(dependency: object, name: str) -> object:
        packages = dependency.get("packages") if isinstance(dependency, dict) else None
        if not isinstance(packages, list):
            return None
        for item in packages:
            if isinstance(item, dict) and str(item.get("name", "")).lower() == name.lower():
                return item.get("version")
        return None

    def zero_work_end(self) -> dict[str, object]:
        status = _control(self.operator_socket, "status")
        if not isinstance(status, dict):
            raise ExternalMeasurementError("operator status is not an object")
        capacity = status.get("capacity")
        if not isinstance(capacity, dict):
            raise ExternalMeasurementError("operator capacity is absent")
        live = capacity.get("live")
        file = capacity.get("file")
        queues = capacity.get("queues")
        return {
            "active_live": live.get("active") if isinstance(live, dict) else None,
            "active_file": file.get("active") if isinstance(file, dict) else None,
            "queue_depths": dict(queues) if isinstance(queues, dict) else {},
        }

    def cross_owner_matrix(self) -> dict[str, object]:
        meeting_id = self._live_id("a")
        sentinel = Path(self._text("account_a_sentinel_file")).read_bytes().strip()
        if not sentinel:
            raise ExternalMeasurementError("Account A sentinel is empty")
        renamed = self.a.request(
            "PUT",
            f"/api/meetings/{meeting_id}/title",
            json={"title": sentinel.decode("utf-8")},
        )
        if renamed.status_code != 200:
            raise ExternalMeasurementError("owner sentinel title could not be installed")
        before_payload, _ = self.a.json("GET", f"/api/meetings/{meeting_id}", 200)
        before = _owner_state_digest(before_payload)

        invalid = httpx.Client(base_url=self.origin, headers={"Cookie": f"{SESSION_COOKIE}=invalid"})
        try:
            cases: list[dict[str, object]] = []
            for case_id, (method, route, expected_status) in G1_CROSS_OWNER_MATRIX.items():
                client: AccountHttpClient | httpx.Client = self.b
                actual = route.format(
                    foreign_meeting_id=meeting_id,
                    foreign_session_id=meeting_id,
                    foreign_cursor=0,
                    foreign_job_id=meeting_id,
                )
                kwargs: dict[str, object] = {}
                if method in {"POST", "PUT"}:
                    kwargs["json"] = (
                        {"title": "foreign mutation"} if "title" in actual else {}
                    )
                if case_id == "live_stop_foreign":
                    kwargs["json"] = {"deadline": ACCEPTANCE_STOP_DEADLINE_SECONDS}
                if case_id.startswith("invalid_session"):
                    client = invalid
                elif case_id.startswith("revoked"):
                    # Revoke a disposable third workspace, never a peer tab of A/B.
                    if case_id == "revoked_session_meeting":
                        identity, _ = self.revoked_probe.json("GET", "/api/auth/session", 200)
                        owner = identity.get("workspace_id")
                        if not isinstance(owner, str) or not owner:
                            raise ExternalMeasurementError("Revocation probe identity is unavailable")
                        revoked = _control(self.operator_socket, "accounts.revoke", owner)
                        if not isinstance(revoked, dict) or revoked.get("revoked") is not True:
                            raise ExternalMeasurementError("Disposable probe revocation failed")
                    client = self.revoked_probe
                response = client.request(method, actual, **kwargs)
                after_payload, _ = self.a.json("GET", f"/api/meetings/{meeting_id}", 200)
                after = _owner_state_digest(after_payload)
                cases.append(
                    {
                        "id": case_id,
                        "method": method,
                        "route": route,
                        "observed_status": response.status_code,
                        "owner_state_unchanged": after == before,
                        "owner_content_matches": response.content.count(sentinel),
                    }
                )
            return {"cases": cases}
        finally:
            invalid.close()

    def same_account_convergence(self) -> dict[str, object]:
        meeting_id = self._live_id("a")
        observations = 0
        mismatches = 0
        for path in ("/api/meetings", f"/api/live/sessions/{meeting_id}/snapshot"):
            first = self.a.request("GET", path)
            second = self.a_peer.request("GET", path)
            observations += 2
            if first.status_code != 200 or second.status_code != 200 or first.json() != second.json():
                mismatches += 1
        return {"clients": 2, "observations": observations, "mismatches": mismatches}

    def sentinel_absence(self) -> dict[str, object]:
        web_journal = self._journal_window("moss-web.service")
        inference_journal = self._journal_window("moss-vllm.service")
        a_sentinel = Path(self._text("account_a_sentinel_file")).read_bytes().strip()
        b_sentinel = Path(self._text("account_b_sentinel_file")).read_bytes().strip()
        if not a_sentinel or not b_sentinel:
            raise ExternalMeasurementError("Account sentinels must be nonempty")
        meeting_a = self._live_id("a")
        meeting_b = self._live_id("b")
        self.a.json(
            "PUT",
            f"/api/meetings/{meeting_a}/title",
            200,
            json={"title": a_sentinel.decode()},
        )
        self.b.json(
            "PUT",
            f"/api/meetings/{meeting_b}/title",
            200,
            json={"title": b_sentinel.decode()},
        )
        a_transcript = self._seed_live_transcript("a", meeting_a, 0)
        b_transcript = self._seed_live_transcript("b", meeting_b, 1)
        audio_a = self._seed_audio_sentinel("a", 0)
        audio_b = self._seed_audio_sentinel("b", 1)
        if audio_a[1] == audio_b[1]:
            raise ExternalMeasurementError("Account audio sentinels are not distinct")
        audio_checks = []
        for owner, foreign, audio in (
            (self.a, self.b, audio_a),
            (self.b, self.a, audio_b),
        ):
            owner_download = owner.request(
                "GET", f"/api/meetings/{audio[0]}/audio/download"
            )
            foreign_download = foreign.request(
                "GET", f"/api/meetings/{audio[0]}/audio/download"
            )
            audio_checks.append(
                {
                    "owner_status": owner_download.status_code,
                    "owner_identity_match": hashlib.sha256(owner_download.content).digest()
                    == audio[1],
                    "foreign_status": foreign_download.status_code,
                    "foreign_artifact_bytes": int(
                        foreign_download.status_code == 200
                        and hashlib.sha256(foreign_download.content).digest() == audio[1]
                    )
                    * len(foreign_download.content),
                }
            )
        status = json.dumps(_control(self.operator_socket, "status"), sort_keys=True).encode()
        a_values = (a_sentinel, a_transcript)
        b_values = (b_sentinel, b_transcript)
        paired_surfaces: dict[str, tuple[tuple[bytes, tuple[bytes, ...]], ...]] = {
            "account_ui": (
                (
                    self._rendered_body(
                        Path(self._text("account_a_cookie_file")).expanduser(),
                        meeting_a,
                    ),
                    b_values,
                ),
                (
                    self._rendered_body(
                        Path(self._text("account_b_cookie_file")).expanduser(),
                        meeting_b,
                    ),
                    a_values,
                ),
            ),
            "meeting_history": (
                (self.a.request("GET", "/api/meetings").content, b_values),
                (self.b.request("GET", "/api/meetings").content, a_values),
            ),
            "persistence_projection": (
                (
                    self.a.request("GET", f"/api/meetings/{meeting_a}").content
                    + self.a.request("GET", f"/api/meetings/{audio_a[0]}").content,
                    b_values,
                ),
                (
                    self.b.request("GET", f"/api/meetings/{meeting_b}").content
                    + self.b.request("GET", f"/api/meetings/{audio_b[0]}").content,
                    a_values,
                ),
            ),
            "live_snapshot": (
                (
                    self.a.request(
                        "GET", f"/api/live/sessions/{meeting_a}/snapshot"
                    ).content,
                    b_values,
                ),
                (
                    self.b.request(
                        "GET", f"/api/live/sessions/{meeting_b}/snapshot"
                    ).content,
                    a_values,
                ),
            ),
            "live_events": (
                (
                    self.a.request(
                        "GET", f"/api/live/sessions/{meeting_a}/events?since_seq=0"
                    ).content,
                    b_values,
                ),
                (
                    self.b.request(
                        "GET", f"/api/live/sessions/{meeting_b}/events?since_seq=0"
                    ).content,
                    a_values,
                ),
            ),
        }
        surfaces: dict[str, tuple[int, int]] = {
            name: (
                sum(len(forbidden) for _content, forbidden in observations),
                sum(
                    content.lower().count(value.lower())
                    for content, forbidden in observations
                    for value in forbidden
                ),
            )
            for name, observations in paired_surfaces.items()
        }
        all_values = (*a_values, *b_values)
        surfaces["operator_status"] = (
            len(all_values),
            sum(status.lower().count(value.lower()) for value in all_values),
        )
        web_log = web_journal.read().lower()
        inference_log = inference_journal.read().lower()
        for surface, content in (
            ("operator_journal", web_log),
            ("server_logs", web_log),
            ("inference_logs", inference_log),
        ):
            surfaces[surface] = (
                len(all_values),
                sum(content.count(value.lower()) for value in all_values),
            )
        return {
            "audio_sentinel_checks": audio_checks,
            "journal_sources": [web_journal.observation(), inference_journal.observation()],
            "surfaces": [
                {
                    "id": name,
                    "searches": searches,
                    "foreign_matches": matches,
                }
                for name, (searches, matches) in sorted(surfaces.items())
            ]
        }

    def _seed_live_transcript(self, owner: str, meeting_id: str, clip_index: int) -> bytes:
        repo = Path(self._text("repo_root")).resolve()
        fixture = json.loads(
            (
                repo
                / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json"
            ).read_text(encoding="utf-8")
        )
        clips = fixture.get("clips") if isinstance(fixture, dict) else None
        audio = fixture.get("audio") if isinstance(fixture, dict) else None
        if not isinstance(clips, list) or not isinstance(audio, dict):
            raise ExternalMeasurementError("sentinel speech fixture is invalid")
        clip = clips[clip_index]
        marker = str(clip["expected_marker"]).encode("utf-8")
        pcm = _wav_pcm_clip(
            repo / str(audio["path"]),
            float(clip["start_seconds"]),
            float(clip["end_seconds"]),
        )
        cookie_key = f"account_{owner}_cookie_file"
        adapter = self._replay_service(
            base_url=self.origin,
            cookie_file=Path(self._text(cookie_key)).expanduser(),
            timeout_seconds=60,
        )
        adapter.attach_existing(meeting_id, helper=self._live_helpers[meeting_id][1])
        samples = adapter.descriptor().frame_samples
        deadline = time.monotonic() + 90
        sequence = 0
        while time.monotonic() < deadline:
            offset = sequence * samples * 2 % len(pcm)
            chunk = (pcm + pcm)[offset : offset + samples * 2]
            adapter.accept_frame(
                meeting_id,
                AudioFrame(sequence, chunk, samples, LIVE_SAMPLE_RATE),
            )
            projection = (self.a if owner == "a" else self.b).request(
                "GET", f"/api/meetings/{meeting_id}"
            ).content
            if marker.lower() in projection.lower():
                return marker
            sequence += 1
            time.sleep(samples / LIVE_SAMPLE_RATE)
        raise ExternalMeasurementError("sentinel speech did not reach durable transcript")

    def _seed_audio_sentinel(
        self, owner: str, clip_index: int
    ) -> tuple[str, bytes]:
        repo = Path(self._text("repo_root")).resolve()
        fixture = json.loads(
            (
                repo
                / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json"
            ).read_text(encoding="utf-8")
        )
        clips = fixture.get("clips") if isinstance(fixture, dict) else None
        audio = fixture.get("audio") if isinstance(fixture, dict) else None
        if not isinstance(clips, list) or not isinstance(audio, dict):
            raise ExternalMeasurementError("sentinel audio fixture is invalid")
        source_path = repo / str(audio["path"])
        clip = clips[clip_index]
        pcm = _wav_pcm_clip(
            source_path,
            float(clip["start_seconds"]),
            float(clip["end_seconds"]),
        )
        token = f"account-audio-sentinel-{owner}".encode("ascii")
        directory = Path(self._text("campaign_work_dir")) / "audio-sentinels"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / f"{token.decode()}.wav"
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(LIVE_SAMPLE_RATE)
            target.writeframes(pcm)
        path.chmod(0o600)
        client = self.a if owner == "a" else self.b
        meeting_id = self._submit_file_for(client, path)
        self._await_meeting_terminal_for(client, meeting_id)
        # Upload filenames are not Meeting titles. Install the marker explicitly,
        # then verify the owner's durable title rather than arbitrary JSON text.
        client.json(
            "PUT", f"/api/meetings/{meeting_id}/title", 200,
            json={"title": token.decode("ascii")},
        )
        meeting, _ = client.json("GET", f"/api/meetings/{meeting_id}", 200)
        if meeting.get("title") != token.decode("ascii"):
            raise ExternalMeasurementError("audio sentinel title is absent from owner state")
        download = client.request("GET", f"/api/meetings/{meeting_id}/audio/download")
        if download.status_code != 200 or not download.content:
            raise ExternalMeasurementError("audio sentinel artifact is unavailable")
        return meeting_id, hashlib.sha256(download.content).digest()

    def _rendered_body(self, cookie_file: Path, meeting_id: str) -> bytes:
        from playwright.sync_api import sync_playwright
        from .phase2_acceptance_browser import _meeting_opener

        chrome = Path(self._text("chrome_binary")).expanduser().resolve()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(chrome), headless=True)
            try:
                context = browser.new_context()
                context.add_cookies(
                    [
                        {
                            "name": SESSION_COOKIE,
                            "value": _read_cookie(cookie_file),
                            "url": self.origin,
                            "secure": True,
                            "httpOnly": True,
                            "sameSite": "Lax",
                        }
                    ]
                )
                page = context.new_page()
                page.goto(self.origin, wait_until="networkidle")
                page.wait_for_selector('[data-auth-state="signed-in"]')
                page.wait_for_selector('[data-boot="ready"]')
                _meeting_opener(page, meeting_id).click()
                page.wait_for_selector("#transcript-panel")
                return page.locator("body").inner_text().encode("utf-8")
            finally:
                browser.close()

    def browser_workspace_identity(self) -> dict[str, object]:
        result = self.browser.browser_workspace_identity(
            lambda command, account_id=None: _control(self.operator_socket, command, account_id)
        )
        self._artifact_json("browser/workspace-identity.json", result)
        return result

    def _revocation_snapshot(self, owner: str, meeting_ids: tuple[str, ...]):
        # Cutover prepare proves these disposable roots empty before test admission.
        # Read only exact test-created IDs; this is not a product-content interface.
        plan_path = Path(self._text("cutover_restore_plan")).expanduser().resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        from .phase2_cutover import RESTORE_PLAN_SCHEMA
        if plan.get("schema") != RESTORE_PLAN_SCHEMA or plan.get("candidate_sha") != self.candidate_sha:
            raise ExternalMeasurementError("Revocation snapshot is not bound to this candidate")
        paths = plan.get("candidate_state_paths")
        if not isinstance(paths, dict):
            raise ExternalMeasurementError("Disposable candidate state paths are unavailable")
        if any(not isinstance(paths.get(key), str) or not paths[key] for key in ("database", "meeting_audio")):
            raise ExternalMeasurementError("Disposable candidate state paths are unavailable")
        database, audio_root = Path(paths["database"]), Path(paths["meeting_audio"])
        if not database.is_absolute() or not audio_root.is_absolute():
            raise ExternalMeasurementError("Candidate state paths must be absolute")
        return _read_revocation_snapshot(database, audio_root, owner, meeting_ids)

    def revocation_lifecycle(self) -> dict[str, object]:
        failures = late_commits = stale_revived = 0
        fixture = Path(self._text("file_fixture")).expanduser()
        # Cookie loss does not revoke a stored workspace or cancel accepted files.
        peer_file_id = self._submit_file_for(self.a_peer, fixture)
        if self.a_peer.request("GET", "/api/meetings", headers={"Cookie": ""}).status_code != 401:
            failures += 1
        if self.a.request("GET", "/api/meetings").status_code != 200:
            failures += 1
        peer_saved = self._await_meeting_terminal(peer_file_id)
        if (
            peer_saved.get("status") != "completed"
            or not isinstance(peer_saved.get("transcript"), dict)
            or not peer_saved["transcript"].get("segments")
        ):
            raise ExternalMeasurementError("Cookie loss did not preserve completed File speech")
        identity, _ = self.b.json("GET", "/api/auth/session", 200)
        owner = identity.get("workspace_id")
        if not isinstance(owner, str) or not owner:
            raise ExternalMeasurementError("Revocation workspace identity is unavailable")
        live_id = self._new_live_id("b")
        self._seed_live_transcript("b", live_id, 2)
        before, _ = self.b.json("GET", f"/api/meetings/{live_id}", 200)
        before_transcript = before.get("transcript")
        before_version = int(before.get("transcript_version", 0))
        if before_version <= 0 or not isinstance(before_transcript, dict) or not before_transcript.get("segments"):
            raise ExternalMeasurementError("Revoke probe lacks a durable transcript prefix")
        # Submit last so the gate observes active File work, not an earlier completion.
        b_file_id = self._submit_file_for(self.b, fixture)
        file_before, _ = self.b.json("GET", f"/api/meetings/{b_file_id}", 200)
        if file_before.get("status") != "active":
            raise ExternalMeasurementError("Revoke fixture did not expose active File work")
        revoked = _control(self.operator_socket, "accounts.revoke", owner)
        if not isinstance(revoked, dict) or revoked.get("revoked") is not True:
            raise ExternalMeasurementError("Workspace revocation did not complete")
        # A workspace-scoped revoke must not disable or change the surviving owner.
        peer_after, _ = self.a.json("GET", f"/api/meetings/{peer_file_id}", 200)
        if peer_after != peer_saved:
            raise ExternalMeasurementError("Revocation changed the unrelated workspace")
        settled = self._revocation_snapshot(owner, (live_id, b_file_id))
        for client in (self.b, self.b_peer):
            if client.request("GET", "/api/meetings").status_code != 401:
                failures += 1
        late = self.b.request(
            "POST", f"/api/live/sessions/{live_id}/frames",
            json=AccountCookieLiveReplayService._lane_payload(
                AudioFrame(0, b"\0\0" * 8_000, 8_000, LIVE_SAMPLE_RATE),
                lane="system", timestamp_ns=0, silent=False,
            ),
        )
        if late.status_code != 401:
            late_commits += 1
        fresh, response = self.b.json("POST", "/api/workspace/bootstrap", 200, headers={"Cookie": ""})
        credential = response.cookies.get(SESSION_COOKIE)
        if not credential or fresh.get("workspace_id") == owner:
            raise ExternalMeasurementError("Fresh bootstrap restored revoked ownership")
        for meeting_id in (live_id, b_file_id):
            if self.b.request(
                "GET", f"/api/meetings/{meeting_id}",
                headers={"Cookie": f"{SESSION_COOKIE}={credential}"},
            ).status_code != 404:
                failures += 1
        if self.b.request("GET", "/api/meetings").status_code != 401:
            stale_revived += 1
        after = self._revocation_snapshot(owner, (live_id, b_file_id))
        late_commits += int(settled != after)
        live_state, file_state = after[live_id], after[b_file_id]
        failures += int(live_state["status"] != "interrupted")
        failures += int(file_state["status"] != "interrupted")
        prefix_preserved = (
            live_state["version"] == before_version
            and json.loads(live_state["document_json"]) == before_transcript
        )
        partial_audio = (
            live_state["audio_state"] == "partial" and live_state["audio_decodes"]
            and len(live_state["audio_bytes"]) == live_state["byte_count"]
        )
        self._live.pop("b", None)
        # Revocation has already terminalized this workspace's sessions. Do not keep
        # renewing them or later try to abort them with authority the test revoked.
        for meeting_id, (helper_owner, helper) in tuple(self._live_helpers.items()):
            if helper_owner == "b":
                helper.close()
                del self._live_helpers[meeting_id]
        return {
            "cases": 6, "failures": failures, "late_commits": late_commits,
            "stale_authority_revived": stale_revived,
            "durable_prefix_preserved": prefix_preserved,
            "partial_audio_playable": bool(partial_audio),
        }

    def operator_control(self) -> dict[str, object]:
        journal_window = self._journal_window("moss-web.service")
        mode = stat.S_IMODE(self.operator_socket.stat().st_mode)
        status_before = _control(self.operator_socket, "status")
        if not isinstance(status_before, dict):
            raise ExternalMeasurementError("operator status is not an object")
        forbidden = []
        files = self.config.get("content_boundary_files")
        if isinstance(files, dict):
            for value in files.values():
                if isinstance(value, str):
                    forbidden.append(Path(value).expanduser().read_bytes().strip())
        status_surfaces = _admin_status_surfaces(
            self.operator_socket,
            forbidden,
        )
        capacity = status_before.get("capacity")
        active = status_before.get("active_meetings")
        status_accounts = status_before.get("accounts")
        account_rows = _control(self.operator_socket, "accounts.list")
        count_mismatches = 0
        if not isinstance(capacity, dict) or not isinstance(active, list):
            count_mismatches += 1
        else:
            live = capacity.get("live")
            file = capacity.get("file")
            live_count = sum(
                isinstance(item, dict) and item.get("mode") == "live" for item in active
            )
            file_count = sum(
                isinstance(item, dict) and item.get("mode") in {"file", "url"} for item in active
            )
            count_mismatches += int(not isinstance(live, dict) or live.get("active") != live_count)
            count_mismatches += int(not isinstance(file, dict) or file.get("active") != file_count)
        if isinstance(status_accounts, list) and isinstance(account_rows, list):
            allowlist = {
                item.get("account_id"): item.get("enabled")
                for item in account_rows
                if isinstance(item, dict)
            }
            count_mismatches += sum(
                allowlist.get(item.get("account_id")) != item.get("enabled")
                for item in status_accounts
                if isinstance(item, dict)
            )
        else:
            count_mismatches += 1
        tcp_admin_surfaces = sum(
            self.a.request("GET", path).status_code != 404
            for path in ("/api/operator/status", "/api/admin", "/api/accounts")
        )

        adapter = self._replay_service(
            base_url=self.origin,
            cookie_file=Path(self._text("account_a_cookie_file")).expanduser(),
            timeout_seconds=60,
        )
        created = adapter.create()
        interrupted = False
        try:
            corpus = Path(self._text("quality_corpus")).expanduser()
            manifest = json.loads((corpus / "corpus-manifest.json").read_text())
            pcm = _wav_pcm(corpus / manifest["cases"][0]["case_id"] / "audio.wav")
            frame_samples = created.descriptor.frame_samples
            admitted_item: int | None = None
            admitted_started = False
            probe_started = time.monotonic()
            events = ()
            frames_sent = 0
            # Burst within the existing 120-frame budget: real-time pacing lets
            # a fast canonical decoder finish every span between observations.
            # The interrupt contract needs a queued item, not a second item
            # simultaneously running on the decoder.
            for sequence in range(120):
                if time.monotonic() - probe_started >= 60:
                    break
                offset = sequence * frame_samples * 2 % len(pcm)
                chunk = (pcm + pcm)[offset : offset + frame_samples * 2]
                adapter.accept_frame(
                    created.session_id,
                    AudioFrame(sequence, chunk, frame_samples, LIVE_SAMPLE_RATE),
                )
                frames_sent += 1
                events = adapter.events(created.session_id)
                processed = {
                    int(event.payload["item_id"])
                    for event in events
                    if event.kind == "canonical_processed"
                    and isinstance(event.payload.get("item_id"), int)
                }
                started = [
                    int(event.payload["item_id"])
                    for event in events
                    if event.kind == "canonical_started"
                    and isinstance(event.payload.get("item_id"), int)
                    and int(event.payload["item_id"]) not in processed
                ]
                queued = [
                    int(event.payload["item_id"])
                    for event in events
                    if event.kind == "canonical_queued"
                    and isinstance(event.payload.get("item_id"), int)
                    and int(event.payload["item_id"]) not in processed
                    and int(event.payload["item_id"]) not in started
                ]
                if queued:
                    admitted_item = queued[0]
                    admitted_started = bool(started)
                    break
            admission = {
                "session_id": created.session_id,
                "frames_sent": frames_sent,
                "audio_seconds_sent": frames_sent * frame_samples / LIVE_SAMPLE_RATE,
                "elapsed_seconds": time.monotonic() - probe_started,
                "selected_queued_item_id": admitted_item,
                "lifecycle_counts": {
                    kind: sum(event.kind == kind for event in events)
                    for kind in ("canonical_queued", "canonical_started", "canonical_processed")
                },
            }
            self._artifact_json("operator/interrupt-admission.json", admission)
            if admitted_item is None:
                raise ExternalMeasurementError(
                    f"operator interrupt probe did not observe queued canonical work: {admission}"
                )
            before, _ = self.a.json(
                "GET", f"/api/meetings/{created.session_id}", 200
            )
            outcome = _control(
                self.operator_socket,
                "meetings.interrupt",
                meeting_id=created.session_id,
            )
            interrupted = (
                isinstance(outcome, dict)
                and outcome.get("meeting_id") == created.session_id
                and outcome.get("interrupted") is True
            )
            after = self._await_meeting_terminal(created.session_id)
            after_events = adapter.events(created.session_id)
            after_status = _control(self.operator_socket, "status")
            if not isinstance(after_status, dict):
                raise ExternalMeasurementError("post-interrupt operator status is not an object")
            post_capacity = after_status.get("capacity")
            queues = post_capacity.get("queues") if isinstance(post_capacity, dict) else None
            active_after = after_status.get("active_meetings")
            target_still_active = sum(
                isinstance(item, dict) and item.get("meeting_id") == created.session_id
                for item in (active_after if isinstance(active_after, list) else [])
            )
            audio = self.a.request(
                "GET", f"/api/meetings/{created.session_id}/audio/download"
            )
            audio_probe = _probe_mp3(audio.content) if audio.status_code == 200 else None
            late = self.a.request(
                "POST",
                f"/api/live/sessions/{created.session_id}/frames",
                json=AccountCookieLiveReplayService._lane_payload(
                    AudioFrame(999, b"\0\0" * frame_samples, frame_samples, LIVE_SAMPLE_RATE),
                    lane="system",
                    timestamp_ns=999 * frame_samples * 1_000_000_000 // LIVE_SAMPLE_RATE,
                    silent=False,
                ),
            )
            matching_processed = sum(
                event.kind == "canonical_processed"
                and event.payload.get("item_id") == admitted_item
                for event in after_events
            )
            matching_started = sum(
                event.kind == "canonical_started"
                and event.payload.get("item_id") == admitted_item
                for event in after_events
            )
            matching_discarded = sum(
                event.kind == "canonical_discarded"
                and event.payload.get("item_id") == admitted_item
                for event in after_events
            )
            interrupt_probe = {
                "admission": admission,
                "admitted_work_observed": True,
                "admitted_started": admitted_started,
                "command_interrupted": interrupted,
                "durable_interrupted": after.get("status") == "interrupted",
                "transcript_unchanged": _terminal_transcript_matches(before, after),
                "target_active_after": target_still_active,
                "queue_depth_after": (
                    sum(int(value) for value in queues.values())
                    if isinstance(queues, dict)
                    and all(isinstance(value, int) for value in queues.values())
                    else -1
                ),
                "queued_item_started_events": matching_started,
                "admitted_item_processed_events": matching_processed,
                "queued_item_discarded_events": matching_discarded,
                "audio_partial_playable": (
                    isinstance(after.get("audio"), dict)
                    and after["audio"].get("state") == "partial"
                    and isinstance(audio_probe, dict)
                    and audio_probe.get("codec") == "mp3"
                ),
                "late_frame_status": late.status_code,
            }
        finally:
            if not interrupted:
                try:
                    asyncio.run(adapter.abort(created.session_id, "acceptance cleanup"))
                except Exception:
                    pass

        journal = journal_window.read()
        status = json.dumps(status_before, sort_keys=True).encode()
        result = {
            "socket_mode": f"{mode:04o}",
            "tcp_admin_surfaces": tcp_admin_surfaces,
            "forbidden_content_matches": sum(
                status.count(value) + journal.count(value) for value in forbidden if value
            ) + int(status_surfaces["forbidden_matches"]),
            "count_mismatches": count_mismatches,
            "status_surfaces": status_surfaces,
            "interrupt_probe": interrupt_probe,
            "journal_sources": [journal_window.observation()],
        }
        self._artifact_json(
            "operator/content-free-counts.json",
            {
                "result": result,
                "status_bytes_observed": len(status),
                "journal_bytes_observed": len(journal),
                "accounts_observed": len(status_accounts)
                if isinstance(status_accounts, list)
                else None,
                "active_meetings_observed": len(active) if isinstance(active, list) else None,
            },
        )
        return result

    def meeting_modes_history_restart(self) -> dict[str, object]:
        fixture = Path(self._text("file_fixture")).expanduser()
        if not fixture.is_file():
            raise ExternalMeasurementError("File fixture is unavailable")
        url = self._text("url_fixture")
        if not url.startswith("https://"):
            raise ExternalMeasurementError("URL fixture must use https://")
        live_id = self._live_id("a")
        submitted = self.browser.submit_file_url_batch(fixture, url)
        ordered = submitted.get("ordered")
        detached = submitted.get("detached")
        if not isinstance(ordered, list) or not isinstance(detached, dict):
            raise ExternalMeasurementError("browser batch output is incomplete")
        accepted = [
            item
            for item in ordered
            if isinstance(item, dict)
            and item.get("status") == 201
            and isinstance(item.get("meeting_id"), str)
        ]
        file_ids = [
            str(item["meeting_id"])
            for item in accepted
            if item.get("path") == "/api/meetings/file"
        ]
        all_url_ids = [
            str(item["meeting_id"])
            for item in accepted
            if item.get("path") == "/api/meetings/url"
        ]
        accepted_failure_ids = [
            str(item["meeting_id"])
            for item in accepted
            if item.get("input_kind") == "accepted_failure"
        ]
        successful_url_ids = [
            meeting_id
            for meeting_id in all_url_ids
            if meeting_id not in set(accepted_failure_ids)
        ]
        detached_file_id = detached.get("meeting_id")
        if (
            len(file_ids) != 2
            or len(successful_url_ids) != 2
            or len(accepted_failure_ids) != 1
            or not isinstance(detached_file_id, str)
        ):
            raise ExternalMeasurementError("browser batch did not create the ruled Meetings")
        input_boundary_rejections = sum(
            isinstance(item, dict) and item.get("status") in {400, 422}
            for item in ordered
        )
        terminal_states = {
            meeting_id: self._await_meeting_terminal(meeting_id).get("status")
            for meeting_id in (*file_ids, *successful_url_ids, *accepted_failure_ids, detached_file_id)
        }
        accepted_failure_id = accepted_failure_ids[0]
        failure_isolated = (
            input_boundary_rejections == 1
            and terminal_states[accepted_failure_id] == "failed"
            and all(
                status == "completed"
                for meeting_id, status in terminal_states.items()
                if meeting_id != accepted_failure_id
            )
        )
        stopped = self.a.request("POST", f"/api/live/sessions/{live_id}/stop",
                                 json={"deadline": ACCEPTANCE_STOP_DEADLINE_SECONDS})
        if stopped.status_code != 200:
            # Report only what the refusal actually said -- the cause is still unestablished.
            raise ExternalMeasurementError(
                f"Live Meeting did not Stop: HTTP {stopped.status_code} {stopped.content[:200]!r}"
            )
        self._await_meeting_terminal(live_id)
        self._meetings["file"].extend(file_ids)
        self._meetings["url"].extend(successful_url_ids)
        self._meetings["live"].append(live_id)
        renamed_title = "Wave 1 durable owner title"
        renamed, _ = self.a.json(
            "PUT", f"/api/meetings/{file_ids[0]}/title", 200, json={"title": renamed_title}
        )
        first = self.a.json("GET", "/api/meetings", 200)[0]
        second = self.a_peer.json("GET", "/api/meetings", 200)[0]
        history_mismatches = int(first != second)
        before_history = first.get("meetings", [])
        before_ids = {item.get("id") for item in before_history if isinstance(item, dict)}
        restart_failures = 0
        unit = str(self.config.get("web_unit") or "moss-web.service")
        if unit != "moss-web.service":
            raise ExternalMeasurementError("Account restart unit must be moss-web.service")
        restarted = subprocess.run(
            ("systemctl", "--user", "restart", unit), check=False, capture_output=True
        )
        if restarted.returncode:
            raise ExternalMeasurementError("Account web restart failed")
        self._await_service()
        after = self.a.json("GET", "/api/meetings", 200)[0]
        after_ids = {
            item.get("id") for item in after.get("meetings", []) if isinstance(item, dict)
        }
        if before_ids != after_ids:
            restart_failures += 1
        if before_history != after.get("meetings", []):
            restart_failures += 1
        peer_renamed = next(
            (
                item
                for item in second.get("meetings", [])
                if isinstance(item, dict) and item.get("id") == file_ids[0]
            ),
            None,
        )
        if (
            renamed.get("title") != renamed_title
            or not isinstance(peer_renamed, dict)
            or peer_renamed.get("title") != renamed_title
        ):
            history_mismatches += 1
        return {
            "modes": ["live", "file", "multi_file", "url", "serial_batch"],
            "same_account_clients": 2,
            "history_mismatches": history_mismatches,
            "restart_failures": restart_failures,
            "submissions": {
                "single_file": 1,
                "multi_file": len(file_ids),
                "url": len(successful_url_ids),
                "serial_batch": len(ordered),
                "browser_closed_after_accept": 1,
                "accepted_failure": len(accepted_failure_ids),
                "input_boundary_rejection": input_boundary_rejections,
            },
            # Keep the operands of the isolation verdict, never meeting content.
            "accepted_failure_meeting_id": accepted_failure_id,
            "terminal_states": terminal_states,
            "one_item_failure_isolated": failure_isolated,
        }

    def _submit_file(self, fixture: Path) -> str:
        return self._submit_file_for(self.a, fixture)

    def _submit_file_for(self, client: AccountHttpClient, fixture: Path) -> str:
        with fixture.open("rb") as source:
            payload, _ = client.json(
                "POST",
                "/api/meetings/file",
                201,
                files={"file": (fixture.name, source, "audio/wav")},
            )
        meeting_id = payload.get("id")
        if not isinstance(meeting_id, str):
            raise ExternalMeasurementError("File create omitted Meeting ID")
        return meeting_id

    def _submit_url(self, url: str) -> str:
        payload, _ = self.a.json(
            "POST", "/api/meetings/url", 201, json={"url": url}
        )
        meeting_id = payload.get("id")
        if not isinstance(meeting_id, str):
            raise ExternalMeasurementError("URL create omitted Meeting ID")
        return meeting_id

    def _await_meeting_terminal(self, meeting_id: str, timeout: float = 1800) -> dict[str, Any]:
        return self._await_meeting_terminal_for(self.a, meeting_id, timeout)

    @staticmethod
    def _await_meeting_terminal_for(
        client: AccountHttpClient, meeting_id: str, timeout: float = 1800
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload, _ = client.json("GET", f"/api/meetings/{meeting_id}", 200)
            if payload.get("status") in {"completed", "failed", "interrupted"}:
                return payload
            time.sleep(1)
        raise ExternalMeasurementError("Meeting did not reach terminal truth")

    def _await_service(self, timeout: float = 60) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.a.request("GET", "/api/auth/session")
            if response.status_code == 200:
                return
            time.sleep(0.5)
        raise ExternalMeasurementError("Account web did not return after restart")

    def crash_recovery(self) -> dict[str, object]:
        adapter = self._replay_service(
            base_url=self.origin,
            cookie_file=Path(self._text("account_a_cookie_file")).expanduser(),
            timeout_seconds=60,
        )
        created = adapter.create()
        corpus = Path(self._text("quality_corpus")).expanduser()
        manifest = json.loads((corpus / "corpus-manifest.json").read_text())
        pcm = _wav_pcm(corpus / manifest["cases"][0]["case_id"] / "audio.wav")
        samples = created.descriptor.frame_samples
        sent_pcm = bytearray()
        durable_prefix = False
        before: dict[str, Any] = {}
        for sequence in range(max(120, int(60 * LIVE_SAMPLE_RATE / samples))):
            offset = sequence * samples * 2 % len(pcm)
            chunk = (pcm + pcm)[offset : offset + samples * 2]
            adapter.accept_frame(
                created.session_id,
                AudioFrame(sequence, chunk, samples, LIVE_SAMPLE_RATE),
            )
            sent_pcm.extend(chunk)
            time.sleep(samples / LIVE_SAMPLE_RATE)
            before, _ = self.a.json(
                "GET", f"/api/meetings/{created.session_id}", 200
            )
            transcript = before.get("transcript")
            durable_prefix = (
                isinstance(transcript, dict)
                and int(before.get("transcript_version", 0)) > 0
                and bool(transcript.get("segments"))
            )
            if durable_prefix:
                break
        if not durable_prefix:
            raise ExternalMeasurementError("crash probe did not establish a durable prefix")
        runtime_before = adapter.snapshot(created.session_id)
        if runtime_before is None or runtime_before.session.accepted_samples <= 0:
            raise ExternalMeasurementError("crash probe lacks an accepted audio prefix")
        accepted_prefix_samples = runtime_before.session.accepted_samples
        accepted_pcm = bytes(sent_pcm[: accepted_prefix_samples * 2])
        if len(accepted_pcm) != accepted_prefix_samples * 2:
            raise ExternalMeasurementError("crash probe PCM does not cover the accepted prefix")
        unit = str(self.config.get("web_unit") or "moss-web.service")
        old_pid = _unit_pid(unit)
        kill_error = None
        kill_returncode = None
        try:
            killed = subprocess.run(
                ("systemctl", "--user", "kill", "--kill-whom=main", "--signal=KILL", unit),
                check=False, capture_output=True, timeout=30,
            )
            kill_returncode = killed.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            kill_error = type(exc).__name__
        recovery = _wait_crash_recovery(_CrashRecoveryOps(self.a), unit, old_pid)
        recovery.update(kill_returncode=kill_returncode, kill_error_type=kill_error)
        self._artifact_json("crash-recovery-wait.json", recovery)
        if not recovery["ready"]:
            raise ExternalMeasurementError("Account web recovery did not become ready within 60 seconds")
        after, _ = self.a.json(
            "GET", f"/api/meetings/{created.session_id}", 200
        )
        self._meetings["crash"].append(created.session_id)
        document_mismatches = int(not _terminal_transcript_matches(before, after))
        after_audio = after.get("audio")
        recovered_audio = self.a.request(
            "GET", f"/api/meetings/{created.session_id}/audio/download"
        )
        with tempfile.TemporaryDirectory(
            prefix="moss-crash-audio-oracle-", dir=self._artifact_root()
        ) as directory:
            oracle_root = Path(directory)
            source = oracle_root / "accepted-prefix.pcm"
            source.write_bytes(_recording_mix_pcm(accepted_pcm))
            expected = MeetingAudioArchive(oracle_root / "archive").publish_live_prefix(
                "oracle-account", "oracle-meeting", source, partial=True
            )
            expected_bytes = expected.path.read_bytes()
            expected_metadata = {
                "state": "partial",
                "byte_count": expected.byte_count,
                "duration_ms": expected.duration_ms,
                "format": expected.format,
                "sample_rate_hz": expected.sample_rate_hz,
                "channels": expected.channels,
                "bit_rate_bps": expected.bit_rate_bps,
            }
        recovered_metadata = {
            key: after_audio.get(key) if isinstance(after_audio, dict) else None
            for key in expected_metadata
        }
        audio_prefix_failures = int(
            recovered_metadata != expected_metadata
            or not isinstance(after_audio, dict)
            or not isinstance(after_audio.get("relative_path"), str)
            or not after_audio["relative_path"]
            or recovered_audio.status_code != 200
            or recovered_audio.content != expected_bytes
        )
        reattach = self.a.request(
            "POST",
            f"/api/live/sessions/{created.session_id}/frames",
            json=AccountCookieLiveReplayService._lane_payload(
                AudioFrame(999, b"\0" * samples * 2, samples, LIVE_SAMPLE_RATE),
                lane="system",
                timestamp_ns=999 * samples * 1_000_000_000 // LIVE_SAMPLE_RATE,
                silent=True,
            ),
        )
        comparison = {
            "session_id": created.session_id,
            "expected_metadata": expected_metadata,
            "recovered_metadata": recovered_metadata,
            "download_status": recovered_audio.status_code,
            "recording_bytes_equal": recovered_audio.content == expected_bytes,
            "late_frame_status": reattach.status_code,
        }
        self._artifact_json("crash-audio-comparison.json", comparison)
        return {
            "cases": 1,
            "audio_comparison": comparison,
            "nonempty_durable_prefix": durable_prefix,
            "lost_commits": document_mismatches,
            "durable_document_mismatches": document_mismatches,
            "audio_prefix_failures": audio_prefix_failures,
            "accepted_prefix_samples": accepted_prefix_samples,
            "process_replaced": True,
            "recovery": recovery,
            "resumed_capture": int(200 <= reattach.status_code < 300),
            "non_interrupted_active_rows": int(after.get("status") != "interrupted"),
        }

    def audio_durability_download(self) -> dict[str, object]:
        if not self._meetings["file"] or not self._meetings["live"]:
            self.meeting_modes_history_restart()
        meeting_ids = (self._meetings["file"][0], self._meetings["live"][0])
        format_mismatches = durability_failures = owner_failures = foreign_leaks = 0
        unauthenticated_failures = revoked_failures = partial_download_failures = 0
        permission_failures = path_failures = 0
        probe_rows: list[dict[str, object]] = []
        root = Path(self._text("meeting_audio_root")).expanduser().resolve()
        for meeting_id in meeting_ids:
            payload = self._await_meeting_terminal(meeting_id)
            audio = payload.get("audio")
            if not isinstance(audio, dict) or audio.get("state") != "available":
                durability_failures += 1
                continue
            if (
                audio.get("format") != "mp3"
                or audio.get("sample_rate_hz") != 16_000
                or audio.get("channels") != 1
                or audio.get("bit_rate_bps") != 48_000
            ):
                format_mismatches += 1
            owner = self.a.request("GET", f"/api/meetings/{meeting_id}/audio/download")
            if owner.status_code != 200 or not owner.content:
                owner_failures += 1
            else:
                measured = _probe_mp3(owner.content)
                probe_rows.append({"state": "available", **measured})
                if not (
                    measured.get("codec") == "mp3"
                    and measured.get("sample_rate_hz") == 16_000
                    and measured.get("channels") == 1
                    and measured.get("bit_rate_bps") == 48_000
                ):
                    format_mismatches += 1
                if len(owner.content) != audio.get("byte_count"):
                    format_mismatches += 1
                disposition = owner.headers.get("content-disposition", "")
                if ".mp3" not in disposition or "partial" in disposition.casefold():
                    owner_failures += 1
            relative = audio.get("relative_path")
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
                path_failures += 1
            else:
                stored = (root / relative).resolve()
                if root not in stored.parents or not stored.is_file():
                    path_failures += 1
                else:
                    permission_failures += int(stat.S_IMODE(stored.stat().st_mode) != 0o600)
                    permission_failures += int(
                        any(
                            stat.S_IMODE(parent.stat().st_mode) != 0o700
                            for parent in stored.parents
                            if parent == root or root in parent.parents
                        )
                    )
            foreign = self.b.request("GET", f"/api/meetings/{meeting_id}/audio/download")
            if foreign.status_code != 404:
                foreign_leaks += 1
            if self.revoked_probe.request(
                "GET", f"/api/meetings/{meeting_id}/audio/download"
            ).status_code != 401:
                revoked_failures += 1
            try:
                anonymous = httpx.get(
                    f"{self.origin}/api/meetings/{meeting_id}/audio/download",
                    follow_redirects=False,
                    timeout=30,
                )
            except httpx.HTTPError as exc:
                raise ExternalMeasurementError(
                    "anonymous audio boundary transport failed"
                ) from exc
            if anonymous.status_code != 401:
                unauthenticated_failures += 1
        cleanup_failures = sum(
            1
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".wav", ".pcm", ".raw"}
        )
        partial_cases = 0
        if not self._meetings["crash"] and not self._meetings["partial"]:
            # Pre-admission has no process-kill probe. Exercise a deliberate
            # audio-bearing abort, instead of depending on incidental failures.
            partial_id = self._new_live_id("a")
            try:
                self._seed_live_transcript("a", partial_id, 0)
            finally:
                response = self.a.request(
                    "POST", f"/api/live/sessions/{partial_id}/abort", json={}
                )
                if response.status_code not in {200, 409}:
                    raise ExternalMeasurementError(
                        f"partial audio abort failed: session_id={partial_id}, "
                        f"status={response.status_code}"
                    )
                registered = self._live_helpers.pop(partial_id, None)
                if registered is not None:
                    registered[1].close()
                if self._live.get("a") == partial_id:
                    self._live.pop("a")
            self._await_meeting_terminal(partial_id)
            self._meetings["partial"].append(partial_id)
        if self._meetings["crash"] or self._meetings["partial"]:
            crash_id = (self._meetings["crash"] or self._meetings["partial"])[0]
            partial = self.a.json(
                "GET", f"/api/meetings/{crash_id}", 200
            )[0]
            partial_audio = partial.get("audio")
            partial_cases = int(
                isinstance(partial_audio, dict)
                and partial_audio.get("state") == "partial"
            )
            partial_response = self.a.request(
                "GET", f"/api/meetings/{crash_id}/audio/download"
            )
            if (
                partial_response.status_code != 200
                or not partial_response.content
                or "partial" not in partial_response.headers.get(
                    "content-disposition", ""
                ).casefold()
            ):
                partial_download_failures += 1
            else:
                measured = _probe_mp3(partial_response.content)
                probe_rows.append({"state": "partial", **measured})
                if (
                    not isinstance(partial_audio, dict)
                    or len(partial_response.content) != partial_audio.get("byte_count")
                    or measured.get("codec") != "mp3"
                    or measured.get("sample_rate_hz") != 16_000
                    or measured.get("channels") != 1
                    or measured.get("bit_rate_bps") != 48_000
                ):
                    partial_download_failures += 1
            if self.b.request(
                "GET", f"/api/meetings/{crash_id}/audio/download"
            ).status_code != 404:
                foreign_leaks += 1

        # A missing archive member is a reachable operator/filesystem failure. The public download
        # path owns reconciliation and must make durable metadata truthful before returning 404.
        out_of_band_id = self._submit_file(Path(self._text("file_fixture")).expanduser())
        out_of_band = self._await_meeting_terminal(out_of_band_id)
        out_audio = out_of_band.get("audio")
        out_of_band_reconciled = False
        if isinstance(out_audio, dict) and isinstance(out_audio.get("relative_path"), str):
            stored = root / str(out_audio["relative_path"])
            stored.unlink()
            missing = self.a.request("GET", f"/api/meetings/{out_of_band_id}/audio/download")
            reconciled = self.a.json("GET", f"/api/meetings/{out_of_band_id}", 200)[0]
            reconciled_audio = reconciled.get("audio")
            out_of_band_reconciled = (
                missing.status_code == 404
                and isinstance(reconciled_audio, dict)
                and reconciled_audio.get("state") == "unavailable"
            )
        result = {
            "live_cases": 1,
            "file_cases": 1,
            "format_mismatches": format_mismatches,
            "durability_failures": durability_failures,
            "cleanup_failures": cleanup_failures,
            "owner_download_failures": owner_failures,
            "foreign_leaks": foreign_leaks,
            "unauthenticated_failures": unauthenticated_failures,
            "revoked_failures": revoked_failures,
            "partial_download_failures": partial_download_failures,
            "partial_or_unavailable_crash_cases": partial_cases,
            "path_failures": path_failures,
            "permission_failures": permission_failures,
            "out_of_band_reconciled": out_of_band_reconciled,
            "ffprobe": probe_rows,
        }
        self._artifact_json("audio/content-free-format-durability.json", result)
        return result

    def account_product_regression(self) -> dict[str, object]:
        active_id = self._new_live_id("a")
        try:
            completed = self._durable_transcript_meeting()
            result = self.browser.product_regression(active_id, str(completed["id"]))
            self._artifact_json("browser/product-suite-counts.json", result)
            return result
        finally:
            failed = sys.exc_info()[0] is not None
            try:
                response = self.a.request(
                    "POST", f"/api/live/sessions/{active_id}/abort", json={}
                )
                if response.status_code not in {200, 409}:
                    raise ExternalMeasurementError(
                        f"product observer cleanup failed: session_id={active_id}, "
                        f"abort_status={response.status_code}"
                    )
                registered = self._live_helpers.pop(active_id, None)
                if registered is not None:
                    registered[1].close()
                if self._live.get("a") == active_id:
                    self._live.pop("a")
            except Exception:
                # Keep failed cleanup registered for the campaign's final sweep;
                # a secondary cleanup failure must not erase the browser failure.
                if not failed:
                    raise

    def transcript_pane_fidelity(self) -> dict[str, object]:
        result = self.browser.transcript_fidelity(self._durable_transcript_meeting())
        self._artifact_json("browser/transcript-fidelity-metrics.json", result)
        return result

    def _durable_transcript_meeting(self) -> dict[str, object]:
        payload, _ = self.a.json("GET", "/api/meetings", 200)
        meetings = payload.get("meetings")
        if isinstance(meetings, list):
            for meeting in meetings:
                transcript = meeting.get("transcript") if isinstance(meeting, dict) else None
                segments = transcript.get("segments") if isinstance(transcript, dict) else None
                if (
                    meeting.get("status") in {"completed", "interrupted"}
                    and isinstance(segments, list)
                    and segments
                ):
                    return meeting
        fixture = Path(self._text("file_fixture")).expanduser()
        meeting_id = self._submit_file(fixture)
        return self._await_meeting_terminal(meeting_id)

    def quality_corpus(self) -> dict[str, object]:
        """Run the frozen six cases twice through Account Live and the retained scorer."""

        repo = Path(self._text("repo_root")).resolve()
        corpus = Path(self._text("quality_corpus")).expanduser().resolve()
        work = Path(self._text("campaign_work_dir")).resolve() / "quality"
        work.parent.mkdir(mode=0o700, exist_ok=True)
        os.mkdir(work, mode=0o700)
        manifest_path = corpus / "corpus-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        cases = manifest.get("cases") if isinstance(manifest, dict) else None
        if not isinstance(cases, list) or len(cases) != 6:
            raise ExternalMeasurementError("quality corpus must contain six cases")
        expected_ids = {
            "mono_javier_intro_50s",
            "interview_bill_ackman_60s",
            "interview_keyu_jin_60s",
            "interview_adam_frank_180s",
            "discussion_jamie_dimon_180s",
            "discussion_rtfl_90s",
        }
        case_by_id = {
            str(item.get("case_id")): item for item in cases if isinstance(item, dict)
        }
        if set(case_by_id) != expected_ids:
            raise ExternalMeasurementError("quality corpus case IDs differ from the frozen set")
        input_identities = _verify_quality_inputs(
            repo=repo, corpus=corpus, cases=cases
        )
        surface = _load_surface_harness(repo)
        observations: list[dict[str, object]] = []
        descriptor_identity: tuple[str, str, str] | None = None
        order = tuple(item["case_id"] for item in cases)
        cookie_paths = (
            Path(self._text("account_a_cookie_file")).expanduser(),
            Path(self._text("account_b_cookie_file")).expanduser(),
        )
        for pass_number in (1, 2):
            pass_order = order if pass_number == 1 else tuple(reversed(order))
            for index, case_id in enumerate(pass_order):
                case_dir = corpus / str(case_id)
                audio = case_dir / "audio.wav"
                reference = case_dir / "reference.jsonl"
                if not audio.is_file() or not reference.is_file():
                    raise ExternalMeasurementError("quality case input is incomplete")
                adapter = self._replay_service(
                    base_url=self.origin,
                    cookie_file=cookie_paths[index % 2],
                    timeout_seconds=300,
                )
                descriptor = adapter.descriptor()
                identity = (
                    descriptor.source_revision,
                    descriptor.provider_manifest_hash,
                    descriptor.config_hashes.combined_config_hash,
                )
                if descriptor_identity is None:
                    descriptor_identity = identity
                elif descriptor_identity != identity:
                    raise ExternalMeasurementError("quality descriptor changed during campaign")
                captured = surface.SurfaceCaptureService(
                    adapter,
                    settle_timeout=30.0,
                    poll_seconds=0.25,
                )
                run_dir = work / f"pass-{pass_number}" / str(case_id)
                run_dir.parent.mkdir(mode=0o700, exist_ok=True)
                trace = run_dir / "run-001" / "trace.jsonl"
                try:
                    run_service_replay(
                        service=captured,
                        audio_path=audio,
                        out_dir=run_dir,
                        pace=1.0,
                        max_pacing_lag=3.0,
                        runs=1,
                        expect_revision=identity[0],
                        expect_provider_hash=identity[1],
                        expect_config_hash=identity[2],
                    )
                    trace = run_dir / "run-001" / "trace.jsonl"
                    if "post_stop_final" not in captured.captures:
                        for line in trace.read_text(encoding="utf-8").splitlines():
                            row = json.loads(line)
                            if row.get("kind") == "terminal" and isinstance(row.get("snapshot"), dict):
                                from .live_service_replay import _snapshot_from_dict

                                captured._capture(
                                    "post_stop_final", _snapshot_from_dict(row["snapshot"])
                                )
                finally:
                    self._artifact_json(
                        f"quality/pass-{pass_number}/{case_id}/terminal-diagnostics.json",
                        _quality_terminal_diagnostics(trace, adapter, captured),
                    )
                required_surfaces = (
                    "pre_stop_immediate",
                    "pre_stop_settled",
                    "post_stop_final",
                )
                if any(name not in captured.captures for name in required_surfaces):
                    raise ExternalMeasurementError("quality run missed a transcript surface")
                duration = _wav_duration(audio)
                scored: dict[str, dict[str, object]] = {}
                settled_rows: list[dict[str, Any]] | None = None
                case = surface.Case(str(case_id), case_dir, reference)
                for name in required_surfaces:
                    rows = surface.transcript_rows(
                        captured.captures[name]["snapshot"], duration
                    )
                    scored[name] = surface.score_surface(case, rows)
                    if name == "pre_stop_settled":
                        settled_rows = rows
                assert settled_rows is not None
                speaker_intervals = _quality_speaker_intervals(
                    captured.captures["pre_stop_settled"]["snapshot"],
                    settled_rows, reference,
                    speech_regions=surface.speech_regions_from_wav(audio),
                )
                if (speaker_intervals["settled_der_s00_diagnostic"]["as_is"]
                        != scored["pre_stop_settled"]["der"]):
                    raise ExternalMeasurementError("settled DER interval replay disagrees with scorer")
                diagnostic = speaker_intervals["settled_der_s00_diagnostic"]
                settled = scored["pre_stop_settled"]
                if ("reference_speech_as_is" in diagnostic
                        and diagnostic["reference_speech_as_is"] != settled["reference_speech_der"]):
                    raise ExternalMeasurementError("reference-speech DER interval replay disagrees with scorer")
                settled["der_raw"] = settled["der"]
                settled["reference_speech_der_raw"] = settled["reference_speech_der"]
                settled["der"] = diagnostic["without_s00_confusion"]
                settled["reference_speech_der"] = diagnostic["reference_speech_without_s00_confusion"]
                events = surface.read_service_events(trace)
                measurements = surface.event_measurements(
                    events,
                    captured.captures["pre_stop_settled"]["snapshot"],
                    captured.captures["post_stop_final"],
                    captured.stop_requested_monotonic_ns,
                    duration,
                )
                final_session = captured.captures["post_stop_final"]["snapshot"]["session"]
                window_coverage = _quality_window_coverage(
                    events, accepted_samples=final_session["accepted_samples"],
                    finalization_status=final_session.get("finalization_status"),
                )
                trace_rows = [
                    json.loads(line)
                    for line in trace.read_text(encoding="utf-8").splitlines()
                    if line
                ]
                created_rows = [
                    row for row in trace_rows if row.get("kind") == "session_created"
                ]
                if (
                    len(created_rows) != 1
                    or not isinstance(created_rows[0].get("session_id"), str)
                ):
                    raise ExternalMeasurementError("quality trace lacks one exact session ID")
                observations.append(
                    {
                        "case_id": str(case_id),
                        "pass": pass_number,
                        "session_id": f"session-{len(observations) + 1:02d}",
                        "category": case_by_id[str(case_id)].get("category"),
                        "duration_seconds": duration,
                        "windows": window_coverage["rolling_decoded"],
                        "window_coverage": window_coverage,
                        "metrics": {
                            "immediate": scored["pre_stop_immediate"],
                            "settled": scored["pre_stop_settled"],
                            "final": scored["post_stop_final"],
                        },
                        **speaker_intervals,
                        "surface_observations": _quality_surface_observations(
                            captured.captures,
                            reference_speaker_count=len({json.loads(line)["speaker"]
                                for line in reference.read_text(encoding="utf-8").splitlines() if line.strip()}),
                        ),
                        "event_counts": {
                            "service": len(events),
                            "trace": len(trace_rows),
                            "rolling_windows": len(
                                measurements["rolling_queue"]["windows"]
                            ),
                        },
                    }
                )
        result = _quality_projection(
            observations,
            corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
        result["input_identities"] = input_identities
        self._artifact_json("quality/content-free-metrics.json", result)
        return result

    def two_session_capacity(self) -> dict[str, object]:
        result = self._run_live_load(sessions=2, duration_seconds=600.0)
        backpressure = self._backpressure_probe()
        result.update(
            {
                "accounts": 2,
                "real_human_speech": True,
                "ingress_cadence_seconds": 0.5,
                "continuous_wrong_owner_probes": result.pop("wrong_owner_probes") > 0,
                "per_session_429_peer_progress_retry": all(
                    backpressure[key] is True
                    for key in ("observed_429", "peer_progress", "same_sequence_retry")
                ),
                "backpressure_observation": backpressure,
            }
        )
        return result

    def voiceprint_production_rule(self) -> dict[str, object]:
        from .phase2_acceptance_completion import measure_voiceprint_rule
        return measure_voiceprint_rule(self)

    def voiceprint_workspace_behavior(self) -> dict[str, object]:
        from .phase2_acceptance_completion import measure_voiceprint_workspace
        return measure_voiceprint_workspace(self)

    def browser_final_summary(self) -> dict[str, object]:
        from .phase2_acceptance_summary import measure_browser_summary
        return measure_browser_summary(self)

    def excess_admission_overload(self) -> dict[str, object]:
        descriptor = self.a.json("GET", "/api/live/descriptor", 200)[0]["descriptor"]
        capacity_samples = int(descriptor["bounds"]["max_retained_samples"])
        frame_samples = int(descriptor["frame_samples"])
        # One retained buffer plus another buffer of drain headroom, then one
        # whole frame beyond it. Keep peers paced for the same audio duration so
        # the target's refusal/retry occurs inside this eight-session campaign.
        frames = max(math.ceil(30 * LIVE_SAMPLE_RATE / frame_samples),
                     overload_minimum_frames(capacity_samples, frame_samples))
        duration = frames * frame_samples / LIVE_SAMPLE_RATE
        result = self._run_live_load(
            sessions=2,
            duration_seconds=duration,
            embedded_backpressure=True,
        )
        backpressure = result.pop("embedded_backpressure_observation")
        if not isinstance(backpressure, dict):
            raise ExternalMeasurementError(
                "two-session overload campaign omitted its backpressure observation"
            )
        result.update(
            {
                "accounts": 2,
                "isolation_failures": int(result["cross_account_sentinel_deliveries"])
                + int(result["marker_isolation_failures"]),
                "fairness_failures": int(
                    result["dispatch_skew"] > 1
                    or result["fairness_measured"] is not True
                ),
                "per_session_backpressure_observed": backpressure["observed_429"],
                "peer_progress_during_backpressure": backpressure["peer_progress"],
                "refused_frame_retry_succeeded": backpressure["same_sequence_retry"],
                "backpressure_observation": backpressure,
                "backpressure_workload": {"lane_capacity_samples": capacity_samples,
                                          "frame_samples": frame_samples,
                                          "frames_per_session": frames,
                                          "audio_seconds_per_session": duration},
            }
        )
        return result

    def _run_live_load(
        self,
        *,
        sessions: int,
        duration_seconds: float,
        embedded_backpressure: bool = False,
    ) -> dict[str, object]:
        if embedded_backpressure and sessions != 2:
            raise ValueError("embedded backpressure belongs to the two-session overload campaign")
        artifact_prefix = "overload/" if embedded_backpressure else ""
        repo = Path(self._text("repo_root")).resolve()
        fixture = json.loads(
            (repo / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json")
            .read_text(encoding="utf-8")
        )
        clips = fixture.get("clips") if isinstance(fixture, dict) else None
        audio_config = fixture.get("audio") if isinstance(fixture, dict) else None
        if not isinstance(clips, list) or len(clips) < sessions or not isinstance(audio_config, dict):
            raise ExternalMeasurementError("capacity fixture lacks unique session clips")
        source_audio = repo / str(audio_config.get("path"))
        session_inputs = [
            (
                _wav_pcm_clip(
                    source_audio,
                    float(clips[index]["start_seconds"]),
                    float(clips[index]["end_seconds"]),
                ),
                str(clips[index]["expected_marker"]),
            )
            for index in range(sessions)
        ]
        cookie_paths = (
            Path(self._text("account_a_cookie_file")).expanduser(),
            Path(self._text("account_b_cookie_file")).expanduser(),
        )
        web_unit = str(self.config.get("web_unit") or "moss-web.service")
        web_pid = _unit_pid(web_unit)
        vllm_pid = _unit_pid("moss-vllm.service")
        rss_before = _process_tree_rss(web_pid) + _process_tree_rss(vllm_pid)
        log_windows = {
            "server_log": self._journal_window(web_unit),
            "vllm_log": self._journal_window("moss-vllm.service"),
        }
        barrier = threading.Barrier(sessions)
        lock = threading.Lock()
        created: list[tuple[str, int, int]] = []
        outputs: list[dict[str, object]] = []
        failures: list[str] = []
        cross_sentinel_deliveries = 0
        wrong_owner_observations: list[dict[str, object]] = []
        a_sentinel = Path(self._text("account_a_sentinel_file")).read_bytes().strip()
        b_sentinel = Path(self._text("account_b_sentinel_file")).read_bytes().strip()
        rss_samples = [rss_before]
        cache_samples = [_vllm_cache_use(self._text("vllm_metrics_url"))]
        next_resource_sample = time.monotonic() + 2.0
        backpressure = _CampaignBackpressure(sessions) if embedded_backpressure else None

        def worker(index: int) -> None:
            nonlocal cross_sentinel_deliveries
            owner = index % 2
            adapter = self._replay_service(
                base_url=self.origin,
                cookie_file=cookie_paths[owner],
                timeout_seconds=300,
            )
            probe = AccountHttpClient(self.origin, cookie_paths[1 - owner])
            session_id: str | None = None
            terminal = False
            captured_events = _LoadEventCapture()
            try:
                descriptor = adapter.descriptor()
                frame_samples = descriptor.frame_samples
                cadence = frame_samples / LIVE_SAMPLE_RATE
                if not math.isclose(cadence, 0.5, abs_tol=1e-9):
                    raise ExternalMeasurementError("capacity descriptor cadence is not 0.5 s")
                pcm, marker = session_inputs[index]
                created_result = adapter.create()
                session_id = created_result.session_id
                with lock:
                    created.append((session_id, owner, index + 1))
                barrier.wait(timeout=30)
                started = time.monotonic()
                started_ns = time.monotonic_ns()
                frames = int(duration_seconds / cadence)
                last_snapshot = created_result.snapshot
                maximum_pending = last_snapshot.pending_work_items
                for sequence in range(frames):
                    offset = sequence * frame_samples * 2 % len(pcm)
                    chunk = (pcm + pcm)[offset : offset + frame_samples * 2]
                    if not (embedded_backpressure and index == 0):
                        target = started + sequence * cadence
                        delay = target - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                    frame = AudioFrame(
                        sequence=sequence,
                        pcm=chunk,
                        sample_count=frame_samples,
                        sample_rate=LIVE_SAMPLE_RATE,
                    )
                    last_snapshot = (
                        adapter.accept_frame(session_id, frame).snapshot
                        if backpressure is None
                        else backpressure.accept(index, adapter, session_id, frame)
                    )
                    captured_events.read(adapter, session_id)
                    maximum_pending = max(maximum_pending, last_snapshot.pending_work_items)
                    response = probe.request(
                        "GET", f"/api/live/sessions/{session_id}/snapshot"
                    )
                    forbidden = a_sentinel if owner == 0 else b_sentinel
                    foreign_matches = response.content.count(forbidden)
                    with lock:
                        wrong_owner_observations.append(
                            {
                                "session_ordinal": index + 1,
                                "sequence": sequence,
                                "status": response.status_code,
                                "foreign_matches": foreign_matches,
                            }
                        )
                        if response.status_code != 404:
                            failures.append("CrossOwnerProbe")
                        cross_sentinel_deliveries += foreign_matches
                stopped = asyncio.run(adapter.stop(session_id, ACCEPTANCE_STOP_DEADLINE_SECONDS))
                terminal = True
                captured_events.read(adapter, session_id)
                payloads = captured_events.events
                lags = [
                    max(
                        0.0,
                        (int(event["payload"]["runtime_monotonic_ns"]) - started_ns)
                        / 1_000_000_000
                        - int(event["payload"]["committed_samples"]) / LIVE_SAMPLE_RATE,
                    )
                    for event in payloads
                    if event.get("kind") == "canonical_processed"
                    and isinstance(event.get("payload"), dict)
                    and isinstance(event["payload"].get("runtime_monotonic_ns"), int)
                    and isinstance(event["payload"].get("committed_samples"), int)
                    and event["payload"].get("submitted") is True
                ]
                transcript_text = "\n".join(
                    segment.text for segment in stopped.session.effective_transcript
                ).casefold()
                foreign_markers = [
                    candidate.casefold()
                    for position, (_candidate_pcm, candidate) in enumerate(session_inputs)
                    if position != index
                ]
                with lock:
                    outputs.append(
                        {
                            "ordinal": index + 1,
                            "account_ordinal": owner + 1,
                            "session_id": session_id,
                            "frames": frames,
                            "lags": lags,
                            "accepted_samples": stopped.session.accepted_samples,
                            "accounted_samples": stopped.session.accounted_samples,
                            "finalization_status": stopped.session.finalization_status,
                            "events": payloads,
                            "maximum_pending_work_items": maximum_pending,
                            "own_marker_present": marker.casefold() in transcript_text,
                            "foreign_markers_absent": all(
                                candidate not in transcript_text for candidate in foreign_markers
                            ),
                        }
                    )
            except Exception as exc:
                with lock:
                    failures.append(type(exc).__name__)
            finally:
                if session_id is not None:
                    self._artifact_json(f"{artifact_prefix}load-{sessions}/session-{index + 1}-events.json", {
                        "session_id": session_id, "next_seq": captured_events.next_seq,
                        "events": [_diagnostic_event(event) for event in captured_events.events
                                   if event.get("kind") in _DIAGNOSTIC_EVENT_KINDS],
                    })
                    wait = getattr(adapter, "stop_observations", {}).get(session_id)
                    if wait is not None:
                        self._artifact_json(f"{artifact_prefix}load-{sessions}/session-{index + 1}-stop-wait.json", wait)
                probe.close()
                if session_id is not None and not terminal:
                    try:
                        asyncio.run(adapter.abort(session_id, "acceptance load failure"))
                    except Exception:
                        with lock:
                            failures.append("LoadCleanup")

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(sessions)]
        campaign_started_ns = time.monotonic_ns()
        for thread in threads:
            thread.start()
        admission_observation = None
        if embedded_backpressure:
            admission_deadline = time.monotonic() + 30
            while time.monotonic() < admission_deadline:
                with lock:
                    accepted = tuple(created)
                if len(accepted) == sessions or not any(
                    thread.is_alive() for thread in threads
                ):
                    break
                time.sleep(0.01)
            response = self.a.request(
                "POST", "/api/live/sessions", json={"echo_mode": "speakers"}
            )
            try:
                response_payload = response.json()
            except ValueError:
                response_payload = {}
            detail = response_payload.get("detail", {}) if isinstance(response_payload, dict) else {}
            active_after_refusal = []
            for session_id, owner, _ordinal in accepted:
                client = self.a if owner == 0 else self.b
                snapshot, _ = client.json(
                    "GET", f"/api/live/sessions/{session_id}/snapshot", 200
                )
                active_after_refusal.append(
                    ((snapshot.get("snapshot") or {}).get("session") or {}).get("status")
                    == "active"
                )
            admission_observation = {
                "accepted_sessions": len(accepted),
                "excess_attempts": 1,
                "excess_status": response.status_code,
                "refusal_code": detail.get("code") if isinstance(detail, dict) else None,
                "accepted_active_after_refusal": all(active_after_refusal)
                and len(active_after_refusal) == sessions,
            }
            if response.status_code == 201 and isinstance(response_payload, dict):
                excess_id = response_payload.get("id")
                if isinstance(excess_id, str):
                    self.a.request(
                        "POST", f"/api/live/sessions/{excess_id}/abort", json={}
                    )
        wrong_owner_probes = 0
        while any(thread.is_alive() for thread in threads):
            if time.monotonic() >= next_resource_sample:
                rss_samples.append(
                    _process_tree_rss(web_pid) + _process_tree_rss(vllm_pid)
                )
                cache_samples.append(_vllm_cache_use(self._text("vllm_metrics_url")))
                next_resource_sample = time.monotonic() + 2.0
            for thread in threads:
                thread.join(timeout=0.25)
        campaign_finished_ns = time.monotonic_ns()
        if backpressure is not None:
            # Preserve the actual refusal/retry outcome even when a worker fails.
            self._artifact_json(f"{artifact_prefix}load-{sessions}/backpressure-observation.json", backpressure.observation())
        if failures or len(outputs) != sessions:
            raise ExternalMeasurementError(
                f"live load failed in {len(failures)} session/probe paths"
            )
        wrong_owner_probes = len(wrong_owner_observations)
        rss_after = _process_tree_rss(web_pid) + _process_tree_rss(vllm_pid)
        rss_samples.append(rss_after)
        cache_samples.append(_vllm_cache_use(self._text("vllm_metrics_url")))
        all_events = [event for output in outputs for event in output["events"]]  # type: ignore[index]
        accepted_audio_seconds = sum(
            int(output["accepted_samples"]) for output in outputs
        ) / LIVE_SAMPLE_RATE
        try:
            inference = prestop_inference_projection(
                all_events,
                accepted_audio_seconds=accepted_audio_seconds,
            )
        except ValueError as exc:
            if embedded_backpressure:
                self._artifact_json(
                    "overload/prestop-inference-failure.json",
                    _prestop_inference_failure_record(
                        outputs, accepted_audio_seconds, str(exc)
                    ),
                )
            raise
        rolling_pending: dict[str, set[int]] = defaultdict(set)
        refinement_depth = 0
        terminal_failures = 0
        lifecycle = sorted(
            (
                event
                for event in all_events
                if event.get("kind")
                in {"canonical_queued", "canonical_started", "canonical_processed"}
            ),
            key=lambda event: int((event.get("payload") or {}).get("runtime_monotonic_ns", 0)),
        )
        fairness = canonical_lifecycle_fairness(
            lifecycle,
            {str(output["session_id"]) for output in outputs},
            maximum_skew=1,
        )
        dispatch_skew = int(fairness.get("maximum_contended_pair_dispatch_skew", 2))
        if fairness.get("passes") is not True:
            failures.append("StandingFairnessEvaluator")
        for event in all_events:
            kind = event.get("kind")
            payload = event.get("payload") or {}
            session_id = str(event.get("session_id") or "")
            if kind == "rolling_decode_queued" and payload.get("admitted") is True:
                item_id = payload.get("item_id")
                if isinstance(item_id, int):
                    rolling_pending[session_id].add(item_id)
                    refinement_depth = max(
                        refinement_depth, len(rolling_pending[session_id])
                    )
            elif kind == "rolling_decode_completed":
                item_id = payload.get("item_id")
                if isinstance(item_id, int):
                    rolling_pending[session_id].discard(item_id)
            elif kind == "terminal_finalization_failed":
                terminal_failures += 1
        accepted_expected = int(duration_seconds * LIVE_SAMPLE_RATE)
        sequence_gaps = sum(
            int(output["accepted_samples"] != accepted_expected) for output in outputs
        )
        dropped_commits = sum(
            int(output["accounted_samples"] != output["accepted_samples"])
            for output in outputs
        )
        marker_isolation_failures = sum(
            int(
                output["own_marker_present"] is not True
                or output["foreign_markers_absent"] is not True
            )
            for output in outputs
        )
        logs = b""
        log_byte_counts: dict[str, int] = {}
        for key, window in log_windows.items():
            tail = window.read()
            log_byte_counts[key] = len(tail)
            logs += tail.lower()
        oom_errors = logs.count(b"out of memory") + logs.count(b"cuda oom")
        accelerator_errors = logs.count(b"accelerator error") + logs.count(b"cuda error")
        result = {
            "sessions": sessions,
            "requested_duration_seconds": duration_seconds,
            "duration_seconds": (campaign_finished_ns - campaign_started_ns)
            / 1_000_000_000,
            "campaign_interval": {
                "started_monotonic_ns": campaign_started_ns,
                "finished_monotonic_ns": campaign_finished_ns,
            },
            "transcript_lag_seconds": {
                f"session-{index + 1:02d}": output["lags"]
                for index, output in enumerate(outputs)
            },
            "dispatch_skew": dispatch_skew,
            "fairness_measured": fairness.get("applicability") == "measured"
            and fairness.get("passes") is True,
            "prestop_inference_rtf": inference["rtf"],
            "refinement_queue_depth": refinement_depth,
            "rss_growth_bytes": max(rss_samples) - min(rss_samples),
            "rss_samples": rss_samples,
            "vllm_gpu_cache_samples": cache_samples,
            "vllm_gpu_cache_use": max(cache_samples),
            "oom_errors": oom_errors,
            "journal_sources": [window.observation() for window in log_windows.values()],
            "accelerator_errors": accelerator_errors,
            "sequence_gaps": sequence_gaps,
            "dropped_canonical_commits": dropped_commits,
            "terminal_failures": terminal_failures,
            "cross_account_sentinel_deliveries": cross_sentinel_deliveries,
            "marker_isolation_failures": marker_isolation_failures,
            "wrong_owner_probes": wrong_owner_probes,
            "wrong_owner_observations": wrong_owner_observations,
            "fairness_observation": fairness,
            "session_observations": [
                {
                    "session_ordinal": output["ordinal"],
                    "account_ordinal": output["account_ordinal"],
                    "frames": output["frames"],
                    "lags": output["lags"],
                    "accepted_samples": output["accepted_samples"],
                    "accounted_samples": output["accounted_samples"],
                    "finalization_status": output["finalization_status"],
                    "maximum_pending_work_items": output[
                        "maximum_pending_work_items"
                    ],
                    "own_marker_present": output["own_marker_present"],
                    "foreign_markers_absent": output["foreign_markers_absent"],
                    "session_id": output["session_id"],
                    "events": [
                        _diagnostic_event(event)
                        for event in output["events"]
                        if event.get("kind") in _DIAGNOSTIC_EVENT_KINDS
                    ],
                }
                for output in sorted(outputs, key=lambda item: int(item["ordinal"]))
            ],
            "log_match_counts": {
                "oom": oom_errors,
                "accelerator": accelerator_errors,
            },
        }
        if embedded_backpressure:
            assert backpressure is not None
            result["embedded_backpressure_observation"] = backpressure.observation()
            result["admission_observation"] = admission_observation
        label = f"{artifact_prefix}capacity-{sessions}"
        self._artifact_json(
            f"{label}/observations.json",
            {
                "result": result,
                "sessions": result["session_observations"],
                "wrong_owner_observations": wrong_owner_observations,
                "rss_samples": rss_samples,
                "vllm_gpu_cache_samples": cache_samples,
                "observed_log_bytes": log_byte_counts,
                "log_match_counts": {
                    "oom": oom_errors,
                    "accelerator": accelerator_errors,
                },
            },
        )
        return result

    def _backpressure_probe(self) -> dict[str, object]:
        # Existing replay/account transport owns exact retry identity.  Saturate one Meeting while
        # advancing its peer; only an observed refusal followed by accepted same-sequence retry can
        # satisfy this predicate.
        corpus = Path(self._text("quality_corpus")).expanduser().resolve()
        manifest = json.loads((corpus / "corpus-manifest.json").read_text())
        case_id = manifest["cases"][0]["case_id"]
        pcm = _wav_pcm(corpus / case_id / "audio.wav")
        hot = self._replay_service(
            base_url=self.origin,
            cookie_file=Path(self._text("account_a_cookie_file")).expanduser(),
            timeout_seconds=30,
        )
        peer = self._replay_service(
            base_url=self.origin,
            cookie_file=Path(self._text("account_b_cookie_file")).expanduser(),
            timeout_seconds=30,
        )
        hot_created, peer_created = hot.create(), peer.create()
        samples = hot_created.descriptor.frame_samples
        chunk = (pcm + pcm)[: samples * 2]
        refused: tuple[dict[str, object], int] | None = None
        peer_progress = False
        result: dict[str, object] | None = None
        cleanup_failures = 0
        try:
            for sequence in range(256):
                frame = AudioFrame(sequence, chunk, samples, LIVE_SAMPLE_RATE)
                timestamp_ns = sequence * samples * 1_000_000_000 // LIVE_SAMPLE_RATE
                for lane, silent, pcm_bytes in (
                    ("system", False, frame.pcm),
                    ("microphone", True, b"\0" * len(frame.pcm)),
                ):
                    payload = AccountCookieLiveReplayService._lane_payload(
                        AudioFrame(sequence, pcm_bytes, samples, LIVE_SAMPLE_RATE),
                        lane=lane,
                        timestamp_ns=timestamp_ns,
                        silent=silent,
                    )
                    try:
                        hot.accept_lane(hot_created.session_id, payload)
                    except AccountReplayTransportFailure as exc:
                        if exc.http_status == 429:
                            refused = (payload, sequence)
                            break
                        raise
                hot.heartbeat(hot_created.session_id)
                if refused is not None:
                    break
            peer_result = peer.accept_frame(
                peer_created.session_id,
                AudioFrame(0, chunk, samples, LIVE_SAMPLE_RATE),
            )
            peer_progress = peer_result.ack.accepted_samples > 0
            retry_succeeded = False
            if refused is not None:
                retry_deadline = time.monotonic() + 30.0
                while time.monotonic() < retry_deadline:
                    hot.heartbeat(hot_created.session_id)
                    peer.heartbeat(peer_created.session_id)
                    try:
                        retry = hot.accept_lane(hot_created.session_id, refused[0])
                    except AccountReplayTransportFailure as exc:
                        if exc.http_status != 429:
                            raise
                        time.sleep(0.25)
                        continue
                    retry_succeeded = (
                        isinstance(retry.get("ack"), dict)
                        and int(retry["ack"].get("accepted_samples", 0)) > 0
                    )
                    break
            result = {
                "observed_429": refused is not None,
                "peer_progress": peer_progress,
                "same_sequence_retry": retry_succeeded,
                "refused_sequence": None if refused is None else refused[1],
                "refused_lane": None if refused is None else refused[0]["lane"],
            }
        finally:
            for service, session_id in (
                (hot, hot_created.session_id),
                (peer, peer_created.session_id),
            ):
                try:
                    asyncio.run(service.abort(session_id, "acceptance backpressure probe"))
                except Exception:
                    cleanup_failures += 1
        if cleanup_failures:
            raise ExternalMeasurementError("backpressure probe cleanup failed")
        if result is None:
            raise ExternalMeasurementError("backpressure probe produced no result")
        return result


def _verify_quality_inputs(
    *, repo: Path, corpus: Path, cases: list[object]
) -> list[dict[str, object]]:
    """Verify every consumed corpus byte against the frozen manifest before inference."""

    identities: list[dict[str, object]] = []
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise ExternalMeasurementError("quality manifest case is invalid")
        case_id = str(case["case_id"])
        audio_claim = case.get("audio")
        if not isinstance(audio_claim, dict):
            raise ExternalMeasurementError("quality audio claim is absent")
        audio_path = corpus / case_id / "audio.wav"
        reference_path = corpus / case_id / "reference.jsonl"
        audio_bytes = audio_path.read_bytes()
        reference_bytes = reference_path.read_bytes()
        try:
            with wave.open(str(audio_path), "rb") as source:
                pcm = source.readframes(source.getnframes())
                samples = source.getnframes()
        except (wave.Error, EOFError) as exc:
            raise ExternalMeasurementError("quality WAV is invalid") from exc
        checks = {
            "wav_sha256": hashlib.sha256(audio_bytes).hexdigest()
            == audio_claim.get("wav_sha256"),
            "wav_bytes": len(audio_bytes) == audio_claim.get("wav_bytes"),
            "pcm_sha256": hashlib.sha256(pcm).hexdigest()
            == audio_claim.get("pcm_sha256"),
            "samples": samples == audio_claim.get("samples"),
            "reference_sha256": hashlib.sha256(reference_bytes).hexdigest()
            == case.get("reference_sha256"),
        }
        source_dir = repo / str(case.get("source_directory") or "")
        source_present = source_dir.is_dir()
        source_audio_match: bool | None = None
        source_reference_match: bool | None = None
        if source_present:
            file_digests = {
                hashlib.sha256(path.read_bytes()).hexdigest()
                for path in source_dir.iterdir()
                if path.is_file()
            }
            source_audio_match = case.get("source_audio_sha256") in file_digests
            source_reference_match = case.get("source_reference_sha256") in file_digests
            checks["source_audio_sha256"] = source_audio_match
            checks["source_reference_sha256"] = source_reference_match
        if not all(checks.values()):
            raise ExternalMeasurementError("quality corpus input identity mismatch")
        identities.append(
            {
                "case_id": case_id,
                "checks": checks,
                "source_present": source_present,
                "source_audio_match": source_audio_match,
                "source_reference_match": source_reference_match,
            }
        )
    return identities


# Explicit projection: never retain transcripts, HTTP bodies, credentials, or failure messages.
_DIAGNOSTIC_EVENT_KINDS = frozenset({
    "canonical_queued", "canonical_started", "canonical_processed",
    "rolling_decode_queued", "rolling_decode_completed", "stop_requested",
    "session_closed", "terminal_failure", "session_aborted",
    "terminal_finalization_started", "terminal_finalization_completed",
    "terminal_finalization_failed",
    "text_revision_applied",
})
_DIAGNOSTIC_PAYLOAD_FIELDS = (
    "runtime_monotonic_ns", "canonical_decode_elapsed_sec", "frozen_span_duration_sec",
    "rolling_decode_elapsed_sec", "decode_failure", "windows_failed", "stale_completions",
    "submitted", "admitted", "item_id", "outcome", "reason", "refusal",
    "submission_refusal", "finalization_status", "applied", "source",
    "window_index", "start_sample", "end_sample",
    "accepted_samples", "accounted_samples", "rolling_through_sample",
    "rolling_status", "rolling_windows_completed", "rolling_windows_failed",
)


def _prestop_inference_failure_record(
    outputs: list[dict[str, object]], accepted_audio_seconds: float, failure_check: str,
) -> dict[str, object]:
    """Keep reducer inputs needed to explain a rejected overload, without content."""

    def counter(value: object) -> dict[str, object]:
        return {
            "type": type(value).__name__,
            "value": value if value is None or isinstance(value, (bool, int, float)) else None,
        }

    sessions = []
    for output in sorted(outputs, key=lambda row: int(row["ordinal"])):
        events = output["events"]
        assert isinstance(events, list)
        kinds = [event.get("kind") for event in events]
        stop_items = {
            event.get("payload", {}).get("item_id") for event in events
            if event.get("kind") == "canonical_queued"
            and event.get("payload", {}).get("reason") == "stop"
        }
        canonical = [event for event in events if event.get("kind") == "canonical_processed"]
        queued = [event for event in events if event.get("kind") == "rolling_decode_queued"
                  and event.get("payload", {}).get("admitted") is True]
        completed = [event for event in events if event.get("kind") == "rolling_decode_completed"]
        frontier = [event.get("payload", {}).get("end_sample") for event in queued]
        sessions.append({
            "session_id": output["session_id"],
            "accepted_samples": output["accepted_samples"],
            "accounted_samples": output["accounted_samples"],
            "prestop_frontier_samples": max(
                (value for value in frontier if isinstance(value, int) and not isinstance(value, bool)),
                default=None,
            ),
            "canonical_queued": kinds.count("canonical_queued"),
            "canonical_started": kinds.count("canonical_started"),
            "canonical_processed": len(canonical) - sum(
                event.get("payload", {}).get("item_id") in stop_items for event in canonical
            ),
            "canonical_stop_items": len(stop_items),
            "rolling_admitted": len(queued),
            "rolling_completed": len(completed),
            "rolling_counter_checks": [
                {
                    "item_id": event.get("payload", {}).get("item_id"),
                    "windows_failed": counter(event.get("payload", {}).get("windows_failed")),
                    "stale_completions": counter(event.get("payload", {}).get("stale_completions")),
                }
                for event in completed
            ],
        })
    return {
        "failure_check": failure_check,
        "accepted_audio_seconds": accepted_audio_seconds,
        "sessions": sessions,
    }


def _diagnostic_event(event: Mapping[str, Any]) -> dict[str, object]:
    payload = event.get("payload") or {}
    row = {key: event.get(key) for key in ("kind", "seq", "session_id", "snapshot_version")}
    row.update({key: payload.get(key) for key in _DIAGNOSTIC_PAYLOAD_FIELDS})
    failure = payload.get("failure") or {}
    window_failure = payload.get("window_failure")
    row["window_failure"] = (
        {key: window_failure.get(key) for key in
         ("condition", "window_index", "start_seconds", "end_seconds",
          "exception_type", "exception_message") if key in window_failure}
        if isinstance(window_failure, dict) else None
    )
    row["window_diagnostics"] = [
        {key: diagnostic[key] for key in
         ("condition", "window_index", "start_seconds", "end_seconds", "vad", "vad_mode",
          "frame_ms", "samples", "voiced_samples", "voiced_fraction", "speechless_threshold")
         if key in diagnostic}
        for diagnostic in (payload.get("window_diagnostics") or []) if isinstance(diagnostic, dict)
    ]
    row["failure_code"] = failure.get("code")
    row["failure_kind"] = failure.get("kind")
    return row


def _quality_window_coverage(
    events: list[dict[str, Any]], *, accepted_samples: int,
    finalization_status: str | None,
) -> dict[str, int]:
    """Count full corpus windows proved by rolling or the applied terminal revision."""
    window = int(LIVE_SAMPLE_RATE * ROLLING_WINDOW_SECONDS)
    stride = int(LIVE_SAMPLE_RATE * ROLLING_STRIDE_SECONDS)
    if isinstance(accepted_samples, bool) or not isinstance(accepted_samples, int) or accepted_samples < 0:
        raise ExternalMeasurementError("quality final surface lacks accepted sample count")
    planned = set(range(0, max(0, accepted_samples - window + 1), stride))
    rolling: set[int] = set()
    terminal_revisions = []
    for event in events:
        kind = event.get("kind")
        payload = event.get("payload") or {}
        if kind == "rolling_decode_completed" and payload.get("decode_failure") is None and payload.get("outcome") in {
            "applied", "refused", "no_proposal"
        }:
            start, end = payload.get("start_sample"), payload.get("end_sample")
            if (
                isinstance(start, bool) or not isinstance(start, int)
                or isinstance(end, bool) or not isinstance(end, int)
                or start not in planned or end != start + window or start in rolling
                or payload.get("window_index") != start // stride
            ):
                raise ExternalMeasurementError("quality rolling completion has invalid full window")
            rolling.add(start)
        elif kind == "text_revision_applied" and payload.get("source") == "terminal":
            terminal_revisions.append(payload)
    if len(terminal_revisions) > 1:
        raise ExternalMeasurementError("quality trace has duplicate terminal coverage evidence")
    terminal_range = None
    if terminal_revisions and finalization_status == "final":
        revision = terminal_revisions[0]
        if revision.get("finalization_status") == "final":
            start, end = revision.get("start_sample"), revision.get("end_sample")
            if (
                isinstance(start, bool) or not isinstance(start, int) or start < 0
                or isinstance(end, bool) or not isinstance(end, int)
                or end > accepted_samples or end <= start
            ):
                raise ExternalMeasurementError("quality terminal coverage range is invalid")
            terminal_range = (start, end)
    terminal_only = {
        start for start in planned - rolling
        if terminal_range is not None
        and terminal_range[0] <= start
        and start + window <= terminal_range[1]
    }
    return {
        "planned_full_windows": len(planned),
        "rolling_decoded": len(rolling),
        "terminal_only": len(terminal_only),
        "uncovered": len(planned - rolling - terminal_only),
    }


def _quality_terminal_diagnostics(trace: Path, adapter: Any, captured: Any) -> dict[str, object]:
    """Preserve the failed replay's status evidence before its workspace is deleted."""
    rows = []
    if trace.is_file():
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
    session_ids = sorted({row["session_id"] for row in rows if row.get("kind") == "session_created"})
    events = {
        (row["event"]["session_id"], row["event"]["seq"]): row["event"]
        for row in rows if row.get("kind") == "service_event"
    }
    read_errors = []
    for session_id in session_ids:
        try:
            # Replay may raise before draining its final events into the trace.
            for event in adapter.events(session_id):
                events[(session_id, event.seq)] = event.to_dict()
        except Exception as exc:
            read_errors.append({"session_id": session_id, "error_type": type(exc).__name__})
    return {
        "session_ids": session_ids,
        "stop_requested_monotonic_ns": captured.stop_requested_monotonic_ns,
        "events": [_diagnostic_event(event) for _, event in sorted(events.items())
                   if event.get("kind") in _DIAGNOSTIC_EVENT_KINDS],
        "event_read_errors": read_errors,
        "replay_terminal": [
            {key: row.get(key) for key in ("seq", "status", "failure_kind")}
            for row in rows if row.get("kind") == "terminal"
        ],
        "surfaces": {
            name: {
                "session_id": capture["snapshot"].get("session_id"),
                "observed_monotonic_ns": capture.get("observed_monotonic_ns"),
                "status": capture["snapshot"].get("session", {}).get("status"),
                "finalization_status": capture["snapshot"].get("session", {}).get("finalization_status"),
                "pending_work_items": capture["snapshot"].get("pending_work_items"),
            } for name, capture in captured.captures.items()
        },
    }


def _wav_duration(path: Path) -> float:
    import wave

    with wave.open(str(path), "rb") as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (
            1,
            2,
            16_000,
        ):
            raise ExternalMeasurementError("quality WAV must be mono PCM16 16 kHz")
        return handle.getnframes() / 16_000


def _probe_mp3(payload: bytes) -> dict[str, object]:
    # MP3 duration needs seeking; a successful probe of pipe:0 can omit it.
    with tempfile.NamedTemporaryFile(suffix=".mp3") as audio:
        audio.write(payload)
        audio.flush()
        process = subprocess.run(
            (
                "ffprobe", "-v", "error", "-show_entries",
                "stream=codec_name,sample_rate,channels,bit_rate:format=duration,bit_rate",
                "-of", "json", audio.name,
            ),
            capture_output=True,
            check=False,
        )
    if process.returncode:
        raise ExternalMeasurementError("ffprobe rejected owner MP3")
    try:
        result = json.loads(process.stdout)
        stream = result["streams"][0]
        format_row = result["format"]
        return {
            "codec": stream.get("codec_name"),
            "sample_rate_hz": int(stream.get("sample_rate")),
            "channels": int(stream.get("channels")),
            "bit_rate_bps": int(stream.get("bit_rate") or format_row.get("bit_rate")),
            "duration_seconds": float(format_row.get("duration")),
            "bytes": len(payload),
        }
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ExternalMeasurementError("ffprobe output is incomplete") from exc


def _wav_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (
            1,
            2,
            LIVE_SAMPLE_RATE,
        ):
            raise ExternalMeasurementError("Live load WAV must be mono PCM16 16 kHz")
        return handle.readframes(handle.getnframes())


def _wav_pcm_clip(path: Path, start_seconds: float, end_seconds: float) -> bytes:
    if not (0 <= start_seconds < end_seconds):
        raise ExternalMeasurementError("capacity clip interval is invalid")
    with wave.open(str(path), "rb") as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (
            1,
            2,
            LIVE_SAMPLE_RATE,
        ):
            raise ExternalMeasurementError("capacity WAV must be mono PCM16 16 kHz")
        start = int(start_seconds * LIVE_SAMPLE_RATE)
        count = int((end_seconds - start_seconds) * LIVE_SAMPLE_RATE)
        handle.setpos(start)
        payload = handle.readframes(count)
    if len(payload) != count * 2:
        raise ExternalMeasurementError("capacity clip exceeds its source WAV")
    return payload


def _unit_pid(unit: str, *, timeout: float = 30) -> int:
    if not supported_moss_unit(unit):
        raise ExternalMeasurementError("qualification accepts only MOSS user service units")
    if unit not in {"moss-web.service", "moss-vllm.service"}:
        loaded = subprocess.run(
            ("systemctl", "--user", "show", unit, "--property", "LoadState", "--value"),
            check=False, capture_output=True, text=True, timeout=timeout,
        )
        if loaded.returncode or loaded.stdout.strip() != "loaded":
            raise ExternalMeasurementError(f"{unit} is not a loaded user service")
    result = subprocess.run(
        ("systemctl", "--user", "show", unit, "--property", "MainPID", "--value"),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        pid = int(result.stdout.strip())
    except ValueError as exc:
        raise ExternalMeasurementError(f"{unit} MainPID is unavailable") from exc
    if result.returncode or pid <= 0:
        raise ExternalMeasurementError(f"{unit} is not running")
    return pid


def _version_line(argv: tuple[str, ...], label: str) -> str:
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    lines = (result.stdout or result.stderr).splitlines()
    if result.returncode or not lines or not lines[0].strip():
        raise ExternalMeasurementError(f"{label} version is unavailable")
    return lines[0].strip()


def _toolchain_identity(chrome: Path) -> dict[str, str]:
    if not chrome.is_file():
        raise ExternalMeasurementError("Chrome executable is unavailable")
    tools = {
        "chrome": (str(chrome), "--version"),
        "node": (shutil.which("node") or "", "--version"),
        "npm": (shutil.which("npm") or "", "--version"),
        "ffmpeg": (shutil.which("ffmpeg") or "", "-version"),
        "ffprobe": (shutil.which("ffprobe") or "", "-version"),
    }
    if any(not argv[0] for argv in tools.values()):
        raise ExternalMeasurementError("qualification toolchain is incomplete")
    return {
        name: _version_line(argv, name)
        for name, argv in tools.items()
    }


def _accelerator_identity(vllm_pid: int) -> dict[str, str]:
    try:
        argv = [
            value.decode("utf-8", "strict")
            for value in (Path("/proc") / str(vllm_pid) / "cmdline").read_bytes().split(b"\0")
            if value
        ]
    except OSError as exc:
        raise ExternalMeasurementError("vLLM runtime argv is unreadable") from exc
    expected_root = Path.home() / ".local/share/moss-transcribe-diarize/venv/bin"
    if not argv:
        raise ExternalMeasurementError("vLLM runtime argv is empty")
    python = Path(argv[0]).absolute()
    if python.parent != expected_root or not python.name.startswith("python"):
        raise ExternalMeasurementError("vLLM runtime is outside the declared GPU venv")
    code = (
        "import importlib.metadata,json,torch;"
        "print(json.dumps({'vllm':importlib.metadata.version('vllm'),"
        "'torch':torch.__version__,'cuda':torch.version.cuda or '',"
        "'cuda_available':torch.cuda.is_available()}))"
    )
    result = subprocess.run(
        (str(python), "-c", code), check=False, capture_output=True, text=True
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ExternalMeasurementError("vLLM/CUDA identity is unavailable") from exc
    if (
        result.returncode
        or payload.get("cuda_available") is not True
        or any(not isinstance(payload.get(key), str) or not payload[key] for key in ("vllm", "torch", "cuda"))
    ):
        raise ExternalMeasurementError("vLLM/CUDA identity is incomplete")
    return {
        "vllm": payload["vllm"],
        "torch": payload["torch"],
        "cuda": payload["cuda"],
    }


def _tls_identity(origin: str) -> dict[str, object]:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ExternalMeasurementError("qualification origin must use HTTPS")
    port = parsed.port or 443
    context = ssl.create_default_context()
    try:
        with socket.create_connection((parsed.hostname, port), timeout=15) as raw:
            with context.wrap_socket(raw, server_hostname=parsed.hostname) as secured:
                certificate = secured.getpeercert()
    except (OSError, ssl.SSLError) as exc:
        raise ExternalMeasurementError("deployed TLS is not trusted") from exc
    subject = ",".join(
        f"{key}={value}"
        for group in certificate.get("subject", ())
        for key, value in group
    )
    sans = sorted(
        value
        for kind, value in certificate.get("subjectAltName", ())
        if kind in {"DNS", "IP Address"}
    )
    expiry = certificate.get("notAfter")
    if not subject or not sans or not isinstance(expiry, str) or not expiry:
        raise ExternalMeasurementError("deployed TLS identity is incomplete")
    return {
        "trusted": True,
        "subject": subject,
        "subject_alt_names": sans,
        "not_after": expiry,
    }


def _file_fixture_identity(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if not data:
        raise ExternalMeasurementError("File fixture is empty")
    try:
        with wave.open(str(path), "rb") as source:
            format_identity = {
                "channels": source.getnchannels(),
                "sample_width_bytes": source.getsampwidth(),
                "sample_rate_hz": source.getframerate(),
                "frames": source.getnframes(),
            }
    except (wave.Error, EOFError) as exc:
        raise ExternalMeasurementError("File fixture is not a WAV") from exc
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        **format_identity,
    }


def _process_tree_rss(root_pid: int) -> int:
    children: dict[int, list[int]] = defaultdict(list)
    rss: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
        except OSError:
            continue
        fields = {
            line.split(":", 1)[0]: line.split(":", 1)[1].strip()
            for line in status.splitlines()
            if ":" in line
        }
        try:
            pid = int(fields["Pid"])
            parent = int(fields["PPid"])
            rss[pid] = int(fields.get("VmRSS", "0 kB").split()[0]) * 1024
        except (KeyError, ValueError):
            continue
        children[parent].append(pid)
    pending = [root_pid]
    seen: set[int] = set()
    total = 0
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += rss.get(pid, 0)
        pending.extend(children.get(pid, ()))
    return total


def _vllm_cache_use(url: str) -> float:
    if not url.startswith("http://127.0.0.1:"):
        raise ExternalMeasurementError("vLLM metrics must be host-local")
    try:
        response = httpx.get(url, timeout=10)
    except httpx.HTTPError as exc:
        raise ExternalMeasurementError("vLLM metrics are unavailable") from exc
    if response.status_code != 200:
        raise ExternalMeasurementError("vLLM metrics returned an error")
    candidates: list[float] = []
    for line in response.text.splitlines():
        metric_name = line.split("{", 1)[0].split(" ", 1)[0]
        if metric_name not in {"vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"}:
            continue
        try:
            candidates.append(float(line.rsplit(" ", 1)[1]))
        except ValueError:
            continue
    if not candidates or not all(math.isfinite(value) for value in candidates):
        raise ExternalMeasurementError("vLLM GPU cache metric is absent")
    return max(candidates)


def _load_surface_harness(repo: Path):
    path = (
        repo
        / "prototypes"
        / "streaming-diarization"
        / "live-surface-optimization"
        / "measure_three_surfaces.py"
    )
    name = "moss_phase2_acceptance_surface_harness"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ExternalMeasurementError("quality scorer is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    import ssl

    original_context = ssl._create_default_https_context
    try:
        spec.loader.exec_module(module)
    finally:
        ssl._create_default_https_context = original_context
    return module


def _mean(rows: list[dict[str, object]], surface: str, field: str) -> float:
    values = [float(row["metrics"][surface][field]) for row in rows]  # type: ignore[index]
    if not values or not all(math.isfinite(value) for value in values):
        raise ExternalMeasurementError("quality scorer returned non-finite output")
    return sum(values) / len(values)


def _quality_surface_observations(captures: Mapping[str, Any], *, reference_speaker_count: int | None = None) -> dict[str, object]:
    """Retain timing and completion state without exporting transcript content."""
    observations = {}
    for name in ("pre_stop_immediate", "pre_stop_settled", "post_stop_final"):
        capture = captures[name]
        snapshot = capture["snapshot"]
        session = snapshot.get("session", {})
        identity = snapshot.get("identity_counts") or {}
        segments = session.get("effective_transcript", [])
        observations[name] = {
            "identity_counts": {
                "emitted_speaker_count": len({segment["canonical_speaker"] for segment in segments
                                               if segment.get("canonical_speaker") is not None}),
                "reference_speaker_count": reference_speaker_count,
                "identities_born_count": identity.get("identities_born_count"),
                "album_admitted_count": identity.get("album_admitted_count"),
                "provisional_only_count": identity.get("provisional_only_count"),
                "abstention_count": identity.get("abstention_count"),
                "unattributed_segment_count": sum(segment.get("canonical_speaker") is None for segment in segments),
            },
            "finalization_status": session.get("finalization_status"),
            "pending_work_items": snapshot.get("pending_work_items"),
            "pending_span_count": len(session.get("pending_span_ids", [])),
            "accepted_samples": session.get("accepted_samples"),
            "accounted_samples": session.get("accounted_samples"),
            "canonical_through_sample": session.get("canonical_through_sample"),
            "text_revision_version": session.get("text_revision_version"),
            "observed_monotonic_ns": capture.get("observed_monotonic_ns"),
            "wait": capture.get("wait"),
        }
    return observations


def _quality_speaker_intervals(
    snapshot: Mapping[str, Any], rows: list[dict[str, Any]], reference: Path,
    *, speech_regions: tuple[tuple[float, float], ...] | None = None,
) -> dict[str, object]:
    """Retain the scored settled timing/identity, without transcript or reference names."""
    session = snapshot.get("session")
    if not isinstance(session, dict) or not isinstance(session.get("effective_transcript"), list):
        raise ExternalMeasurementError("settled quality surface lacks effective transcript")
    identity = session.get("identity_snapshot")
    speakers = identity.get("canonical_speakers") if isinstance(identity, dict) else None
    if not isinstance(speakers, (list, tuple)) or not all(
        isinstance(value, str) and re.fullmatch(r"speaker-[0-9]{4,}", value)
        for value in speakers
    ):
        raise ExternalMeasurementError("settled quality speaker IDs are not opaque identifiers")
    label_classes = {f"S{index + 1:02d}": f"named:{value}"
                     for index, value in enumerate(speakers)}
    hypothesis = []
    for row in rows:
        label = row["speaker"]
        if label != "S00" and label not in label_classes:
            raise ExternalMeasurementError("settled quality speaker label is not canonical")
        hypothesis.append({
            "start_sample": round(float(row["start"]) * LIVE_SAMPLE_RATE),
            "end_sample": round(float(row["end"]) * LIVE_SAMPLE_RATE),
            "speaker": "S00" if label == "S00" else label_classes[label],
        })
    reference_rows = load_reference_jsonl(reference)
    reference_ids = {speaker: f"ref:{index + 1:02d}"
                     for index, speaker in enumerate(sorted({row.speaker for row in reference_rows}))}
    reference_intervals = [
        {"start_sample": round(row.start * LIVE_SAMPLE_RATE),
         "end_sample": round(row.end * LIVE_SAMPLE_RATE),
         "speaker": reference_ids[row.speaker]}
        for row in reference_rows
    ]
    ref_eval = [Segment(row.start, row.end, row.speaker, "") for row in reference_rows]
    hyp_eval = [Segment(float(row["start"]), float(row["end"]), str(row["speaker"]), "")
                for row in rows]
    as_is = calculate_diarization(ref_eval, hyp_eval)
    ref_duration = sum(row.duration for row in ref_eval)
    confusion = 0.0
    s00_confusion = 0.0
    s00_mapped_correct = 0.0
    for ref in ref_eval:
        for hyp in hyp_eval:
            overlap = max(0.0, min(ref.end, hyp.end) - max(ref.start, hyp.start))
            if as_is["speaker_mapping"].get(ref.speaker) != hyp.speaker:
                confusion += overlap
                if hyp.speaker == "S00":
                    s00_confusion += overlap
            elif hyp.speaker == "S00":
                # S00 was the optimal match for this reference speaker: its time scores as correct.
                s00_mapped_correct += overlap
    difference = (min(confusion, ref_duration)
                  - min(confusion - s00_confusion, ref_duration)) / ref_duration
    without_s00_confusion = max(0.0, round(as_is["der"] - difference, 6))
    diagnostic = {
        "as_is": as_is["der"],
        "without_s00_confusion": without_s00_confusion,
        "s00_confusion_difference": round(difference, 6),
        "s00_mapped_reference": sorted(
            reference_ids[speaker] for speaker, label in as_is["speaker_mapping"].items()
            if label == "S00" and speaker in reference_ids
        ),
        "s00_mapped_correct_seconds": round(s00_mapped_correct, 6),
        "unattributed_der": without_s00_confusion,
    }
    if speech_regions is not None:
        from evaluator_v2 import (Segment as V2Segment, _der_reference_speech_axis,
                                  intersect_intervals, segments_to_intervals,
                                  total_seconds, union_intervals)

        ref_v2 = [V2Segment(row.start, row.end, row.speaker, "") for row in reference_rows]
        hyp_v2 = [V2Segment(float(row["start"]), float(row["end"]),
                            str(row["speaker"]), "") for row in rows]
        axis = _der_reference_speech_axis(ref_v2, hyp_v2, speech_regions)
        scored_reference = union_intervals(
            interval for speaker in {row.speaker for row in reference_rows}
            for interval in intersect_intervals(
                segments_to_intervals([row for row in ref_v2 if row.speaker == speaker]),
                speech_regions,
            )
        )
        denominator = total_seconds(scored_reference)
        s00_wrong = 0.0
        s00_correct = 0.0
        s00_intervals = intersect_intervals(
            segments_to_intervals([row for row in hyp_v2 if row.speaker == "S00"]),
            speech_regions,
        )
        named_intervals = union_intervals(intersect_intervals(
            segments_to_intervals([row for row in hyp_v2 if row.speaker != "S00"]),
            speech_regions,
        ))
        for speaker in {row.speaker for row in reference_rows}:
            ref_intervals = intersect_intervals(
                segments_to_intervals([row for row in ref_v2 if row.speaker == speaker]),
                speech_regions,
            )
            seconds = total_seconds(intersect_intervals(ref_intervals, s00_intervals))
            if axis["speaker_mapping"].get(speaker) == "S00":
                s00_correct += seconds
            else:
                # Only reference time covered by S00 alone is unattributed; where S00 overlaps a
                # named label, that named label's confusion stays charged (review F1).
                covered = total_seconds(intersect_intervals(
                    ref_intervals, union_intervals([*s00_intervals, *named_intervals])))
                s00_wrong += covered - total_seconds(intersect_intervals(ref_intervals, named_intervals))
        raw_confusion = axis["speaker_confusion"] * denominator
        excluded = (raw_confusion - max(raw_confusion - s00_wrong, 0.0)) / denominator if denominator else 0.0
        reference_adjusted = max(0.0, round(axis["der"] - excluded, 6))
        diagnostic.update({
            "reference_speech_as_is": axis["der"],
            "reference_speech_without_s00_confusion": reference_adjusted,
            "reference_speech_s00_confusion_difference": round(excluded, 6),
            "reference_speech_s00_mapped_correct_seconds": round(s00_correct, 6),
            "reference_speech_unattributed_der": reference_adjusted,
        })
    return {
        "settled_hypothesis_speaker_intervals": hypothesis,
        "reference_speaker_intervals": reference_intervals,
        "settled_der_s00_diagnostic": diagnostic,
    }


def _quality_projection(
    rows: list[dict[str, object]], *, corpus_manifest_sha256: str
) -> dict[str, object]:
    if len(rows) != 12:
        raise ExternalMeasurementError("quality campaign did not produce 12 sessions")
    by_category: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["category"])].append(row)
    fields = (
        "wer",
        "tbsa",
        "der",
        "content_recall",
        "matched_word_speaker_accuracy",
        "reference_speech_der",
        "der_raw",
        "reference_speech_der_raw",
    )
    total_duration = sum(float(row["duration_seconds"]) for row in rows)
    duration_weighted = {
            field: sum(
                float(row["duration_seconds"])
            * float(row["metrics"]["settled"][field])  # type: ignore[index]
            for row in rows
        )
        / total_duration
        for field in fields
    }
    per_category = {
        category: {
            field: _mean(group, "settled", field) for field in fields
        }
        for category, group in sorted(by_category.items())
    }
    return {
        "cases": 6,
        "passes": 2,
        "sessions": 12,
        "windows": sum(int(row["windows"]) for row in rows),
        "duration_seconds": total_duration,
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "per_case": [
            {
                "case_id": row["case_id"],
                "pass": row["pass"],
                "session_id": row["session_id"],
                "category": row["category"],
                "duration_seconds": row["duration_seconds"],
                "windows": row["windows"],
                "window_coverage": row["window_coverage"],
                "metrics": row["metrics"],
                "settled_hypothesis_speaker_intervals": row["settled_hypothesis_speaker_intervals"],
                "reference_speaker_intervals": row["reference_speaker_intervals"],
                "settled_der_s00_diagnostic": row["settled_der_s00_diagnostic"],
                "surface_observations": row.get("surface_observations"),
            }
            for row in rows
        ],
        "per_category": per_category,
        "duration_weighted": duration_weighted,
        "macro": {
            "immediate_wer": _mean(rows, "immediate", "wer"),
            "settled_wer": _mean(rows, "settled", "wer"),
            "recall": _mean(rows, "settled", "content_recall"),
            "time_speaker_attribution": _mean(rows, "settled", "tbsa"),
            "diarization_error_rate": _mean(rows, "settled", "der"),
            "diarization_error_rate_raw": _mean(rows, "settled", "der_raw"),
            "matched_speaker_accuracy": _mean(
                rows, "settled", "matched_word_speaker_accuracy"
            ),
            "reference_speech_der": _mean(
                rows, "settled", "reference_speech_der"
            ),
            "reference_speech_der_raw": _mean(rows, "settled", "reference_speech_der_raw"),
            "final_wer": _mean(rows, "final", "wer"),
        },
    }
