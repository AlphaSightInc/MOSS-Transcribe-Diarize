from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from moss_transcribe_diarize.app.jobs import JobManager
from moss_transcribe_diarize.app.model_runner import TranscriptionResult


class InstantRunner:
    model_path = "fake-model"

    def transcribe(self, audio_path, **kwargs):
        callback = kwargs.get("status_callback")
        if callback:
            callback("transcribing", 0.5, 1)
        return TranscriptionResult(
            text="[0][S01]hello[1]",
            prompt_len=3,
            generated_tokens=4,
            elapsed_sec=0.01,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


def make_manager(runs_dir: str | Path) -> JobManager:
    return JobManager(
        runs_dir,
        InstantRunner(),
        prompt="default prompt",
        max_length=123,
        max_new_tokens=9,
    )


def test_upload_transaction_commits_source_metadata_before_job_processing():
    payload = b"first chunk" + b"second chunk"
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = make_manager(tmpdir)
        upload = manager.create_upload_transaction("sample.wav")
        upload.write(payload[:11])
        upload.write(payload[11:])

        job = upload.commit_and_enqueue()
        manager._queue.join()
        finished = manager.get_job(job.id)

        assert Path(finished.input_path).read_bytes() == payload
        assert finished.source_sha256 == hashlib.sha256(payload).hexdigest()
        assert finished.status == "waiting_review"
        assert finished.raw_transcript_path.read_text(encoding="utf-8") == "[0][S01]hello[1]"
        assert finished.job_path.is_file()


def test_upload_transaction_abort_removes_unpublished_job_materials():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = make_manager(tmpdir)
        upload = manager.create_upload_transaction("sample.wav")
        job_id = upload.job.id
        job_dir = Path(upload.job.job_dir)
        upload.write(b"partial")

        upload.abort()

        assert job_id not in manager._jobs
        assert not job_dir.exists()
