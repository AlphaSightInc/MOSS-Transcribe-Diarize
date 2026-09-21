"""Claude fix-wave review (9d8562e7) -- THROWAWAY controls, not for merge.

Every test asserts the behaviour the wave's briefs/rulings require. A failure (RED) on
9d8562e7 is a review finding; a pass is a NO-FINDING receipt. Zero decoder / GPU /
network / tunnel calls: loopback ephemeral HTTP stubs and local ffmpeg only.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import json
import math
import os
import signal
import struct
import subprocess
import sys
import textwrap
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from _browser_workspace_fixtures import seed_workspace
from test_retained_file_claim import _RestartDecoder, _app, _snapshot

from moss_transcribe_diarize.app import phase2_file as phase2_file_module
from moss_transcribe_diarize.app.inference_scheduler import (
    InferenceDispatchScheduler,
    ScheduledInferenceRunner,
)
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import (
    AccountRevoked,
    MeetingHandle,
    Phase2Store,
    create_phase2_app,
)
from moss_transcribe_diarize.app.phase2_file import (
    RETAINED_FILE_WORK_CONTRACT_VERSION,
    FileMeetingTasks,
)
from moss_transcribe_diarize.app.phase2_lifecycle import (
    AccountLifecycleUnavailable,
    MeetingLifecycleSettlementError,
)
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowedRunner,
    _CheckpointStore,
    _checkpoint_inference,
    plan_windows,
)

REPO = Path(__file__).resolve().parents[2]
PRODUCTION_OPTIONS = {
    "prompt": "fix-wave review production-shaped prompt",
    "max_length": 16384,
    "max_new_tokens": 12000,
    "decoding": "greedy",
}


# --------------------------------------------------------------------------- helpers
async def _seed_owner(root: Path, *, manifest: object | None = None, status: str = "active"):
    store = await Phase2Store.open(root / "state.sqlite3")
    try:
        account, session = await seed_workspace(store, "account-a")
        handle = await store.workspace(account).create_meeting("file")
        if status != "active":
            await handle.finish(status)
    finally:
        await store.close()
    owner = root / "file-retained" / account.account_id / handle.meeting_id
    owner.mkdir(parents=True)
    (owner / "input.wav").write_bytes(b"retained source")
    (owner / "checkpoint").mkdir()
    (owner / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": "file",
                "source": "input.wav",
                "checkpoint": "checkpoint",
                "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if manifest is not None:
        (owner / "checkpoint" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
    return account, session, handle, owner


def _tree(root: Path) -> dict[str, tuple]:
    if not root.exists():
        return {}
    listing = {".": (True, root.stat().st_mtime_ns)}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        listing[str(path.relative_to(root))] = (
            path.is_dir(),
            stat.st_size,
            stat.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return listing


# =========================================================================== A. resume path
CHILD = textwrap.dedent(
    r'''
    import asyncio, json, sys, threading
    from pathlib import Path
    root, k, src = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    from moss_transcribe_diarize.app.phase2 import Phase2Store
    from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
    from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive
    from moss_transcribe_diarize.app.inference_scheduler import (
        InferenceDispatchScheduler, ScheduledInferenceRunner)
    from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner
    from moss_transcribe_diarize.app.model_runner import TranscriptionResult
    OPTIONS = json.loads(sys.argv[4])

    class Decoder:
        model_path = "fixwave-review-decoder"
        def transcribe(self, audio_path, **kwargs):
            index = int(Path(audio_path).stem.rsplit("-", 1)[1])
            with (root / "child-calls.jsonl").open("a") as out:
                out.write(json.dumps({"index": index, "kwargs": sorted(kwargs)}) + "\n")
            if index == k:
                (root / "blocked").write_text("1")
                threading.Event().wait()
            return TranscriptionResult(
                text=f"[1][S01]window {index} words[5]", prompt_len=1, generated_tokens=5,
                elapsed_sec=0.0, model=self.model_path, audio=str(audio_path),
                decoding="greedy", temperature=None)

    class Upload:
        filename = "upload.wav"
        def __init__(self, path):
            self._stream = path.open("rb")
        async def read(self, size):
            return self._stream.read(size)

    async def main():
        store = await Phase2Store.open(root / "state.sqlite3")
        account, session = await store.bootstrap_browser(None)
        scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
        runner = WindowedRunner(ScheduledInferenceRunner(Decoder(), scheduler, kind="background"))
        tasks = FileMeetingTasks(
            runner, root / "file-work", **OPTIONS,
            audio_archive=MeetingAudioArchive(root / "meeting-audio"),
            inference_scheduler=scheduler)
        handle = await tasks.accept(store.workspace(account), Upload(src))
        (root / "child.json").write_text(json.dumps({
            "session": session, "meeting_id": handle.meeting_id,
            "account_id": account.account_id}))
        await asyncio.Event().wait()

    asyncio.run(main())
    '''
)


class _ParentDecoder:
    model_path = "fixwave-review-decoder"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def transcribe(self, audio_path, **_kwargs):
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        return TranscriptionResult(
            text=f"[1][S01]window {index} words[5]", prompt_len=1, generated_tokens=5,
            elapsed_sec=0.0, model=self.model_path, audio=str(audio_path),
            decoding="greedy", temperature=None,
        )


class _Upload:
    filename = "upload.wav"

    def __init__(self, path: Path) -> None:
        self._stream = path.open("rb")

    async def read(self, size: int) -> bytes:
        return self._stream.read(size)


def _write_stereo_tone(path: Path, seconds: int, rate: int = 8000) -> None:
    frame = []
    for n in range(rate):
        value = int(3000 * math.sin(2 * math.pi * 220 * n / rate)) + (n % 7) - 3
        frame.append(struct.pack("<hh", value, -value // 2))
    second = b"".join(frame)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        for _ in range(seconds):
            out.writeframes(second)


def _gated_audio_recovery(monkeypatch, gated_calls: int):
    original = MeetingHandle.recover_interrupted_file_audio
    entered = [asyncio.Event() for _ in range(gated_calls)]
    gates = [asyncio.Event() for _ in range(gated_calls)]
    counter = {"calls": 0}

    async def gated(self, archive):
        index = counter["calls"]
        counter["calls"] += 1
        if index < gated_calls:
            entered[index].set()
            await gates[index].wait()
        return await original(self, archive)

    monkeypatch.setattr(MeetingHandle, "recover_interrupted_file_audio", gated)
    return entered, gates, counter


REFUSED_MANIFEST = {"source_sha256": "0" * 64}  # names neither retained file => refused


@pytest.mark.xfail(strict=True, reason="A2: fence must join the claim's refused settlement")
def test_a2_operator_interrupt_during_refused_reservation_settlement_reports_truth(tmp_path, monkeypatch):
    """Fence lands while the claim's own refused path is settling (reservation still listed)."""

    async def exercise():
        _account, _session, handle, owner = await _seed_owner(tmp_path, manifest=REFUSED_MANIFEST)
        entered, gates, counter = _gated_audio_recovery(monkeypatch, 2)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(entered[0].wait(), 5)       # claim: _interrupt_refused_reservation
            interrupt = asyncio.create_task(app.state.phase2_lifecycle.interrupt_meeting(handle.meeting_id))
            await asyncio.wait_for(entered[1].wait(), 5)       # fence settlement saw status=active
            gates[0].set()                                     # claim finishes first
            await app.state.phase2_file_tasks._retained_resume_task
            gates[1].set()
            try:
                outcome = f"returned {await interrupt}"
            except MeetingLifecycleSettlementError as exc:
                outcome = f"ERROR {type(exc).__name__}: {exc} (cause {type(exc.__cause__).__name__})"
            snapshot = await _snapshot(app, handle)
        return outcome, snapshot.status, counter["calls"], owner.exists()

    outcome, status, recoveries, owner_exists = asyncio.run(exercise())
    print(f"\nA2 interrupt outcome={outcome!r} durable_status={status} audio_recoveries={recoveries} owner_exists={owner_exists}")
    assert status == "interrupted"
    assert not outcome.startswith("ERROR"), outcome


