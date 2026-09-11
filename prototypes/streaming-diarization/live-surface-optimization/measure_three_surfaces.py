"""Measure immediate/settled pre-Stop, Stop, terminal, and file transcript surfaces.

One command and full state are defined in PREREGISTRATION.md. This is bench-only code: it wraps
the existing production replay client and changes no service behavior.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import socket
import ssl
import subprocess
import sys
import time
import wave
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONVERGENCE = HERE.parent / "live-convergence"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(CONVERGENCE))

from evaluator_v2 import Segment as V2Segment  # noqa: E402
from evaluator_v2 import score_v2, speech_regions_from_wav  # noqa: E402
from moss_transcribe_diarize import live_service_replay as replay  # noqa: E402
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment, calculate_diarization, calculate_tbsa  # noqa: E402
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE  # noqa: E402

BASE_URL = "https://127.0.0.1:7861"
TOKEN_PATH = Path.home() / ".local/share/moss-transcribe-diarize/g3/shared-token"
DATA = REPO / "prototypes/streaming-diarization/data/real"
TERMINAL_JOB_STATES = {"waiting_review", "done", "failed", "cancelled"}
SURFACES = (
    "pre_stop_immediate",
    "pre_stop_settled",
    "stop_return",
    "post_stop_final",
    "file",
)
QUALITY_FIELDS = (
    "wer",
    "tbsa",
    "der",
    "text_coverage",
    "content_recall",
    "speaker_accuracy",
    "matched_word_speaker_accuracy",
    "reference_speech_der",
)


@dataclass(frozen=True)
class Case:
    case_id: str
    directory: Path
    comparator: Path

    @property
    def audio(self) -> Path:
        return self.directory / "audio.wav"

    @property
    def reference(self) -> Path:
        return self.directory / "reference.jsonl"


M4 = REPO / "evidence/live-convergence-0824/M4-e4-exit-2/passes"
CASES = (
    Case(
        "lex_bill_ackman",
        DATA / "benchmark_diarization_1min/samples/lex_bill_ackman",
        M4 / "trio-A/lex_bill_ackman/file-hypothesis.jsonl",
    ),
    Case(
        "lex_javier_milei",
        DATA / "benchmark_diarization_1min/samples/lex_javier_milei",
        M4 / "trio-A/lex_javier_milei/file-hypothesis.jsonl",
    ),
    Case(
        "lex_keyu_jin_1m",
        DATA / "benchmark_diarization_1min/samples/lex_keyu_jin",
        M4 / "trio-A/lex_keyu_jin/file-hypothesis.jsonl",
    ),
    Case(
        "lex_adam_frank_3m",
        DATA / "calibration_diarization_3min/samples/lex_adam_frank",
        M4 / "three-minute/adam3m-A/file-hypothesis.jsonl",
    ),
    Case(
        "lex_keyu_jin_5m",
        DATA / "benchmark_5m/lex_keyu_jin",
        M4 / "keyu5m-A/file-hypothesis.jsonl",
    ),
)
TRIO = frozenset(case.case_id for case in CASES[:3])


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(message: str) -> None:
    print(f"[{utc_now()}] {message}", flush=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def jsonl_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "max": None}

    def percentile(q: float) -> float:
        ordered = sorted(values)
        position = (len(ordered) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction

    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 6),
        "p50": round(percentile(0.50), 6),
        "p95": round(percentile(0.95), 6),
        "max": round(max(values), 6),
    }


def wav_facts(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        facts = {
            "channels": handle.getnchannels(),
            "sample_width_bytes": handle.getsampwidth(),
            "sample_rate": handle.getframerate(),
            "sample_count": handle.getnframes(),
        }
        pcm = handle.readframes(handle.getnframes())
    if (facts["channels"], facts["sample_width_bytes"], facts["sample_rate"]) != (1, 2, 16000):
        raise RuntimeError(f"unsupported live WAV shape: {path}: {facts}")
    facts.update(
        {
            "path": str(path),
            "wav_bytes": path.stat().st_size,
            "wav_sha256": sha256(path),
            "pcm_bytes": len(pcm),
            "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
            "duration_seconds": facts["sample_count"] / facts["sample_rate"],
        }
    )
    return facts


def headers() -> dict[str, str]:
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"empty bearer token: {TOKEN_PATH}")
    return {"Authorization": f"Bearer {token}"}


class SurfaceCaptureService:
    """Observe the existing replay client's Stop boundary without changing the service."""

    def __init__(self, inner: replay.HttpLiveReplayService, settle_timeout: float, poll_seconds: float):
        self.inner = inner
        self.settle_timeout = settle_timeout
        self.poll_seconds = poll_seconds
        self.captures: dict[str, dict[str, Any]] = {}
        self.stop_requested_monotonic_ns: int | None = None
        self._next_event_seq = 0
        self._pending_rolling: set[int] = set()

    def _capture(self, name: str, snapshot) -> None:
        if name == "post_stop_final" and (
            snapshot is None or snapshot.session.finalization_status != "final"
        ):
            status = None if snapshot is None else snapshot.session.finalization_status
            raise replay.ServiceReplayFailure(f"final capture requires final terminal state; observed {status}")
        if snapshot is None or name in self.captures:
            return
        self.captures[name] = {
            "surface": name,
            "observed_utc": utc_now(),
            "observed_monotonic_ns": time.monotonic_ns(),
            "snapshot": snapshot.to_dict(),
        }
        session = snapshot.session
        log(
            f"capture={name} status={session.status} finalization={session.finalization_status} "
            f"accepted={session.accepted_samples} accounted={session.accounted_samples} "
            f"pending={snapshot.pending_work_items} segments={len(session.effective_transcript)}"
        )

    def create(self):
        return self.inner.create()

    def accept_frame(self, session_id, frame):
        return self.inner.accept_frame(session_id, frame)

    def events(self, session_id, since_seq=0):
        events = self.inner.events(session_id, since_seq=since_seq)
        for event in events:
            if event.seq < self._next_event_seq:
                continue
            if event.seq != self._next_event_seq:
                raise replay.ServiceReplayFailure("settle rolling event history has a gap")
            self._next_event_seq = event.seq + 1
            if event.kind == "rolling_decode_queued" and event.payload.get("admitted") is True:
                self._pending_rolling.add(int(event.payload["item_id"]))
            elif event.kind == "rolling_decode_completed":
                self._pending_rolling.discard(int(event.payload["item_id"]))
        return events

    def snapshot(self, session_id, since_version=None):
        snapshot = self.inner.snapshot(session_id, since_version=since_version)
        if (
            snapshot is not None
            and snapshot.session.finalization_status in replay.TERMINAL_FINALIZATION_SETTLED
            and snapshot.session.finalization_status != "not_started"
        ):
            self._capture("post_stop_final", snapshot)
        return snapshot

    async def stop(self, session_id: str, deadline: float):
        immediate = self.inner.snapshot(session_id)
        self._capture("pre_stop_immediate", immediate)
        wait_started = time.monotonic()
        settled = immediate
        polls = 0
        while True:
            if settled is None:
                raise replay.ServiceReplayFailure("settle snapshot is unavailable")
            # Replay drains events continuously during ingress; finish tracking rolling
            # admissions/completions here without changing canonical backpressure counts.
            self.events(session_id, since_seq=self._next_event_seq)
            if settled.pending_work_items == 0 and not self._pending_rolling:
                # Completion may have happened after the snapshot above. Capture the
                # document after observing its completion, never the earlier snapshot.
                settled = self.inner.snapshot(session_id)
                if settled is None:
                    raise replay.ServiceReplayFailure("settle snapshot is unavailable")
                if settled.pending_work_items == 0:
                    break
            if time.monotonic() - wait_started >= self.settle_timeout:
                raise replay.ServiceReplayFailure(
                    f"settle timed out after {self.settle_timeout:g}s: "
                    f"canonical={settled.pending_work_items}, rolling={len(self._pending_rolling)}"
                )
            time.sleep(self.poll_seconds)
            polls += 1
            settled = self.inner.snapshot(session_id)
        self._capture("pre_stop_settled", settled)
        self.captures["pre_stop_settled"]["wait"] = {
            "seconds": round(time.monotonic() - wait_started, 6),
            "polls": polls,
            "timeout_seconds": self.settle_timeout,
            "drained": True,
            "pending_rolling_work_items": len(self._pending_rolling),
        }
        self.stop_requested_monotonic_ns = time.monotonic_ns()
        stopped = await self.inner.stop(session_id, deadline)
        self._capture("stop_return", stopped)
        if stopped.session.finalization_status in replay.TERMINAL_FINALIZATION_SETTLED:
            self._capture("post_stop_final", stopped)
        return stopped

    async def abort(self, session_id, reason):
        return await self.inner.abort(session_id, reason)


