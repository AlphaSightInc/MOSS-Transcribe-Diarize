#!/usr/bin/env python3
"""Server-side live-pipeline probe: everything E3's canary does except the Mac.

Why this exists
---------------
The deployed live service has never received a single audio frame (the host journal
shows zero frame posts). Every stage after ingress -- lane contract, mixer, endpointer,
decoder, diarizer, publish, snapshot -- is therefore unexercised on the real host with
the real GPU and the deployed manifest. That risk is only discoverable *after* the
operator's irreducible TCC step unless something drives the same HTTP contract without
a Mac. This script is that driver.

It is a Ralph evidence tool, not product source: it lives under scripts/ralph-afk/ and
nothing in the product imports it.

What it deliberately mirrors from the Mac client
------------------------------------------------
* Full-certificate pinning with no PKI: the peer leaf's DER sha256 must equal --pin,
  exactly like PinnedCertificateURLSessionDelegate. No chain, no hostname evaluation.
* The canonical wire format: 16000 Hz mono, exact 8000-sample frames, per-lane
  sequences from zero, `capture_timestamp_ns` in real nanoseconds in one time domain
  shared by both lanes, `silent` computed as "every sample is zero" (the Swift rule).
* The pump cadence: one frame per lane per 0.5 s tick, lanes independent, paced against
  a wall clock rather than sent as fast as the socket allows.
* The portal's read path: snapshot(since_version) then events(since_seq), serially.

What it deliberately does NOT mirror
------------------------------------
* No helper heartbeat. The lease is armed only by the first `observe`, so a probe that
  never heartbeats never arms one; sending fabricated helper health would be inventing
  evidence about a component that is not under test here.
* No outbox/retry. A failed publish is reported, not retried -- the point is to learn
  whether the server accepts, not to prove client resilience (which has Swift nodes).

Secret hygiene
--------------
The pairing payload arrives on **stdin**, never argv. Payload, device token and view
token are held in locals, sent only in a request body or an `Authorization` header, and
are never printed, logged or written to disk. The report prints lengths, never values.
"""

from __future__ import annotations

import argparse
import array
import base64
import hashlib
import http.client
import json
import math
import re
import ssl
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

# --- domain contract (prd.md "Domain-contract values"); implemented exactly ----------
SAMPLE_RATE = 16000
FRAME_SAMPLES = 8000            # 0.5 s
NS_PER_SAMPLE = 1_000_000_000 // SAMPLE_RATE   # exact: 16000 divides 1e9
TICK_SECONDS = 0.5
LANES = ("system", "microphone")


class ProbeError(RuntimeError):
    pass


class PinMismatch(ProbeError):
    pass