@pytest.mark.xfail(strict=True, reason="A3: revoke must join the claim's refused settlement")
def test_a3_account_revoke_during_refused_reservation_settlement_completes(tmp_path, monkeypatch):
    async def exercise():
        account, _session, handle, owner = await _seed_owner(tmp_path, manifest=REFUSED_MANIFEST)
        entered, gates, _counter = _gated_audio_recovery(monkeypatch, 2)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            lifecycle = app.state.phase2_lifecycle
            await asyncio.wait_for(entered[0].wait(), 5)
            revoke = asyncio.create_task(lifecycle.revoke_account(account.account_id))
            await asyncio.wait_for(entered[1].wait(), 5)
            gates[0].set()
            await app.state.phase2_file_tasks._retained_resume_task
            gates[1].set()
            try:
                first = f"returned {await revoke}"
            except Exception as exc:  # noqa: BLE001 - the observed failure is the finding
                first = f"ERROR {type(exc).__name__}: {exc}"
            try:
                second = f"returned {await lifecycle.revoke_account(account.account_id)}"
            except Exception as exc:  # noqa: BLE001
                second = f"ERROR {type(exc).__name__}: {exc}"
            cursor = await app.state.phase2_store._connection.execute(
                "SELECT enabled FROM accounts WHERE account_id = ?", (account.account_id,)
            )
            enabled = (await cursor.fetchone())["enabled"]
            await cursor.close()
        return first, second, enabled

    first, second, enabled = asyncio.run(exercise())
    print(f"\nA3 first revoke={first!r} retry={second!r} account_enabled_after={enabled}")
    assert first == "returned True", first


