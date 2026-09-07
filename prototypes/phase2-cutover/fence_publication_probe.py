"""Run: .venv/bin/python prototypes/phase2-cutover/fence_publication_probe.py

Question: can a pending failure fence admit a new successful terminal publication
while joining an accepted Stop? Minimum primitives are the existing publication
gate, Stop completion, and terminal settlement. The gate must close before the
join yields, without closing owner mutation authority prematurely. Falsifier:
the real _accept_raw admits a publication during that join. No timing threshold.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from moss_transcribe_diarize.app.phase2_live import Phase2LiveMeetings


async def main():
    live = Phase2LiveMeetings(object(), audio_archive=None, audio_stages=None)
    completion = asyncio.Event()
    binding = SimpleNamespace(
        terminal_persisted=False, raw_stop_attempt=SimpleNamespace(completed=completion),
        capture_fenced=False, publication_fenced=False, queue=asyncio.Queue(),
        raw_event_high_water=-1, handle=SimpleNamespace(meeting_id="m"),
        persistence_failure=None, durable_document={},
    )
    async def abort(*_args):
        return None
    live.runtime = SimpleNamespace(snapshot=lambda _: None, events=lambda _: (), abort=abort)
    live._bindings["m"] = binding
    live._accepting_publications = True
    async def settle(*_args, **_kwargs):
        pass
    live._settle_terminal = settle
    pending = asyncio.create_task(live._fence(binding, "transcript_persistence_failed"))
    await asyncio.sleep(0)
    live._accept_raw("m", None, (SimpleNamespace(seq=1),))
    state = {"stop_pending": not completion.is_set(), "capture_fenced_before_join": binding.capture_fenced,
             "publication_fenced_before_join": binding.publication_fenced,
             "terminal_publications_admitted_during_join": binding.queue.qsize()}
    completion.set()
    await pending
    print(json.dumps(state, indent=2))
    assert state["terminal_publications_admitted_during_join"] == 0
    assert state["capture_fenced_before_join"] is False


asyncio.run(main())
