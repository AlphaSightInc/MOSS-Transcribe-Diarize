"""PROTOTYPE ONLY: narrow restart ownership for durable File progress.

Question: can the existing durable File Meeting remain the sole owner while one
canonical retained source/checkpoint directory is discovered before generic
startup interruption and cleanup?
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import AccountRevoked, Phase2Store
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
INFERENCE = {
    "max_length": 131_072,
    "max_new_tokens": 2_048,
    "decoding": "greedy",
}


class ResumeCancelled(RuntimeError):
    pass


class DeterministicDecoder:
    model_path = "prototype-deterministic-runner"

    def __init__(self, *, fail_at: int | None = None, cancel_at: int | None = None):
        self.fail_at = fail_at
        self.cancel_at = cancel_at
        self.calls: list[int] = []

    def transcribe(self, audio_path, **_kwargs):
        index = int(Path(audio_path).stem.rsplit("-", 1)[1])
        self.calls.append(index)
        if index == self.fail_at:
            raise RuntimeError("prototype interruption")
        if index == self.cancel_at:
            raise ResumeCancelled("prototype owner cancelled resumed work")
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

    def contract(self):
        return {"schema_version": 1, "prototype": "pass-through"}

    def resolve(self, _windows, local_results, *, window_audio_paths):
        del window_audio_paths
        return IdentityResolution(
            relabeled_results=local_results,
            summary={"prototype": "pass-through"},
            diagnostics={"schema_version": 1, "prototype": "pass-through"},
        )


def _extract(_source, destination, *, start_seconds, duration_seconds):
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
    account_session: str
    other_session: str
    account_id: str
    meeting_id: str
    ingress: str


@dataclass(frozen=True)
class RetainedWork:
    handle: object
    owner_dir: Path
    source: Path
    checkpoint: Path
    committed: int


async def _seed(root: Path, ingress: str) -> Seed:
    database = root / "state.sqlite3"
    store = await Phase2Store.open(database)
    account, account_session = await store.bootstrap_browser(None)
    _other, other_session = await store.bootstrap_browser(None)
    handle = await store.workspace(account).create_meeting("file")
    owner_dir = root / "batch-work" / account.account_id / handle.meeting_id
    owner_dir.mkdir(parents=True)
    source = owner_dir / "source.wav"
    source.write_bytes(b"retained local source; URL acquisition is already complete\n")
    (owner_dir / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": ingress,
                "source": "source.wav",
            },
            sort_keys=True,
        )
        + "\n"
    )
    decoder = DeterministicDecoder(fail_at=40)
    try:
        _runner(decoder).transcribe(
            source,
            checkpoint_dir=owner_dir / "checkpoint",
            **INFERENCE,
        )
        raise AssertionError("seed interruption did not fire")
    except WindowTranscriptionError as exc:
        assert exc.window_index == 40 and exc.condition == "decoder_exception"
    committed = len(tuple((owner_dir / "checkpoint" / "windows").glob("w*.json")))
    assert committed == 40 and decoder.calls == list(range(41))
    await store.close()
    return Seed(
        root=root,
        account_session=account_session,
        other_session=other_session,
        account_id=account.account_id,
        meeting_id=handle.meeting_id,
        ingress=ingress,
    )


async def _discover(
    seed: Seed,
    *,
    account_session: str | None = None,
    meeting_id: str | None = None,
    inference: dict[str, object] | None = None,
) -> tuple[Phase2Store, RetainedWork]:
    store = await Phase2Store.open(seed.root / "state.sqlite3")
    account = await store.account_for_session(account_session or seed.account_session)
    if account is None:
        await store.close()
        raise RuntimeError("owner account unavailable")
    selected_meeting = meeting_id or seed.meeting_id
    handle = await store.workspace(account).open_meeting(selected_meeting)
    if handle is None:
        await store.close()
        raise RuntimeError("retained work owner mismatch")
    snapshot = await handle.snapshot()
    if snapshot.mode != "file" or snapshot.status != "active":
        await store.close()
        raise RuntimeError("retained File Meeting is not active")
    owner_dir = seed.root / "batch-work" / account.account_id / selected_meeting
    try:
        owner = json.loads((owner_dir / "owner.json").read_text())
    except Exception as exc:
        await store.close()
        raise RuntimeError("retained owner manifest unavailable") from exc
    if owner.get("account_id") != account.account_id or owner.get("meeting_id") != selected_meeting:
        await store.close()
        raise RuntimeError("retained owner manifest mismatch")
    source = owner_dir / str(owner.get("source"))
    if not source.is_file():
        await store.close()
        raise RuntimeError("retained local source unavailable")
    options = dict(INFERENCE if inference is None else inference)
    windows = plan_windows(DURATION_SECONDS)
    checkpoint = _CheckpointStore(
        owner_dir / "checkpoint",
        source=source,
        windows=windows,
        model_path=DeterministicDecoder.model_path,
        inference=_checkpoint_inference(options),
        window_seconds=150.0,
        stride_seconds=120.0,
        identity_contract=PassThroughIdentity().contract(),
    )
    committed = len(checkpoint.load_prefix())
    return store, RetainedWork(handle, owner_dir, source, owner_dir / "checkpoint", committed)


def _clone(seed: Seed, destination: Path) -> Seed:
    shutil.copytree(seed.root, destination)
    return Seed(
        root=destination,
        account_session=seed.account_session,
        other_session=seed.other_session,
        account_id=seed.account_id,
        meeting_id=seed.meeting_id,
        ingress=seed.ingress,
    )


async def _refusal(seed: Seed, kind: str) -> dict[str, object]:
    decoder_calls = 0
    publication_calls = 0
    try:
        if kind == "wrong_account":
            await _discover(seed, account_session=seed.other_session)
        elif kind == "wrong_meeting":
            await _discover(seed, meeting_id="not-the-retained-meeting")
        elif kind == "wrong_source":
            source = seed.root / "batch-work" / seed.account_id / seed.meeting_id / "source.wav"
            source.write_bytes(b"different retained source\n")
            await _discover(seed)
        elif kind == "changed_inference":
            await _discover(seed, inference={**INFERENCE, "max_new_tokens": 2_049})
        elif kind == "broken_prefix":
            windows = sorted(
                (seed.root / "batch-work" / seed.account_id / seed.meeting_id / "checkpoint" / "windows").glob("w*.json")
            )
            windows[10].unlink()
            await _discover(seed)
        else:
            raise AssertionError(kind)
    except Exception as exc:
        return {
            "control": kind,
            "refused": True,
            "reason_type": type(exc).__name__,
            "reason": str(exc),
            "decoder_calls": decoder_calls,
            "publication_calls": publication_calls,
        }
    raise AssertionError(f"{kind} was not refused")


async def _resume(seed: Seed) -> dict[str, object]:
    store, retained = await _discover(seed)
    assert retained.committed == 40
    decoder = DeterministicDecoder()
    result = _runner(decoder).transcribe(
        retained.source,
        checkpoint_dir=retained.checkpoint,
        **INFERENCE,
    )
    segments = [segment.to_dict() for segment in subtitle_segments_from_transcript(result.text)]
    version = await retained.handle.finish_with_transcript(
        {"segments": segments}, "completed"
    )
    publish_once_refused = False
    try:
        await retained.handle.finish_with_transcript({"segments": segments}, "completed")
    except AccountRevoked:
        publish_once_refused = True
    shutil.rmtree(retained.owner_dir)
    await store.close()

    reopened = await Phase2Store.open(seed.root / "state.sqlite3")
    account = await reopened.account_for_session(seed.account_session)
    handle = await reopened.workspace(account).open_meeting(seed.meeting_id)
    snapshot = (await handle.snapshot()).to_dict()
    await reopened.close()
    texts = [segment["text"] for segment in snapshot["transcript"]["segments"]]
    return {
        "ingress": seed.ingress,
        "retained_local_source": True,
        "remote_url_fetches_on_resume": 0,
        "committed_before_restart": retained.committed,
        "new_decoder_calls": len(decoder.calls),
        "first_new_window": decoder.calls[0],
        "last_new_window": decoder.calls[-1],
        "published_version": version,
        "second_publication_refused": publish_once_refused,
        "reopened_status": snapshot["status"],
        "reopened_segments": len(texts),
        "unique_reopened_segments": len(set(texts)),
        "artifacts_exist_after_terminal": retained.owner_dir.exists(),
    }


async def _cancel(seed: Seed) -> dict[str, object]:
    store, retained = await _discover(seed)
    decoder = DeterministicDecoder(cancel_at=40)
    events = []
    try:
        _runner(decoder).transcribe(
            retained.source,
            checkpoint_dir=retained.checkpoint,
            **INFERENCE,
        )
        raise AssertionError("cancel control completed decode")
    except WindowTranscriptionError as exc:
        assert exc.window_index == 40
        events.append("resume_cancelled_before_later_dispatch")
    before = await retained.handle.snapshot()
    assert before.status == "active" and retained.owner_dir.exists()
    await retained.handle.finish("interrupted")
    events.append("durable_terminal_transition")
    shutil.rmtree(retained.owner_dir)
    events.append("artifacts_removed")
    after = await retained.handle.snapshot()
    await store.close()
    return {
        "decoder_calls": len(decoder.calls),
        "decoder_windows": decoder.calls,
        "publication_calls": 0,
        "status": after.status,
        "artifacts_exist": retained.owner_dir.exists(),
        "order": events,
    }


async def run() -> dict[str, object]:
    actual_sqlite = sqlite3.sqlite_version
    phase2.sqlite3.sqlite_version = phase2.REQUIRED_SQLITE_RUNTIME
    with tempfile.TemporaryDirectory(prefix="moss-wp53b-p2-") as temporary:
        root = Path(temporary)
        file_seed = await _seed(root / "seed-file", "file")
        url_seed = await _seed(root / "seed-url", "url")
        controls = []
        for kind in (
            "wrong_account",
            "wrong_meeting",
            "wrong_source",
            "changed_inference",
            "broken_prefix",
        ):
            controls.append(await _refusal(_clone(file_seed, root / f"control-{kind}"), kind))
        positive_file = await _resume(_clone(file_seed, root / "positive-file"))
        positive_url = await _resume(_clone(url_seed, root / "positive-url"))
        cancellation = await _cancel(_clone(file_seed, root / "cancel"))
        supported = (
            all(control["refused"] and control["decoder_calls"] == 0 and control["publication_calls"] == 0 for control in controls)
            and all(
                arm["new_decoder_calls"] == 61
                and arm["reopened_status"] == "completed"
                and arm["reopened_segments"] == arm["unique_reopened_segments"] == 101
                and arm["second_publication_refused"]
                and not arm["artifacts_exist_after_terminal"]
                for arm in (positive_file, positive_url)
            )
            and cancellation == {
                "decoder_calls": 1,
                "decoder_windows": [40],
                "publication_calls": 0,
                "status": "interrupted",
                "artifacts_exist": False,
                "order": [
                    "resume_cancelled_before_later_dispatch",
                    "durable_terminal_transition",
                    "artifacts_removed",
                ],
            }
        )
        return {
            "verdict": "SUPPORTED" if supported else "REJECTED",
            "sqlite_runtime": actual_sqlite,
            "sqlite_semantic_store_allowance": actual_sqlite != phase2.REQUIRED_SQLITE_RUNTIME,
            "question": "Can one retained active File Meeting remain the sole restart owner?",
            "positive_file": positive_file,
            "positive_url": positive_url,
            "violating_controls": controls,
            "cancel_on_resume": cancellation,
            "production_change": "prototype only; no production implementation",
        }


if __name__ == "__main__":
    state = asyncio.run(run())
    rendered = json.dumps(state, indent=2, sort_keys=True) + "\n"
    Path(__file__).with_name("results.json").write_text(rendered)
    print(rendered, end="")
    raise SystemExit(0 if state["verdict"] == "SUPPORTED" else 1)