@pytest.mark.xfail(strict=True, reason="A4: fenced validation error must reclaim in the same boot")
def test_a4_fenced_reservation_whose_validation_then_errors_is_reclaimed_same_boot(tmp_path, monkeypatch):
    """S1 ruling: an interrupted stalled owner's dir is removed once its validation returns."""

    async def exercise():
        _account, _session, handle, owner = await _seed_owner(tmp_path)
        monkeypatch.setattr(phase2_file_module, "RETAINED_VALIDATION_BACKOFF_SECONDS", 0.01)
        entered, release = threading.Event(), threading.Event()
        attempts: list[float] = []

        def stalled_then_failing(_self, _handle, _owner_dir):
            attempts.append(time.monotonic())
            if len(attempts) == 1:
                entered.set()
                release.wait(5)
            raise OSError("controlled validation I/O failure")

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", stalled_then_failing)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            assert await asyncio.to_thread(entered.wait, 5)
            honoured = await app.state.phase2_lifecycle.interrupt_meeting(handle.meeting_id)
            release.set()
            await app.state.phase2_file_tasks._retained_resume_task
            snapshot = await _snapshot(app, handle)
            survived = owner.exists()
        return honoured, snapshot.status, snapshot.failure_code, len(attempts), survived

    honoured, status, code, attempts, survived = asyncio.run(exercise())
    print(f"\nA4 interrupt honoured={honoured} status={status}/{code} validation_attempts={attempts} owner_dir_survived_boot={survived}")
    assert honoured is True and status == "interrupted"
    assert survived is False, "fenced owner dir must be removed once its validation thread returned"


@pytest.mark.xfail(strict=True, reason="A6: reclaim must await validation and settlement")
def test_a6_validation_returning_while_fence_settlement_is_in_flight_still_reclaims(tmp_path, monkeypatch):
    """The claim's post-validation removal does not wait for an in-flight fence settlement,
    and the settlement itself never removes a reservation's directory."""

    async def exercise():
        _account, _session, handle, owner = await _seed_owner(tmp_path)
        entered_v, release_v = threading.Event(), threading.Event()
        original = FileMeetingTasks._verified_retained_resume_source

        def held(self, target, directory):
            entered_v.set()
            release_v.wait(5)
            return original(self, target, directory)

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", held)
        entered, gates, _counter = _gated_audio_recovery(monkeypatch, 1)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            assert await asyncio.to_thread(entered_v.wait, 5)
            interrupt = asyncio.create_task(app.state.phase2_lifecycle.interrupt_meeting(handle.meeting_id))
            await asyncio.wait_for(entered[0].wait(), 5)        # settlement reconciling audio
            release_v.set()                                      # validation returns now
            await app.state.phase2_file_tasks._retained_resume_task
            gates[0].set()
            honoured = await interrupt
            status = (await _snapshot(app, handle)).status
            survived = owner.exists()
            reservations = dict(app.state.phase2_file_tasks._reservations)
        return honoured, status, survived, reservations

    honoured, status, survived, reservations = asyncio.run(exercise())
    print(f"\nA6 interrupt honoured={honoured} status={status} owner_dir_survived_boot={survived} reservations_left={reservations}")
    assert honoured is True and status == "interrupted"
    assert survived is False


