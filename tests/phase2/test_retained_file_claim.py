"""Product-seam controls for Meeting-owned retained File work."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from _browser_workspace_fixtures import seed_workspace

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import MeetingHandle, Phase2Store, create_phase2_app
from moss_transcribe_diarize.app.phase2_file import (
    FileMeetingTasks,
    RetainedFileWorkBusy,
)
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowTranscriptionError,
    WindowedRunner,
)


class _RestartDecoder:
    model_path = "retained-claim-test-runner"

    def __init__(self) -> None:
        self.calls: list[int] = []
        self.fail_window: int | None = 2
        self.block_window: int | None = None
        self.blocked = threading.Event()
        self.release = threading.Event()

    def transcribe(self, audio_path: str | Path, **_kwargs: object) -> TranscriptionResult:
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if index == self.fail_window:
            raise RuntimeError("controlled restart interruption")
        if index == self.block_window:
            self.blocked.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("controlled startup did not release")
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


class _NoUrlAcquirer:
    def __init__(self) -> None:
        self.calls = 0

    async def acquire(self, *_args: object, **_kwargs: object) -> Path:
        self.calls += 1
        raise AssertionError("retained URL work must not reacquire its source")


def _extract(
    _source: str | Path,
    destination: str | Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    Path(destination).write_text(f"{start_seconds}:{duration_seconds}\n", encoding="utf-8")


def _runner(decoder: _RestartDecoder) -> WindowedRunner:
    return WindowedRunner(
        decoder,
        duration_probe=lambda _source: 390.0,
        window_extractor=_extract,
    )


async def _seed_retained_claim(
    root: Path,
) -> tuple[FileMeetingTasks, object, _RestartDecoder, Path, Phase2Store]:
    store = await Phase2Store.open(root / "state.sqlite3")
    account, _ = await seed_workspace(store, "account-a")
    handle = await store.workspace(account).create_meeting("file")
    decoder = _RestartDecoder()
    runner = _runner(decoder)
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


async def _snapshot(app: object, handle: object) -> object:
    store = app.state.phase2_store  # type: ignore[attr-defined]
    account_id, generation = handle.owner_key  # type: ignore[attr-defined]
    reopened = MeetingHandle(store, account_id, generation, handle.meeting_id)  # type: ignore[attr-defined]
    return await reopened.snapshot()


def _app(
    root: Path,
    decoder: _RestartDecoder,
    *,
    url_acquirer: object | None = None,
):
    return create_phase2_app(
        database_path=root / "state.sqlite3",
        file_runner=_runner(decoder),
        file_work_root=root / "file-work",
        meeting_audio_root=root / "meeting-audio",
        **({"url_acquirer": url_acquirer} if url_acquirer is not None else {}),
    )


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


def test_lifespan_replays_retained_url_only_from_its_local_copy(tmp_path: Path) -> None:
    """C7: product startup uses the retained File source, never reacquisition."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            owner = json.loads((owner_dir / "owner.json").read_text(encoding="utf-8"))
            owner["ingress"] = "url"
            (owner_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
        finally:
            await store.close()

        acquirer = _NoUrlAcquirer()
        app = _app(tmp_path, decoder, url_acquirer=acquirer)
        async with app.router.lifespan_context(app):
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [0, 1, 2, 2, 3]
            assert acquirer.calls == 0
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            assert not owner_dir.exists()

    asyncio.run(exercise())


def test_lifespan_retries_the_uncommitted_window_after_a_prior_crash(tmp_path: Path) -> None:
    """C2: a retained prefix makes the product replay only the interrupted window."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()

        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [0, 1, 2, 2, 3]
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            assert not owner_dir.exists()

    asyncio.run(exercise())


def test_lifespan_refuses_missing_retained_url_copy_without_decoder_dispatch(
    tmp_path: Path,
) -> None:
    """C7 violating arm: no retained local URL source still reaches fallback truth."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        try:
            owner = json.loads((owner_dir / "owner.json").read_text(encoding="utf-8"))
            owner["ingress"] = "url"
            (owner_dir / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
            (owner_dir / "input.wav").unlink()
        finally:
            await store.close()

        acquirer = _NoUrlAcquirer()
        app = _app(tmp_path, decoder, url_acquirer=acquirer)
        async with app.router.lifespan_context(app):
            snapshot = await _snapshot(app, handle)
            assert decoder.calls == [0, 1, 2]
            assert acquirer.calls == 0
            assert snapshot.status == "interrupted"
            assert snapshot.transcript is None
            assert owner_dir.exists()

    asyncio.run(exercise())


def test_account_lifecycle_claims_retained_file_work_before_account_fallback(
    tmp_path: Path,
) -> None:
    """C8: the account-scoped product caller shares the retained-work claim."""

    async def exercise() -> None:
        decoder = _RestartDecoder()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            store = app.state.phase2_store
            account, _ = await seed_workspace(store, "account-a")
            handle = await store.workspace(account).create_meeting("file")
            owner_dir = (
                app.state.phase2_file_tasks.retained_root
                / account.account_id
                / handle.meeting_id
            )
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
            crashed = _RestartDecoder()
            with pytest.raises(WindowTranscriptionError):
                _runner(crashed).transcribe(source, checkpoint_dir=owner_dir / "checkpoint")
            assert crashed.calls == [0, 1, 2]

            assert await app.state.phase2_lifecycle.revoke_account(account.account_id)
            async with store._external_read():
                cursor = await store._connection.execute(
                    "SELECT status, version FROM meetings m "
                    "LEFT JOIN meeting_transcripts t "
                    "ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id "
                    "WHERE m.meeting_id = ?",
                    (handle.meeting_id,),
                )
                row = await cursor.fetchone()
                await cursor.close()
            assert decoder.calls == [2, 3]
            assert tuple(row) == ("completed", 1)
            assert not owner_dir.exists()

    asyncio.run(exercise())


def test_lifespan_refuses_nonresumable_file_and_live_rows_without_dispatch(
    tmp_path: Path,
) -> None:
    """C9/C10: invalid File and every Live row remain the generic fallback's job."""

    async def exercise() -> None:
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            file_handle = await store.workspace(account).create_meeting("file")
            live_handle = await store.workspace(account).create_meeting("live")
        finally:
            await store.close()

        decoder = _RestartDecoder()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        async with app.router.lifespan_context(app):
            file_snapshot = await _snapshot(app, file_handle)
            live_snapshot = await _snapshot(app, live_handle)
            assert decoder.calls == []
            assert file_snapshot.status == "interrupted"
            assert file_snapshot.transcript is None
            assert live_snapshot.status == "interrupted"
            assert live_snapshot.transcript is None

    asyncio.run(exercise())


def test_lifespan_refuses_a_competing_retained_work_owner(tmp_path: Path) -> None:
    """C4: a second real lifespan cannot dispatch or recover the first owner's Meeting."""

    async def exercise() -> None:
        _, handle, decoder, owner_dir, store = await _seed_retained_claim(tmp_path)
        await store.close()
        decoder.block_window = 2
        first = _app(tmp_path, decoder)
        first_context = first.router.lifespan_context(first)
        first_startup = asyncio.create_task(first_context.__aenter__())
        assert await asyncio.to_thread(decoder.blocked.wait, 2)

        competing = _RestartDecoder()
        competing.fail_window = None
        second = _app(tmp_path, competing)
        with pytest.raises(RetainedFileWorkBusy):
            async with second.router.lifespan_context(second):
                pass

        decoder.release.set()
        await first_startup
        try:
            snapshot = await _snapshot(first, handle)
            assert decoder.calls == [0, 1, 2, 2, 3]
            assert competing.calls == []
            assert snapshot.status == "completed"
            assert snapshot.transcript_version == 1
            assert not owner_dir.exists()
        finally:
            await first_context.__aexit__(None, None, None)

    asyncio.run(exercise())
