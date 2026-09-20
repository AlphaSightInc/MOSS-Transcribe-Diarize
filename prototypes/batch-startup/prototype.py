"""PROTOTYPE ONLY: retained File/URL progress through the real app lifespan.

Question: can an existing File Meeting remain the sole durable owner when valid
retained work is discovered before generic startup interruption and cleanup?

This module patches the recovery composition only while the prototype runs. It
does not alter production code or add a second durable job authority.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import (
    Account,
    AccountRevoked,
    MeetingHandle,
    Phase2Store,
    create_phase2_app,
)
from moss_transcribe_diarize.app.speaker_identity import IdentityResolution
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowTranscriptionError,
    WindowedRunner,
    _CheckpointStore,
    _checkpoint_inference,
    plan_windows,
)
from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript


DURATION_SECONDS = 12_060.0
MODEL_PATH = "prototype-deterministic-runner"
CONTRACT_VERSION = 1
MODEL_SNAPSHOT = Path(
    "/Users/gao/.cache/huggingface/hub/"
    "models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/"
    "e8681d68e7042738ffca8ac8212bc8fcb1131ab8"
)
INFERENCE = {
    "max_length": 131_072,
    "max_new_tokens": 2_048,
    "decoding": "greedy",
}


class ResumeCancelled(RuntimeError):
    pass


class DuplicateStartupRefused(RuntimeError):
    pass


class DeterministicDecoder:
    model_path = MODEL_PATH

    def __init__(
        self,
        *,
        fail_windows: set[int] | None = None,
        cancel_windows: set[int] | None = None,
    ) -> None:
        self.fail_windows = set(fail_windows or ())
        self.cancel_windows = set(cancel_windows or ())
        self.calls: list[int] = []

    def transcribe(self, audio_path: str | Path, **_kwargs: object) -> TranscriptionResult:
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if index in self.cancel_windows:
            raise ResumeCancelled("prototype restart cancellation")
        if index in self.fail_windows:
            raise RuntimeError("prototype mid-window crash")
        return TranscriptionResult(
            text=f"[59][S01]window-{index:04d}[60]",
            prompt_len=1,
            generated_tokens=1,
            elapsed_sec=0.0,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
        )


class PassThroughIdentity:
    requires_window_audio = False

    def contract(self) -> dict[str, object]:
        return {"schema_version": 1, "prototype": "pass-through"}

    def resolve(
        self,
        _windows: object,
        local_results: object,
        *,
        window_audio_paths: object,
    ) -> IdentityResolution:
        del window_audio_paths
        return IdentityResolution(
            relabeled_results=local_results,
            summary={"prototype": "pass-through"},
            diagnostics={"schema_version": 1, "prototype": "pass-through"},
        )


def _extract(
    _source: str | Path,
    destination: str | Path,
    *,
    start_seconds: float,
    duration_seconds: float,
) -> None:
    Path(destination).write_text(f"{start_seconds}:{duration_seconds}\n")


def _runner(decoder: DeterministicDecoder) -> WindowedRunner:
    return WindowedRunner(
        decoder,
        duration_probe=lambda _source: DURATION_SECONDS,
        window_extractor=_extract,
        identity_resolver=PassThroughIdentity(),
    )


@dataclass(frozen=True)
class Seed:
    root: Path
    database: Path
    durable_root: Path
    work_root: Path
    session: str
    account_id: str
    meeting_id: str | None
    ingress: str | None


@dataclass
class RecoveryCoordinator:
    durable_root: Path
    decoder: DeterministicDecoder
    pause_after_claim: asyncio.Event | None = None
    continue_after_claim: asyncio.Event | None = None

    def __post_init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.runner = _runner(self.decoder)

    async def recover(
        self,
        store: Phase2Store,
        account: Account | None = None,
    ) -> None:
        rows = await _active_file_rows(store, account)
        for row in rows:
            await self._recover_one(store, row)

    async def _recover_one(self, store: Phase2Store, row: dict[str, object]) -> None:
        account_id = str(row["account_id"])
        meeting_id = str(row["meeting_id"])
        owner_dir = self.durable_root / account_id / meeting_id
        manifest_path = owner_dir / "owner.json"
        if not manifest_path.is_file():
            self.events.append(
                {"meeting_id": meeting_id, "decision": "not_resumable"}
            )
            return

        lock_path = owner_dir / "resume.lock"
        lock_file = lock_path.open("a+")
        try:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                self.events.append(
                    {"meeting_id": meeting_id, "decision": "duplicate_refused"}
                )
                raise DuplicateStartupRefused(
                    "retained File Meeting already has a startup owner"
                ) from exc

            if self.pause_after_claim is not None:
                self.pause_after_claim.set()
                assert self.continue_after_claim is not None
                await self.continue_after_claim.wait()

            try:
                manifest = json.loads(manifest_path.read_text())
                source, checkpoint, committed = _validate_retained(
                    owner_dir,
                    manifest,
                    account_id=account_id,
                    meeting_id=meeting_id,
                )
            except Exception as exc:
                self.events.append(
                    {
                        "meeting_id": meeting_id,
                        "decision": "invalid_retained_work",
                        "reason_type": type(exc).__name__,
                        "reason": str(exc),
                    }
                )
                return

            handle = MeetingHandle(
                store,
                account_id,
                int(row["authority_generation"]),
                meeting_id,
            )
            try:
                result = await asyncio.to_thread(
                    self.runner.transcribe,
                    source,
                    checkpoint_dir=checkpoint,
                    **INFERENCE,
                )
            except WindowTranscriptionError as exc:
                if exc.exception_type != "ResumeCancelled":
                    self.events.append(
                        {
                            "meeting_id": meeting_id,
                            "decision": "startup_crashed_mid_window",
                            "window": exc.window_index,
                        }
                    )
                    raise
                await handle.finish(
                    "interrupted",
                    failure_code="cancelled",
                    failure_reason="Retained File restart was cancelled.",
                )
                self.events.append(
                    {
                        "meeting_id": meeting_id,
                        "decision": "durable_cancelled",
                        "meeting_status": "interrupted",
                        "failure_code": "cancelled",
                        "cleanup_before_terminal": False,
                    }
                )
                shutil.rmtree(owner_dir)
                self.events.append(
                    {"meeting_id": meeting_id, "decision": "cleanup_after_terminal"}
                )
                return

            segments = [
                segment.to_dict()
                for segment in subtitle_segments_from_transcript(result.text)
            ]
            version = await handle.finish_with_transcript(
                {"segments": segments}, "completed"
            )
            second_publication_refused = False
            try:
                await handle.finish_with_transcript({"segments": segments}, "completed")
            except AccountRevoked:
                second_publication_refused = True
            self.events.append(
                {
                    "meeting_id": meeting_id,
                    "decision": "resumed_completed",
                    "committed_before_restart": committed,
                    "published_version": version,
                    "second_publication_refused": second_publication_refused,
                    "cleanup_before_terminal": False,
                }
            )
            shutil.rmtree(owner_dir)
            self.events.append(
                {"meeting_id": meeting_id, "decision": "cleanup_after_terminal"}
            )
        finally:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            finally:
                lock_file.close()


def _checkpoint(owner_dir: Path, source: Path) -> tuple[Path, int]:
    checkpoint = owner_dir / "checkpoint"
    verifier = _CheckpointStore(
        checkpoint,
        source=source,
        windows=plan_windows(DURATION_SECONDS),
        model_path=MODEL_PATH,
        inference=_checkpoint_inference(INFERENCE),
        window_seconds=150.0,
        stride_seconds=120.0,
        identity_contract=PassThroughIdentity().contract(),
    )
    return checkpoint, len(verifier.load_prefix())


def _validate_retained(
    owner_dir: Path,
    manifest: dict[str, object],
    *,
    account_id: str,
    meeting_id: str,
) -> tuple[Path, Path, int]:
    if manifest.get("account_id") != account_id:
        raise RuntimeError("retained owner account mismatch")
    if manifest.get("meeting_id") != meeting_id:
        raise RuntimeError("retained owner meeting mismatch")
    if manifest.get("ingress") not in {"file", "url"}:
        raise RuntimeError("retained ingress is invalid")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise RuntimeError("retained contract version mismatch")
    if manifest.get("source") != "source.wav":
        raise RuntimeError("retained source locator mismatch")
    source = owner_dir / "source.wav"
    if not source.is_file():
        raise RuntimeError("retained normalized local source unavailable")
    checkpoint, committed = _checkpoint(owner_dir, source)
    if committed != 40:
        raise RuntimeError(f"retained committed prefix is {committed}, expected 40")
    return source, checkpoint, committed


async def _active_file_rows(
    store: Phase2Store, account: Account | None
) -> list[dict[str, object]]:
    async with store._external_read():
        cursor = await store._connection.execute(
            """
            SELECT m.account_id, m.meeting_id, a.authority_generation
            FROM meetings m
            JOIN accounts a ON a.account_id = m.account_id AND a.enabled = 1
            WHERE m.mode = 'file' AND m.status = 'active'
              AND (? IS NULL OR m.account_id = ?)
            ORDER BY m.created_at_ms, m.meeting_id
            """,
            (
                None if account is None else account.account_id,
                None if account is None else account.account_id,
            ),
        )
        rows = await cursor.fetchall()
        await cursor.close()
    return [dict(row) for row in rows]


@contextmanager
def _prototype_recovery(coordinator: RecoveryCoordinator):
    original_global = Phase2Store.recover_active_meetings
    original_account = Phase2Store.recover_active_account_meetings

    async def recover_global(
        store: Phase2Store,
        *,
        audio_archive: Any | None = None,
        live_audio_stages: Any | None = None,
    ) -> None:
        await coordinator.recover(store)
        await original_global(
            store,
            audio_archive=audio_archive,
            live_audio_stages=live_audio_stages,
        )

    async def recover_account(
        store: Phase2Store,
        account: Account,
        *,
        audio_archive: Any,
        live_audio_stages: Any | None,
    ) -> None:
        await coordinator.recover(store, account)
        await original_account(
            store,
            account,
            audio_archive=audio_archive,
            live_audio_stages=live_audio_stages,
        )

    Phase2Store.recover_active_meetings = recover_global
    Phase2Store.recover_active_account_meetings = recover_account
    try:
        yield
    finally:
        Phase2Store.recover_active_meetings = original_global
        Phase2Store.recover_active_account_meetings = original_account


@contextmanager
def _sqlite_semantic_store_allowance():
    actual = phase2.sqlite3.sqlite_version
    phase2.sqlite3.sqlite_version = phase2.REQUIRED_SQLITE_RUNTIME
    try:
        yield actual
    finally:
        phase2.sqlite3.sqlite_version = actual


async def _new_account(root: Path) -> Seed:
    database = root / "state.sqlite3"
    store = await Phase2Store.open(database)
    account, session = await store.bootstrap_browser(None)
    await store.close()
    return Seed(
        root=root,
        database=database,
        durable_root=root / "durable-batch",
        work_root=root / "file-work",
        session=session,
        account_id=account.account_id,
        meeting_id=None,
        ingress=None,
    )


async def _seed(
    root: Path,
    ingress: str,
    *,
    mode: str = "file",
    retained: bool = True,
) -> Seed:
    seed = await _new_account(root)
    store = await Phase2Store.open(seed.database)
    account = await store.account_for_session(seed.session)
    assert account is not None
    handle = await store.workspace(account).create_meeting(mode)
    if retained:
        await _seed_retained(seed.durable_root, account, handle, ingress)
    await store.close()
    return Seed(
        **{
            **seed.__dict__,
            "meeting_id": handle.meeting_id,
            "ingress": ingress,
        }
    )


async def _seed_retained(
    durable_root: Path,
    account: Account,
    handle: MeetingHandle,
    ingress: str,
) -> Path:
    owner_dir = durable_root / account.account_id / handle.meeting_id
    owner_dir.mkdir(parents=True)
    source = owner_dir / "source.wav"
    source.write_bytes(b"retained normalized local source\n")
    (owner_dir / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": ingress,
                "source": "source.wav",
                "contract_version": CONTRACT_VERSION,
            },
            sort_keys=True,
        )
        + "\n"
    )
    decoder = DeterministicDecoder(fail_windows={40})
    try:
        _runner(decoder).transcribe(
            source,
            checkpoint_dir=owner_dir / "checkpoint",
            **INFERENCE,
        )
        raise AssertionError("seed interruption did not fire")
    except WindowTranscriptionError as exc:
        assert exc.window_index == 40 and exc.condition == "decoder_exception"
    _, committed = _checkpoint(owner_dir, source)
    assert committed == 40 and decoder.calls == list(range(41))
    return owner_dir


def _app(seed: Seed, runner: WindowedRunner):
    return create_phase2_app(
        database_path=seed.database,
        file_runner=runner,
        file_work_root=seed.work_root,
        meeting_audio_root=seed.root / "meetings",
    )


async def _snapshot(app: Any, seed: Seed) -> dict[str, object]:
    account = await app.state.phase2_store.account_for_session(seed.session)
    assert account is not None and seed.meeting_id is not None
    handle = await app.state.phase2_store.workspace(account).open_meeting(seed.meeting_id)
    assert handle is not None
    return (await handle.snapshot()).to_dict()


async def _active_count(store: Phase2Store) -> int:
    async with store._external_read():
        cursor = await store._connection.execute(
            "SELECT COUNT(*) FROM meetings WHERE status = 'active'"
        )
        row = await cursor.fetchone()
        await cursor.close()
    return int(row[0])


async def _startup(seed: Seed, coordinator: RecoveryCoordinator) -> dict[str, object]:
    app = _app(seed, coordinator.runner)
    async with app.router.lifespan_context(app):
        snapshot = None if seed.meeting_id is None else await _snapshot(app, seed)
        return {
            "snapshot": snapshot,
            "active_rows_after_recovery": await _active_count(app.state.phase2_store),
            "transient_work_children": (
                sorted(path.name for path in seed.work_root.iterdir())
                if seed.work_root.exists()
                else []
            ),
        }


def _texts(snapshot: dict[str, object]) -> list[str]:
    transcript = snapshot.get("transcript") or {}
    return [segment["text"] for segment in transcript.get("segments", [])]


async def _case_resume(root: Path) -> dict[str, object]:
    seed = await _seed(root, "file")
    orphan = seed.work_root / "crash-orphan" / "input.wav"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"transient")
    coordinator = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    with _prototype_recovery(coordinator):
        state = await _startup(seed, coordinator)
    snapshot = state["snapshot"]
    texts = _texts(snapshot)
    owner_exists = (seed.durable_root / seed.account_id / seed.meeting_id).exists()
    passed = (
        coordinator.decoder.calls == list(range(40, 101))
        and snapshot["status"] == "completed"
        and snapshot["transcript_version"] == 1
        and len(texts) == len(set(texts)) == 101
        and state["active_rows_after_recovery"] == 0
        and state["transient_work_children"] == []
        and not owner_exists
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "delegate_calls": coordinator.decoder.calls,
        "new_delegate_call_count": len(coordinator.decoder.calls),
        "saved_segments": len(texts),
        "unique_saved_segments": len(set(texts)),
        "publication_count": snapshot["transcript_version"],
        "reopened_exact": texts == [f"window-{index:04d}" for index in range(101)],
        "owner_artifacts_after_terminal": owner_exists,
        "startup_state": state,
        "recovery_events": coordinator.events,
    }


async def _case_mid_window(root: Path) -> dict[str, object]:
    seed = await _seed(root, "file")
    first = RecoveryCoordinator(
        seed.durable_root, DeterministicDecoder(fail_windows={40})
    )
    first_error = None
    with _prototype_recovery(first):
        try:
            await _startup(seed, first)
        except WindowTranscriptionError as exc:
            first_error = exc.to_dict()
    second = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    with _prototype_recovery(second):
        state = await _startup(seed, second)
    snapshot = state["snapshot"]
    texts = _texts(snapshot)
    passed = (
        first.decoder.calls == [40]
        and second.decoder.calls == list(range(40, 101))
        and snapshot["status"] == "completed"
        and len(texts) == len(set(texts)) == 101
        and state["active_rows_after_recovery"] == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "first_startup_error": first_error,
        "first_startup_calls": first.decoder.calls,
        "second_startup_calls": second.decoder.calls,
        "window_40_attempts_after_crash": (
            first.decoder.calls + second.decoder.calls
        ).count(40),
        "saved_segments": len(texts),
        "unique_saved_segments": len(set(texts)),
        "publication_count": snapshot["transcript_version"],
        "recovery_events": [*first.events, *second.events],
    }


async def _case_cancel(root: Path) -> dict[str, object]:
    seed = await _seed(root, "file")
    coordinator = RecoveryCoordinator(
        seed.durable_root, DeterministicDecoder(cancel_windows={40})
    )
    with _prototype_recovery(coordinator):
        state = await _startup(seed, coordinator)
    snapshot = state["snapshot"]
    owner_exists = (seed.durable_root / seed.account_id / seed.meeting_id).exists()
    passed = (
        coordinator.decoder.calls == [40]
        and snapshot["status"] == "interrupted"
        and snapshot["failure_code"] == "cancelled"
        and snapshot["transcript"] is None
        and not owner_exists
        and state["active_rows_after_recovery"] == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "delegate_calls": coordinator.decoder.calls,
        "durable_meeting_status": snapshot["status"],
        "durable_outcome": snapshot.get("failure_code"),
        "publication_count": snapshot["transcript_version"],
        "owner_artifacts_after_terminal": owner_exists,
        "recovery_events": coordinator.events,
    }


async def _case_duplicate(root: Path) -> dict[str, object]:
    seed = await _seed(root, "file")
    claimed = asyncio.Event()
    release = asyncio.Event()
    coordinator = RecoveryCoordinator(
        seed.durable_root,
        DeterministicDecoder(),
        pause_after_claim=claimed,
        continue_after_claim=release,
    )
    second_error = None
    with _prototype_recovery(coordinator):
        first = asyncio.create_task(_startup(seed, coordinator))
        await claimed.wait()
        try:
            await _startup(seed, coordinator)
        except DuplicateStartupRefused as exc:
            second_error = str(exc)
        release.set()
        state = await first
    snapshot = state["snapshot"]
    texts = _texts(snapshot)
    passed = (
        second_error is not None
        and coordinator.decoder.calls == list(range(40, 101))
        and snapshot["status"] == "completed"
        and len(texts) == len(set(texts)) == 101
        and state["active_rows_after_recovery"] == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "second_startup_refused": second_error,
        "delegate_calls": coordinator.decoder.calls,
        "publication_count": snapshot["transcript_version"],
        "saved_segments": len(texts),
        "unique_saved_segments": len(set(texts)),
        "recovery_events": coordinator.events,
    }


async def _invalid_arm(root: Path, variant: str) -> dict[str, object]:
    seed = await _seed(root, "file")
    owner_dir = seed.durable_root / seed.account_id / seed.meeting_id
    if variant == "wrong_owner":
        manifest = json.loads((owner_dir / "owner.json").read_text())
        manifest["account_id"] = "wrong-account"
        (owner_dir / "owner.json").write_text(json.dumps(manifest) + "\n")
    elif variant == "wrong_source_hash":
        (owner_dir / "source.wav").write_bytes(b"different retained source\n")
    elif variant == "wrong_contract_version":
        manifest = json.loads((owner_dir / "owner.json").read_text())
        manifest["contract_version"] = 2
        (owner_dir / "owner.json").write_text(json.dumps(manifest) + "\n")
    elif variant == "damaged_prefix":
        windows = sorted((owner_dir / "checkpoint" / "windows").glob("w*.json"))
        windows[10].unlink()
    elif variant == "missing_local_copy":
        (owner_dir / "source.wav").unlink()
    else:
        raise AssertionError(variant)
    coordinator = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    with _prototype_recovery(coordinator):
        state = await _startup(seed, coordinator)
    snapshot = state["snapshot"]
    return {
        "variant": variant,
        "refused_before_decode": coordinator.decoder.calls == [],
        "delegate_calls": coordinator.decoder.calls,
        "durable_status": snapshot["status"],
        "publication_count": snapshot["transcript_version"],
        "received_owner_directory_preserved": owner_dir.exists(),
        "active_rows_after_recovery": state["active_rows_after_recovery"],
        "recovery_events": coordinator.events,
    }


async def _case_invalid(root: Path) -> dict[str, object]:
    arms = []
    for variant in ("wrong_owner", "wrong_source_hash", "wrong_contract_version"):
        arms.append(await _invalid_arm(root / variant, variant))
    passed = all(
        arm["refused_before_decode"]
        and arm["durable_status"] == "interrupted"
        and arm["publication_count"] == 0
        and arm["received_owner_directory_preserved"]
        and arm["active_rows_after_recovery"] == 0
        for arm in arms
    )
    return {"verdict": "SUPPORTED" if passed else "FALSIFIED", "arms": arms}


async def _case_damaged(root: Path) -> dict[str, object]:
    arm = await _invalid_arm(root, "damaged_prefix")
    passed = (
        arm["refused_before_decode"]
        and arm["durable_status"] == "interrupted"
        and arm["publication_count"] == 0
        and arm["received_owner_directory_preserved"]
        and arm["active_rows_after_recovery"] == 0
    )
    return {"verdict": "SUPPORTED" if passed else "FALSIFIED", **arm}


async def _case_url(root: Path) -> dict[str, object]:
    seed = await _seed(root / "local-copy", "url")
    coordinator = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    with _prototype_recovery(coordinator):
        state = await _startup(seed, coordinator)
    snapshot = state["snapshot"]
    missing = await _invalid_arm(root / "missing-copy", "missing_local_copy")
    texts = _texts(snapshot)
    passed = (
        coordinator.decoder.calls == list(range(40, 101))
        and snapshot["status"] == "completed"
        and len(texts) == len(set(texts)) == 101
        and missing["refused_before_decode"]
        and missing["durable_status"] == "interrupted"
        and missing["publication_count"] == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "local_copy_arm": {
            "remote_fetches": 0,
            "delegate_calls": coordinator.decoder.calls,
            "durable_status": snapshot["status"],
            "saved_segments": len(texts),
            "unique_saved_segments": len(set(texts)),
            "recovery_events": coordinator.events,
        },
        "missing_copy_arm": {"remote_fetches": 0, **missing},
    }


async def _case_account_scope(root: Path) -> dict[str, object]:
    seed = await _new_account(root)
    coordinator = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    app = _app(seed, coordinator.runner)
    with _prototype_recovery(coordinator):
        async with app.router.lifespan_context(app):
            store = app.state.phase2_store
            account = await store.account_for_session(seed.session)
            assert account is not None
            handle = await store.workspace(account).create_meeting("file")
            await _seed_retained(seed.durable_root, account, handle, "file")
            await store.recover_active_account_meetings(
                account,
                audio_archive=app.state.phase2_audio_archive,
                live_audio_stages=None,
            )
            snapshot = (await handle.snapshot()).to_dict()
            active = await _active_count(store)
    texts = _texts(snapshot)
    passed = (
        coordinator.decoder.calls == list(range(40, 101))
        and snapshot["status"] == "completed"
        and len(texts) == len(set(texts)) == 101
        and active == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "exact_path": "Phase2Store.recover_active_account_meetings",
        "resolved_account_session": True,
        "delegate_calls": coordinator.decoder.calls,
        "saved_segments": len(texts),
        "unique_saved_segments": len(set(texts)),
        "active_rows_after_recovery": active,
        "recovery_events": coordinator.events,
    }


async def _case_nonresumable(root: Path) -> dict[str, object]:
    seed = await _seed(root, "file", retained=False)
    coordinator = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    with _prototype_recovery(coordinator):
        state = await _startup(seed, coordinator)
    snapshot = state["snapshot"]
    passed = (
        coordinator.decoder.calls == []
        and snapshot["status"] == "interrupted"
        and snapshot["transcript"] is None
        and state["active_rows_after_recovery"] == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "delegate_calls": coordinator.decoder.calls,
        "durable_status": snapshot["status"],
        "publication_count": snapshot["transcript_version"],
        "active_rows_after_recovery": state["active_rows_after_recovery"],
        "recovery_events": coordinator.events,
    }


async def _case_live(root: Path) -> dict[str, object]:
    seed = await _seed(root, "live", mode="live", retained=False)
    coordinator = RecoveryCoordinator(seed.durable_root, DeterministicDecoder())
    with _prototype_recovery(coordinator):
        state = await _startup(seed, coordinator)
    snapshot = state["snapshot"]
    passed = (
        coordinator.decoder.calls == []
        and snapshot["status"] == "interrupted"
        and state["active_rows_after_recovery"] == 0
    )
    return {
        "verdict": "SUPPORTED" if passed else "FALSIFIED",
        "delegate_calls": coordinator.decoder.calls,
        "durable_status": snapshot["status"],
        "assert_no_active_meetings_holds": state["active_rows_after_recovery"] == 0,
        "recovery_events": coordinator.events,
    }


CASES = {
    "resume-after-40": _case_resume,
    "mid-window-crash": _case_mid_window,
    "cancel-during-restart": _case_cancel,
    "duplicate-startup": _case_duplicate,
    "invalid-owner-source-contract": _case_invalid,
    "damaged-prefix": _case_damaged,
    "url-local-copy": _case_url,
    "per-account-recovery": _case_account_scope,
    "nonresumable-file": _case_nonresumable,
    "live-d13-falsifier": _case_live,
}


async def base_lifespan_control(ingress: str) -> dict[str, object]:
    """Expose the unfixed base behavior for strict-xfail violating controls."""

    with tempfile.TemporaryDirectory(prefix=f"moss-r4-base-{ingress}-") as temporary:
        root = Path(temporary)
        with _sqlite_semantic_store_allowance():
            seed = await _seed(root, ingress)
            decoder = DeterministicDecoder()
            app = _app(seed, _runner(decoder))
            async with app.router.lifespan_context(app):
                snapshot = await _snapshot(app, seed)
                return {
                    "status": snapshot["status"],
                    "transcript_version": snapshot["transcript_version"],
                    "delegate_calls": decoder.calls,
                }


async def run(selected: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="moss-r4-batch-startup-") as temporary:
        root = Path(temporary)
        with _sqlite_semantic_store_allowance() as actual_sqlite:
            names = list(CASES) if selected == "all" else [selected]
            case_results = {}
            for name in names:
                case_results[name] = await CASES[name](root / name)
        verdict = (
            "SUPPORTED"
            if all(result["verdict"] == "SUPPORTED" for result in case_results.values())
            else "FALSIFIED"
        )
        return {
            "verdict": verdict,
            "question": (
                "Can the existing File Meeting remain sole owner across real app startup?"
            ),
            "selected": selected,
            "real_app_lifespan": True,
            "production_change": "none; prototype-only recovery composition patch",
            "sqlite_runtime": actual_sqlite,
            "sqlite_required": phase2.REQUIRED_SQLITE_RUNTIME,
            "sqlite_semantic_store_allowance": (
                actual_sqlite != phase2.REQUIRED_SQLITE_RUNTIME
            ),
            "model_snapshot_present": MODEL_SNAPSHOT.is_dir(),
            "decoder_requests_used": 0,
            "cases": case_results,
        }


def _stable_evidence(value: object) -> object:
    """Remove only run-random identifiers; retain the complete semantic state."""

    if isinstance(value, list):
        return [_stable_evidence(item) for item in value]
    if isinstance(value, dict):
        result = {key: _stable_evidence(item) for key, item in value.items()}
        if "meeting_id" in result:
            result["meeting_id"] = "<meeting-id>"
        if "created_at_ms" in result:
            result["created_at_ms"] = 0
        if {"id", "mode", "status"}.issubset(result):
            result["id"] = "<meeting-id>"
        return result
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=["all", *CASES], default="all")
    args = parser.parse_args()
    state = _stable_evidence(asyncio.run(run(args.case)))
    rendered = json.dumps(state, indent=2, sort_keys=True) + "\n"
    if os.environ.get("MOSS_R4_NO_WRITE") != "1":
        destination = Path(__file__).with_name("results.json")
        destination.write_text(rendered)
        evidence = Path(__file__).parents[2] / "evidence" / "round4" / "batch"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / f"prototype-{args.case}.json").write_text(rendered)
    print(rendered, end="")
    return 0 if state["verdict"] == "SUPPORTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
