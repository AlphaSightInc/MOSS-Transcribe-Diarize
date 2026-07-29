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
* Optionally (`--concurrent-readers N`) the Mac's *read concurrency*: N extra view
  readers, each on its own pinned connection and its own thread, polling snapshot and
  events while frames are being posted. On m4mbp two readers run at once -- the app's
  own latency probe and the portal poller -- and F1 measured 325 + 56 snapshot fetches
  in 73.3 s, i.e. ~4.4 reads/s against 4 frame posts/s. `live_snapshot`/`live_events`
  are sync `def` handlers that Starlette runs in its threadpool while
  `accept_live_frame` is `async def` on the event loop, so a strictly serial probe
  structurally cannot overlap a read with a write. Default 0, which leaves every
  earlier run comparable.

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
import threading
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


class ConcurrentViewReader(threading.Thread):
    """A view reader on its own pinned connection, polling while frames are posted.

    `PinnedClient` holds one socket and is not thread-safe, so each reader owns one --
    which is also what the Mac does: the app's latency probe and the portal poller are
    two independent HTTPS clients.

    It records *when* a read first stopped returning 200 and *what the server said*.
    That is the point: on the Mac both readers 401 at the same instant a frame first
    409s, and neither host keeps the body, so no recorded run names the cause.
    """

    def __init__(
        self,
        *,
        name: str,
        host: str,
        port: int,
        pin: str,
        session_id: str,
        view_token: str,
        interval: float,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self._client = PinnedClient(host, port, pin)
        self._session_id = session_id
        self._token = view_token
        self._interval = max(0.0, interval)
        # NOT `self._stop`: threading.Thread.join() calls its own private _stop().
        self._stop_event = threading.Event()
        self._started_monotonic: float | None = None
        self.snapshot_ms: list[float] = []
        self.events_ms: list[float] = []
        self.status_counts: dict[str, int] = {}
        self.first_non_200: dict | None = None
        self.last_non_200: dict | None = None
        self.error: str | None = None
        self.last_version: int | None = None
        self.last_seq = 0
        self.polls = 0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        self._started_monotonic = time.monotonic()
        try:
            while not self._stop_event.is_set():
                self._poll_once()
                self.polls += 1
                if self._stop_event.wait(self._interval):
                    break
        except Exception as exc:  # a reader must never take the run down with it
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._client.close()

    def _poll_once(self) -> None:
        path = f"/api/live/sessions/{self._session_id}/snapshot"
        if self.last_version is not None:
            path += f"?since_version={self.last_version}"
        status, body, elapsed = self._client.request("GET", path, bearer=self._token)
        self.snapshot_ms.append(elapsed * 1000.0)
        self._record("snapshot", status, body)
        if status == 200 and isinstance(body, dict) and body.get("snapshot"):
            session = (body["snapshot"].get("session") or {})
            version = session.get("version")
            if isinstance(version, int):
                self.last_version = version

        status, body, elapsed = self._client.request(
            "GET",
            f"/api/live/sessions/{self._session_id}/events?since_seq={self.last_seq}",
            bearer=self._token,
        )
        self.events_ms.append(elapsed * 1000.0)
        self._record("events", status, body)
        if status == 200 and isinstance(body, dict):
            for event in body.get("events") or ():
                self.last_seq = max(self.last_seq, int(event.get("seq", 0)) + 1)

    def _record(self, kind: str, status: int, body: object) -> None:
        key = f"{kind}:{status}"
        self.status_counts[key] = self.status_counts.get(key, 0) + 1
        if status == 200:
            return
        started = self._started_monotonic or time.monotonic()
        entry = {
            "kind": kind,
            "status": status,
            # View-route bodies are `{"detail": ...}` or a failure record; no route
            # echoes a token, so keeping the body cannot leak one.
            "body": body if isinstance(body, (dict, str)) else repr(body),
            "at_seconds": round(time.monotonic() - started, 3),
        }
        if self.first_non_200 is None:
            self.first_non_200 = entry
        self.last_non_200 = entry

    def summary(self) -> dict:
        return {
            "name": self.name,
            "polls": self.polls,
            "status_counts": dict(sorted(self.status_counts.items())),
            "first_non_200": self.first_non_200,
            "last_non_200": self.last_non_200,
            "snapshot_p95_ms": _p95(self.snapshot_ms),
            "events_p95_ms": _p95(self.events_ms),
            "handshakes": self._client.handshakes,
            "error": self.error,
        }


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


# Candidate 55's regime, in audio. A real meeting's microphone lane carries the room, and the
# decoder answers with one-word interjections and `'...'` -- fragments too short for the evidence
# floor (`min_segment_samples` 8000 = 0.5 s) to embed. `birth-floor-probe.py` measured 14 of F2's
# 16 and 13 of F3's 16 canonical speakers born from exactly that, holding no reference at all.
# These lines are chosen only for their LENGTH: each must render shorter than the evidence floor,
# which the builder asserts rather than assumes.
# Measured with `say` on both default voices, seconds rendered: Yeah. 0.457/0.443 · No. 0.414/0.443
# · Ah. 0.354/0.396 · Oh. 0.353/0.373 · Hey. 0.386/0.436 · Huh. 0.412/0.390 -- every one under the
# 0.5 s floor on both. Rejected for being over it on at least one voice: Okay. (0.574/0.570),
# Mm hmm. (0.507/0.745), Right. (0.402/0.535), Hm. (0.203/0.721). The builder re-measures rather
# than trusting this comment.
FRAGMENT_LINES = (
    "Yeah.",
    "No.",
    "Ah.",
    "Oh.",
    "Hey.",
    "Huh.",
)


def build_fragment_track(
    voice: str,
    lines: tuple[str, ...],
    total_seconds: float,
    workdir: Path,
    lead_seconds: float,
    interval_seconds: float,
) -> tuple[array.array, dict]:
    """Short isolated utterances on an otherwise silent lane, one per `interval_seconds`.

    This is the one input property no earlier mode produces: audio that mints a canonical
    speaker the system then has nothing to say about. `continuous` gives a lane the album can
    bank (iteration 7 measured 2 canonical speakers for 2 real voices, the healthy regime);
    `alternating` gives it long turns separated by silence. Neither reaches F2's measured
    **8.0 references per real voice**, which is the shape iteration 5's `sweep-multiplicity-probe`
    predicts the sweep cannot repair.

    The mechanism being reproduced, from Phase N decision 20: a local speaker whose segments
    never total the evidence floor is never embedded, so it cannot match, so
    `live_identity.py:129` births a canonical speaker for it -- with no reference and therefore
    no bank, which decision 7 makes unmergeable. Pair this with a voiced peer lane and every span
    closes on the hard cap carrying one bankable voice plus one unbankable fragment, which is
    exactly what F2 and F3 recorded.

    Returns the track and the measured facts that make the mode falsifiable: if a rendered
    fragment ever reaches the evidence floor it would be embedded, the births would stop, and
    the run would silently be testing something else.
    """

    floor_seconds = FRAME_SAMPLES / SAMPLE_RATE
    total_samples = int(total_seconds * SAMPLE_RATE)
    track = array.array("h", bytes(max(0, total_samples) * 2))
    rendered = [synthesize(voice, line, workdir) for line in lines]
    durations = [len(samples) / SAMPLE_RATE for samples in rendered]
    too_long = [
        (line, round(duration, 3))
        for line, duration in zip(lines, durations)
        if duration >= floor_seconds
    ]
    if too_long:
        raise ProbeError(
            "fragment lines must render shorter than the evidence floor "
            f"({floor_seconds:.2f} s) or they are embeddable and the mode tests nothing: {too_long}"
        )
    step = max(interval_seconds, 0.0)
    if step <= 0:
        raise ProbeError("--fragment-interval must be greater than zero")
    placed = 0
    index = 0
    start = max(0.0, lead_seconds)
    while True:
        offset = int(start * SAMPLE_RATE)
        if offset >= total_samples:
            break
        samples = rendered[index % len(rendered)]
        index += 1
        end = min(offset + len(samples), total_samples)
        track[offset:end] = samples[: end - offset]
        placed += 1
        start += step
    facts = {
        "fragments_placed": placed,
        "interval_seconds": step,
        "evidence_floor_seconds": floor_seconds,
        "rendered_seconds": {
            line: round(duration, 3) for line, duration in zip(lines, durations)
        },
    }
    return track, facts


def build_continuous_track(
    voice: str,
    lines: tuple[str, ...],
    total_seconds: float,
    workdir: Path,
    lead_seconds: float,
) -> array.array:
    """Tile `lines` back to back so the lane is voiced for the whole run.

    `build_lane_track` lays a handful of utterances on a silent timeline, so between turns
    the lane sends frames whose every sample is zero and whose wire `silent` flag is true.
    A real capture device never does that: the microphone hears the room and the process
    tap carries the program, so on the Mac **both lanes are non-silent continuously** and
    every span closes on the 2.5 s hard cap with content on both lanes. That difference is
    measured, not assumed -- iteration 26's F1 run B committed 12 spans in 30 s, all
    `hard_cap`, while iteration 23's 120 s probe run committed 36 of 59 spans *empty*. It
    is the largest remaining gap between what this probe drives and what the real client
    drives, which is why it is a mode rather than a rewrite: `alternating` stays the
    default so every earlier run remains comparable.

    Utterances are concatenated rather than placed at offsets, so no silence can appear
    between them however long `say` makes each line.
    """

    total_samples = int(total_seconds * SAMPLE_RATE)
    track = array.array("h", bytes(max(0, total_samples) * 2))
    rendered = [synthesize(voice, line, workdir) for line in lines]
    cursor = int(max(0.0, lead_seconds) * SAMPLE_RATE)
    index = 0
    while cursor < total_samples:
        samples = rendered[index % len(rendered)]
        index += 1
        if not samples:
            continue
        end = min(cursor + len(samples), total_samples)
        track[cursor:end] = samples[: end - cursor]
        cursor = end
    return track


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


def words_of(transcript: str) -> str:
    """A committed transcript with its speaker tags removed.

    Phase N decision 10 is that a revision moves labels and never words. Reading that off a
    run needs the words isolated from the tags, and the tag grammar has exactly one shape.
    """
    return SPEAKER_TOKEN.sub("", transcript or "").strip()


def _unseen_events(batch, seen: set[int]) -> tuple[list[dict], int]:
    """The events in this poll that no earlier poll already delivered, and how many repeated.

    `since_seq` is inclusive server-side, so the highest event of every poll comes back in the
    next one. The portal drops the repeat by seq rather than asking for a different range
    (`live_portal.py:474`), and this probe mirrors the portal, so the dedupe belongs here and
    the request stays exactly what a browser sends. The repeat count is RETURNED rather than
    silently dropped: the fence's own rule is that a run never subtracts a sample without
    printing it, and "the probe read 687 events" and "the meeting produced 590" are different
    facts about the same run.
    """
    fresh: list[dict] = []
    repeats = 0
    for event in batch:
        if not isinstance(event, dict):
            continue
        seq = event.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            if seq in seen:
                repeats += 1
                continue
            seen.add(seq)
        fresh.append(event)
    return fresh, repeats


def _sweep_summary(items: list[dict], canonical_events: list[dict]) -> dict:
    """What a sweep published, reduced to the numbers that decide it -- one half at a time.

    Iteration 7 read these by hand out of 31 items and that does not scale to a 150 s run.
    More to the point, the loop's own rule -- a verdict word must name the thing it decides --
    applies here: "the sweep ran" and "the sweep changed a label" and "the sweep rewrote a
    span to itself" are three different findings, and only counting them apart tells a
    fragmented meeting from a healthy one.

    **The two halves are read off two different surfaces and this reduction says which**
    (candidate 67). The CADENCE half's version is on
    `canonical_processed.identity_revision_version` (`live_service_runtime.py:615,800`); a
    committed item carries `identity_snapshot_version` (`live_session.py:165,814`), a different
    quantity written by a different writer. Reading the version off the item -- which is what
    this reduction did until now -- returns `None` on every span of every run, and an
    `isinstance(..., int)` filter turned that into a silent **0**: it would have reported "no
    revision" on the very soak that measured three. An absent field is `null` here and never 0,
    because this is the third time in this loop that a missing field was read as a negative
    measurement (`identity_finalized`, then `storageWrites`, now this).

    The SESSION-END half's version reaches no live reader at all -- it rides
    `identity_finalized`, which `_record_event` appends to an in-memory list -- so it is filled
    in from the post-stop capture-authority drain, by `_session_end_sweep`, and stays `null`
    with its reason when that drain is refused.

    `revised_items` and the three counts beside it are read off the FINAL snapshot, so they are
    BOTH halves together and cannot separate them. Only a snapshot taken mid-meeting can
    attribute a revision to the cadence, which is what the version histogram is for.
    """
    revised = [item for item in items if item.get("revised_transcript")]
    label_changing = 0
    byte_identical = 0
    words_moved = 0
    for item in revised:
        original = str(item.get("transcript") or "")
        revision = str(item.get("revised_transcript") or "")
        if revision == original:
            byte_identical += 1
            continue
        if words_of(revision) != words_of(original):
            words_moved += 1
        if speakers_in(revision) != speakers_in(original):
            label_changing += 1
    versions: list[int] = []
    histogram: dict[int, int] = {}
    without_version = 0
    spans_revised = 0
    merges = 0
    first_nonzero: dict | None = None
    for event in canonical_events:
        version = event.get("identity_revision_version")
        if not isinstance(version, int) or isinstance(version, bool):
            without_version += 1
            continue
        histogram[version] = histogram.get(version, 0) + 1
        if version not in versions:
            versions.append(version)
        if version and first_nonzero is None:
            first_nonzero = {"span_id": event.get("span_id"), "version": version}
        spans_revised += _as_count(event.get("identity_revision_spans"))
        merges += _as_count(event.get("identity_revision_merges"))
    measured = bool(histogram)
    return {
        "committed_items": len(items),
        "revised_items": len(revised),
        "label_changing": label_changing,
        "byte_identical_rewrites": byte_identical,
        "words_moved": words_moved,
        "cadence": {
            "version_surface": "canonical_processed.identity_revision_version",
            "spans_reporting": len(canonical_events),
            "spans_without_version": without_version,
            # `null` and not `[]`/0: a run whose events never carried the field did not measure
            # zero revisions, it measured nothing. Only `measured` distinguishes them.
            "versions": sorted(versions) if measured else None,
            "version_histogram": (
                {str(key): histogram[key] for key in sorted(histogram)} if measured else None
            ),
            "max_version": max(versions) if measured else None,
            "first_nonzero": first_nonzero,
            "spans_revised": spans_revised if measured else None,
            "merges": merges if measured else None,
        },
    }


def _as_count(value) -> int:
    """A count the server reported, or 0 -- never a TypeError on a null."""
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _session_end_sweep(post_stop: dict) -> dict:
    """The final sweep's own numbers, or the named reason they are unreadable.

    ADR-0002's final sweep records `identity_finalized` whether or not it changed anything, so
    its payload is the only surface that tells "the last sweep ran and found nothing" from "the
    last sweep never ran". It is also the surface no live reader can reach. When the post-stop
    drain is refused -- iteration 7 measured 403 for capture authority on a closed session --
    every number here is `null` and the refusal is named, rather than reading as a sweep that
    published nothing.
    """
    finalized = list(post_stop.get("identity_finalized") or ())
    if not finalized:
        return {
            "version": None,
            "spans_revised": None,
            "units_revised": None,
            "merges": None,
            "refusals": None,
            "unreadable": (
                "identity_finalized not read: post-stop events drain returned "
                f"{post_stop.get('status')}"
            ),
        }
    payload = finalized[-1]
    return {
        "version": payload.get("identity_revision_version"),
        "spans_revised": payload.get("identity_revision_spans"),
        "units_revised": payload.get("identity_revision_units"),
        "merges": payload.get("identity_revision_merges"),
        "refusals": payload.get("identity_revision_refusals"),
        "unreadable": None,
    }


def transcript_of(snapshot: dict) -> list[dict]:
    session = snapshot.get("session") or {}
    items = []
    for commit in session.get("committed") or ():
        if isinstance(commit, dict):
            items.append(commit)
    return items


def main() -> int:
    # Checked before the parser because a run needs --host/--pin/--device-id and a self-test
    # needs none of them; the instrument must be checkable on a host with no server, which is
    # the whole point of a regression that costs no session.
    if "--self-test" in sys.argv[1:]:
        return _self_test()
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
        "--lane-audio",
        choices=("alternating", "continuous", "fragmented"),
        default="alternating",
        help="alternating: one lane speaks while the other sends silent frames (the "
        "original schedule). continuous: both lanes are voiced for the whole run, which "
        "is what a real Mac capture does -- the microphone hears the room and the tap "
        "carries the program, so no lane is ever silent and every span closes on the hard "
        "cap with content on both lanes. fragmented: the peer lane stays continuous while "
        "--fragment-lane carries isolated sub-floor interjections, which is candidate 55's "
        "measured regime -- a canonical speaker minted per span from audio the system "
        "refuses to embed.",
    )
    parser.add_argument(
        "--fragment-lane",
        choices=LANES,
        default="microphone",
        help="which lane carries the fragments under --lane-audio fragmented; the "
        "microphone is the lane a real room fragments, so it is the default",
    )
    parser.add_argument(
        "--fragment-interval",
        type=float,
        default=3.0,
        help="seconds between fragments under --lane-audio fragmented. At the deployed "
        "2.5 s hard cap a value at or below it puts a fragment in nearly every span, which "
        "is what drives the canonical count up; larger values fragment more slowly.",
    )
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
        "--concurrent-readers",
        type=int,
        default=0,
        help="extra view readers, each on its own thread and its own pinned connection, "
        "polling snapshot+events while frames are posted. The Mac runs 2 (the app's "
        "latency probe and the portal poller); 0 keeps this probe strictly serial and "
        "every earlier run comparable.",
    )
    parser.add_argument(
        "--reader-interval",
        type=float,
        default=0.22,
        help="seconds between polls per concurrent reader; 0.22 reproduces F1's measured "
        "~4.4 snapshot reads per second per reader",
    )
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
        fragment_facts: dict | None = None
        if args.lane_audio == "continuous":
            tracks = {
                "microphone": build_continuous_track(
                    args.mic_voice, MIC_LINES, args.seconds, workdir, args.lead_seconds
                ),
                "system": build_continuous_track(
                    args.system_voice, SYSTEM_LINES, args.seconds, workdir, args.lead_seconds
                ),
            }
        elif args.lane_audio == "fragmented":
            voices = {"microphone": args.mic_voice, "system": args.system_voice}
            peer_lines = {"microphone": MIC_LINES, "system": SYSTEM_LINES}
            peer_lane = next(lane for lane in LANES if lane != args.fragment_lane)
            fragment_track, fragment_facts = build_fragment_track(
                voices[args.fragment_lane],
                FRAGMENT_LINES,
                args.seconds,
                workdir,
                args.lead_seconds,
                args.fragment_interval,
            )
            fragment_facts["lane"] = args.fragment_lane
            tracks = {
                args.fragment_lane: fragment_track,
                peer_lane: build_continuous_track(
                    voices[peer_lane],
                    peer_lines[peer_lane],
                    args.seconds,
                    workdir,
                    args.lead_seconds,
                ),
            }
        else:
            tracks = {
                "microphone": build_lane_track(args.mic_voice, mic_schedule, args.seconds, workdir),
                "system": build_lane_track(args.system_voice, system_schedule, args.seconds, workdir),
            }
    lane_frames = {lane: frames_of(track) for lane, track in tracks.items()}
    tick_count = max(len(frames) for frames in lane_frames.values())
    report["audio"] = {
        "voices": {"microphone": args.mic_voice, "system": args.system_voice},
        "lane_audio": args.lane_audio,
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
    if fragment_facts is not None:
        report["audio"]["fragments"] = fragment_facts

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

    # --- the Mac's read concurrency, if asked for -------------------------------------
    readers: list[ConcurrentViewReader] = []
    for index in range(max(0, args.concurrent_readers)):
        reader = ConcurrentViewReader(
            name=f"view-reader-{index + 1}",
            host=args.host,
            port=args.port,
            pin=args.pin,
            session_id=session_id,
            view_token=view_token,
            interval=args.reader_interval,
        )
        readers.append(reader)
        reader.start()

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
    # Which kinds, not merely how many. `events_seen` was a bare count for six runs, and a
    # count cannot answer "did the session-end sweep run", which is the question ADR-0002's
    # second acceptance half turns on. Counting by kind costs nothing and makes the absence
    # of a kind a measurement rather than an inference.
    event_kinds: dict[str, int] = {}
    # `since_seq` is INCLUSIVE server-side (`live_service_runtime.events`: `event.seq >=
    # since_seq`), so every poll re-delivers the highest event of the previous one. The portal
    # this probe mirrors keeps the same request and drops the repeat on the reader side
    # (`live_portal.py:474` -- `event.seq <= state.eventSequence || renderedEvents.has(seq)`),
    # so the faithful mirror is to keep the wire behaviour and dedupe here. Without it a
    # re-read is a second measurement: every report before this one counted `session_created`
    # TWICE, and `_decode_summary`'s `spans_total` and RTF percentiles were computed over a
    # span list with the boundary span repeated once per poll.
    seen_event_seqs: set[int] = set()
    duplicate_event_reads = 0
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
                fresh, repeats = _unseen_events(body.get("events") or (), seen_event_seqs)
                duplicate_event_reads += repeats
                for event in fresh:
                    events_seen += 1
                    kind = str(event.get("kind") or "")
                    event_kinds[kind] = event_kinds.get(kind, 0) + 1
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
                                    # D-c (candidate 50, iteration 16) put the decode bound and
                                    # its verdict on this event. Collecting the RTF alone made the
                                    # probe unable to say whether a span was CAPPED or merely
                                    # fast, which is the whole question the cap was added to answer.
                                    "canonical_decode_elapsed_sec",
                                    "canonical_decode_token_cap",
                                    "canonical_decode_capped",
                                    "frozen_span_duration_sec",
                                    # The ONE sweep-refusal surface a client can read
                                    # (`live_service_runtime.py:804`). A session-end sweep's
                                    # refusals ride `identity_finalized`, which no client can
                                    # reach, so this covers the CADENCE half only -- and an
                                    # empty map here with a revision published is the
                                    # difference between "the sweep proposed nothing" and
                                    # "it proposed something the session would not apply".
                                    "identity_revision_refusals",
                                    # The cadence sweep's own product, on the only surface that
                                    # carries it (`live_service_runtime.py:615,800`). `version`
                                    # is the session's CURRENT label revision, written on every
                                    # span, so its histogram over a meeting is the record of
                                    # when each correction became visible; `spans`/`merges` are
                                    # what that one revision changed. A committed item does not
                                    # carry any of this -- it carries `identity_snapshot_
                                    # version`, a different quantity (candidate 67).
                                    "identity_revision_version",
                                    "identity_revision_spans",
                                    "identity_revision_merges",
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

    # Stopped before the `stop` call, so a 401 recorded by a reader means the session
    # stopped being viewable *during the meeting* -- which is candidate 56 -- and not
    # because this probe ended it.
    for reader in readers:
        reader.stop()
    for reader in readers:
        reader.join(timeout=10.0)
    if readers:
        report["concurrent_readers"] = {
            "count": len(readers),
            "interval_seconds": args.reader_interval,
            "readers": [reader.summary() for reader in readers],
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
                # The version a committed item DOES carry, and the only one it carries: the
                # identity snapshot the span was labelled against. The revision version is not
                # here and never was -- projecting it off this item is candidate 67, and the
                # `sweep.cadence` reduction reads it off `canonical_processed` instead.
                "identity_snapshot_version": item.get("identity_snapshot_version"),
                "speakers": speakers_in(str(item.get("transcript") or "")),
                "transcript": item.get("transcript"),
                # Phase N decision 10 publishes a correction BESIDE the transcript: `transcript`
                # and `prefix_hash` never move, and the revision lands in `revised_transcript`.
                # Projecting only `transcript` made every prior run of this probe report an
                # unswept and a swept span identically.
                "revised_transcript": item.get("revised_transcript"),
                "revised_speakers": speakers_in(str(item.get("revised_transcript") or "")),
            }
            for item in items
        ],
    }
    report["sweep"] = _sweep_summary(report["transcript"]["items"], canonical_events)
    cadence_refusals: dict[str, int] = {}
    for event in canonical_events:
        for reason, count in (event.get("identity_revision_refusals") or {}).items():
            cadence_refusals[str(reason)] = cadence_refusals.get(str(reason), 0) + int(count)
    report["sweep"]["cadence_refusals"] = dict(sorted(cadence_refusals.items()))
    # The fragmentation the run set out to produce, measured on the wire rather than assumed.
    # `canonical_speakers` counts what the session minted; the denominator is the number of
    # distinct synthesized voices, which this probe knows exactly -- that ratio is the axis
    # iteration 5's multiplicity model is defined on (F2 measured 8.0).
    canonical = list(
        ((report.get("stop") or {}).get("snapshot") or {}).get(
            "identity_canonical_speakers"
        )
        or ()
    )
    real_voices = len({args.mic_voice, args.system_voice})
    report["fragmentation"] = {
        "canonical_speakers": len(canonical),
        "real_voices": real_voices,
        "references_per_real_voice": (
            round(len(canonical) / real_voices, 2) if real_voices else None
        ),
        "labels_seen_in_transcript": report["transcript"]["speakers"],
        "capacity_abstains": sum(
            1
            for event in canonical_events
            if event.get("identity_reason") == "speaker_capacity_exceeded"
        ),
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

    # The events a stop EMITS are the ones no run has ever read. `canonical_queued`,
    # `identity_finalized` and `session_closed` are all recorded inside `stop`, i.e. after the
    # last view poll, and the same stop revokes view authority -- so a view-token reader is
    # structurally blind to exactly the events that say how the meeting ended. Capture
    # authority is not: `CAPTURE_ACTIONS` carries `events`, and the capture path authorizes on
    # session OWNERSHIP, never on `VIEWABLE_SESSION_STATUSES`. So the owning device can still
    # read them once the session is closed.
    post_stop = _drain_events_after_stop(client, session_id, device_token, last_seq, seen_event_seqs)
    for kind, count in (post_stop.get("kinds") or {}).items():
        event_kinds[kind] = event_kinds.get(kind, 0) + count
    report["post_stop_events"] = post_stop
    report["sweep"]["session_end"] = _session_end_sweep(post_stop)
    report["events_seen"] = events_seen
    report["duplicate_event_reads"] = duplicate_event_reads
    report["event_kinds"] = dict(sorted(event_kinds.items()))
    report["canonical_events"] = canonical_events
    report["decode"] = _decode_summary(canonical_events)
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


def _expected_cap_function():
    """The cap the deployed service *should* have applied, preferring the product's own function.

    Restating the derivation here would let the probe drift from the code it is checking, which
    is the mistake the lane-refusal probe already avoided by importing the suite's payload
    builders. So import `canonical_decode_token_cap` when this checkout is importable, and fall
    back to the recorded literal (`68 + ceil(87 x duration_sec)`, iteration 16) only when it is
    not -- the probe must still run from a host that has no package. The report says which was
    used, because "matches the product" and "matches a number I typed" are different claims.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from moss_transcribe_diarize.app.live_adapters import (  # noqa: PLC0415
            canonical_decode_token_cap,
        )
    except Exception:  # pragma: no cover - exercised only on a host without the checkout
        return (lambda samples: 68 + math.ceil(87 * (samples / 16000)), "recorded-literal")
    return (lambda samples: canonical_decode_token_cap(sample_count=samples), "product-function")


def _decode_summary(canonical_events: list[dict]) -> dict:
    """Reduce the decode measurements D-c added to the `canonical_processed` event.

    F1 measured a committed p95 of 9053 ms whose entire tail came from two spans out of 42
    that decoded for 8.49 s and 8.29 s as degenerate repeat loops. D-c's answer was a token
    cap derived from the span's own duration (`68 + ceil(87 x duration_sec)`), so the
    question this section exists to answer is not "was the decode fast" but three sharper
    ones: is a cap in force at all, does the cap the service applied match the derivation on
    record, and did any span actually hit it. A run where nothing is capped still answers the
    first two -- an absent cap and an unexercised cap are different results and must not
    reduce to the same silence.

    `spans_total` counts spans, not event reads: the caller dedupes by `seq` before this sees
    them. Reports written before that fix counted the re-delivered boundary event as another
    span -- iteration 9's fragmented run reported `spans_total` 62 for a 61-span meeting, and
    its RTF p95 0.190 is 0.212 once the repeats are removed.
    """
    measured = [
        event
        for event in canonical_events
        if isinstance(event.get("canonical_decode_elapsed_sec"), (int, float))
    ]
    summary: dict = {
        "spans_total": len(canonical_events),
        "spans_measured": len(measured),
        "cap_present_count": sum(
            1 for event in measured if isinstance(event.get("canonical_decode_token_cap"), int)
        ),
        "capped_count": sum(1 for event in measured if event.get("canonical_decode_capped")),
        "capped_span_ids": [
            event.get("span_id") for event in measured if event.get("canonical_decode_capped")
        ],
    }
    if not measured:
        return summary

    elapsed = sorted(float(event["canonical_decode_elapsed_sec"]) for event in measured)
    rtfs = sorted(
        float(event["canonical_decode_rtf"])
        for event in measured
        if isinstance(event.get("canonical_decode_rtf"), (int, float))
    )
    summary["elapsed_sec"] = {
        "min": round(elapsed[0], 3),
        "p50": round(elapsed[max(1, math.ceil(0.50 * len(elapsed))) - 1], 3),
        "p95": round(elapsed[max(1, math.ceil(0.95 * len(elapsed))) - 1], 3),
        "max": round(elapsed[-1], 3),
    }
    if rtfs:
        summary["rtf"] = {
            "min": round(rtfs[0], 3),
            "p50": round(rtfs[max(1, math.ceil(0.50 * len(rtfs))) - 1], 3),
            "p95": round(rtfs[max(1, math.ceil(0.95 * len(rtfs))) - 1], 3),
            "max": round(rtfs[-1], 3),
            "bound": 1.0,
            "p95_under_bound": rtfs[max(1, math.ceil(0.95 * len(rtfs))) - 1] < 1.0,
        }

    # Re-derive the cap the service should have applied, from the span duration it reported.
    # This is the ONLY check that can tell "D-c is deployed" from "D-c is in the source tree":
    # the number has to come back off the wire matching the recorded derivation, not merely be
    # present. Mismatches are listed rather than counted so a drift names its span.
    expected_cap, cap_source = _expected_cap_function()
    summary["cap_expectation_source"] = cap_source
    mismatches = []
    caps_seen = set()
    for event in measured:
        cap = event.get("canonical_decode_token_cap")
        duration = event.get("frozen_span_duration_sec")
        if not isinstance(cap, int) or not isinstance(duration, (int, float)):
            continue
        caps_seen.add(cap)
        expected = expected_cap(round(float(duration) * 16000))
        if cap != expected:
            mismatches.append(
                {"span_id": event.get("span_id"), "cap": cap, "expected": expected, "duration_sec": duration}
            )
    summary["caps_observed"] = sorted(caps_seen)
    summary["cap_derivation_mismatches"] = mismatches
    summary["cap_derivation_holds"] = not mismatches and bool(caps_seen)
    return summary


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return round(ordered[rank - 1], 1)


def _drain_events_after_stop(
    client: PinnedClient,
    session_id: str,
    device_token: str,
    since_seq: int,
    seen: set[int] | None = None,
) -> dict:
    """Read the events a clean stop emitted, with the authority that still may.

    Reports the kinds and, for `identity_finalized`, its whole payload -- that event is
    recorded whether or not the final sweep changed anything (ADR-0002's final sweep;
    `live_service_runtime._finalize_identity_locked`), so its payload is the only surface in
    the system that tells "the last sweep ran and found nothing" from "the last sweep never
    ran". It is recorded through `_record_event`, which appends to the session's in-memory
    event list and writes NOTHING to the journal -- so a journal grep for it is 0 either way
    and is not evidence. Read the events.

    A non-200 is reported by status rather than raised: this runs after the run's own verdict
    is already decided, and losing the report to an exception here would be the worse trade.
    """

    status, body, _ = client.request(
        "GET",
        f"/api/live/sessions/{session_id}/events?since_seq={since_seq}",
        bearer=device_token,
    )
    result: dict = {"status": status, "since_seq": since_seq, "authority": "capture"}
    if status != 200 or not isinstance(body, dict):
        result["body"] = body
        return result
    # `since_seq` is inclusive here too, so the drain re-delivers events the run already
    # counted; merging its kinds into the run's histogram without this would double-count them.
    events, repeats = _unseen_events(body.get("events") or (), set() if seen is None else seen)
    kinds: dict[str, int] = {}
    finalized: list[dict] = []
    for event in events:
        kind = str(event.get("kind") or "")
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "identity_finalized":
            finalized.append(dict(event.get("payload") or {}))
    result["count"] = len(events)
    result["already_seen"] = repeats
    result["kinds"] = dict(sorted(kinds.items()))
    result["identity_finalized"] = finalized
    result["session_end_sweep_ran"] = bool(finalized)
    return result


def _probe_view_after_stop(client: PinnedClient, session_id: str, view_token: str) -> dict:
    """A clean stop must immediately revoke view authority (C1's contract)."""
    status, _body, _ = client.request(
        "GET", f"/api/live/sessions/{session_id}/snapshot", bearer=view_token
    )
    return {"snapshot_status": status, "revoked": status in (401, 403, 404)}


def _self_test() -> int:
    """Check the two reductions that read a field off a surface, without a server.

    `--self-test` exists because the defect it guards was invisible for two runs: the probe
    reported `revision_versions: []` on meetings that had published revisions, and nothing in
    the loop could tell that from a meeting that published none. Every case below is written so
    that the code as it stood before candidate 67 fails it.
    """
    failures: list[str] = []

    def check(name: str, got, want) -> None:
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # 1. The version comes off `canonical_processed`, and a committed item's own version is
    #    NEVER read. The items here carry a deliberately wrong `identity_revision_version` so a
    #    reduction that reads the item -- the pre-candidate-67 code -- reports 7 and fails.
    items = [
        {"span_id": f"s{i}", "identity_snapshot_version": 4, "identity_revision_version": 7}
        for i in range(3)
    ]
    events = [
        {"span_id": "s0", "identity_revision_version": 0, "identity_revision_spans": 0},
        {"span_id": "s1", "identity_revision_version": 0, "identity_revision_spans": 0},
        {"span_id": "s2", "identity_revision_version": 1, "identity_revision_spans": 2,
         "identity_revision_merges": 1},
    ]
    cadence = _sweep_summary(items, events)["cadence"]
    check("versions", cadence["versions"], [0, 1])
    check("histogram", cadence["version_histogram"], {"0": 2, "1": 1})
    check("max_version", cadence["max_version"], 1)
    check("first_nonzero", cadence["first_nonzero"], {"span_id": "s2", "version": 1})
    check("spans_revised", cadence["spans_revised"], 2)
    check("merges", cadence["merges"], 1)
    check("spans_reporting", cadence["spans_reporting"], 3)

    # 2. An ABSENT field is null, never 0. This is the case the old `isinstance(..., int)`
    #    filter collapsed into an empty list, which reads as "swept nothing".
    blind = _sweep_summary(items, [{"span_id": "s0"}, {"span_id": "s1"}])["cadence"]
    check("blind versions", blind["versions"], None)
    check("blind histogram", blind["version_histogram"], None)
    check("blind max_version", blind["max_version"], None)
    check("blind spans_revised", blind["spans_revised"], None)
    check("blind without_version", blind["spans_without_version"], 2)

    # 3. No events at all is the same answer, not a zero.
    empty = _sweep_summary([], [])["cadence"]
    check("empty versions", empty["versions"], None)
    check("empty max_version", empty["max_version"], None)
    check("empty spans_reporting", empty["spans_reporting"], 0)

    # 4. The shape the F3 soak actually measured (run 20260729-094359 iteration 12): the
    #    histogram {0:130, 1:122, 2:173, 3:223} over 648 spans, three revisions published
    #    mid-meeting. A reduction that cannot report this cannot answer candidate 65.
    f3: list[dict] = []
    for version, count in ((0, 130), (1, 122), (2, 173), (3, 223)):
        for index in range(count):
            f3.append(
                {
                    "span_id": f"v{version}-{index}",
                    "identity_revision_version": version,
                    "identity_revision_spans": 1 if index == 0 and version else 0,
                }
            )
    soak = _sweep_summary([], f3)["cadence"]
    check("f3 histogram", soak["version_histogram"], {"0": 130, "1": 122, "2": 173, "3": 223})
    check("f3 max_version", soak["max_version"], 3)
    check("f3 first_nonzero", soak["first_nonzero"], {"span_id": "v1-0", "version": 1})
    check("f3 spans_revised", soak["spans_revised"], 3)
    check("f3 spans_reporting", soak["spans_reporting"], 648)

    # 5. A re-delivered event is one measurement, and the repeat is counted rather than
    #    dropped in silence. `since_seq` is inclusive, so this is every poll, not an edge case.
    seen: set[int] = set()
    first, repeat_a = _unseen_events([{"seq": 0, "kind": "session_created"}, {"seq": 1}], seen)
    second, repeat_b = _unseen_events([{"seq": 1}, {"seq": 2}], seen)
    check("first poll", [event["seq"] for event in first], [0, 1])
    check("first repeats", repeat_a, 0)
    check("second poll", [event["seq"] for event in second], [2])
    check("second repeats", repeat_b, 1)

    # 6. The session-end half names its refusal instead of reporting a silent zero.
    refused = _session_end_sweep({"status": 403})
    check("session_end version", refused["version"], None)
    check(
        "session_end unreadable",
        refused["unreadable"],
        "identity_finalized not read: post-stop events drain returned 403",
    )
    read = _session_end_sweep(
        {"status": 200, "identity_finalized": [{"identity_revision_version": 4,
                                               "identity_revision_spans": 19}]}
    )
    check("session_end read version", read["version"], 4)
    check("session_end read spans", read["spans_revised"], 19)
    check("session_end read unreadable", read["unreadable"], None)

    for failure in failures:
        print(f"FAIL {failure}")
    print(f"self-test: {'FAIL' if failures else 'PASS'} ({len(failures)} failures)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
