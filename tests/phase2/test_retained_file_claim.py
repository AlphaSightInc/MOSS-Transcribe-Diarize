"""Product-seam controls for Meeting-owned retained File work."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowTranscriptionError,
    WindowedRunner,
)


class _RestartDecoder:
    model_path = "retained-claim-test-runner"

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail_window: int | None = 2

    def transcribe(self, audio_path: str | Path, **_kwargs: object) -> TranscriptionResult:
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if index == self.fail_window:
            raise RuntimeError("controlled restart interruption")
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
    _source: str | Path,
    destination: str | Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    Path(destination).write_text(f"{start_seconds}:{duration_seconds}\n", encoding="utf-8")


async def _seed_retained_claim(
    root: Path,
) -> tuple[FileMeetingTasks, object, _RestartDecoder, Path, Phase2Store]:
    store = await Phase2Store.open(root / "state.sqlite3")
    account, _ = await seed_workspace(store, "account-a")
    handle = await store.workspace(account).create_meeting("file")
    decoder = _RestartDecoder()
    runner = WindowedRunner(
        decoder,
        duration_probe=lambda _source: 390.0,
        window_extractor=_extract,
    )
    tasks = FileMeetingTasks(runner, root / "file-work")
    owner_dir = tasks.retained_root / account.account_id / handle.meeting_id
    owner_dir.mkdir(parents=True)
    source = owner_dir / "input.wav"
    source.write_bytes(b"retained source")
    (owner_dir / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": "file",
                "source": source.name,
                "checkpoint": "checkpoint",
                "contract_version": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(WindowTranscriptionError):
        runner.transcribe(source, checkpoint_dir=owner_dir / "checkpoint")
    assert decoder.calls == [0, 1, 2]
    decoder.fail_window = None
    return tasks, handle, decoder, owner_dir, store


def test_retained_claim_reuses_only_the_verified_prefix(tmp_path: Path) -> None:
    async def exercise() -> None:
        tasks, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            assert await tasks.claim_retained_work(handle) is True
            await tasks._tasks[handle.meeting_id].task
            assert decoder.calls == [0, 1, 2, 2, 3]
            assert (await handle.snapshot()).status == "completed"
            assert not owner_dir.exists()
        finally:
            await store.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("mutation", ["owner", "source", "contract", "prefix"])
def test_retained_claim_refuses_mutated_owner_source_contract_or_prefix(
    tmp_path: Path,
    mutation: str,
) -> None:
    async def exercise() -> None:
        tasks, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            manifest_path = owner_dir / "owner.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if mutation == "owner":
                manifest["account_id"] = "other-account"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            elif mutation == "source":
                (owner_dir / "input.wav").write_bytes(b"substituted source")
            elif mutation == "contract":
                manifest["contract_version"] = 2
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            else:
                next((owner_dir / "checkpoint" / "windows").glob("w*.json")).unlink()

            assert await tasks.claim_retained_work(handle) is False
            assert decoder.calls == [0, 1, 2]
            assert (await handle.snapshot()).status == "active"
            assert owner_dir.exists()
        finally:
            await store.close()

    asyncio.run(exercise())