@pytest.mark.xfail(strict=True, reason="A7: resumed input failure must retain transcode_failed parity")
def test_a7_input_bound_resume_failure_keeps_the_fresh_run_failure_code(tmp_path):
    """Fresh run: mix failed -> decoder failure is `transcode_failed`. The resumed
    input-bound run skips prepare_mix, so the same failure becomes `decode_failed`."""

    class FailingMixArchive:
        root = tmp_path / "meeting-audio"

        def prepare_mix(self, _source, destination, *, notices):
            raise RuntimeError("controlled transcode failure")

        def discard_staged(self, *_args):
            return None

        def discard_unrecorded(self, *_args):
            return None

    class Decoder:
        model_path = "a7-decoder"

        def __init__(self, fail_at):
            self.fail_at = fail_at

        def transcribe(self, audio_path, **_kwargs):
            index = int(Path(audio_path).stem.rsplit("-", 1)[1])
            if index == self.fail_at:
                raise RuntimeError("controlled decoder failure")
            return TranscriptionResult(text=f"[1][S01]w{index}[2]", prompt_len=1, generated_tokens=1,
                                       elapsed_sec=0.0, model=self.model_path, audio=str(audio_path),
                                       decoding="greedy", temperature=None)

    def runner(decoder):
        return WindowedRunner(decoder, duration_probe=lambda _s: 390.0,
                              window_extractor=lambda _s, d, **_k: Path(d).write_text("w\n"))

    async def exercise():
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            fresh = await store.workspace(account).create_meeting("file")
            resumed = await store.workspace(account).create_meeting("file")
            # Fresh run: mix fails, decoder fails at window 2 (after committing 0-1).
            decoder = Decoder(fail_at=2)
            tasks = FileMeetingTasks(runner(decoder), tmp_path / "file-work", audio_archive=FailingMixArchive())
            fresh_dir = tasks.retained_root / account.account_id / fresh.meeting_id
            fresh_dir.mkdir(parents=True)
            (fresh_dir / "input.wav").write_bytes(b"retained source")
            await tasks._run(fresh, fresh_dir / "input.wav", asyncio.Event())
            # Resumed run: identical crash state (input-bound prefix 0-1), restart fails at window 2.
            owner = tasks.retained_root / account.account_id / resumed.meeting_id
            owner.mkdir(parents=True)
            (owner / "input.wav").write_bytes(b"retained source")
            (owner / "owner.json").write_text(json.dumps({
                "account_id": account.account_id, "meeting_id": resumed.meeting_id, "ingress": "file",
                "source": "input.wav", "checkpoint": "checkpoint", "contract_version": 1}), encoding="utf-8")
            try:
                tasks._transcribe_from_one_mix(owner / "input.wav", {})
            except Exception:
                pass
            assert len(list((owner / "checkpoint" / "windows").glob("w*.json"))) == 2
            assert await tasks.claim_retained_work(resumed) is True
            await tasks._tasks[resumed.meeting_id].task
            return (await fresh.snapshot()).failure_code, (await resumed.snapshot()).failure_code
        finally:
            await store.close()

    fresh_code, resumed_code = asyncio.run(exercise())
    print(f"\nA7 fresh failure_code={fresh_code} resumed(input-bound) failure_code={resumed_code}")
    assert fresh_code == resumed_code


