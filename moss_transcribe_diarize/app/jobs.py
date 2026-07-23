from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from moss_transcribe_diarize.subtitle import (
    SubtitleSegment,
    SubtitleStyle,
    coerce_subtitle_segments,
    export_ass,
    export_json,
    export_srt,
    subtitle_segments_from_transcript,
    write_text,
)

from .ffmpeg import burn_ass_subtitles, detect_ffmpeg, probe_video_size
from .model_runner import ModelRunner


TERMINAL_STATES = {"waiting_review", "done", "failed", "cancelled"}
STARTUP_RESUMABLE_STATES = {"queued", "loading_model", "transcribing", "postprocessing"}
ACTIVE_STATES = STARTUP_RESUMABLE_STATES | {"rendering"}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


@dataclass(slots=True)
class JobRecord:
    id: str
    status: str
    media_name: str
    input_path: str
    job_dir: str
    inference_prompt: str
    max_length: int
    max_new_tokens: int
    decoding: str
    temperature: float | None
    progress: float = 0.0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    model: str | None = None
    prompt_len: int | None = None
    generated_tokens: int | None = None
    elapsed_sec: float | None = None
    window_count: int | None = None
    completed_windows: int | None = None
    possibly_truncated: bool | None = None
    identity_summary: dict[str, Any] | None = None
    subtitle_style: dict[str, Any] = field(default_factory=dict)
    source_sha256: str | None = None
    checkpoint_dir: str | None = None
    checkpoint_state: str | None = None
    resume_attempts: int = 0

    @property
    def raw_transcript_path(self) -> Path:
        return Path(self.job_dir) / "raw_transcript.txt"

    @property
    def segments_path(self) -> Path:
        return Path(self.job_dir) / "segments.json"

    @property
    def srt_path(self) -> Path:
        return Path(self.job_dir) / "subtitle.srt"

    @property
    def ass_path(self) -> Path:
        return Path(self.job_dir) / "subtitle.ass"

    @property
    def output_path(self) -> Path:
        return Path(self.job_dir) / "output.mp4"

    @property
    def identity_resolution_path(self) -> Path:
        return Path(self.job_dir) / "identity-resolution.json"

    @property
    def job_path(self) -> Path:
        return Path(self.job_dir) / "job.json"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        possibly_truncated = self.possibly_truncated
        if possibly_truncated is None:
            possibly_truncated = (
                self.generated_tokens is not None
                and self.max_new_tokens > 0
                and self.generated_tokens >= self.max_new_tokens
            )
        data["inference"] = {
            "prompt": self.inference_prompt,
            "max_length": self.max_length,
            "max_new_tokens": self.max_new_tokens,
            "decoding": self.decoding,
            "temperature": self.temperature,
        }
        data["usage"] = {
            "prompt_tokens": self.prompt_len,
            "generated_tokens": self.generated_tokens,
            "max_new_tokens": self.max_new_tokens,
            "possibly_truncated": possibly_truncated,
            "elapsed_sec": self.elapsed_sec,
            "window_count": self.window_count,
            "completed_windows": self.completed_windows,
        }
        data["files"] = {
            "raw_transcript": str(self.raw_transcript_path),
            "segments": str(self.segments_path),
            "srt": str(self.srt_path),
            "ass": str(self.ass_path),
            "mp4": str(self.output_path),
            "identity_resolution": str(self.identity_resolution_path),
        }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        inference = data.get("inference") or {}
        usage = data.get("usage") or {}
        temperature = data.get("temperature", inference.get("temperature"))
        return cls(
            id=str(data["id"]),
            status=str(data.get("status") or "failed"),
            media_name=str(data.get("media_name") or "input.media"),
            input_path=str(data.get("input_path") or ""),
            job_dir=str(data.get("job_dir") or ""),
            inference_prompt=str(data.get("inference_prompt") or inference.get("prompt") or ""),
            max_length=int(data.get("max_length") or inference.get("max_length") or 0),
            max_new_tokens=int(data.get("max_new_tokens") or inference.get("max_new_tokens") or 0),
            decoding=str(data.get("decoding") or inference.get("decoding") or "greedy"),
            temperature=None if temperature is None else float(temperature),
            progress=float(data.get("progress") or 0.0),
            error=data.get("error"),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            model=data.get("model"),
            prompt_len=_optional_int(data.get("prompt_len", usage.get("prompt_tokens"))),
            generated_tokens=_optional_int(data.get("generated_tokens", usage.get("generated_tokens"))),
            elapsed_sec=_optional_float(data.get("elapsed_sec", usage.get("elapsed_sec"))),
            window_count=_optional_int(data.get("window_count", usage.get("window_count"))),
            completed_windows=_optional_int(data.get("completed_windows", usage.get("completed_windows"))),
            possibly_truncated=_optional_bool(data.get("possibly_truncated", usage.get("possibly_truncated"))),
            identity_summary=data.get("identity_summary"),
            subtitle_style=dict(data.get("subtitle_style") or {}),
            source_sha256=data.get("source_sha256"),
            checkpoint_dir=data.get("checkpoint_dir"),
            checkpoint_state=data.get("checkpoint_state"),
            resume_attempts=int(data.get("resume_attempts") or 0),
        )