# ---------------------------------------------------------------------------
# Pinned transport
# ---------------------------------------------------------------------------
class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS with the leaf pin as the *whole* trust decision, like the Mac client."""

    def __init__(self, host: str, port: int, pin: str, timeout: float = 30.0):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(host, port, timeout=timeout, context=context)
        self._pin = pin.lower()

    def connect(self) -> None:
        super().connect()
        der = self.sock.getpeercert(binary_form=True)
        observed = hashlib.sha256(der).hexdigest()
        if observed != self._pin:
            self.close()
            raise PinMismatch(
                f"served leaf sha256 {observed} does not match the pin {self._pin}"
            )


@dataclass
class PinnedClient:
    host: str
    port: int
    pin: str
    timeout: float = 30.0
    _conn: PinnedHTTPSConnection | None = None
    handshakes: int = 0

    def _connection(self) -> PinnedHTTPSConnection:
        if self._conn is None:
            self._conn = PinnedHTTPSConnection(self.host, self.port, self.pin, self.timeout)
            self._conn.connect()
            self.handshakes += 1
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        bearer: str | None = None,
    ) -> tuple[int, dict | str, float]:
        """Return (status, decoded_body, elapsed_seconds). Reconnects once on a dead socket."""
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"accept": "application/json"}
        if payload is not None:
            headers["content-type"] = "application/json"
        if bearer is not None:
            headers["authorization"] = f"Bearer {bearer}"
        for attempt in (0, 1):
            conn = self._connection()
            started = time.monotonic()
            try:
                conn.request(method, path, body=payload, headers=headers)
                response = conn.getresponse()
                raw = response.read()
                elapsed = time.monotonic() - started
            except (http.client.HTTPException, OSError):
                self.close()
                if attempt == 1:
                    raise
                continue
            try:
                return response.status, json.loads(raw.decode("utf-8")), elapsed
            except (ValueError, UnicodeDecodeError):
                return response.status, raw.decode("utf-8", "replace"), elapsed
        raise ProbeError("unreachable")


# ---------------------------------------------------------------------------
# Two-speaker audio, synthesized locally
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Utterance:
    start_seconds: float
    text: str


def synthesize(voice: str, text: str, workdir: Path) -> array.array:
    """One `say` utterance as 16 kHz mono int16."""
    out = workdir / f"{abs(hash((voice, text)))}.wav"
    subprocess.run(
        ["say", "-v", voice, "-o", str(out), "--data-format=LEI16@16000", text],
        check=True,
        capture_output=True,
    )
    with wave.open(str(out)) as handle:
        if (handle.getnchannels(), handle.getframerate(), handle.getsampwidth()) != (
            1,
            SAMPLE_RATE,
            2,
        ):
            raise ProbeError(f"say produced an unexpected format for voice {voice}")
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    out.unlink(missing_ok=True)
    return samples


def build_lane_track(
    voice: str,
    utterances: tuple[Utterance, ...],
    total_seconds: float,
    workdir: Path,
) -> array.array:
    """Lay utterances on a silent timeline of the requested length."""
    track = array.array("h", bytes(int(total_seconds * SAMPLE_RATE) * 2))
    for utterance in utterances:
        samples = synthesize(voice, utterance.text, workdir)
        offset = int(utterance.start_seconds * SAMPLE_RATE)
        end = min(offset + len(samples), len(track))
        track[offset:end] = samples[: end - offset]
    return track


def frames_of(track: array.array) -> list[array.array]:
    """Exact 8000-sample frames; a trailing partial is zero-padded to full size."""
    frames = []
    for start in range(0, len(track), FRAME_SAMPLES):
        chunk = track[start : start + FRAME_SAMPLES]
        if len(chunk) < FRAME_SAMPLES:
            chunk = chunk + array.array("h", bytes((FRAME_SAMPLES - len(chunk)) * 2))
        frames.append(chunk)
    return frames


def is_silent(chunk: array.array) -> bool:
    """The Swift rule: every sample is zero (|x| < 1/32768 on a float scale)."""
    return not any(chunk)


# ---------------------------------------------------------------------------
# Latency accounting (the same arithmetic CaptureLatencySampler does)
# ---------------------------------------------------------------------------
@dataclass
class CommittedLatency:
    origin_ns: int
    baseline_seen: bool = False
    last_committed: int = 0
    samples_ms: list[float] = field(default_factory=list)
    rejected_negative: int = 0

    def observe(self, committed_samples: int, now_ns: int) -> None:
        if not self.baseline_seen:
            self.baseline_seen = True
            self.last_committed = committed_samples
            return
        if committed_samples <= self.last_committed:
            return
        self.last_committed = committed_samples
        committed_end_ns = self.origin_ns + committed_samples * NS_PER_SAMPLE
        delta_ms = (now_ns - committed_end_ns) / 1e6
        if delta_ms < 0:
            self.rejected_negative += 1
            return
        self.samples_ms.append(delta_ms)

    def percentile(self, fraction: float) -> float | None:
        """Nearest-rank, so every quoted figure was actually observed."""
        if not self.samples_ms:
            return None
        ordered = sorted(self.samples_ms)
        rank = max(1, math.ceil(fraction * len(ordered)))
        return ordered[rank - 1]


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
MIC_LINES = (
    "Good morning everyone, this is the microphone lane and I am the first speaker.",
    "The transcription service should be receiving two separate audio lanes right now.",
    "Let us check whether the speaker labels come through on the live page.",
    "I will hand over to the second speaker for a moment.",
    "Thank you, that confirms the microphone lane is being transcribed.",
    "This is the last thing the first speaker says before the session stops.",
)

SYSTEM_LINES = (
    "This is the system audio lane, and I am the second speaker in this meeting.",
    "My voice is arriving on a different lane from the first speaker.",
    "The mixer should combine both lanes onto a single sixteen kilohertz timeline.",
    "Diarization should separate the two of us into distinct speaker labels.",
    "I am finishing my part of the conversation now.",
    "Goodbye from the system audio lane.",
)


def build_schedule(
    total_seconds: float,
    lead_seconds: float = 1.0,
) -> tuple[tuple[Utterance, ...], tuple[Utterance, ...]]:
    """Alternate the two speakers, starting after `lead_seconds` of silence.

    Turn spacing is derived from the requested length and the number of lines, so the
    schedule is a function of the arguments rather than a hard-coded table. `lead_seconds`
    is a knob rather than a constant because whether the *first* span contains speech is
    exactly the variable one experiment here needs to move.
    """
    turns = len(MIC_LINES) + len(SYSTEM_LINES)
    spacing = (total_seconds - lead_seconds) / turns
    mic, system = [], []
    for index in range(turns):
        start = lead_seconds + index * spacing
        if index % 2 == 0:
            mic.append(Utterance(start, MIC_LINES[index // 2]))
        else:
            system.append(Utterance(start, SYSTEM_LINES[index // 2]))
    return tuple(mic), tuple(system)


def redact_snapshot(snapshot: dict) -> dict:
    """Session facts worth reporting; no tokens live in a snapshot, but be explicit."""
    session = snapshot.get("session") or {}
    identity = session.get("identity_snapshot") or {}
    return {
        "status": session.get("status"),
        "version": session.get("version"),
        "accepted_samples": session.get("accepted_samples"),
        "accounted_samples": session.get("accounted_samples"),
        "committed_samples": session.get("committed_samples"),
        "retained_samples": session.get("retained_samples"),
        "pending_span_ids": len(session.get("pending_span_ids") or ()),
        "committed_items": len(session.get("committed") or ()),
        "identity_snapshot_version": identity.get("version"),
        "identity_canonical_speakers": list(identity.get("canonical_speakers") or ()),
        "failure_reason": session.get("failure_reason"),
        "terminal_failure": snapshot.get("terminal_failure"),
        "pending_work_items": snapshot.get("pending_work_items"),
    }


# A canonical commit carries its speaker inside the transcript, not as a field: the wire
# grammar is `[start][Sxx]words[end]`. Reading a `speaker` key instead reports "no labels"
# for a perfectly labelled meeting, which is what the first J5d run did.
SPEAKER_TOKEN = re.compile(r"\[(S\d+)\]")

# J2's marker for a span whose identity did not resolve: its words publish, its speaker does
# not. Restated here rather than imported because this probe deliberately shares no code with
# the product; if the product ever changes it, this line is the one to move.
UNATTRIBUTED_SPEAKER = "S00"


def speakers_in(transcript: str) -> list[str]:
    """Canonical speaker labels a committed transcript claims, in first-seen order."""
    seen: list[str] = []
    for label in SPEAKER_TOKEN.findall(transcript or ""):
        if label not in seen:
            seen.append(label)
    return seen


def transcript_of(snapshot: dict) -> list[dict]:
    session = snapshot.get("session") or {}
    items = []
    for commit in session.get("committed") or ():
        if isinstance(commit, dict):
            items.append(commit)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--pin", required=True, help="expected leaf certificate sha256 (hex)")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--seconds", type=float, default=48.0)
    parser.add_argument(
        "--lead-seconds",
        type=float,
        default=1.0,
        help="silence before the first utterance; 0 puts speech in the very first span",
    )
    parser.add_argument("--mic-voice", default="Samantha")
    parser.add_argument("--system-voice", default="Fred")
    parser.add_argument(
        "--lane-offset-ms",
        default="",
        help="comma-separated LANE=MS shifts applied to that lane's whole "
        "capture_timestamp_ns timeline, e.g. 'system=137'. Two real capture devices "
        "never start on the same instant; without this every lane shares one origin, "
        "which is the one input property more degenerate than a real Mac capture.",
    )
    parser.add_argument("--poll-every-ticks", type=int, default=2)
    parser.add_argument("--stop-deadline", type=float, default=30.0)
    parser.add_argument(
        "--no-fail-fast",
        dest="fail_fast",
        action="store_false",
        help="keep publishing after a non-200 (a terminal failure is sticky, so this only "
        "buries the answer; use it deliberately)",
    )
    parser.add_argument(
        "--report",
        default="",
        help="optional path for the JSON report (never contains a secret)",
    )
    args = parser.parse_args()

    payload = sys.stdin.read().strip()
    if not payload:
        print("error: pairing payload must arrive on stdin", file=sys.stderr)
        return 2

    lane_offset_ns = {lane: 0 for lane in LANES}
    for item in (part.strip() for part in args.lane_offset_ms.split(",") if part.strip()):
        lane, _, milliseconds = item.partition("=")
        if lane not in lane_offset_ns:
            print(f"error: unknown lane in --lane-offset-ms: {lane}", file=sys.stderr)
            return 2
        lane_offset_ns[lane] = int(round(float(milliseconds) * 1e6))

    report: dict = {
        "schema": "ralph-live-pipeline-probe.v1",
        "host": f"{args.host}:{args.port}",
        "pin_prefix": args.pin[:8],
        "requested_seconds": args.seconds,
    }

    with tempfile.TemporaryDirectory(prefix="moss-probe-say-") as tmp:
        workdir = Path(tmp)
        mic_schedule, system_schedule = build_schedule(args.seconds, args.lead_seconds)
        tracks = {
            "microphone": build_lane_track(args.mic_voice, mic_schedule, args.seconds, workdir),
            "system": build_lane_track(args.system_voice, system_schedule, args.seconds, workdir),
        }
    lane_frames = {lane: frames_of(track) for lane, track in tracks.items()}
    tick_count = max(len(frames) for frames in lane_frames.values())
    report["audio"] = {
        "voices": {"microphone": args.mic_voice, "system": args.system_voice},
        "lead_seconds": args.lead_seconds,
        "lane_offset_ms": {
            lane: offset / 1e6 for lane, offset in lane_offset_ns.items()
        },
        "turns": {"microphone": len(mic_schedule), "system": len(system_schedule)},
        "frames_per_lane": {lane: len(frames) for lane, frames in lane_frames.items()},
        "voiced_frames": {
            lane: sum(0 if is_silent(chunk) else 1 for chunk in frames)
            for lane, frames in lane_frames.items()
        },
    }

    client = PinnedClient(args.host, args.port, args.pin)

    # --- pair (non-loopback TLS peer, which is why this half cannot run on the host) --
    status, body, _ = client.request(
        "POST",
        "/api/live/pairings",
        body={"pairing_payload": payload, "device_id": args.device_id},
    )
    if status != 200 or not isinstance(body, dict):
        report["pairing"] = {"status": status, "body": body}
        print(json.dumps(report, indent=2))
        return 1
    device_token = body["device_token"]
    report["pairing"] = {
        "status": status,
        "device_id": body.get("device_id"),
        "scope": body.get("scope"),
        "device_token_len": len(device_token),
    }

    # --- session ------------------------------------------------------------------
    status, body, _ = client.request("POST", "/api/live/sessions", bearer=device_token)
    if status != 200 or not isinstance(body, dict):
        report["session"] = {"status": status, "body": body}
        print(json.dumps(report, indent=2))
        return 1
    session_id = body["id"]
    view_token = body["view_token"]
    descriptor = body.get("descriptor") or {}
    report["session"] = {
        "status": status,
        "session_id_len": len(session_id),
        "view_token_len": len(view_token),
        "view_expires_at": body.get("view_expires_at"),
        "descriptor": {
            "sample_rate": descriptor.get("sample_rate"),
            "frame_samples": descriptor.get("frame_samples"),
            "source_revision": descriptor.get("source_revision"),
            "provider_manifest_hash": descriptor.get("provider_manifest_hash"),
        },
    }

    # --- publish, paced like the production pump ------------------------------------
    origin_ns = time.time_ns() - int(TICK_SECONDS * 1e9)
    latency = CommittedLatency(origin_ns=origin_ns)
    publish_ms: list[float] = []
    snapshot_ms: list[float] = []
    events_ms: list[float] = []
    accepted = {lane: 0 for lane in LANES}
    non_200: list[dict] = []
    last_version = None
    last_seq = 0
    events_seen = 0
    # J4 makes every refusal on the live path carry the word that names it. Keeping the
    # canonical_processed payloads is what turns "the run survived" into "and here is why
    # each span published the way it did" without a host-side probe.
    canonical_events: list[dict] = []
    started_wall = time.monotonic()

    aborted_at: dict | None = None
    for tick in range(tick_count):
        for lane in LANES:
            frames = lane_frames[lane]
            if tick >= len(frames):
                continue
            chunk = frames[tick]
            frame_body = {
                "lane": lane,
                "sequence": tick,
                "capture_timestamp_ns": origin_ns
                + lane_offset_ns[lane]
                + tick * FRAME_SAMPLES * NS_PER_SAMPLE,
                "device_epoch": 1,
                "silent": is_silent(chunk),
                "discontinuity": False,
                "sample_rate": SAMPLE_RATE,
                "sample_count": FRAME_SAMPLES,
                "pcm_base64": base64.b64encode(chunk.tobytes()).decode("ascii"),
            }
            status, body, elapsed = client.request(
                "POST",
                f"/api/live/sessions/{session_id}/frames",
                body=frame_body,
                bearer=device_token,
            )
            publish_ms.append(elapsed * 1000.0)
            print(
                f"tick={tick:3d} lane={lane:10s} status={status} {elapsed * 1000:7.1f} ms",
                file=sys.stderr,
                flush=True,
            )
            if status == 200:
                accepted[lane] += 1
            else:
                non_200.append({"tick": tick, "lane": lane, "status": status, "body": body})
                # A live session's terminal failure is sticky: every later frame gets the same
                # answer, so continuing only buries the one response that explains it.
                if args.fail_fast:
                    aborted_at = {"tick": tick, "lane": lane, "status": status, "body": body}
                    break
        if aborted_at is not None:
            break

        if tick % max(1, args.poll_every_ticks) == 0:
            path = f"/api/live/sessions/{session_id}/snapshot"
            if last_version is not None:
                path += f"?since_version={last_version}"
            status, body, elapsed = client.request("GET", path, bearer=view_token)
            snapshot_ms.append(elapsed * 1000.0)
            print(
                f"tick={tick:3d} snapshot     status={status} {elapsed * 1000:7.1f} ms"
                f" version={last_version}",
                file=sys.stderr,
                flush=True,
            )
            if status == 200 and isinstance(body, dict) and body.get("snapshot"):
                snap = body["snapshot"]
                last_version = (snap.get("session") or {}).get("version", last_version)
                latency.observe(
                    (snap.get("session") or {}).get("committed_samples", 0), time.time_ns()
                )
                report.setdefault("last_live_snapshot", {}).update(redact_snapshot(snap))
            elif status != 200:
                # 401 here means view authority went away, i.e. the session left
                # VIEWABLE_SESSION_STATUSES. That is the C1 contract reporting a dead session.
                non_200.append({"tick": tick, "lane": "view/snapshot", "status": status, "body": body})
                if args.fail_fast:
                    aborted_at = {
                        "tick": tick,
                        "lane": "view/snapshot",
                        "status": status,
                        "body": body,
                    }
                    break
            status, body, elapsed = client.request(
                "GET",
                f"/api/live/sessions/{session_id}/events?since_seq={last_seq}",
                bearer=view_token,
            )
            events_ms.append(elapsed * 1000.0)
            if status == 200 and isinstance(body, dict):
                for event in body.get("events") or ():
                    events_seen += 1
                    last_seq = max(last_seq, int(event.get("seq", last_seq)))
                    if event.get("kind") == "canonical_processed":
                        payload = event.get("payload") or {}
                        canonical_events.append(
                            {
                                key: payload.get(key)
                                for key in (
                                    "span_id",
                                    "submitted",
                                    "identity_status",
                                    "identity_reason",
                                    "submission_refusal",
                                    "empty_reason",
                                    "canonical_decode_rtf",
                                    "frozen_span_duration_sec",
                                )
                            }
                        )

        target = started_wall + (tick + 1) * TICK_SECONDS
        remaining = target - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    report["publish"] = {
        "ticks_planned": tick_count,
        "ticks_run": tick + 1,
        "accepted_frames": accepted,
        "non_200_count": len(non_200),
        "aborted_at": aborted_at,
        "wall_seconds": round(time.monotonic() - started_wall, 2),
        "tls_handshakes": client.handshakes,
    }

    # --- stop and drain --------------------------------------------------------------
    status, body, _ = client.request(
        "POST",
        f"/api/live/sessions/{session_id}/stop",
        body={"deadline": args.stop_deadline},
        bearer=device_token,
    )
    report["stop"] = {"status": status}
    final_snapshot = body.get("snapshot") if isinstance(body, dict) else None
    if final_snapshot:
        report["stop"]["snapshot"] = redact_snapshot(final_snapshot)
    elif isinstance(body, dict):
        report["stop"]["body"] = body

    # --- the transcript, which is the whole point ------------------------------------
    items = transcript_of(final_snapshot or {})
    labelled = sorted({label for item in items for label in speakers_in(str(item.get("transcript") or ""))})
    report["transcript"] = {
        "item_count": len(items),
        "speakers": labelled,
        "attributed_speakers": [label for label in labelled if label != UNATTRIBUTED_SPEAKER],
        "unattributed_spans": sum(
            1 for item in items if UNATTRIBUTED_SPEAKER in speakers_in(str(item.get("transcript") or ""))
        ),
        "empty_spans": sum(1 for item in items if not (item.get("transcript") or "").strip()),
        "items": [
            {
                "span_id": item.get("span_id"),
                "start_sample": item.get("start_sample"),
                "end_sample": item.get("end_sample"),
                "identity_snapshot_version": item.get("identity_snapshot_version"),
                "speakers": speakers_in(str(item.get("transcript") or "")),
                "transcript": item.get("transcript"),
            }
            for item in items
        ],
    }

    report["latency"] = {
        "committed_advances": len(latency.samples_ms),
        "rejected_negative": latency.rejected_negative,
        "committed_p50_ms": latency.percentile(0.50),
        "committed_p95_ms": latency.percentile(0.95),
        "snapshot_p95_ms": _p95(snapshot_ms),
        "events_p95_ms": _p95(events_ms),
        "publish_p95_ms": _p95(publish_ms),
    }
    committed_p95 = report["latency"]["committed_p95_ms"]
    if committed_p95 is not None:
        render_bound = 1000.0 + (report["latency"]["snapshot_p95_ms"] or 0.0) + (
            report["latency"]["events_p95_ms"] or 0.0
        )
        report["latency"]["render_bound_ms"] = round(render_bound, 1)
        report["latency"]["user_visible_ms"] = round(committed_p95 + render_bound, 1)

    report["events_seen"] = events_seen
    report["canonical_events"] = canonical_events
    report["view_authority_after_stop"] = _probe_view_after_stop(client, session_id, view_token)

    text = json.dumps(report, indent=2, sort_keys=False)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    client.close()
    if not items:
        return 3
    # The PRD's canary asks for a transcript *with speaker labels*, so a run that commits every
    # span as S00 is a survived run and a failed gate. Say so in the exit code rather than
    # leaving it for a reader of the JSON.
    return 0 if report["transcript"]["attributed_speakers"] else 5


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return round(ordered[rank - 1], 1)


def _probe_view_after_stop(client: PinnedClient, session_id: str, view_token: str) -> dict:
    """A clean stop must immediately revoke view authority (C1's contract)."""
    status, _body, _ = client.request(
        "GET", f"/api/live/sessions/{session_id}/snapshot", bearer=view_token
    )
    return {"snapshot_status": status, "revoked": status in (401, 403, 404)}


if __name__ == "__main__":
    sys.exit(main())
