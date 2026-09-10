"""THROWAWAY: naming must own COMMIT-to-publication; Stop closes pending admission.

Question: can transport cancellation split a durable manual name from live label state?
Primitives: real naming transaction, owned task, committed live mutation, pending intent.
Invariant: an accepted mutation finishes synchronization even when its caller disappears;
Stop discards an unfulfilled intent before any newly eligible tail observation.
Unknown: full transport integration remains a regression-test obligation.
Falsifier: committed label differs from memory, or new tail evidence enrolls after closing.
Tool: existing real naming/store path and test meeting adapter; hold the actual COMMIT,
compare direct cancellation to the existing service-owned-task primitive. No audio.
Run: PYTHONPATH=. .venv/bin/python prototypes/phase2-account-lifecycle/manual_identity_lifecycle_probe.py
"""
import asyncio
import json
import sqlite3
import tempfile
from pathlib import Path

from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.phase2_speaker_identity import AccountSpeakerIdentity
from tests.phase2.test_manual_speaker_voiceprints import (
    FakeActiveMeetings, active_meeting, evidence, provision,
)


async def cancellation(root, owned):
    store, workspace, _ = await provision(root / f"cancel-{owned}.sqlite3")
    active = FakeActiveMeetings()
    handle, meeting = await active_meeting(workspace, active)
    meeting.observations["speaker-0001"] = evidence("speaker-0001", seconds=2)
    identity = AccountSpeakerIdentity(store, active)
    committed, release = asyncio.Event(), asyncio.Event()
    original = store._connection.commit
    async def hold_commit():
        await original()
        committed.set()
        await release.wait()
    store._connection.commit = hold_commit
    async def name():
        if owned:
            return await identity.bank(workspace).name_speaker(handle, "speaker-0001", "Durable")
        # Falsifier deliberately bypasses the now-absorbed service-owned entry.
        return await identity._name_speaker_serial(workspace.owner_key, handle, "speaker-0001", "Durable")
    task = asyncio.create_task(name())
    async def request():
        return await task
    caller = asyncio.create_task(request())
    await committed.wait()
    mutation = next(iter(identity._naming_tasks)) if owned else task
    caller.cancel()
    try:
        await caller
    except asyncio.CancelledError:
        pass
    release.set()
    await asyncio.gather(task, return_exceptions=True)
    await identity.shutdown()
    row = await handle.snapshot()
    result = {"owned": owned, "durable_label": row.transcript["segments"][0]["speaker"],
              "live_label": meeting.speaker_labels["speaker-0001"],
              "mutation_cancelled": mutation.cancelled()}
    await store.close()
    return result


async def stop_pending(root, close_first):
    store, workspace, _ = await provision(root / f"stop-{close_first}.sqlite3")
    active = FakeActiveMeetings()
    handle, meeting = await active_meeting(workspace, active)
    meeting.observations["speaker-0001"] = evidence("speaker-0001", seconds=1)
    identity = AccountSpeakerIdentity(store, active)
    await identity.bank(workspace).name_speaker(handle, "speaker-0001", "Pending")
    if close_first:
        await identity.clear_meeting(handle)
    await identity.observe(handle, [evidence("speaker-0001", seconds=2)])
    samples = sum(item.sample_count for item in await identity.bank(workspace).list_voiceprints())
    await identity.clear_meeting(handle)
    await store.close()
    return {"close_at_stop": close_first, "tail_samples": samples}


async def run(root):
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    results = [await cancellation(root, False), await cancellation(root, True),
               await stop_pending(root, False), await stop_pending(root, True)]
    assert results[0]["durable_label"] != results[0]["live_label"]
    assert results[1]["durable_label"] == results[1]["live_label"] == "Durable"
    assert results[2]["tail_samples"] == 1 and results[3]["tail_samples"] == 0
    print(json.dumps({"sqlite": sqlite3.sqlite_version, "states": results, "verdict": "owned mutation and Stop admission fence required"}))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-manual-lifecycle-") as scratch:
        asyncio.run(run(Path(scratch)))