class JobManager:
    def __init__(
        self,
        runs_dir: str | Path,
        model_runner: ModelRunner,
        *,
        prompt: str,
        max_length: int,
        max_new_tokens: int,
        decoding: str = "greedy",
        temperature: float | None = None,
        max_length_cap: int | None = None,
    ):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.model_runner = model_runner
        self.prompt = prompt
        self.max_length = max_length
        self.max_new_tokens = max_new_tokens
        self.max_length_cap = max_length_cap
        self.decoding = decoding
        self.temperature = temperature
        self._jobs: dict[str, JobRecord] = {}
        self._queue: queue.Queue[str] = queue.Queue()
        self._render_lock = threading.Lock()
        self._progress_save_times: dict[str, float] = {}
        startup_resume_ids = self._load_existing_jobs()
        self._worker = threading.Thread(target=self._worker_loop, name="mtd-job-worker", daemon=True)
        self._worker.start()
        for job_id in startup_resume_ids:
            self._queue.put(job_id)

    def create_job_from_file(
        self,
        source_path: str | Path,
        media_name: str | None = None,
        *,
        prompt: str | None = None,
        max_length: int | None = None,
        max_new_tokens: int | None = None,
        decoding: str | None = None,
        temperature: float | None = None,
    ) -> JobRecord:
        options = self._resolve_inference_options(
            prompt=prompt,
            max_length=max_length,
            max_new_tokens=max_new_tokens,
            decoding=decoding,
            temperature=temperature,
        )
        job_id = uuid.uuid4().hex[:12]
        source_path = Path(source_path)
        suffix = source_path.suffix or ".media"
        job_dir = self.runs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        input_path = job_dir / f"input{suffix}"
        shutil.copyfile(source_path, input_path)
        job = JobRecord(
            id=job_id,
            status="queued",
            progress=0.0,
            media_name=media_name or source_path.name,
            input_path=str(input_path),
            job_dir=str(job_dir),
            inference_prompt=options["prompt"],
            max_length=options["max_length"],
            max_new_tokens=options["max_new_tokens"],
            decoding=options["decoding"],
            temperature=options["temperature"],
            model=self.model_runner.model_path,
            source_sha256=_sha256_file(input_path),
            checkpoint_dir=str(job_dir / "checkpoint"),
            checkpoint_state="ready",
        )
        self._jobs[job.id] = job
        self._save_job(job)
        self._queue.put(job.id)
        return job

    def create_upload_transaction(
        self,
        filename: str,
        *,
        prompt: str | None = None,
        max_length: int | None = None,
        max_new_tokens: int | None = None,
        decoding: str | None = None,
        temperature: float | None = None,
    ) -> "UploadTransaction":
        options = self._resolve_inference_options(
            prompt=prompt,
            max_length=max_length,
            max_new_tokens=max_new_tokens,
            decoding=decoding,
            temperature=temperature,
        )
        job_id = uuid.uuid4().hex[:12]
        suffix = Path(filename).suffix or ".media"
        job_dir = self.runs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        input_path = job_dir / f"input{suffix}"
        job = JobRecord(
            id=job_id,
            status="queued",
            progress=0.0,
            media_name=filename,
            input_path=str(input_path),
            job_dir=str(job_dir),
            inference_prompt=options["prompt"],
            max_length=options["max_length"],
            max_new_tokens=options["max_new_tokens"],
            decoding=options["decoding"],
            temperature=options["temperature"],
            model=self.model_runner.model_path,
            checkpoint_dir=str(job_dir / "checkpoint"),
            checkpoint_state="pending",
        )
        return UploadTransaction(self, job, input_path.with_name(f"{input_path.name}.uploading"))

    def enqueue(self, job_id: str) -> None:
        self._ensure_source_metadata(self.get_job(job_id))
        self._queue.put(job_id)

    def abort_unpublished_job(self, job_id: str) -> None:
        job = self._jobs.pop(job_id, None)
        if job is not None:
            shutil.rmtree(job.job_dir, ignore_errors=True)

    def rerun_job(
        self,
        job_id: str,
        *,
        prompt: str | None = None,
        max_length: int | None = None,
        max_new_tokens: int | None = None,
        decoding: str | None = None,
        temperature: float | None = None,
    ) -> JobRecord:
        source = self.get_job(job_id)
        input_path = Path(source.input_path)
        if not input_path.exists():
            raise FileNotFoundError(str(input_path))
        return self.create_job_from_file(
            input_path,
            media_name=source.media_name,
            prompt=source.inference_prompt if prompt is None else prompt,
            max_length=source.max_length if max_length is None else max_length,
            max_new_tokens=source.max_new_tokens if max_new_tokens is None else max_new_tokens,
            decoding=source.decoding if decoding is None else decoding,
            temperature=source.temperature if temperature is None else temperature,
        )

    def resume_job(self, job_id: str) -> JobRecord:
        job = self.get_job(job_id)
        if job.status in ACTIVE_STATES:
            return job
        if job.status in {"waiting_review", "done", "cancelled"}:
            raise RuntimeError(f"Job {job.id} is not resumable from status {job.status}.")
        if job.status != "failed":
            raise RuntimeError(f"Job {job.id} is not resumable from status {job.status}.")
        if not self._runner_accepts_checkpoint():
            raise RuntimeError("This job does not support checkpoint resume.")
        if not job.checkpoint_dir or not job.source_sha256:
            raise RuntimeError("Job has no checkpoint state to resume.")
        if not Path(job.input_path).exists():
            raise FileNotFoundError(str(job.input_path))

        job.resume_attempts += 1
        job.status = "queued"
        job.progress = min(job.progress, 0.84)
        job.error = None
        job.checkpoint_state = "ready"
        job.updated_at = time.time()
        self._save_job(job)
        self._queue.put(job.id)
        return job

    def list_jobs(self) -> list[JobRecord]:
        return sorted(self._jobs.values(), key=lambda job: job.updated_at, reverse=True)

    def get_job(self, job_id: str) -> JobRecord:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Unknown job: {job_id}") from exc

    def delete_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job.status in ACTIVE_STATES:
            raise RuntimeError("Cannot delete a job while it is running.")
        self._jobs.pop(job_id, None)
        shutil.rmtree(job.job_dir, ignore_errors=True)

    def list_segments(self, job_id: str) -> list[dict[str, Any]]:
        job = self.get_job(job_id)
        self._ensure_artifacts_ready(job)
        if not job.segments_path.exists():
            return []
        return json.loads(job.segments_path.read_text(encoding="utf-8"))

    def update_segments(
        self,
        job_id: str,
        payload: list[dict[str, Any]],
        style_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        job = self.get_job(job_id)
        self._ensure_artifacts_ready(job)
        segments = coerce_subtitle_segments(payload)
        style = SubtitleStyle.from_dict(style_payload) if style_payload is not None else None
        if style is not None:
            job.subtitle_style = style.to_dict()
        self._write_subtitle_files(job, segments, style=style)
        if job.status == "done":
            self._set_status(job, "waiting_review", 0.95, error=None)
        else:
            self._touch(job, error=None)
        return [segment.to_dict() for segment in segments]

    def render(self, job_id: str, style_payload: dict[str, Any] | None = None) -> JobRecord:
        job = self.get_job(job_id)
        self._ensure_artifacts_ready(job)
        if not detect_ffmpeg().available:
            raise RuntimeError("ffmpeg and ffprobe are not available on PATH.")
        if not job.segments_path.exists():
            raise RuntimeError("No subtitle segments are available for this job.")
        threading.Thread(
            target=self._render_job,
            args=(job.id, SubtitleStyle.from_dict(style_payload)),
            name=f"mtd-render-{job.id}",
            daemon=True,
        ).start()
        return job

    def download_path(self, job_id: str, kind: str) -> Path:
        job = self.get_job(job_id)
        self._ensure_artifacts_ready(job)
        table = {
            "json": job.segments_path,
            "segments": job.segments_path,
            "srt": job.srt_path,
            "ass": job.ass_path,
            "mp4": job.output_path,
            "transcript": job.raw_transcript_path,
        }
        if kind not in table:
            raise KeyError(f"Unsupported download kind: {kind}")
        path = table[kind]
        if not path.exists():
            raise FileNotFoundError(str(path))
        return path

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._process_job(self.get_job(job_id))
            finally:
                self._queue.task_done()

    def _load_existing_jobs(self) -> list[str]:
        startup_resume_ids: list[str] = []
        for path in sorted(self.runs_dir.glob("*/job.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = JobRecord.from_dict(data)
                if not job.job_dir:
                    job.job_dir = str(path.parent)
                if job.status in STARTUP_RESUMABLE_STATES:
                    self._jobs[job.id] = job
                    if self._prepare_startup_resume(job):
                        startup_resume_ids.append(job.id)
                    continue
                if job.status in {"rendering"}:
                    job.status = "failed"
                    job.progress = 1.0
                    job.error = "Interrupted by previous server shutdown."
                    job.updated_at = time.time()
                    self._save_job(job)
                self._jobs[job.id] = job
            except Exception:
                continue
        return startup_resume_ids

    def _prepare_startup_resume(self, job: JobRecord) -> bool:
        if not Path(job.input_path).exists():
            job.status = "failed"
            job.progress = 1.0
            job.error = "Media file is missing after previous server shutdown."
            job.updated_at = time.time()
            self._save_job(job)
            return False
        if job.status == "postprocessing":
            self._discard_nonterminal_artifacts(job)
        self._ensure_source_metadata(job)
        job.status = "queued"
        job.progress = max(0.0, min(job.progress, 0.84))
        job.error = None
        job.updated_at = time.time()
        self._save_job(job)
        return True

    def _process_job(self, job: JobRecord) -> None:
        try:
            def update(status: str, progress: float | None, generated_tokens: int | None = None) -> None:
                if status == "transcribing" and job.generated_tokens is None:
                    job.generated_tokens = 0
                if generated_tokens is not None:
                    job.generated_tokens = generated_tokens
                save = generated_tokens is None or self._should_save_live_progress(job.id)
                self._set_status(job, status, progress if progress is not None else job.progress, save=save)

            self._ensure_source_metadata(job)
            job.checkpoint_state = "running" if self._runner_accepts_checkpoint() else "unsupported"
            self._save_job(job)
            transcribe_kwargs = {
                "prompt": job.inference_prompt,
                "max_length": job.max_length,
                "max_new_tokens": job.max_new_tokens,
                "decoding": job.decoding,
                "temperature": job.temperature,
                "status_callback": update,
            }
            if job.checkpoint_state == "running":
                transcribe_kwargs["checkpoint_dir"] = job.checkpoint_dir

            result = self.model_runner.transcribe(job.input_path, **transcribe_kwargs)
            job.generated_tokens = result.generated_tokens
            job.window_count = result.window_count
            job.completed_windows = result.completed_windows
            job.possibly_truncated = result.possibly_truncated
            job.identity_summary = result.identity_summary
            self._set_status(job, "postprocessing", 0.85, error=None)
            segments = subtitle_segments_from_transcript(result.text, postprocess=False)
            self._stage_final_artifacts(job, result.text, segments, result.identity_resolution)
            job.prompt_len = result.prompt_len
            job.elapsed_sec = result.elapsed_sec
            if job.checkpoint_state == "running":
                job.checkpoint_state = "complete"
            self._set_status(job, "waiting_review", 0.95, error=None)
            self._progress_save_times.pop(job.id, None)
        except Exception as exc:
            if self._runner_accepts_checkpoint():
                job.checkpoint_state = "failed"
            self._set_status(job, "failed", 1.0, error=str(exc))
            self._progress_save_times.pop(job.id, None)

    def _render_job(self, job_id: str, style: SubtitleStyle) -> None:
        job = self.get_job(job_id)
        with self._render_lock:
            try:
                segments = [SubtitleSegment.from_dict(item) for item in self.list_segments(job.id)]
                self._set_status(job, "rendering", 0.97, error=None)
                width, height = probe_video_size(job.input_path)
                write_text(job.ass_path, export_ass(segments, style=style, video_width=width, video_height=height))
                burn_ass_subtitles(job.input_path, job.ass_path, job.output_path)
                self._set_status(job, "done", 1.0, error=None)
            except Exception as exc:
                self._set_status(job, "waiting_review", 0.95, error=f"Render failed: {exc}")

    def _write_subtitle_files(
        self,
        job: JobRecord,
        segments: list[SubtitleSegment],
        *,
        style: SubtitleStyle | None = None,
        output_dir: Path | None = None,
    ) -> None:
        paths = _artifact_paths(job, output_dir)
        write_text(paths["segments"], export_json(segments))
        if style is None:
            style = SubtitleStyle.from_dict(job.subtitle_style) if job.subtitle_style else SubtitleStyle(font_size=48)
        write_text(
            paths["srt"],
            export_srt(segments, show_speaker=style.show_speaker, speaker_names=style.speaker_names),
            encoding="utf-8-sig",
        )
        width, height = probe_video_size(job.input_path)
        write_text(
            paths["ass"],
            export_ass(segments, style=style, video_width=width, video_height=height),
            encoding="utf-8-sig",
        )

    def _stage_final_artifacts(
        self,
        job: JobRecord,
        transcript: str,
        segments: list[SubtitleSegment],
        identity_resolution: dict[str, Any] | None,
    ) -> None:
        staging_dir = _staging_dir(job)
        shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_paths = _artifact_paths(job, staging_dir)
        _atomic_write_text(staging_paths["raw_transcript"], transcript)
        self._write_subtitle_files(job, segments, output_dir=staging_dir)
        if identity_resolution is not None:
            _atomic_write_text(
                staging_paths["identity_resolution"],
                json.dumps(identity_resolution, ensure_ascii=False, indent=2) + "\n",
            )
        self._validate_staged_artifacts(job, staging_paths, identity_resolution is not None)
        for name, staged_path in staging_paths.items():
            if name == "identity_resolution" and identity_resolution is None:
                job.identity_resolution_path.unlink(missing_ok=True)
                continue
            os.replace(staged_path, _artifact_paths(job)[name])
        shutil.rmtree(staging_dir, ignore_errors=True)

    def _validate_staged_artifacts(
        self,
        job: JobRecord,
        paths: dict[str, Path],
        has_identity_resolution: bool,
    ) -> None:
        required = ["raw_transcript", "segments", "srt", "ass"]
        if has_identity_resolution:
            required.append("identity_resolution")
        for name in required:
            if not paths[name].is_file():
                raise RuntimeError(f"Missing staged artifact: {name}")
        json.loads(paths["segments"].read_text(encoding="utf-8"))
        if has_identity_resolution:
            json.loads(paths["identity_resolution"].read_text(encoding="utf-8"))

    def _discard_nonterminal_artifacts(self, job: JobRecord) -> None:
        shutil.rmtree(_staging_dir(job), ignore_errors=True)
        for path in _artifact_paths(job).values():
            path.unlink(missing_ok=True)

    def _ensure_artifacts_ready(self, job: JobRecord) -> None:
        if job.status not in {"waiting_review", "done"}:
            raise RuntimeError(f"Artifacts are not ready for job status {job.status}.")

    def _set_status(
        self,
        job: JobRecord,
        status: str,
        progress: float,
        *,
        error: str | None = None,
        save: bool = True,
    ) -> None:
        job.status = status
        job.progress = max(0.0, min(1.0, progress))
        self._touch(job, error=error, save=save)

    def _resolve_inference_options(
        self,
        *,
        prompt: str | None,
        max_length: int | None,
        max_new_tokens: int | None,
        decoding: str | None,
        temperature: float | None,
    ) -> dict[str, Any]:
        prompt_value = self.prompt if prompt is None or not prompt.strip() else prompt
        max_length_value = self.max_length if max_length is None else int(max_length)
        max_new_tokens_value = self.max_new_tokens if max_new_tokens is None else int(max_new_tokens)
        decoding_value = decoding or self.decoding
        if decoding_value not in {"greedy", "sample"}:
            raise ValueError("decoding must be greedy or sample.")
        if max_length_value <= 0:
            raise ValueError("max_length must be greater than 0.")
        if self.max_length_cap is not None and max_length_value > self.max_length_cap:
            raise ValueError(f"max_len must be less than or equal to {self.max_length_cap}.")
        if max_new_tokens_value <= 0:
            raise ValueError("max_new_tokens must be greater than 0.")

        temperature_value = self.temperature if temperature is None else float(temperature)
        if decoding_value == "greedy":
            temperature_value = None
        else:
            if temperature_value is None:
                temperature_value = 1.0
            if temperature_value <= 0:
                raise ValueError("temperature must be greater than 0.")

        return {
            "prompt": prompt_value,
            "max_length": max_length_value,
            "max_new_tokens": max_new_tokens_value,
            "decoding": decoding_value,
            "temperature": temperature_value,
        }

    def _touch(self, job: JobRecord, *, error: str | None = None, save: bool = True) -> None:
        job.error = error
        job.updated_at = time.time()
        if save:
            self._save_job(job)

    def _ensure_source_metadata(self, job: JobRecord) -> None:
        changed = False
        if job.checkpoint_dir is None:
            job.checkpoint_dir = str(Path(job.job_dir) / "checkpoint")
            changed = True
        if job.source_sha256 is None:
            job.source_sha256 = _sha256_file(Path(job.input_path))
            changed = True
        if job.checkpoint_state in {None, "pending"}:
            job.checkpoint_state = "ready"
            changed = True
        if changed:
            self._save_job(job)

    def _runner_accepts_checkpoint(self) -> bool:
        return hasattr(self.model_runner, "window_seconds") and hasattr(self.model_runner, "stride_seconds")

    def _save_job(self, job: JobRecord) -> None:
        _atomic_write_json(job.job_path, job.to_dict())

    def _should_save_live_progress(self, job_id: str) -> bool:
        now = time.time()
        last_saved = self._progress_save_times.get(job_id, 0.0)
        if now - last_saved < 0.5:
            return False
        self._progress_save_times[job_id] = now
        return True


class UploadTransaction:
    def __init__(self, manager: JobManager, job: JobRecord, tmp_path: Path):
        self._manager = manager
        self.job = job
        self._input_path = Path(job.input_path)
        self._tmp_path = tmp_path
        self._digest = hashlib.sha256()
        self._byte_count = 0
        self._closed = False
        self._handle: BinaryIO = self._tmp_path.open("wb")

    @property
    def byte_count(self) -> int:
        return self._byte_count

    def write(self, chunk: bytes) -> None:
        if self._closed:
            raise RuntimeError("Upload transaction is closed.")
        written = self._handle.write(chunk)
        if written != len(chunk):
            raise OSError("Short write while storing upload.")
        self._digest.update(chunk)
        self._byte_count += written

    def commit_and_enqueue(self) -> JobRecord:
        if self._closed:
            raise RuntimeError("Upload transaction is closed.")
        try:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()
            self._closed = True
            os.replace(self._tmp_path, self._input_path)
            job = self.job
            job.source_sha256 = self._digest.hexdigest()
            job.checkpoint_state = "ready"
            job.updated_at = time.time()
            self._manager._jobs[job.id] = job
            self._manager._save_job(job)
            self._manager._queue.put(job.id)
            return job
        except Exception:
            self.abort()
            raise

    def abort(self) -> None:
        if not self._closed:
            self._handle.close()
            self._closed = True
        self._manager._jobs.pop(self.job.id, None)
        shutil.rmtree(self.job.job_dir, ignore_errors=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding=encoding) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _staging_dir(job: JobRecord) -> Path:
    return Path(job.job_dir) / ".postprocessing"


def _artifact_paths(job: JobRecord, output_dir: Path | None = None) -> dict[str, Path]:
    if output_dir is None:
        return {
            "raw_transcript": job.raw_transcript_path,
            "segments": job.segments_path,
            "srt": job.srt_path,
            "ass": job.ass_path,
            "identity_resolution": job.identity_resolution_path,
        }
    return {
        "raw_transcript": output_dir / job.raw_transcript_path.name,
        "segments": output_dir / job.segments_path.name,
        "srt": output_dir / job.srt_path.name,
        "ass": output_dir / job.ass_path.name,
        "identity_resolution": output_dir / job.identity_resolution_path.name,
    }
