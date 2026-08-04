#!/usr/bin/env python3
"""PROTOTYPE: measure the A4 retained-tape finalizer resource envelope.

Question: can one nice'd, one-thread production CPU embedder process a 30-minute
bench tape inside the fixed resource gates while the A3 single-worker lifecycle
keeps stop acknowledgement and new-session admission responsive?

The tape is read sequentially in production-sized 40,000-sample chunks. Only one
chunk exists in memory and in the scratch WAV at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import queue
import resource
import subprocess
import sys
import threading
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


SCHEMA = "moss-l2-stage0-a4-runtime.v1"
EXPECTED_SOURCE_REVISION = "9089b33210401111865da7abc160ab0bcb4aa266"
EXPECTED_SOURCE_SHA256 = "b710a06c4c31582f2c84aabf10286795e2f7a988d8769085728a5735ef65a2b4"
EXPECTED_MODEL_SHA256 = "5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8"
EXPECTED_AUDIO_SHA256 = "842c9609ac4473bee0c29275fa2f38d73b00484acc603673f2317039005f8996"
SAMPLE_RATE = 16_000
HARD_CAP_SAMPLES = 40_000
DURATIONS_SECONDS = (25, 100, 300, 1_800)
SESSION_PROBE_REPETITIONS = 1_000
STOP_ACK_REPETITIONS = 1_000


class MeasurementError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise MeasurementError("empty_percentile")
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def proc_io() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/self/io").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip())
    return values


def current_rss_bytes() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise MeasurementError("vmrss_unavailable")


def peak_rss_bytes() -> int:
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def import_production(repo: Path) -> tuple[Any, type[Any], type[Any]]:
    package = types.ModuleType("moss_transcribe_diarize")
    package.__path__ = [str(repo / "moss_transcribe_diarize")]
    app_package = types.ModuleType("moss_transcribe_diarize.app")
    app_package.__path__ = [str(repo / "moss_transcribe_diarize" / "app")]
    sys.modules["moss_transcribe_diarize"] = package
    sys.modules["moss_transcribe_diarize.app"] = app_package

    transcript_spec = importlib.util.spec_from_file_location(
        "moss_transcribe_diarize.transcript_parser",
        repo / "moss_transcribe_diarize" / "transcript_parser.py",
    )
    if transcript_spec is None or transcript_spec.loader is None:
        raise MeasurementError("transcript_parser_import_failed")
    transcript = importlib.util.module_from_spec(transcript_spec)
    sys.modules[transcript_spec.name] = transcript
    transcript_spec.loader.exec_module(transcript)

    speaker_path = repo / "moss_transcribe_diarize" / "app" / "speaker_identity.py"
    speaker_spec = importlib.util.spec_from_file_location(
        "moss_transcribe_diarize.app.speaker_identity", speaker_path
    )
    if speaker_spec is None or speaker_spec.loader is None:
        raise MeasurementError("speaker_identity_import_failed")
    speaker = importlib.util.module_from_spec(speaker_spec)
    sys.modules[speaker_spec.name] = speaker
    speaker_spec.loader.exec_module(speaker)

    from moss_transcribe_diarize.app.live_session import LiveSession
    from moss_transcribe_diarize.app.live_v2_session import LiveV2SessionRegistry

    return speaker, LiveSession, LiveV2SessionRegistry


def import_lifecycle(path: Path) -> type[Any]:
    spec = importlib.util.spec_from_file_location("a3_lifecycle_prototype", path)
    if spec is None or spec.loader is None:
        raise MeasurementError("lifecycle_prototype_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.LifecyclePrototype


def verify_inputs(repo: Path, model: Path, audio: Path) -> dict[str, Any]:
    source_revision = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source_path = repo / "moss_transcribe_diarize" / "app" / "speaker_identity.py"
    values = {
        "source_revision": source_revision,
        "source_path": str(source_path),
        "source_sha256": sha256(source_path),
        "model_path": str(model),
        "model_sha256": sha256(model),
        "audio_path": str(audio),
        "audio_sha256": sha256(audio),
    }
    expected = {
        "source_revision": EXPECTED_SOURCE_REVISION,
        "source_sha256": EXPECTED_SOURCE_SHA256,
        "model_sha256": EXPECTED_MODEL_SHA256,
        "audio_sha256": EXPECTED_AUDIO_SHA256,
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise MeasurementError(f"pin_mismatch:{key}")
    return values


def session_settings(embedder: Any) -> dict[str, Any]:
    session = embedder._session
    options = session.get_session_options()
    return {
        "providers": list(session.get_providers()),
        "inter_op_num_threads": int(options.inter_op_num_threads),
        "intra_op_num_threads": int(options.intra_op_num_threads),
    }


def run_embedding_pass(
    embedder: Any,
    *,
    audio: Path,
    duration_seconds: int,
    scratch: Path,
    phase: str,
) -> dict[str, Any]:
    import soundfile as sf

    scratch.mkdir(parents=True, exist_ok=True)
    chunk_path = scratch / "current-chunk.wav"
    chunks: list[dict[str, Any]] = []
    frames_remaining = duration_seconds * SAMPLE_RATE
    rss_before = current_rss_bytes()
    pass_started = time.perf_counter()
    with sf.SoundFile(audio, "r") as source:
        if source.samplerate != SAMPLE_RATE or source.channels != 1:
            raise MeasurementError("audio_format_mismatch")
        if len(source) < frames_remaining:
            raise MeasurementError("audio_duration_short")
        chunk_index = 0
        while frames_remaining:
            requested_frames = min(HARD_CAP_SAMPLES, frames_remaining)
            samples = source.read(
                requested_frames,
                dtype="float32",
                always_2d=False,
            )
            frames_read = int(len(samples))
            if frames_read != requested_frames:
                raise MeasurementError("short_chunk_read")
            sf.write(chunk_path, samples, SAMPLE_RATE, subtype="PCM_16")
            file_bytes = chunk_path.stat().st_size
            io_before = proc_io()
            chunk_started = time.perf_counter()
            embedder.embed(chunk_path, [(0.0, frames_read / SAMPLE_RATE)])
            chunk_wall = time.perf_counter() - chunk_started
            io_after = proc_io()
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "frames": frames_read,
                    "audio_seconds": frames_read / SAMPLE_RATE,
                    "source_pcm_bytes": frames_read * 2,
                    "decoded_array_bytes": int(samples.nbytes),
                    "scratch_wav_bytes": file_bytes,
                    "embed_rchar_delta": io_after["rchar"] - io_before["rchar"],
                    "embed_read_bytes_delta": io_after["read_bytes"] - io_before["read_bytes"],
                    "wall_seconds": chunk_wall,
                    "rss_bytes_after": current_rss_bytes(),
                }
            )
            frames_remaining -= frames_read
            chunk_index += 1
    wall_seconds = time.perf_counter() - pass_started
    chunk_path.unlink(missing_ok=True)
    return {
        "phase": phase,
        "audio_seconds": duration_seconds,
        "wall_seconds": wall_seconds,
        "rtf": wall_seconds / duration_seconds,
        "projected_30m_wall_seconds": wall_seconds / duration_seconds * 1_800,
        "chunk_count": len(chunks),
        "max_chunk_frames": max(item["frames"] for item in chunks),
        "max_chunk_scratch_wav_bytes": max(item["scratch_wav_bytes"] for item in chunks),
        "rss_bytes_before": rss_before,
        "rss_bytes_after": current_rss_bytes(),
        "peak_rss_bytes": peak_rss_bytes(),
        "whole_tape_materialized": False,
        "chunks": chunks,
    }


def duration_worker(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo.resolve()
    model = args.model.resolve()
    audio = args.audio.resolve()
    pins_before = verify_inputs(repo, model, audio)
    speaker, _, _ = import_production(repo)
    embedder = speaker._OnnxWeSpeakerEmbedder(model, device="cpu")
    cold = run_embedding_pass(
        embedder,
        audio=audio,
        duration_seconds=args.worker_duration,
        scratch=args.scratch / f"duration-{args.worker_duration}",
        phase="cold_model_session",
    )
    settings = session_settings(embedder)
    if settings != {
        "providers": ["CPUExecutionProvider"],
        "inter_op_num_threads": 1,
        "intra_op_num_threads": 1,
    }:
        raise MeasurementError("production_session_settings_mismatch")
    warm = run_embedding_pass(
        embedder,
        audio=audio,
        duration_seconds=args.worker_duration,
        scratch=args.scratch / f"duration-{args.worker_duration}",
        phase="warm_reused_model_session",
    )
    pins_after = verify_inputs(repo, model, audio)
    return {
        "schema": SCHEMA,
        "duration_seconds": args.worker_duration,
        "pins_before": pins_before,
        "pins_after": pins_after,
        "session_settings": settings,
        "runs": [cold, warm],
    }


def measure_latencies(operation: Callable[[int], None], repetitions: int) -> dict[str, Any]:
    samples_ms: list[float] = []
    for index in range(repetitions):
        started = time.perf_counter_ns()
        operation(index)
        samples_ms.append((time.perf_counter_ns() - started) / 1_000_000)
    return {
        "count": repetitions,
        "p50_ms": percentile(samples_ms, 0.50),
        "p95_ms": percentile(samples_ms, 0.95),
        "max_ms": max(samples_ms),
        "samples_ms": samples_ms,
    }


def session_probe_factory(LiveSession: type[Any], LiveV2SessionRegistry: type[Any]) -> Callable[[int], None]:
    registry = LiveV2SessionRegistry(max_retained_samples=960_000)

    def probe(index: int) -> None:
        session_id = f"a4-proxy-{index}"
        mono = LiveSession(max_retained_samples=960_000)
        v2 = registry.create(session_id)
        mono.snapshot()
        v2.snapshot()
        registry.release(session_id)

    return probe


def stop_ack_probe(LifecyclePrototype: type[Any]) -> dict[str, Any]:
    def l2_off(index: int) -> None:
        state = {
            "meeting_id": f"off-{index}",
            "state": "closing",
            "capture_authority": True,
        }
        state["capture_authority"] = False
        state["state"] = "closed"

    def l2_on(index: int) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=1)
        meeting_id = f"on-{index}"
        lifecycle.start(meeting_id)
        lifecycle.begin_stop(meeting_id)
        lifecycle.acknowledge_stop(meeting_id)

    off = measure_latencies(l2_off, STOP_ACK_REPETITIONS)
    on = measure_latencies(l2_on, STOP_ACK_REPETITIONS)
    return {
        "proxy": "post-canonical-drain A3 lifecycle transition and bounded enqueue",
        "l2_off": off,
        "l2_on": on,
        "p95_overhead_ms": max(0.0, on["p95_ms"] - off["p95_ms"]),
    }


@dataclass
class FinalizerJob:
    job_id: str
    enqueued_at: float
    result: dict[str, Any] | None = None
    error: str | None = None
    done: threading.Event = field(default_factory=threading.Event)


class SingleFinalizerWorker:
    def __init__(self, operation: Callable[[str], dict[str, Any]], *, capacity: int) -> None:
        self.operation = operation
        self.jobs: queue.Queue[FinalizerJob | None] = queue.Queue(maxsize=capacity)
        self.thread = threading.Thread(target=self._run, name="a4-finalizer", daemon=True)
        self.active_count = 0
        self.max_active_count = 0
        self.active_event = threading.Event()

    def enqueue(self, job_id: str) -> FinalizerJob:
        job = FinalizerJob(job_id=job_id, enqueued_at=time.perf_counter())
        self.jobs.put_nowait(job)
        return job

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.jobs.put(None)
        self.thread.join()

    def _run(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                self.jobs.task_done()
                return
            started = time.perf_counter()
            self.active_count += 1
            self.max_active_count = max(self.max_active_count, self.active_count)
            self.active_event.set()
            try:
                operation_result = self.operation(job.job_id)
                visible_at = time.perf_counter()
                job.result = {
                    "queue_wait_seconds": started - job.enqueued_at,
                    "finalizing_seconds": operation_result["wall_seconds"],
                    "final_visible_revision_seconds": visible_at - job.enqueued_at,
                    "operation": operation_result,
                }
            except Exception as exc:  # diagnosis output must preserve worker failures
                job.error = f"{type(exc).__name__}:{exc}"
            finally:
                self.active_count -= 1
                self.active_event.clear()
                job.done.set()
                self.jobs.task_done()


def contention_probe(
    *,
    repo: Path,
    model: Path,
    audio: Path,
    scratch: Path,
    LiveSession: type[Any],
    LiveV2SessionRegistry: type[Any],
    LifecyclePrototype: type[Any],
) -> dict[str, Any]:
    speaker, _, _ = import_production(repo)
    embedder = speaker._OnnxWeSpeakerEmbedder(model, device="cpu")
    probe = session_probe_factory(LiveSession, LiveV2SessionRegistry)
    no_finalizer = measure_latencies(probe, SESSION_PROBE_REPETITIONS)

    def operation(job_id: str) -> dict[str, Any]:
        return run_embedding_pass(
            embedder,
            audio=audio,
            duration_seconds=25,
            scratch=scratch / f"contention-{job_id}",
            phase=f"contention-{job_id}",
        )

    worker = SingleFinalizerWorker(operation, capacity=2)
    first = worker.enqueue("first")
    lifecycle = LifecyclePrototype(queue_capacity=2)
    lifecycle.start("older-1")
    lifecycle.begin_stop("older-1")
    lifecycle.acknowledge_stop("older-1")
    queued_snapshot = lifecycle.scheduler_snapshot()
    queued_finalizer = measure_latencies(probe, SESSION_PROBE_REPETITIONS)

    worker.start()
    if not worker.active_event.wait(timeout=30.0):
        raise MeasurementError("active_finalizer_start_timeout")
    lifecycle.start_next_finalizer()
    active_snapshot = lifecycle.scheduler_snapshot()
    active_finalizer = measure_latencies(probe, SESSION_PROBE_REPETITIONS)
    second = worker.enqueue("second")

    for job in (first, second):
        if not job.done.wait(timeout=120.0):
            raise MeasurementError(f"finalizer_timeout:{job.job_id}")
        if job.error is not None or job.result is None:
            raise MeasurementError(f"finalizer_failed:{job.job_id}:{job.error}")
    worker.close()
    settings = session_settings(embedder)
    return {
        "new_session_proxy": "production LiveSession plus LiveV2Session creation/snapshot/release",
        "latency": {
            "no_finalizer": no_finalizer,
            "one_queued_finalizer": queued_finalizer,
            "one_active_finalizer": active_finalizer,
        },
        "queued_state": queued_snapshot,
        "active_state": active_snapshot,
        "jobs": [first.result, second.result],
        "measured_max_active_finalizers": worker.max_active_count,
        "queue_capacity": 2,
        "session_settings": settings,
    }


def host_metadata() -> dict[str, Any]:
    cpu_model = ""
    for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    meminfo = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith(("MemTotal:", "SwapTotal:")):
            key, rest = line.split(":", 1)
            meminfo[key] = rest.strip()
    governors = sorted(
        {
            path.read_text(encoding="utf-8").strip()
            for path in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor")
            if path.is_file()
        }
    )
    thermal = []
    for path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        if path.is_file():
            thermal.append({"path": str(path), "millidegrees_c": path.read_text().strip()})
    cgroup_memory_max = Path("/sys/fs/cgroup/memory.max")
    wsl_config = []
    for path in sorted(Path("/mnt/c/Users").glob("*/.wslconfig")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith(("memory=", "swap=", "processors=")):
                wsl_config.append({"path": str(path), "setting": stripped})
    return {
        "captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hostname": os.uname().nodename,
        "kernel": os.uname().release,
        "cpu_model": cpu_model,
        "logical_cpus": os.cpu_count(),
        "governors": governors,
        "thermal_state": thermal if thermal else "unavailable_in_wsl",
        "wsl_memory": {
            "meminfo": meminfo,
            "cgroup_memory_max": cgroup_memory_max.read_text().strip()
            if cgroup_memory_max.is_file()
            else "unavailable",
            "windows_wslconfig_limits": wsl_config if wsl_config else "not_declared_or_unavailable",
        },
        "nice_value": os.nice(0),
    }


def projections(measurements: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for phase in ("cold_model_session", "warm_reused_model_session"):
        result[phase] = [
            {
                "source_audio_seconds": row["duration_seconds"],
                "projected_30m_wall_seconds": next(
                    run["projected_30m_wall_seconds"]
                    for run in row["runs"]
                    if run["phase"] == phase
                ),
            }
            for row in measurements
            if row["duration_seconds"] < 1_800
        ]
    return result


def evaluate_gates(
    measurements: list[dict[str, Any]],
    stop_ack: dict[str, Any],
    contention: dict[str, Any],
) -> dict[str, Any]:
    thirty = next(row for row in measurements if row["duration_seconds"] == 1_800)
    thirty_runs = thirty["runs"]
    max_30m_rtf = max(run["rtf"] for run in thirty_runs)
    max_30m_wall = max(run["wall_seconds"] for run in thirty_runs)
    all_runs = [run for row in measurements for run in row["runs"]]
    max_chunk_frames = max(run["max_chunk_frames"] for run in all_runs)
    contention_p95 = max(
        contention["latency"][state]["p95_ms"]
        for state in ("one_queued_finalizer", "one_active_finalizer")
    )
    gates = [
        {
            "gate": "finalizer_rtf_30m_cold_and_warm",
            "limit": 0.10,
            "actual": max_30m_rtf,
            "pass": max_30m_rtf <= 0.10,
        },
        {
            "gate": "analysis_30m_cold_and_warm_seconds",
            "limit": 180.0,
            "actual": max_30m_wall,
            "pass": max_30m_wall <= 180.0,
        },
        {
            "gate": "no_whole_tape_in_memory_read",
            "limit": HARD_CAP_SAMPLES,
            "actual": max_chunk_frames,
            "pass": max_chunk_frames <= HARD_CAP_SAMPLES
            and all(not run["whole_tape_materialized"] for run in all_runs),
        },
        {
            "gate": "one_active_finalizer_maximum",
            "limit": 1,
            "actual": contention["measured_max_active_finalizers"],
            "pass": contention["measured_max_active_finalizers"] <= 1,
        },
        {
            "gate": "new_session_contention_p95_ms_prototype_proxy",
            "limit": 4_000.0,
            "actual": contention_p95,
            "pass": contention_p95 < 4_000.0,
        },
        {
            "gate": "stop_ack_p95_over_l2_off_ms_prototype_proxy",
            "limit": 100.0,
            "actual": stop_ack["p95_overhead_ms"],
            "pass": stop_ack["p95_overhead_ms"] <= 100.0,
        },
    ]
    return {
        "gates": gates,
        "overall": "PASS" if all(item["pass"] for item in gates) else "BLOCKED",
    }


def orchestrate(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo.resolve()
    model = args.model.resolve()
    audio = args.audio.resolve()
    lifecycle_path = args.lifecycle.resolve()
    scratch = args.scratch.resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    pins_before = verify_inputs(repo, model, audio)
    measurements = []
    for duration in DURATIONS_SECONDS:
        worker_output = scratch / f"duration-{duration}.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--repo",
            str(repo),
            "--model",
            str(model),
            "--audio",
            str(audio),
            "--scratch",
            str(scratch),
            "--worker-duration",
            str(duration),
            "--output",
            str(worker_output),
        ]
        subprocess.run(command, check=True)
        measurements.append(json.loads(worker_output.read_text(encoding="utf-8")))

    _, LiveSession, LiveV2SessionRegistry = import_production(repo)
    LifecyclePrototype = import_lifecycle(lifecycle_path)
    stop_ack = stop_ack_probe(LifecyclePrototype)
    contention = contention_probe(
        repo=repo,
        model=model,
        audio=audio,
        scratch=scratch,
        LiveSession=LiveSession,
        LiveV2SessionRegistry=LiveV2SessionRegistry,
        LifecyclePrototype=LifecyclePrototype,
    )
    verdict = evaluate_gates(measurements, stop_ack, contention)
    pins_after = verify_inputs(repo, model, audio)
    return {
        "schema": SCHEMA,
        "question": (
            "Can one nice'd one-thread production CPU embedder satisfy A4 while the "
            "A3 single-worker prototype preserves responsive acknowledgement/admission?"
        ),
        "measurement_frame": {
            "audio_case": "30m-acquired-jamie-dimon",
            "audio_use": "resource-only exploratory bench audio; no reference read",
            "chunk_samples": HARD_CAP_SAMPLES,
            "chunk_seconds": HARD_CAP_SAMPLES / SAMPLE_RATE,
            "cold_definition": "new production ONNX session; OS page cache uncontrolled",
            "warm_definition": "same production ONNX session immediately reused",
            "rtf_gate_frame": "worst measured cold/warm 30-minute run",
            "lifecycle_metrics": "A3 prototype-frame proxies; Campaign B product gate remains required",
        },
        "host": host_metadata(),
        "pins_before": pins_before,
        "pins_after": pins_after,
        "measurements": measurements,
        "projections": projections(measurements),
        "stop_acknowledgement": stop_ack,
        "contention": contention,
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--lifecycle", type=Path)
    parser.add_argument("--worker-duration", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.worker_duration is not None:
        if args.worker_duration not in DURATIONS_SECONDS:
            raise MeasurementError("unexpected_duration")
        result = duration_worker(args)
    else:
        if args.lifecycle is None:
            raise MeasurementError("lifecycle_path_required")
        result = orchestrate(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": sha256(args.output),
                "verdict": result.get("verdict", {}).get("overall", "worker_complete"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
