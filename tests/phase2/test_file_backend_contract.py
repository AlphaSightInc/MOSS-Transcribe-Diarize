from __future__ import annotations

import io
import threading
import time
import wave
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app import model_runner, runner_composition
from moss_transcribe_diarize.app.inference_scheduler import (
    InferenceDispatchScheduler,
    ScheduledInferenceRunner,
)
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner


def _wav_bytes(seconds: float = 1.0) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x01\x00" * int(seconds * 16_000))
    return output.getvalue()


class _WavAcquirer:
    def __init__(self, payload: bytes):
        self.payload = payload

    async def acquire(self, _source_url: str, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        source = directory / "input.wav"
        source.write_bytes(self.payload)
        return source


def _await_terminal(client: TestClient, meeting_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get(f"/api/meetings/{meeting_id}").json()
        if state["status"] != "active":
            return state
        time.sleep(0.01)
    raise AssertionError("File Meeting did not become terminal")


def _build_hf_runner(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, failure=False):
    calls = []

    def generate(*args, **kwargs):
        calls.append((args, kwargs))
        if failure:
            raise RuntimeError("injected decoder failure")
        return {
            "text": "[0][S01]strict hf product path[1]",
            "prompt_len": 8,
            "generated_tokens": 7,
        }

    monkeypatch.setattr(model_runner, "generate_transcription", generate)
    runner = runner_composition.build_file_runner(
        model_path=tmp_path / "model",
        device="cpu",
        dtype="float32",
        backend="hf",
        vllm_base_url=None,
        vllm_model=None,
        vllm_api_key=None,
        vllm_timeout=30,
    )
    delegate = runner.delegate if isinstance(runner, WindowedRunner) else runner
    delegate._model = object()
    delegate._processor = object()
    return runner, calls


@pytest.mark.parametrize("ingress", ["file", "url"])
def test_strict_hf_file_and_url_complete_with_audio_and_no_checkpoint_io(
    monkeypatch, tmp_path, ingress
):
    runner, calls = _build_hf_runner(monkeypatch, tmp_path)
    payload = _wav_bytes()
    work_root = tmp_path / "file-work"
    app = create_phase2_app(
        database_path=tmp_path / "state.sqlite3",
        file_runner=runner,
        file_work_root=work_root,
        meeting_audio_root=tmp_path / "audio",
        url_acquirer=_WavAcquirer(payload),
    )

    with TestClient(app, base_url="https://moss.test") as client:
        assert client.post("/api/workspace/bootstrap").status_code == 200
        if ingress == "file":
            accepted = client.post(
                "/api/meetings/file",
                files={"file": ("meeting.wav", payload, "audio/wav")},
            )
        else:
            accepted = client.post(
                "/api/meetings/url", json={"url": "https://media.test/meeting.wav"}
            )
        assert accepted.status_code == 201
        meeting_id = accepted.json()["id"]
        completed = _await_terminal(client, meeting_id)

        assert completed["status"] == "completed"
        assert completed["transcript"]["segments"][0]["text"] == "strict hf product path"
        assert completed["audio"]["state"] == "available"
        assert client.get(f"/api/meetings/{meeting_id}/audio/download").status_code == 200

    assert len(calls) == 1
    assert not list(work_root.glob("**/*"))


def test_hf_delegate_failure_is_durable_and_removes_transient_work(monkeypatch, tmp_path):
    runner, calls = _build_hf_runner(monkeypatch, tmp_path, failure=True)
    work_root = tmp_path / "file-work"
    app = create_phase2_app(
        database_path=tmp_path / "state.sqlite3",
        file_runner=runner,
        file_work_root=work_root,
        meeting_audio_root=tmp_path / "audio",
    )

    with TestClient(app, base_url="https://moss.test") as client:
        assert client.post("/api/workspace/bootstrap").status_code == 200
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", _wav_bytes(), "audio/wav")},
        )
        failed = _await_terminal(client, accepted.json()["id"])
        assert failed["status"] == "failed"
        assert failed["failure_code"] == "decode_failed"
        assert failed["transcript"] is None

    assert len(calls) == 1
    assert not list(work_root.glob("**/*"))


def test_hf_cancellation_before_second_window_stops_dispatch_and_publication(
    monkeypatch, tmp_path
):
    started = threading.Event()
    release = threading.Event()
    calls: list[Path] = []

    class BlockingModelRunner:
        model_path = "blocking-hf"
        is_loaded = True

        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(
            self,
            audio_path,
            *,
            prompt="prompt",
            max_length=131_072,
            max_new_tokens=2_048,
            decoding="greedy",
            temperature=None,
            status_callback=None,
        ):
            del prompt, max_length, max_new_tokens, decoding, temperature, status_callback
            calls.append(Path(audio_path))
            started.set()
            assert release.wait(timeout=5)
            return TranscriptionResult(
                text="[0][S01]first window only[1]",
                prompt_len=1,
                generated_tokens=1,
                elapsed_sec=0.0,
                model=self.model_path,
                audio=str(audio_path),
                decoding="greedy",
                temperature=None,
            )

    monkeypatch.setattr(model_runner, "ModelRunner", BlockingModelRunner)
    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    runner = runner_composition.build_file_runner(
        model_path=tmp_path / "model",
        device="cpu",
        dtype="float32",
        backend="hf",
        vllm_base_url=None,
        vllm_model=None,
        vllm_api_key=None,
        vllm_timeout=30,
        inference_scheduler=scheduler,
    )
    assert isinstance(runner, WindowedRunner)
    runner.duration_probe = lambda _path: 300.0
    runner.window_extractor = lambda _source, destination, **_kwargs: Path(destination).write_bytes(
        b"bounded window"
    )
    work_root = tmp_path / "file-work"
    app = create_phase2_app(
        database_path=tmp_path / "state.sqlite3",
        file_runner=runner,
        file_work_root=work_root,
        meeting_audio_root=tmp_path / "audio",
        inference_scheduler=scheduler,
    )

    with TestClient(app, base_url="https://moss.test") as client:
        assert client.post("/api/workspace/bootstrap").status_code == 200
        accepted = client.post(
            "/api/meetings/file",
            files={"file": ("meeting.wav", _wav_bytes(), "audio/wav")},
        )
        meeting_id = accepted.json()["id"]
        assert started.wait(timeout=2)
        entry = app.state.phase2_file_tasks.fence_meeting(meeting_id)
        assert entry is not None
        release.set()
        assert client.portal.call(app.state.phase2_file_tasks.settle_meeting, entry) is True
        interrupted = client.get(f"/api/meetings/{meeting_id}").json()
        assert interrupted["status"] == "interrupted"
        assert interrupted["transcript"] is None
        assert interrupted["audio"]["state"] == "unavailable"

    assert [path.name for path in calls] == ["window-0000.wav"]
    assert not list(work_root.glob("**/*"))


@pytest.mark.parametrize("backend", ["hf", "vllm"])
def test_file_runner_schedules_each_window_beneath_windowing(monkeypatch, tmp_path, backend):
    calls = []

    class Delegate:
        model_path = f"{backend}-delegate"
        is_loaded = True

        def __init__(self, *_args, **_kwargs):
            pass

        def transcribe(self, audio_path, **_kwargs):
            calls.append(Path(audio_path).name)
            return TranscriptionResult(
                text="[0][S01]window[1]",
                prompt_len=1,
                generated_tokens=1,
                elapsed_sec=0.0,
                model=self.model_path,
                audio=str(audio_path),
                decoding="greedy",
                temperature=None,
            )

    if backend == "hf":
        monkeypatch.setattr(model_runner, "ModelRunner", Delegate)
    else:
        from moss_transcribe_diarize.app import vllm_runner

        monkeypatch.setattr(vllm_runner, "VllmRunner", Delegate)
    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    runner = runner_composition.build_file_runner(
        model_path=tmp_path / "model",
        device="cpu",
        dtype="float32",
        backend=backend,
        vllm_base_url="http://unused/v1" if backend == "vllm" else None,
        vllm_model="test" if backend == "vllm" else None,
        vllm_api_key=None,
        vllm_timeout=30,
        file_identity="legacy",
        inference_scheduler=scheduler,
    )
    assert isinstance(runner, WindowedRunner)
    assert isinstance(runner.delegate, ScheduledInferenceRunner)
    runner.duration_probe = lambda _path: 300.0
    runner.window_extractor = lambda _source, destination, **_kwargs: Path(destination).write_bytes(
        b"bounded window"
    )

    result = runner.transcribe(tmp_path / "source.wav", _dispatch_key="meeting-one")

    assert result.completed_windows == 3
    assert calls == ["window-0000.wav", "window-0001.wav", "window-0002.wav"]
    assert scheduler.snapshot().running_calls == 0
    assert scheduler.snapshot().running_background_calls == 0