@pytest.mark.xfail(strict=True, reason="A8: unbound restart must validate nothing and run fresh")
def test_a8_unbound_restart_of_a_streamed_webm_matches_a_fresh_run(tmp_path, monkeypatch):
    """R1 rule: an unbound checkpoint (every single-window File) resumes exactly like a fresh
    run. Production probes the *input* container during validation; a streamed WebM (the
    MediaRecorder shape) has no container duration although ffmpeg decodes it to a mix."""

    monkeypatch.setattr(phase2_file_module, "RETAINED_VALIDATION_BACKOFF_SECONDS", 0.01)
    webm = tmp_path / "streamed.webm"
    with webm.open("wb") as output:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=100",
             "-c:a", "libopus", "-f", "webm", "pipe:1"],
            stdout=output, check=True,
        )

    class Decoder:
        model_path = "a8-decoder"

        def __init__(self):
            self.calls = 0

        def transcribe(self, audio_path, **_kwargs):
            self.calls += 1
            return TranscriptionResult(text="[1][S01]tone words[5]", prompt_len=1, generated_tokens=3,
                                       elapsed_sec=0.0, model=self.model_path, audio=str(audio_path),
                                       decoding="greedy", temperature=None)

    async def exercise():
        _account, session, handle, owner = await _seed_owner(tmp_path)
        (owner / "input.wav").unlink()
        (owner / "input.webm").write_bytes(webm.read_bytes())
        manifest = json.loads((owner / "owner.json").read_text())
        manifest["source"] = "input.webm"
        (owner / "owner.json").write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
        decoder = Decoder()
        app = create_phase2_app(
            database_path=tmp_path / "state.sqlite3",
            file_runner=WindowedRunner(decoder),
            file_work_root=tmp_path / "file-work",
            meeting_audio_root=tmp_path / "meeting-audio",
        )
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            await tasks._retained_resume_task
            entry = tasks._tasks.get(handle.meeting_id)
            if entry is not None:
                await entry.task
            resumed = await _snapshot(app, handle)
            resumed_calls = decoder.calls
            store = app.state.phase2_store
            account, _ = await store.bootstrap_browser(session)

            class Upload:
                filename = "fresh.webm"

                def __init__(self):
                    self._stream = webm.open("rb")

                async def read(self, size):
                    return self._stream.read(size)

            fresh_handle = await tasks.accept(store.workspace(account), Upload())
            fresh_entry = tasks._tasks.get(fresh_handle.meeting_id)
            if fresh_entry is not None:
                await fresh_entry.task
            fresh = await fresh_handle.snapshot()
        return resumed, resumed_calls, fresh

    resumed, resumed_calls, fresh = asyncio.run(exercise())
    print(f"\nA8 fresh: status={fresh.status} audio={getattr(fresh.audio, 'state', None)} | unbound restart: "
          f"status={resumed.status}/{resumed.failure_code} decoder_calls={resumed_calls}")
    assert fresh.status == "completed"
    assert resumed.status == fresh.status


@pytest.mark.xfail(strict=True, reason="A5: claim must await started or task completion")
def test_a5_fence_before_resumed_task_first_step_does_not_wedge_the_claim(tmp_path, monkeypatch):
    """Pre-existing shape: _register -> await started.wait(); a fence scheduled ahead of the
    new task's first step cancels it before `started` is set."""

    async def exercise():
        _account, _session, handle, _owner = await _seed_owner(tmp_path)
        loop = asyncio.get_running_loop()
        original_run = FileMeetingTasks._run
        settled: list[bool] = []

        def run_then_fence(self, target, *args, **kwargs):
            coroutine = original_run(self, target, *args, **kwargs)

            def fence() -> None:
                entry = self.fence_meeting(target.meeting_id)

                async def settle() -> None:
                    settled.append(await self.settle_meeting(entry))

                loop.create_task(settle())

            loop.call_soon(fence)  # already queued ahead of the task created next
            return coroutine

        monkeypatch.setattr(FileMeetingTasks, "_run", run_then_fence)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            tasks = app.state.phase2_file_tasks
            try:
                await asyncio.wait_for(asyncio.shield(tasks._retained_resume_task), 2)
                wedged = False
            except TimeoutError:
                wedged = True
            status = (await _snapshot(app, handle)).status
        return wedged, settled, status

    wedged, settled, status = asyncio.run(exercise())
    print(f"\nA5 coordinator_wedged={wedged} settle_results={settled} status={status}")
    assert wedged is False


