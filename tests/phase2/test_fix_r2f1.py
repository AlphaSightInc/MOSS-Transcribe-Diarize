"""Review-2 violating controls; no decoder/provider/network calls."""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import MeetingHandle, create_phase2_app
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from moss_transcribe_diarize.app.phase2_audio import (
    MeetingAudioArchive,
    PublishedMeetingAudio,
)
from moss_transcribe_diarize.app.windowed_transcription import _CheckpointStore, WindowedRunner


class _ProcessCrash(BaseException):
    """Abrupt process loss: product Exception cleanup must not consume it."""


def _wav() -> bytes:
    from io import BytesIO

    output = BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x01\x00" * 16_000)
    return output.getvalue()


class _Upload:
    filename = "real-multi-window.wav"

    def __init__(self) -> None:
        self._chunks = [_wav(), b""]

    async def read(self, _size: int) -> bytes:
        await asyncio.sleep(0)
        return self._chunks.pop(0)


class _UrlAcquirer:
    async def acquire(self, _url: str, owner_dir: Path) -> Path:
        await asyncio.sleep(0)
        source = owner_dir / "input.wav"
        source.write_bytes(_wav())
        return source


class _Decoder:
    model_path = "closure-review-2-local"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def transcribe(self, audio_path: str | Path, **_kwargs) -> TranscriptionResult:
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        return TranscriptionResult(
            text=f"[0][S01]window {index}[1]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.0,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


def _extract(
    _source: Path,
    destination: Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    del start_seconds, duration_seconds
    destination.write_bytes(_wav())


class _Archive(MeetingAudioArchive):
    """Deterministic stand-in only for ffmpeg encode/decode."""

    def prepare_mix(
        self,
        _source_path: str | Path,
        destination_path: str | Path,
        *,
        notices: list[str] | None = None,
    ) -> Path:
        del notices
        destination = Path(destination_path)
        destination.write_bytes(_wav())
        return destination

    def publish(
        self,
        account_id: str,
        meeting_id: str,
        source_path: str | Path,
    ) -> PublishedMeetingAudio:
        final = self.root / account_id / meeting_id / "audio.mp3"
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, final)
        return PublishedMeetingAudio(
            path=final,
            relative_path=final.relative_to(self.root).as_posix(),
            byte_count=final.stat().st_size,
            duration_ms=390_000,
        )


def _runner(decoder: _Decoder) -> WindowedRunner:
    return WindowedRunner(
        decoder,
        duration_probe=lambda _source: 390.0,
        window_extractor=_extract,
    )


def _app(root: Path, decoder: _Decoder, *, url_acquirer: object | None = None):
    return create_phase2_app(
        database_path=root / "state.sqlite3",
        file_runner=_runner(decoder),
        file_work_root=root / "file-work",
        file_audio_archive=_Archive(root / "meeting-audio"),
        url_acquirer=url_acquirer or _UrlAcquirer(),
    )


async def _wait_terminal(handle: MeetingHandle) -> object:
    for _ in range(200):
        snapshot = await handle.snapshot()
        if snapshot.status != "active":
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError("File Meeting did not settle")


def _outcome(snapshot: object) -> dict[str, object]:
    audio = None if snapshot.audio is None else snapshot.audio.to_dict()
    if audio is not None and isinstance(audio["relative_path"], str):
        audio["relative_path"] = Path(audio["relative_path"]).name
    return {
        "status": snapshot.status,
        "transcript": snapshot.transcript,
        "transcript_version": snapshot.transcript_version,
        "audio": audio,
        "failure_code": snapshot.failure_code,
        "failure_reason": snapshot.failure_reason,
        "notice": snapshot.notice,
        "needs_review": snapshot.needs_review,
    }


@pytest.mark.parametrize("ingress", ["file", "url"])
@pytest.mark.parametrize("crash_stage", ["transcript_commit", "audio_publish"])
def test_post_publication_await_crash_equals_uninterrupted_meeting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ingress: str,
    crash_stage: str,
) -> None:
    async def exercise() -> None:
        first_decoder = _Decoder()
        app = _app(tmp_path, first_decoder)
        reached = threading.Event()
        release = threading.Event()
        original_commit = MeetingHandle.commit_transcript
        original_publish = MeetingHandle.publish_audio

        async with app.router.lifespan_context(app):
            store = app.state.phase2_store
            account, _ = await seed_workspace(store, "account-a")
            workspace = store.workspace(account)

            reference = await app.state.phase2_file_tasks.accept(workspace, _Upload())
            reference_snapshot = await _wait_terminal(reference)
            assert reference_snapshot.transcript_version == 1

            if crash_stage == "transcript_commit":
                async def crash_after_commit(self, document, *, terminal=False):
                    await original_commit(self, document, terminal=terminal)
                    reached.set()
                    await asyncio.to_thread(release.wait, 5)
                    raise _ProcessCrash()

                monkeypatch.setattr(MeetingHandle, "commit_transcript", crash_after_commit)
            else:
                async def crash_after_publish(self, archive, source_path, **kwargs):
                    await original_publish(self, archive, source_path, **kwargs)
                    reached.set()
                    await asyncio.to_thread(release.wait, 5)
                    raise _ProcessCrash()

                monkeypatch.setattr(MeetingHandle, "publish_audio", crash_after_publish)
            if ingress == "file":
                crashed = await app.state.phase2_file_tasks.accept(workspace, _Upload())
            else:
                crashed = await app.state.phase2_file_tasks.accept_url(
                    workspace,
                    "https://example.test/real-multi-window.wav",
                )
            assert await asyncio.to_thread(reached.wait, 5)
            entry = app.state.phase2_file_tasks._tasks[crashed.meeting_id]
            release.set()
            with pytest.raises(_ProcessCrash):
                await entry.task
            crashed_snapshot = await crashed.snapshot()
            assert crashed_snapshot.status == "active"
            assert crashed_snapshot.transcript_version == 1
            owner_dir = (
                app.state.phase2_file_tasks.retained_root
                / account.account_id
                / crashed.meeting_id
            )
            manifest = json.loads((owner_dir / "owner.json").read_text(encoding="utf-8"))
            assert set(manifest) == {
                "account_id",
                "meeting_id",
                "ingress",
                "source",
                "checkpoint",
                "contract_version",
            }
            assert len(tuple((owner_dir / "checkpoint" / "windows").glob("w*.json"))) == 4

        monkeypatch.setattr(MeetingHandle, "commit_transcript", original_commit)
        monkeypatch.setattr(MeetingHandle, "publish_audio", original_publish)
        restart_decoder = _Decoder()
        restarted = _app(tmp_path, restart_decoder)
        async with restarted.router.lifespan_context(restarted):
            tasks = restarted.state.phase2_file_tasks
            assert tasks._retained_resume_task is not None
            await tasks._retained_resume_task
            entry = tasks._tasks.get(crashed.meeting_id)
            if entry is not None:
                await entry.task
            reopened = MeetingHandle(
                restarted.state.phase2_store,
                account.account_id,
                account.authority_generation,
                crashed.meeting_id,
            )
            resumed_snapshot = await reopened.snapshot()
            assert restart_decoder.calls == []
            assert _outcome(resumed_snapshot) == _outcome(reference_snapshot)

    asyncio.run(exercise())