def transcript_rows(snapshot: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    hypothesis = lsa.hypothesis_from_live_snapshot(
        {"snapshot": snapshot}, corpus_start_sample=0, corpus_duration_sec=duration
    )
    return [
        {"start": row.start, "end": row.end, "speaker": row.speaker, "text": row.text}
        for row in hypothesis
    ]


def hypothesis(rows: list[dict[str, Any]]):
    return [
        lsa.TranscriptSegment(
            start=float(row["start"]),
            end=float(row["end"]),
            speaker=str(row["speaker"]),
            text=str(row.get("text") or ""),
        )
        for row in rows
    ]


def score_surface(case: Case, rows: list[dict[str, Any]]) -> dict[str, Any]:
    reference = lsa.load_reference_jsonl(case.reference)
    activity = lsa.load_reference_speaker_activity_jsonl(case.reference)
    hyp = hypothesis(rows)
    ref_eval = [Segment(r.start, r.end, r.speaker, r.text) for r in reference]
    hyp_eval = [Segment(r.start, r.end, r.speaker, r.text) for r in hyp]
    tbsa = calculate_tbsa(ref_eval, hyp_eval)
    diarization = calculate_diarization(ref_eval, hyp_eval)
    speaker = lsa.score_live_speaker_accuracy(
        list(activity),
        [lsa.SpeakerActivityInterval(r.start, r.end, r.speaker) for r in hyp],
    )
    v2 = score_v2(
        [V2Segment(r.start, r.end, r.speaker, r.text) for r in reference],
        [V2Segment(r.start, r.end, r.speaker, r.text) for r in hyp],
        speech_regions=speech_regions_from_wav(case.audio),
        speech_regions_source="webrtcvad_mode1_10ms",
    )
    return {
        "wer": tbsa["wer"],
        "tbsa": tbsa["composite"],
        "der": diarization["der"],
        "text_coverage": tbsa["text_coverage"],
        "text_speaker_accuracy": tbsa["text_speaker_accuracy"],
        "content_recall": v2["content_recall"],
        "speaker_accuracy": speaker["speaker_accuracy"],
        "matched_word_speaker_accuracy": v2["matched_word_speaker"]["matched_word_speaker_accuracy"],
        "reference_speech_der": v2["der_reference_speech"]["der"],
        "reference_words": v2["wer"]["reference_words"],
        "hypothesis_words": v2["wer"]["hypothesis_words"],
        "segments": len(rows),
    }


def read_service_events(trace: Path) -> list[dict[str, Any]]:
    events = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("kind") == "service_event":
            events.append(row["event"])
    return events


def words_in_region(segments, start_sample: int, end_sample: int) -> list[str]:
    lo, hi = start_sample / LIVE_SAMPLE_RATE, end_sample / LIVE_SAMPLE_RATE
    words: list[str] = []
    for segment in segments:
        if lo - 1e-9 <= segment.start < hi + 1e-9:
            words.extend(segment.text.split())
    return words


def event_measurements(
    events: list[dict[str, Any]],
    pre_stop_snapshot: dict[str, Any],
    final_capture: dict[str, Any],
    stop_requested_ns: int | None,
    duration: float,
) -> dict[str, Any]:
    canonical: list[dict[str, Any]] = []
    queued: dict[int, int] = {}
    rolling: list[dict[str, Any]] = []
    terminal: list[dict[str, Any]] = []
    depth = max_depth = 0
    admission_refusals = 0
    text_revision_refusals: list[dict[str, Any]] = []
    terminal_failures = []
    for event in events:
        kind, payload = event["kind"], event.get("payload") or {}
        if kind == "canonical_queued":
            queued[int(payload["item_id"])] = int(payload["runtime_monotonic_ns"])
        elif kind == "canonical_processed":
            end = int(payload.get("committed_samples") or 0)
            samples = int(payload.get("frozen_span_sample_count") or 0)
            canonical.append(
                {
                    "item_id": int(payload["item_id"]),
                    "start_sample": end - samples,
                    "end_sample": end,
                    "queued_ns": queued.get(int(payload["item_id"])),
                    "published_ns": int(payload["runtime_monotonic_ns"]),
                    "decode_seconds": float(payload.get("canonical_decode_elapsed_sec") or 0.0),
                    "decoded_audio_samples": samples,
                    "queue_wait_ms": payload.get("queue_wait_ms"),
                    "submitted": payload.get("submitted"),
                }
            )
        elif kind == "rolling_decode_queued":
            if payload.get("admitted"):
                depth += 1
                max_depth = max(max_depth, depth)
            else:
                admission_refusals += 1
        elif kind == "rolling_decode_completed":
            depth -= 1
            rolling.append(payload)
        elif kind == "text_revision_refused":
            text_revision_refusals.append(payload)
        elif kind == "terminal_finalization_completed":
            terminal.append(payload)
        elif kind in {"terminal_finalization_failed", "terminal_failure"}:
            terminal_failures.append(payload)

    base = lsa._hypothesis_from_committed(
        pre_stop_snapshot["session"], corpus_start_sample=0, corpus_duration_sec=duration
    )
    settled = lsa._hypothesis_from_surface(
        pre_stop_snapshot["session"], corpus_start_sample=0, corpus_duration_sec=duration
    )
    epoch_candidates = [
        row["queued_ns"] - int(row["end_sample"] / LIVE_SAMPLE_RATE * 1e9)
        for row in canonical
        if row["queued_ns"] is not None
    ]
    meeting_epoch = min(epoch_candidates) if epoch_candidates else None
    first_rows = []
    for row in canonical:
        in_span = [
            segment for segment in base
            if row["start_sample"] / LIVE_SAMPLE_RATE - 1e-9 <= segment.start < row["end_sample"] / LIVE_SAMPLE_RATE + 1e-9
            and segment.text.strip()
        ]
        if not in_span or meeting_epoch is None:
            continue
        published = (row["published_ns"] - meeting_epoch) / 1e9
        first_rows.append(
            {
                "item_id": row["item_id"],
                "first_spoken_word_seconds": min(segment.start for segment in in_span),
                "publication_seconds": published,
                "age_seconds": max(0.0, published - min(segment.start for segment in in_span)),
            }
        )

    corrections = []
    for row in rolling:
        if not row.get("applied"):
            continue
        start, end = int(row["owned_start_sample"]), int(row["owned_end_sample"])
        changed = words_in_region(base, start, end) != words_in_region(settled, start, end)
        if not changed:
            continue
        for provisional in canonical:
            midpoint = (provisional["start_sample"] + provisional["end_sample"]) / 2
            if start <= midpoint <= end + 1e-9:
                corrections.append(
                    {
                        "rolling_item_id": row.get("item_id"),
                        "canonical_item_id": provisional["item_id"],
                        "age_seconds": max(
                            0.0,
                            (int(row["runtime_monotonic_ns"]) - provisional["published_ns"]) / 1e9,
                        ),
                    }
                )

    base_decode = sum(row["decode_seconds"] for row in canonical)
    rolling_decode = sum(float(row.get("rolling_decode_elapsed_sec") or 0.0) for row in rolling)
    terminal_decode = sum(float(row.get("decode_elapsed_sec") or 0.0) for row in terminal)
    decoded_samples = {
        "base": sum(row["decoded_audio_samples"] for row in canonical),
        "rolling": sum(int(row.get("decoded_audio_samples") or 0) for row in rolling),
        "terminal": sum(int(row.get("decoded_audio_samples") or 0) for row in terminal),
    }
    stop_to_final = None
    if stop_requested_ns is not None:
        stop_to_final = (final_capture["observed_monotonic_ns"] - stop_requested_ns) / 1e9
    return {
        "first_publication_rows": first_rows,
        "first_publication_seconds": distribution([row["age_seconds"] for row in first_rows]),
        "correction_rows": corrections,
        "correction_age_seconds": distribution([row["age_seconds"] for row in corrections]),
        "stop_to_final_seconds": None if stop_to_final is None else round(stop_to_final, 6),
        "decode_seconds": {
            "base": round(base_decode, 6),
            "rolling": round(rolling_decode, 6),
            "terminal": round(terminal_decode, 6),
        },
        "rtf": {
            "base": round(base_decode / duration, 6),
            "rolling": round(rolling_decode / duration, 6),
            "terminal": round(terminal_decode / duration, 6),
            "pre_stop_combined": round((base_decode + rolling_decode) / duration, 6),
            "all_decode_combined": round((base_decode + rolling_decode + terminal_decode) / duration, 6),
        },
        "decode_requests": {
            "base": len(canonical),
            "rolling": len(rolling),
            "terminal": len(terminal),
            "total": len(canonical) + len(rolling) + len(terminal),
        },
        "decoded_audio_work_seconds": {
            key: round(value / LIVE_SAMPLE_RATE, 6) for key, value in decoded_samples.items()
        },
        "rolling_queue": {
            "max_depth": max_depth,
            "final_depth": depth,
            "admission_refusals": admission_refusals,
            "stale_completions": max([int(row.get("stale_completions") or 0) for row in rolling] or [0]),
            "failed_windows": max([int(row.get("windows_failed") or 0) for row in rolling] or [0]),
            "proposal_refusals": max(
                [int(row.get("proposal_refusals") or 0) for row in rolling] or [0]
            ),
            "last_proposal_refusal": next(
                (
                    row.get("last_proposal_refusal")
                    for row in reversed(rolling)
                    if row.get("last_proposal_refusal")
                ),
                None,
            ),
            "text_revision_refusals": [
                {
                    "window_index": row.get("window_index"),
                    "refusal": row.get("refusal"),
                }
                for row in text_revision_refusals
            ],
            "status_counts": {
                status: sum(row.get("rolling_status") == status for row in rolling)
                for status in sorted(
                    {str(row.get("rolling_status")) for row in rolling if row.get("rolling_status")}
                )
            },
            "windows": [
                {
                    "window_index": row.get("window_index"),
                    "start_sample": row.get("start_sample"),
                    "end_sample": row.get("end_sample"),
                    "outcome": row.get("outcome"),
                    "rolling_status": row.get("rolling_status"),
                    "normalization_merged_segments": row.get(
                        "normalization_merged_segments"
                    ),
                    "normalization_dropped_segments": row.get(
                        "normalization_dropped_segments"
                    ),
                    "normalization_displaced_samples": row.get(
                        "normalization_displaced_samples"
                    ),
                }
                for row in rolling
            ],
            "completed": len(rolling),
        },
        "terminal_failures": terminal_failures,
        "base_unsubmitted": sum(row["submitted"] is not True for row in canonical),
    }


def run_file(case: Case) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    started = time.monotonic()
    with case.audio.open("rb") as handle:
        response = requests.post(
            f"{BASE_URL}/api/jobs",
            headers=headers(),
            files={"file": (f"{case.case_id}.wav", handle, "audio/wav")},
            verify=False,
            timeout=300,
        )
    response.raise_for_status()
    job = response.json()
    while job.get("status") not in TERMINAL_JOB_STATES:
        time.sleep(1.0)
        response = requests.get(
            f"{BASE_URL}/api/jobs/{job['id']}", headers=headers(), verify=False, timeout=30
        )
        response.raise_for_status()
        job = response.json()
    if job.get("status") not in {"done", "waiting_review"}:
        raise RuntimeError(f"file job failed: {job}")
    response = requests.get(
        f"{BASE_URL}/api/jobs/{job['id']}/segments", headers=headers(), verify=False, timeout=30
    )
    response.raise_for_status()
    rows = [
        {
            "start": float(row["start"]),
            "end": float(row["end"]),
            "speaker": str(row["speaker"]),
            "text": str(row.get("text") or ""),
        }
        for row in response.json()["segments"]
        if float(row["end"]) > float(row["start"])
    ]
    return (
        {
            "job_id": job["id"],
            "status": job.get("status"),
            "wall_seconds": round(time.monotonic() - started, 6),
            "generated_tokens": job.get("generated_tokens"),
        },
        rows,
    )


def runtime_descriptor() -> dict[str, Any]:
    response = requests.get(f"{BASE_URL}/api/runtime", verify=False, timeout=20)
    response.raise_for_status()
    return response.json()


def warm_decoder(out: Path) -> None:
    log("discarded decoder warm-up START")
    with (out / "warmup.log").open("w", encoding="utf-8") as sink:
        subprocess.run(
            [sys.executable, str(CONVERGENCE / "probe_decode_determinism.py"), "--repeats", "1"],
            cwd=REPO,
            stdout=sink,
            stderr=subprocess.STDOUT,
            check=True,
        )
    log("discarded decoder warm-up DONE")


def measure_run(
    case: Case,
    run_dir: Path,
    run_label: str,
    deployed_code_revision: str,
    expected_runtime: dict[str, Any],
    settle_timeout: float,
    poll_seconds: float,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=False)
    audio = wav_facts(case.audio)
    runtime = runtime_descriptor()
    descriptor = runtime["live"]["descriptor"]
    if descriptor != expected_runtime["live"]["descriptor"]:
        raise RuntimeError("runtime descriptor changed during the matrix")
    service = SurfaceCaptureService(
        replay.HttpLiveReplayService(
            base_url=BASE_URL,
            bearer_token=TOKEN_PATH.read_text(encoding="utf-8").strip(),
        ),
        settle_timeout=settle_timeout,
        poll_seconds=poll_seconds,
    )
    live_dir = run_dir / "live-replay"
    log(f"run={run_label} case={case.case_id} live START duration={audio['duration_seconds']:.1f}s")
    replay.run_service_replay(
        service=service,
        audio_path=case.audio,
        out_dir=live_dir,
        pace=1.0,
        max_pacing_lag=3.0,
        runs=1,
        expect_revision=descriptor["source_revision"],
        expect_provider_hash=descriptor["provider_manifest_hash"],
        expect_config_hash=descriptor["config_hashes"]["combined_config_hash"],
    )
    trace = live_dir / "run-001/trace.jsonl"
    events = read_service_events(trace)
    jsonl_dump(run_dir / "events.jsonl", events)
    if "post_stop_final" not in service.captures:
        for line in trace.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("kind") == "terminal" and row.get("snapshot"):
                service._capture("post_stop_final", replay._snapshot_from_dict(row["snapshot"]))
    missing = [name for name in SURFACES[:-1] if name not in service.captures]
    if missing:
        raise RuntimeError(f"missing live surface captures: {missing}")
    if service.captures["post_stop_final"]["snapshot"]["session"]["finalization_status"] != "final":
        raise RuntimeError("post-Stop terminal surface did not reach final")

    snapshots = [service.captures[name] for name in SURFACES[:-1]]
    jsonl_dump(run_dir / "snapshots.jsonl", snapshots)
    rows_by_surface: dict[str, list[dict[str, Any]]] = {}
    for name in SURFACES[:-1]:
        rows = transcript_rows(service.captures[name]["snapshot"], audio["duration_seconds"])
        rows_by_surface[name] = rows
        jsonl_dump(run_dir / f"{name}.jsonl", rows)

    log(f"run={run_label} case={case.case_id} file START")
    file_meta, file_rows = run_file(case)
    rows_by_surface["file"] = file_rows
    jsonl_dump(run_dir / "file.jsonl", file_rows)
    file_hash = sha256(run_dir / "file.jsonl")
    comparator_hash = sha256(case.comparator)
    log(
        f"run={run_label} case={case.case_id} file DONE segments={len(file_rows)} "
        f"byte_identical={file_hash == comparator_hash}"
    )

    scores = {}
    for name, rows in rows_by_surface.items():
        scores[name] = score_surface(case, rows)
        log(
            f"run={run_label} case={case.case_id} surface={name} "
            f"WER={scores[name]['wer']:.6f} DER={scores[name]['der']:.6f} "
            f"spk={scores[name]['speaker_accuracy']:.6f} rows={len(rows)}"
        )

    settled_snapshot = service.captures["pre_stop_settled"]["snapshot"]
    event_metrics = event_measurements(
        events,
        settled_snapshot,
        service.captures["post_stop_final"],
        service.stop_requested_monotonic_ns,
        audio["duration_seconds"],
    )
    final_session = service.captures["post_stop_final"]["snapshot"]["session"]
    result = {
        "run": run_label,
        "case_id": case.case_id,
        "duration_seconds": audio["duration_seconds"],
        "audio": audio,
        "reference": {"path": str(case.reference), "bytes": case.reference.stat().st_size, "sha256": sha256(case.reference)},
        "provenance": {
            "repo_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
            "deployed_code_revision": deployed_code_revision,
            "runtime_descriptor": descriptor,
            "model": runtime.get("model"),
            "inference": runtime.get("inference"),
            "client_host": socket.gethostname(),
            "base_url": BASE_URL,
            "started_utc": utc_now(),
        },
        "surface_files": {name: f"{run_dir.name}/{name}.jsonl" for name in SURFACES},
        "surface_sha256": {name: sha256(run_dir / f"{name}.jsonl") for name in SURFACES},
        "surface_scores": scores,
        "surface_clocks": {
            name: {
                key: value for key, value in service.captures[name].items() if key != "snapshot"
            }
            for name in SURFACES[:-1]
        },
        "sample_accounting": {
            "accepted_samples": final_session["accepted_samples"],
            "accounted_samples": final_session["accounted_samples"],
            "exact": final_session["accepted_samples"] == final_session["accounted_samples"],
        },
        "file": {
            **file_meta,
            "jsonl_sha256": file_hash,
            "comparator_path": str(case.comparator),
            "comparator_sha256": comparator_hash,
            "byte_identical": file_hash == comparator_hash,
        },
        "events": event_metrics,
    }
    json_dump(run_dir / "run-result.json", result)
    return result


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_surface: dict[str, Any] = {}
    for surface in SURFACES:
        per_case = defaultdict(list)
        for row in rows:
            per_case[row["case_id"]].append(row["surface_scores"][surface])
        macro = {}
        weighted = {}
        total_seconds = sum(row["duration_seconds"] for row in rows)
        for field in QUALITY_FIELDS:
            case_means = [
                sum(item[field] for item in scores) / len(scores) for scores in per_case.values()
            ]
            macro[field] = round(sum(case_means) / len(case_means), 6)
            weighted[field] = round(
                sum(row["duration_seconds"] * row["surface_scores"][surface][field] for row in rows)
                / total_seconds,
                6,
            )
        by_surface[surface] = {
            "macro_mean": macro,
            "duration_weighted_mean": weighted,
            "denominator": {
                "cases": len(per_case),
                "observations": len(rows),
                "observed_audio_seconds": total_seconds,
            },
        }
    return by_surface


def stability(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "denominator": {
            "case": CASES[0].case_id,
            "sessions": len(rows),
            "observed_audio_seconds": sum(row["duration_seconds"] for row in rows),
        },
        "surface_hashes": {
            surface: {
                "hashes": [row["surface_sha256"][surface] for row in rows],
                "unique": len({row["surface_sha256"][surface] for row in rows}),
            }
            for surface in SURFACES
        },
    }


def validate_inputs(deployed_code_revision: str) -> dict[str, Any]:
    if not TOKEN_PATH.is_file():
        raise RuntimeError(f"missing bearer token file: {TOKEN_PATH}")
    for case in CASES:
        for path in (case.audio, case.reference, case.comparator):
            if not path.is_file():
                raise RuntimeError(f"missing corpus/comparator path: {path}")
    subprocess.run(["git", "cat-file", "-e", f"{deployed_code_revision}^{{commit}}"], cwd=REPO, check=True)
    runtime = runtime_descriptor()
    descriptor = runtime.get("live", {}).get("descriptor")
    if not descriptor or not descriptor.get("feature_enabled"):
        raise RuntimeError("live service descriptor is unavailable or disabled")
    return runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--deployed-code-revision", required=True)
    parser.add_argument("--settle-timeout", type=float, default=20.0)
    parser.add_argument("--poll-seconds", type=float, default=0.1)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--stability-runs", type=int, default=5)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.settle_timeout <= 0 or args.poll_seconds <= 0:
        raise SystemExit("settle and poll seconds must be positive")
    if args.passes not in {1, 2} or args.stability_runs < 0:
        raise SystemExit("passes must be 1 or 2 and stability runs must be non-negative")
    runtime = validate_inputs(args.deployed_code_revision)
    log(
        "validation PASS "
        f"descriptor_revision={runtime['live']['descriptor']['source_revision']} "
        f"deployed_code_revision={args.deployed_code_revision}"
    )
    if args.validate_only:
        return 0
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    json_dump(out / "runtime-start.json", runtime)

    warm_decoder(out)
    headline = []
    for pass_index in range(args.passes):
        cases = CASES if pass_index % 2 == 0 else tuple(reversed(CASES))
        pass_name = chr(ord("A") + pass_index)
        for case in cases:
            label = f"pass-{pass_name}-{case.case_id}"
            headline.append(
                measure_run(
                    case,
                    out / label,
                    label,
                    args.deployed_code_revision,
                    runtime,
                    args.settle_timeout,
                    args.poll_seconds,
                )
            )

    stability_rows = []
    for index in range(1, args.stability_runs + 1):
        label = f"stability-{index:02d}-{CASES[0].case_id}"
        stability_rows.append(
            measure_run(
                CASES[0],
                out / label,
                label,
                args.deployed_code_revision,
                runtime,
                args.settle_timeout,
                args.poll_seconds,
            )
        )

    runtime_end = runtime_descriptor()
    json_dump(out / "runtime-end.json", runtime_end)
    if runtime_end["live"]["descriptor"] != runtime["live"]["descriptor"]:
        raise RuntimeError("runtime descriptor changed between matrix start and end")
    trio_rows = [row for row in headline if row["case_id"] in TRIO]
    results = {
        "schema_version": 1,
        "preregistration": str(HERE / "PREREGISTRATION.md"),
        "created_utc": utc_now(),
        "headline": {
            "runs": headline,
            "all_five": aggregate(headline),
            "trio": aggregate(trio_rows),
            "latency": {
                "first_publication_seconds": distribution(
                    [
                        item["age_seconds"]
                        for row in headline
                        for item in row["events"]["first_publication_rows"]
                    ]
                ),
                "correction_age_seconds": distribution(
                    [
                        item["age_seconds"]
                        for row in headline
                        for item in row["events"]["correction_rows"]
                    ]
                ),
                "stop_to_final_seconds": distribution(
                    [row["events"]["stop_to_final_seconds"] for row in headline]
                ),
            },
        },
        "stability": {"runs": stability_rows, "summary": stability(stability_rows)},
        "checks": {
            "runtime_descriptor_unchanged": True,
            "exact_sample_accounting": all(row["sample_accounting"]["exact"] for row in headline + stability_rows),
            "file_byte_identical": all(row["file"]["byte_identical"] for row in headline + stability_rows),
            "pre_stop_combined_rtf_lt_1": all(row["events"]["rtf"]["pre_stop_combined"] < 1 for row in headline + stability_rows),
            "rolling_queue_bounded": all(
                row["events"]["rolling_queue"]["max_depth"] <= 1
                and row["events"]["rolling_queue"]["final_depth"] == 0
                and row["events"]["rolling_queue"]["admission_refusals"] == 0
                and row["events"]["rolling_queue"]["stale_completions"] == 0
                and row["events"]["rolling_queue"]["failed_windows"] == 0
                for row in headline + stability_rows
            ),
            "terminal_failures_zero": all(not row["events"]["terminal_failures"] for row in headline + stability_rows),
        },
        "unmeasured": ["browser_capture_to_paint", "portal_render_time", "peer_actual_live_surfaces"],
    }
    json_dump(out / "results.json", results)
    log(f"RESULTS {out / 'results.json'}")
    log(f"CHECKS {json.dumps(results['checks'], sort_keys=True)}")
    return 0 if all(results["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