# =========================================================================== B. read-only validation
def _shape_runner(tmp: Path):
    decoder = _RestartDecoder()
    decoder.fail_window = 2
    runner = WindowedRunner(
        decoder,
        duration_probe=lambda _source: 390.0,
        window_extractor=lambda _s, d, **_k: Path(d).write_text("w\n"),
    )
    return decoder, runner


@pytest.mark.parametrize("shape", ["empty", "missing", "partial", "valid"])
def test_b1_validation_writes_nothing(tmp_path, shape):
    decoder, runner = _shape_runner(tmp_path)
    tasks = FileMeetingTasks(runner, tmp_path / "file-work", **PRODUCTION_OPTIONS)
    handle = SimpleNamespace(owner_key=("account-a", 1), meeting_id="meeting-a")
    owner = tasks.retained_root / "account-a" / "meeting-a"
    owner.mkdir(parents=True)
    source = owner / "input.wav"
    source.write_bytes(b"retained source")
    (owner / "owner.json").write_text(json.dumps({
        "account_id": "account-a", "meeting_id": "meeting-a", "ingress": "file",
        "source": "input.wav", "checkpoint": "checkpoint",
        "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION}), encoding="utf-8")
    checkpoint = owner / "checkpoint"
    if shape == "empty":
        checkpoint.mkdir()
    elif shape in {"partial", "valid"}:
        if shape == "valid":
            decoder.fail_window = None
        try:
            runner.transcribe(source, checkpoint_dir=checkpoint, **PRODUCTION_OPTIONS)
        except Exception:
            pass
        if shape == "partial":
            (checkpoint / "windows" / "w000002-240000000-390000000.json.4242.tmp").write_text("{", encoding="utf-8")
    before = _tree(tmp_path)
    verdict = runner.validate_resume(source, checkpoint, inference=tasks._inference_options())
    product = tasks._verified_retained_resume_source(handle, owner)
    after = _tree(tmp_path)
    print(f"\nB1 {shape}: validate_resume={verdict.status} product={None if product is None else product.checkpoint_bound} "
          f"entries_before={len(before)} after={len(after)}")
    assert before == after


SHAPES_SCRIPT = textwrap.dedent(
    r'''
    import json, sys, tempfile
    from pathlib import Path
    from types import SimpleNamespace
    from moss_transcribe_diarize.app.model_runner import TranscriptionResult
    from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
    from moss_transcribe_diarize.app import windowed_transcription as wt

    OPTIONS = {"prompt": "p", "max_length": 16384, "max_new_tokens": 12000, "decoding": "greedy"}

    class Decoder:
        model_path = "shape-decoder"
        def __init__(self, speechless=False):
            self.speechless = speechless
        def transcribe(self, audio_path, **_k):
            index = int(Path(audio_path).stem.rsplit("-", 1)[1])
            if index == 2:
                raise RuntimeError("crash")
            if self.speechless and index == 0:
                return TranscriptionResult(text="", prompt_len=0, generated_tokens=0, elapsed_sec=0.0,
                    model=self.model_path, audio=str(audio_path), decoding="greedy", temperature=None,
                    window_diagnostics=[{"condition": "speechless_window_empty"}])
            return TranscriptionResult(text=f"[1][S01]w{index}[2]", prompt_len=1, generated_tokens=1,
                elapsed_sec=0.0, model=self.model_path, audio=str(audio_path), decoding="greedy",
                temperature=None)

    import wave

    def extract(_source, destination, **_kwargs):
        with wave.open(str(destination), "wb") as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 16000)

    def runner(speechless=False):
        return wt.WindowedRunner(Decoder(speechless), duration_probe=lambda _s: 390.0,
                                 window_extractor=extract)

    def make(root, shape):
        r = runner(shape == "speechless_accepted")
        source = root / "input.wav"; source.write_bytes(b"retained source")
        ck = root / "checkpoint"
        if shape == "empty_dir":
            ck.mkdir(); return r, source, ck, OPTIONS
        try:
            r.transcribe(source, checkpoint_dir=ck, **OPTIONS)
        except Exception:
            pass
        windows = sorted((ck / "windows").glob("w*.json"))
        manifest = ck / "manifest.json"
        options = OPTIONS
        if shape == "damaged_prefix":
            windows[0].unlink()
        elif shape == "wrong_source_hash":
            source.write_bytes(b"other bytes")
        elif shape == "wrong_contract":
            options = {**OPTIONS, "prompt": "other"}
        elif shape == "truncated_json":
            text = windows[1].read_text(); windows[1].write_text(text[: len(text) // 2])
        elif shape == "wrong_schema_version":
            data = json.loads(manifest.read_text()); data["schema_version"] = 2
            manifest.write_text(json.dumps(data))
        elif shape == "manifest_json_array":
            manifest.write_text("[]")
        elif shape == "manifest_binary_garbage":
            manifest.write_bytes(b"\xff\xfe\x00garbage")
        elif shape == "manifest_without_source_sha":
            data = json.loads(manifest.read_text()); data.pop("source_sha256"); manifest.write_text(json.dumps(data))
        return r, source, ck, options

    SHAPES = ["valid", "damaged_prefix", "wrong_source_hash", "wrong_contract", "speechless_accepted",
              "truncated_json", "wrong_schema_version", "empty_dir",
              "manifest_json_array", "manifest_binary_garbage", "manifest_without_source_sha"]
    out = {}
    for shape in SHAPES:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "file-retained" / "account-a" / "meeting-a"; root.mkdir(parents=True)
            r, source, ck, options = make(root, shape)
            row = {}
            tasks = FileMeetingTasks(r, Path(raw) / "file-work", **options)
            if hasattr(wt.WindowedRunner, "validate_resume"):
                try:
                    v = r.validate_resume(source, ck, inference=options)
                except TypeError:
                    r.bind_resume_inference(options); v = r.validate_resume(source, ck)
                row["validate_resume"] = v.status
            try:
                row["inline_or_wrapper_is_valid"] = tasks._checkpoint_is_valid(source, ck)
            except Exception as exc:
                row["inline_or_wrapper_is_valid"] = "raised " + type(exc).__name__
            (root / "owner.json").write_text(json.dumps({"account_id": "account-a", "meeting_id": "meeting-a",
                "ingress": "file", "source": "input.wav", "checkpoint": "checkpoint", "contract_version": 1}))
            handle = SimpleNamespace(owner_key=("account-a", 1), meeting_id="meeting-a")
            probe = getattr(tasks, "_verified_retained_resume_source", None) or tasks._verified_retained_input
            try:
                result = probe(handle, root)
                row["product_claim_validation"] = "accepted" if result is not None else "refused"
            except Exception as exc:
                row["product_claim_validation"] = "error:" + type(exc).__name__
            out[shape] = row
    print(json.dumps(out))
    '''
)


def _run_shapes(tree: Path, tmp_path: Path) -> dict:
    script = tmp_path / f"shapes-{tree.name}.py"
    script.write_text(SHAPES_SCRIPT, encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(tree), PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, cwd=tree)
    assert completed.returncode == 0, completed.stderr[-3000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


HISTORICAL_SHAPES = ["valid", "damaged_prefix", "wrong_source_hash", "wrong_contract",
                     "speechless_accepted", "truncated_json", "wrong_schema_version", "empty_dir"]


def test_b2_eight_historical_shapes_keep_their_verdicts(tmp_path):
    trees = {"head": REPO}
    for name in ("base-85aec978", "frozen-0de56e1a"):
        candidate = Path(os.environ.get("FIXWAVE_TREES", "/nonexistent")) / name
        if candidate.is_dir():
            trees[name] = candidate
    results = {name: _run_shapes(tree, tmp_path) for name, tree in trees.items()}
    for shape in results["head"]:
        print(f"\nB2 {shape:<28} " + " | ".join(f"{name}: {results[name].get(shape)}" for name in results))
    head = results["head"]
    expected = {shape: ("accepted" if shape in {"valid", "speechless_accepted", "empty_dir"} else "refused")
                for shape in HISTORICAL_SHAPES}
    assert {s: head[s]["validate_resume"] for s in HISTORICAL_SHAPES} == expected
    assert {s: head[s]["product_claim_validation"] for s in HISTORICAL_SHAPES} == expected
    for name, other in results.items():
        if name == "head":
            continue
        assert {s: other[s]["inline_or_wrapper_is_valid"] for s in HISTORICAL_SHAPES} == {
            s: head[s]["inline_or_wrapper_is_valid"] for s in HISTORICAL_SHAPES}, name
    # Corrupt checkpoint evidence is a contract refusal, not "validation could not complete".
    for shape in ("manifest_json_array", "manifest_binary_garbage"):
        assert head[shape]["product_claim_validation"] == "refused", (shape, head[shape])


@pytest.mark.xfail(strict=True, reason="B3: corrupt checkpoint manifest is refused")
def test_b3_corrupt_manifest_ends_interrupted_not_failed_after_retries(tmp_path, monkeypatch):
    async def exercise():
        _account, _session, handle, owner = await _seed_owner(tmp_path, manifest=[])
        monkeypatch.setattr(phase2_file_module, "RETAINED_VALIDATION_BACKOFF_SECONDS", 0.01)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            await app.state.phase2_file_tasks._retained_resume_task
            snapshot = await _snapshot(app, handle)
        return snapshot.status, snapshot.failure_code, snapshot.failure_reason, owner.exists()

    status, code, reason, owner_exists = asyncio.run(exercise())
    print(f"\nB3 manifest='[]' -> status={status} code={code} reason={reason!r} owner_exists={owner_exists}")
    assert status == "interrupted", (status, code)


# =========================================================================== C. same-boot reclaim
def test_c1_post_fallback_sweep_never_touches_reserved_owner_that_settled_during_the_sweep(tmp_path, monkeypatch):
    async def exercise():
        store = await Phase2Store.open(tmp_path / "state.sqlite3")
        try:
            account, _ = await seed_workspace(store, "account-a")
            reserved = await store.workspace(account).create_meeting("file")
            unreserved = await store.workspace(account).create_meeting("file")
        finally:
            await store.close()
        base = tmp_path / "file-retained" / account.account_id
        reserved_dir, unreserved_dir = base / reserved.meeting_id, base / unreserved.meeting_id
        for owner, meeting in ((reserved_dir, reserved), (unreserved_dir, unreserved)):
            owner.mkdir(parents=True)
            (owner / "input.wav").write_bytes(b"raw user media")
        (reserved_dir / "checkpoint").mkdir()
        (reserved_dir / "owner.json").write_text(json.dumps({
            "account_id": account.account_id, "meeting_id": reserved.meeting_id, "ingress": "file",
            "source": "input.wav", "checkpoint": "checkpoint", "contract_version": 1}), encoding="utf-8")
        entered, release = threading.Event(), threading.Event()
        reads_after_sweep: list[bool] = []

        def stalled(_self, _handle, owner_dir):
            entered.set()
            release.wait(5)
            reads_after_sweep.append((owner_dir / "input.wav").is_file())
            return None

        monkeypatch.setattr(FileMeetingTasks, "_verified_retained_resume_source", stalled)
        original = Phase2Store.terminal_file_meeting_owners
        calls = {"n": 0}

        async def during_sweep(self, account_id=None, *, retained_owners=None):
            calls["n"] += 1
            if calls["n"] == 2:  # the post-fallback computation: the reserved owner settles now
                assert await asyncio.to_thread(entered.wait, 5)
                await MeetingHandle(self, account.account_id, account.authority_generation,
                                    reserved.meeting_id).finish("interrupted")
            return await original(self, account_id, retained_owners=retained_owners)

        monkeypatch.setattr(Phase2Store, "terminal_file_meeting_owners", during_sweep)
        app = _app(tmp_path, _RestartDecoder())
        async with app.router.lifespan_context(app):
            state = {"reserved_dir_after_sweep": reserved_dir.exists(),
                     "unreserved_dir_after_sweep": unreserved_dir.exists(),
                     "sweep_calls": calls["n"]}
            release.set()
            await app.state.phase2_file_tasks._retained_resume_task
        state["validation_could_still_read"] = reads_after_sweep
        return state

    state = asyncio.run(exercise())
    print(f"\nC1 {state}")
    assert state["reserved_dir_after_sweep"] is True
    assert state["unreserved_dir_after_sweep"] is False
    assert state["validation_could_still_read"] == [True]