class _VersionedHandle:
    owner_key = ("account-a", 1)
    meeting_id = "meeting-a"

    def __init__(self, transcript: dict[str, object] | None, version: int) -> None:
        self.transcript = transcript
        self.version = version
        self.commit_calls = 0

    async def snapshot(self) -> object:
        return SimpleNamespace(transcript=self.transcript)

    async def commit_transcript(self, document: dict[str, object]) -> None:
        self.commit_calls += 1
        self.transcript = document
        self.version += 1

    async def record_audio_unavailable(self) -> None:
        return None

    async def finish(self, status: str, **_kwargs: object) -> None:
        assert status == "completed"


def _decoded_result() -> TranscriptionResult:
    return TranscriptionResult(
        text="[0][S01]decoded words[1]",
        prompt_len=1,
        generated_tokens=1,
        elapsed_sec=0.0,
        model="local",
        audio="input.wav",
        decoding="greedy",
        temperature=None,
    )


def test_resumed_different_transcript_commits_exactly_once(tmp_path: Path) -> None:
    async def exercise() -> None:
        old_document = {
            "segments": [
                {
                    "id": "seg_0001",
                    "start": 0.0,
                    "end": 1.0,
                    "speaker": "S01",
                    "text": "older words",
                }
            ]
        }
        expected = {
            "segments": [
                {
                    "id": "seg_0001",
                    "start": 0.0,
                    "end": 1.0,
                    "speaker": "S01",
                    "text": "decoded words",
                }
            ]
        }
        handle = _VersionedHandle(old_document, 1)
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        work_dir = tasks.work_root / "meeting-a"
        work_dir.mkdir(parents=True)

        async def decoded() -> tuple[TranscriptionResult, None, list[str]]:
            return _decoded_result(), None, []

        await tasks._complete(
            handle,
            work_dir / "input.wav",
            asyncio.create_task(decoded()),
            resumed=True,
        )
        assert handle.transcript == expected
        assert handle.commit_calls == 1
        assert handle.version == 2

    asyncio.run(exercise())


def test_non_resumed_path_commits_byte_identical_document_at_version_one(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        expected = {
            "segments": [
                {
                    "id": "seg_0001",
                    "start": 0.0,
                    "end": 1.0,
                    "speaker": "S01",
                    "text": "decoded words",
                }
            ]
        }

        class NewHandle(_VersionedHandle):
            async def snapshot(self) -> object:
                raise AssertionError("non-resumed completion must not inspect prior transcript")

        handle = NewHandle(None, 0)
        tasks = FileMeetingTasks(object(), tmp_path / "file-work")
        work_dir = tasks.work_root / "meeting-a"
        work_dir.mkdir(parents=True)

        async def decoded() -> tuple[TranscriptionResult, None, list[str]]:
            return _decoded_result(), None, []

        await tasks._complete(
            handle,
            work_dir / "input.wav",
            asyncio.create_task(decoded()),
        )
        assert handle.transcript == expected
        assert handle.commit_calls == 1
        assert handle.version == 1

    asyncio.run(exercise())
