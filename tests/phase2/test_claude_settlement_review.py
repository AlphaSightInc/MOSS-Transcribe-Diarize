"""Claude settlement review (d772f151) -- THROWAWAY controls, not for merge.

Each test asserts what the retained-reservation settlement design / rulings require.
RED on the reviewed SHA = a finding; GREEN = a NO-FINDING receipt. Real lifespan, real
Phase2Store (MOSS_TEST_REAL_SQLITE=1), real MeetingAudioArchive; gates are threading
Events placed *inside* production code paths (archive thread calls, validation thread).
Zero decoder / GPU / network / tunnel calls.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import math
import os
import stat
import struct
import threading
import time
import wave
from pathlib import Path

import pytest

from _browser_workspace_fixtures import seed_workspace
from test_retained_file_claim import _RestartDecoder, _app, _snapshot

from moss_transcribe_diarize.app import phase2_file as phase2_file_module
from moss_transcribe_diarize.app.phase2 import MeetingHandle, Phase2Store
from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive
from moss_transcribe_diarize.app.phase2_control import Phase2ControlServer
from moss_transcribe_diarize.app.phase2_file import (
    RETAINED_FILE_WORK_CONTRACT_VERSION,
    FileMeetingTasks,
)

TREE = Path(__file__).resolve().parents[2]
REFUSED_MANIFEST = {"source_sha256": "0" * 64}  # names neither retained file => refused


def test_imports_the_tree_under_review():
    assert Path(phase2_file_module.__file__).resolve().is_relative_to(TREE)


# --------------------------------------------------------------------------- helpers
def _tone(path: Path, seconds: float = 1.0, rate: int = 16000) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"".join(
            struct.pack("<h", int(4000 * math.sin(2 * math.pi * 330 * n / rate)))
            for n in range(int(seconds * rate))
        ))


def _write_owner(root: Path, account_id: str, meeting_id: str, manifest: object | None) -> Path:
    owner = root / "file-retained" / account_id / meeting_id
    owner.mkdir(parents=True)
    (owner / "input.wav").write_bytes(b"retained source")
    (owner / "checkpoint").mkdir()
    (owner / "owner.json").write_text(json.dumps({
        "account_id": account_id, "meeting_id": meeting_id, "ingress": "file",
        "source": "input.wav", "checkpoint": "checkpoint",
        "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION,
    }, sort_keys=True) + "\n", encoding="utf-8")
    if manifest is not None:
        (owner / "checkpoint" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return owner


async def _seed(root: Path, *, count: int = 1, manifest: object | None = REFUSED_MANIFEST,
                audio: str = "none"):
    store = await Phase2Store.open(root / "state.sqlite3")
    try:
        account, session = await seed_workspace(store, "account-a")
        handles = []
        for _ in range(count):
            handle = await store.workspace(account).create_meeting("file")
            if audio == "available":
                wav = root / f"{handle.meeting_id}.wav"
                _tone(wav)
                published = await handle.publish_audio(MeetingAudioArchive(root / "meeting-audio"), wav)
                assert published.state == "available", published
            handles.append(handle)
    finally:
        await store.close()
    owners = [_write_owner(root, account.account_id, h.meeting_id, manifest) for h in handles]
    return account, session, handles, owners


class _Observer:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def snapshot(self, **kwargs):
        self.events.append(kwargs)
        return {}


async def _control(control: Phase2ControlServer, request: dict) -> str:
    try:
        return f"returned {await control._execute(request)}"
    except Exception as exc:  # noqa: BLE001 - the observed answer is the evidence
        cause = exc.__cause__
        return f"ERROR {type(exc).__name__}: {exc}" + (
            f" (cause {type(cause).__name__}: {cause})" if cause is not None else ""
        )


def _gate_archive(monkeypatch, method: str, gated_calls: int):
    """Hold the first N calls of one archive thread method (between the audio read and write)."""

    original = getattr(MeetingAudioArchive, method)
    entered = [threading.Event() for _ in range(gated_calls)]
    gates = [threading.Event() for _ in range(gated_calls)]
    lock = threading.Lock()
    counter = {"calls": 0}

    def gated(self, *args, **kwargs):
        with lock:
            index = counter["calls"]
            counter["calls"] += 1
        if index < gated_calls:
            entered[index].set()
            if not gates[index].wait(15):
                raise RuntimeError("throwaway gate timed out")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(MeetingAudioArchive, method, gated)
    return entered, gates


def _count_recoveries(monkeypatch):
    original = MeetingHandle.recover_interrupted_file_audio
    callers: list[object] = []

    async def counted(self, archive):
        callers.append(asyncio.current_task())
        return await original(self, archive)

    monkeypatch.setattr(MeetingHandle, "recover_interrupted_file_audio", counted)
    return callers


def _lock_is_free(owner: Path) -> bool | None:
    path = owner / "resume.lock"
    if not path.exists():
        return None
    with path.open("a+") as probe:
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        return True


async def _account_enabled(app, account_id: str) -> int:
    cursor = await app.state.phase2_store._connection.execute(
        "SELECT enabled FROM accounts WHERE account_id = ?", (account_id,)
    )
    enabled = (await cursor.fetchone())["enabled"]
    await cursor.close()
    return enabled


# =========================================================================== S1 / S2
# Fence settlement reconciles audio BEFORE it checks for the claim's own settlement.
@pytest.mark.xfail(strict=True, reason="S1: fence must join claim settlement before audio")
@pytest.mark.parametrize("fence", ["interrupt", "revoke"])
@pytest.mark.parametrize("claim,audio", [("refused", "none"), ("error", "none"), ("refused", "available")])
def test_s1_fence_joining_claim_settlement_reconciles_audio_once_and_answers_truthfully(
    tmp_path, monkeypatch, fence, claim, audio
):
    async def exercise():
        account, _s, (handle,), (owner,) = await _seed(tmp_path, audio=audio)
        if claim == "error":
            monkeypatch.setattr(phase2_file_module, "RETAINED_VALIDATION_BACKOFF_SECONDS", 0.01)

            def failing(_self, _handle, _owner_dir):
                raise OSError("controlled validation I/O failure")

            monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", failing)
        callers = _count_recoveries(monkeypatch)
        # none: read audio() -> discard_unrecorded [gate] -> record_audio_unavailable (write)
        # available: read audio() -> discard_staged [gate] -> resolve -> downgrade (write)
        method = "discard_unrecorded" if audio == "none" else "discard_staged"
        entered, gates = _gate_archive(monkeypatch, method, 2)
        app = _app(tmp_path, _RestartDecoder())
        observer = _Observer()
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            control = Phase2ControlServer(tmp_path / "unused.sock", app.state.phase2_lifecycle, observer)
            assert await asyncio.to_thread(entered[0].wait, 10)      # claim settlement read audio
            reservation = tasks._reservations[handle.meeting_id]
            request = (
                {"command": "meetings.interrupt", "meeting_id": handle.meeting_id}
                if fence == "interrupt"
                else {"command": "accounts.revoke", "account_id": account.account_id}
            )
            answer_task = asyncio.create_task(_control(control, request))
            assert await asyncio.to_thread(entered[1].wait, 10)      # fence settlement read audio
            gates[0].set()                                          # claim settlement finishes first
            await tasks._retained_resume_task
            status_when_fence_resumes = (await _snapshot(app, handle)).status
            gates[1].set()
            answer = await answer_task
            retry = None
            if fence == "revoke":
                retry = await _control(control, request)
            snapshot = await _snapshot(app, handle) if fence == "interrupt" or not answer.startswith(
                "returned") else None
            enabled = await _account_enabled(app, account.account_id)
            order = [
                "fence" if c is reservation.settlement else "claim"
                for c in callers
            ]
        return {
            "answer": answer, "retry": retry,
            "mutation_outcomes": [(e.get("mutation_outcome"), e.get("mutation_error")) for e in observer.events],
            "status_when_fence_resumes": status_when_fence_resumes,
            "durable": None if snapshot is None else (snapshot.status, snapshot.failure_code,
                                                      getattr(snapshot.audio, "state", None)),
            "audio_reconciles": order, "account_enabled": enabled, "owner_exists": owner.exists(),
        }

    result = asyncio.run(exercise())
    print(f"\nS1[{fence},{claim},{audio}] {result}")
    assert result["audio_reconciles"].count("claim") + result["audio_reconciles"].count("fence") == 1, result
    if fence == "interrupt":
        # This call did not durably interrupt anything: the claim's own settlement did.
        assert result["answer"].startswith("returned {'meeting_id'"), result
        assert result["mutation_outcomes"][-1][0] == "no_change", result
    else:
        assert result["answer"].endswith("'revoked': True}"), result
        assert result["account_enabled"] == 0, result


# =========================================================================== S3
# A reservation's settlement task is cached; a later fence re-reads its old result.
@pytest.mark.xfail(strict=True, reason="S3: later calls must not reuse a cached answer")
@pytest.mark.parametrize("first", ["interrupt", "revoke"])
def test_s3_second_fence_after_settlement_reports_what_this_call_did(tmp_path, monkeypatch, first):
    async def exercise():
        account, _s, (handle,), (owner,) = await _seed(tmp_path)
        entered, release = threading.Event(), threading.Event()

        def stalled(_self, _handle, _owner_dir):
            entered.set()
            release.wait(15)
            return None

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", stalled)
        app = _app(tmp_path, _RestartDecoder())
        observer = _Observer()
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            control = Phase2ControlServer(tmp_path / "unused.sock", app.state.phase2_lifecycle, observer)
            assert await asyncio.to_thread(entered.wait, 10)
            interrupt = {"command": "meetings.interrupt", "meeting_id": handle.meeting_id}
            if first == "interrupt":
                one = await _control(control, interrupt)
            else:
                one = await _control(control, {"command": "accounts.revoke", "account_id": account.account_id})
            status_after_one = (await _snapshot(app, handle)).status if first == "interrupt" else "revoked-account"
            still_listed = handle.meeting_id in tasks._reservations
            two = await _control(control, interrupt)
            release.set()
            await tasks._retained_resume_task
            three = await _control(control, interrupt)
        return {
            "first": one, "status_after_first": status_after_one, "listed_during_second": still_listed,
            "second": two, "after_claim_ended": three,
            "mutation_outcomes": [e.get("mutation_outcome") for e in observer.events],
            "owner_exists": owner.exists(),
        }

    result = asyncio.run(exercise())
    print(f"\nS3[{first}] {result}")
    assert "'interrupted': False" in result["second"], result
    assert result["mutation_outcomes"][1] == "no_change", result


# =========================================================================== S4
# stop() while the claim's own settlement is in flight.
@pytest.mark.xfail(strict=True, reason="S4: stop must join or cancel claim settlements")
@pytest.mark.parametrize("how", ["lifespan_exit", "direct_stop"])
def test_s4_stop_joins_or_cancels_the_claim_settlement(tmp_path, monkeypatch, how):
    async def exercise():
        _a, _s, (handle,), (owner,) = await _seed(tmp_path)
        entered, gates = _gate_archive(monkeypatch, "discard_unrecorded", 1)
        app = _app(tmp_path, _RestartDecoder())
        observations: dict = {}
        me = asyncio.current_task()
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            assert await asyncio.to_thread(entered[0].wait, 10)
            before = {t for t in asyncio.all_tasks() if t is not me}
            if how == "direct_stop":
                await tasks.stop()
                pending = [t for t in before if not t.done()]
                observations.update(
                    stop_returned_with_settlement_pending=bool(pending),
                    pending_after_stop=[t.get_coro().__qualname__ for t in pending],
                    listed_after_stop=handle.meeting_id in tasks._reservations,
                    lock_free_after_stop=_lock_is_free(owner),
                    status_when_stop_returned=(await _snapshot(app, handle)).status,
                )
                gates[0].set()
                await asyncio.gather(*pending, return_exceptions=True)
                await asyncio.sleep(0.3)
                late = await _snapshot(app, handle)
                observations.update(status_committed_after_stop=late.status,
                                    owner_removed_after_stop=not owner.exists())
        if how == "lifespan_exit":
            pending = [t for t in before if not t.done()]
            observations.update(
                lifespan_exited_with_settlement_pending=bool(pending),
                pending_after_exit=[t.get_coro().__qualname__ for t in pending],
                listed_after_exit=handle.meeting_id in tasks._reservations,
                lock_free_after_exit=_lock_is_free(owner),
            )
            gates[0].set()
            outcomes = await asyncio.gather(*pending, return_exceptions=True)
            observations["orphan_settlement_outcome"] = [f"{type(o).__name__}: {o}" for o in outcomes]
            store = await Phase2Store.open(tmp_path / "state.sqlite3")
            try:
                account_id, generation = handle.owner_key
                snap = await MeetingHandle(store, account_id, generation, handle.meeting_id).snapshot()
                observations["durable_after_restart_open"] = (snap.status, getattr(snap.audio, "state", None))
            finally:
                await store.close()
            observations["owner_exists"] = owner.exists()
        return observations

    result = asyncio.run(exercise())
    print(f"\nS4[{how}] {result}")
    pending = result.get("stop_returned_with_settlement_pending", result.get("lifespan_exited_with_settlement_pending"))
    assert pending is False, result


# =========================================================================== S5
# Coordinator cancelled before its children's first step (direct API; the lifespan always
# awaits SQLite I/O between resume_retained_work() and any stop()).
@pytest.mark.xfail(strict=True, reason="S5: coordinator exit must unlist and unlock reservations")
@pytest.mark.parametrize("yield_first", [False, True])
def test_s5_coordinator_cannot_end_with_a_listed_reservation(tmp_path, yield_first):
    async def exercise():
        _a, _s, (handle,), (owner,) = await _seed(tmp_path)
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            tasks = FileMeetingTasks(
                object(), tmp_path / "file-work",
                audio_archive=MeetingAudioArchive(tmp_path / "meeting-audio"),
            )
            await tasks.resume_retained_work(store)
            if yield_first:
                await asyncio.sleep(0)   # coordinator creates its children, which have not run yet
            await tasks.stop()
            coordinator = tasks._retained_resume_task
            return {
                "coordinator_done": coordinator.done(), "coordinator_cancelled": coordinator.cancelled(),
                "reservations_left": sorted(tasks._reservations), "lock_free": _lock_is_free(owner),
            }
        finally:
            await store.close()

    result = asyncio.run(exercise())
    print(f"\nS5[yield_first={yield_first}] {result}")
    assert result["coordinator_done"] and not result["reservations_left"], result


# =========================================================================== S6
# Fence landing during the retry backoff: does the loop still start another attempt?
@pytest.mark.xfail(strict=True, reason="S6: no validation may start after a fence")
def test_s6_retry_loop_starts_no_attempt_after_a_fence(tmp_path, monkeypatch):
    async def exercise():
        _a, _s, (handle,), (owner,) = await _seed(tmp_path)
        monkeypatch.setattr(phase2_file_module, "RETAINED_VALIDATION_BACKOFF_SECONDS", 0.5)
        first_failed = threading.Event()
        attempts: list[tuple[float, bool]] = []

        def failing(_self, _handle, owner_dir):
            attempts.append((time.monotonic(), owner_dir.exists()))
            first_failed.set()
            raise OSError("controlled validation I/O failure")

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", failing)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            assert await asyncio.to_thread(first_failed.wait, 10)
            await asyncio.sleep(0.1)                           # claim is now in its backoff sleep
            answer = await app.state.phase2_lifecycle.interrupt_meeting(handle.meeting_id)
            attempts_at_fence = len(attempts)
            await app.state.phase2_file_tasks._retained_resume_task
            status = (await _snapshot(app, handle)).status
        return {"answer": answer, "status": status, "attempts_at_fence": attempts_at_fence,
                "attempts_total": len(attempts), "owner_exists": owner.exists()}

    result = asyncio.run(exercise())
    print(f"\nS6 {result}")
    assert result["answer"] is True and result["status"] == "interrupted"
    assert result["attempts_total"] == result["attempts_at_fence"], result


# =========================================================================== S7
# A reservation fenced while waiting for a bound-4 slot still acquires a slot and validates.
@pytest.mark.xfail(strict=True, reason="S7: fenced reservation must not take a validation slot")
def test_s7_fenced_reservation_waiting_for_a_slot_does_not_take_one(tmp_path, monkeypatch):
    async def exercise():
        _a, _s, handles, owners = await _seed(tmp_path, count=5)
        release = threading.Event()
        lock = threading.Lock()
        started: list[str] = []
        four = threading.Event()

        def stalled(_self, handle, _owner_dir):
            with lock:
                started.append(handle.meeting_id)
                if len(started) == 4:
                    four.set()
            release.wait(15)
            return None

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", stalled)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            assert await asyncio.to_thread(four.wait, 10)
            waiting = [h for h in handles if h.meeting_id not in started]
            assert len(waiting) == 1
            fifth = waiting[0]
            answer = await app.state.phase2_lifecycle.interrupt_meeting(fifth.meeting_id)
            status = (await _snapshot(app, fifth)).status
            release.set()
            await tasks._retained_resume_task
        return {"answer": answer, "status_before_slot": status,
                "fifth_validations": started.count(fifth.meeting_id),
                "fifth_owner_exists": owners[handles.index(fifth)].exists()}

    result = asyncio.run(exercise())
    print(f"\nS7 {result}")
    assert result["answer"] is True and result["status_before_slot"] == "interrupted"
    assert result["fifth_validations"] == 0, result


# =========================================================================== S8
# Claim exception: the refused path's own settlement fails once (transient finish error).
@pytest.mark.xfail(strict=True, reason="S8: failed refused settlement must fall back to failed")
def test_s8_failed_refused_settlement_still_falls_back_to_failed(tmp_path, monkeypatch):
    async def exercise():
        _a, _s, (handle,), (owner,) = await _seed(tmp_path)
        original = MeetingHandle.finish
        calls: list[str] = []

        async def flaky(self, status, **kwargs):
            calls.append(status)
            if status == "interrupted" and calls.count("interrupted") == 1:
                raise RuntimeError("controlled transient outcome write failure")
            return await original(self, status, **kwargs)

        monkeypatch.setattr(MeetingHandle, "finish", flaky)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            await tasks._retained_resume_task
            snapshot = await _snapshot(app, handle)
            listed = handle.meeting_id in tasks._reservations
            probe = await _control(
                Phase2ControlServer(tmp_path / "unused.sock", app.state.phase2_lifecycle, _Observer()),
                {"command": "meetings.interrupt", "meeting_id": handle.meeting_id},
            )
        return {"status": snapshot.status, "code": snapshot.failure_code, "finish_calls": calls,
                "listed": listed, "owner_exists": owner.exists(), "operator_interrupt_after": probe}

    result = asyncio.run(exercise())
    print(f"\nS8 {result}")
    assert result["status"] != "active", result


# =========================================================================== S10 (Q2)
# Ordinary task whose Meeting durably completes just before the operator interrupt.
def test_s10_task_completing_just_before_interrupt_answers_no_change(tmp_path, monkeypatch):
    async def exercise():
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
        finally:
            await store.close()
        original = MeetingHandle.finish
        committed, hold = asyncio.Event(), asyncio.Event()

        async def completes_then_holds(self, status, **kwargs):
            await original(self, status, **kwargs)
            if status == "completed":
                committed.set()
                await hold.wait()          # durable 'completed' is committed; the task is still listed

        monkeypatch.setattr(MeetingHandle, "finish", completes_then_holds)
        decoder = _RestartDecoder()
        decoder.fail_window = None
        app = _app(tmp_path, decoder)
        observer = _Observer()
        source = tmp_path / "upload.wav"
        _tone(source, 2.0)

        class Upload:
            filename = "upload.wav"

            def __init__(self):
                self._stream = source.open("rb")

            async def read(self, size):
                return self._stream.read(size)

        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            handle = await tasks.accept(app.state.phase2_store.workspace(account), Upload())
            await asyncio.wait_for(committed.wait(), 10)
            listed = handle.meeting_id in tasks._tasks
            control = Phase2ControlServer(tmp_path / "unused.sock", app.state.phase2_lifecycle, observer)
            answer = await _control(control, {"command": "meetings.interrupt", "meeting_id": handle.meeting_id})
            snapshot = await _snapshot(app, handle)
            owner = tasks.retained_root / account.account_id / handle.meeting_id
            owner_left = owner.exists()
        return {"listed_when_interrupted": listed, "answer": answer, "durable": snapshot.status,
                "mutation_outcomes": [e.get("mutation_outcome") for e in observer.events],
                "owner_dir_left_after_completed": owner_left}

    result = asyncio.run(exercise())
    print(f"\nS10 {result}")
    assert "'interrupted': False" in result["answer"] and result["durable"] == "completed", result
    assert result["mutation_outcomes"][-1] == "no_change", result


# =========================================================================== S11 (Q2)
# The settlement now removes a reservation's dir after its durable finish; an rmtree error
# turns a durable interruption into a reported failure (the A6 shape: validation returned
# while the fence settlement was reconciling audio).
@pytest.mark.xfail(strict=True, reason="S11: cleanup failure must not fail durable interruption")
@pytest.mark.parametrize("fence", ["interrupt", "revoke"])
def test_s11_unremovable_reservation_dir_after_durable_interrupt_reports_truth(tmp_path, monkeypatch, fence):
    async def exercise():
        account, _s, (handle,), (owner,) = await _seed(tmp_path)
        sealed = owner / "sealed"
        sealed.mkdir()
        (sealed / "leftover.bin").write_bytes(b"x")
        sealed.chmod(stat.S_IRUSR | stat.S_IXUSR)
        entered_v, release_v = threading.Event(), threading.Event()
        original = FileMeetingTasks._verified_retained_resume_source

        def held(self, target, directory):
            entered_v.set()
            release_v.wait(15)
            return original(self, target, directory)

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", held)
        entered, gates = _gate_archive(monkeypatch, "discard_unrecorded", 1)
        app = _app(tmp_path, _RestartDecoder())
        observer = _Observer()
        try:
            async with app.router.lifespan_context(app):
                control = Phase2ControlServer(tmp_path / "unused.sock", app.state.phase2_lifecycle, observer)
                assert await asyncio.to_thread(entered_v.wait, 10)
                request = (
                    {"command": "meetings.interrupt", "meeting_id": handle.meeting_id}
                    if fence == "interrupt"
                    else {"command": "accounts.revoke", "account_id": account.account_id}
                )
                answer_task = asyncio.create_task(_control(control, request))
                assert await asyncio.to_thread(entered[0].wait, 10)   # fence settlement reconciling audio
                release_v.set()                                      # validation returns now
                await app.state.phase2_file_tasks._retained_resume_task
                gates[0].set()
                answer = await answer_task
                durable = (await _snapshot(app, handle)).status
                enabled = await _account_enabled(app, account.account_id)
        finally:
            sealed.chmod(stat.S_IRWXU)
        return {"answer": answer, "durable": durable, "account_enabled": enabled,
                "mutation_outcomes": [(e.get("mutation_outcome"), e.get("mutation_error")) for e in observer.events]}

    result = asyncio.run(exercise())
    print(f"\nS11[{fence}] {result}")
    assert result["answer"].startswith("returned"), result


# =========================================================================== S3b (Q2)
# The cached reservation settlement also re-serves a *failed* settlement: an operator retry
# during the validation window cannot retry.
@pytest.mark.xfail(strict=True, reason="S3b: failed settlement must be retried")
def test_s3b_operator_retry_after_transient_settlement_failure_is_a_real_retry(tmp_path, monkeypatch):
    async def exercise():
        _a, _s, (handle,), (owner,) = await _seed(tmp_path)
        entered, release = threading.Event(), threading.Event()

        def stalled(_self, _handle, _owner_dir):
            entered.set()
            release.wait(15)
            return None

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", stalled)
        original = MeetingHandle.finish
        calls: list[str] = []

        async def flaky(self, status, **kwargs):
            calls.append(status)
            if status == "interrupted" and calls.count("interrupted") == 1:
                raise RuntimeError("controlled transient outcome write failure")
            return await original(self, status, **kwargs)

        monkeypatch.setattr(MeetingHandle, "finish", flaky)
        app = _app(tmp_path, _RestartDecoder())
        observer = _Observer()
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            control = Phase2ControlServer(tmp_path / "unused.sock", app.state.phase2_lifecycle, observer)
            assert await asyncio.to_thread(entered.wait, 10)
            interrupt = {"command": "meetings.interrupt", "meeting_id": handle.meeting_id}
            one = await _control(control, interrupt)
            two = await _control(control, interrupt)          # operator retry, validation still running
            finish_calls_after_retry = list(calls)
            release.set()
            await tasks._retained_resume_task
            three = await _control(control, interrupt)
            status = (await _snapshot(app, handle)).status
        return {"first": one, "retry": two, "finish_calls_after_retry": finish_calls_after_retry,
                "after_claim_ended": three, "status_at_end": status, "owner_exists": owner.exists()}

    result = asyncio.run(exercise())
    print(f"\nS3b {result}")
    assert result["finish_calls_after_retry"].count("interrupted") == 2, result
