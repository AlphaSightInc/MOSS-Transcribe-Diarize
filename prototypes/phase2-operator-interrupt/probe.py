"""Issue #20 throwaway probe for one-Meeting operator interruption.

One command from the repository root:
  PYTHONDONTWRITEBYTECODE=1 uv run --frozen python \
    prototypes/phase2-operator-interrupt/probe.py

The prototype isolates the new claim policy. Existing production Live/File owners remain
responsible for transcript, audio, and cleanup algorithms; the result decides only where the
per-Meeting fence and service-owned lifetime belong.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field

from moss_transcribe_diarize.app.phase2_lifecycle import AccountLifecycle


@dataclass(slots=True)
class MeetingState:
    meeting_id: str
    mode: str
    status: str = "active"
    transcript: list[str] = field(default_factory=lambda: ["durable-prefix"])
    audio: dict[str, object] | None = field(
        default_factory=lambda: {
            "state": "available",
            "path": "audio.mp3",
            "bytes": 48000,
            "duration_ms": 8000,
        }
    )
    source_present: bool = True
    queued_results: list[str] = field(default_factory=list)
    committed_results: list[str] = field(default_factory=list)
    fenced: bool = False


@dataclass(slots=True)
class WorkClaim:
    meeting: MeetingState
    release: asyncio.Event
    quiesced: asyncio.Event = field(default_factory=asyncio.Event)


class MeetingOwner:
    """Prototype-local shape of the existing Live/File process owner."""

    def __init__(self, meetings: list[MeetingState], *, suppress: str | None) -> None:
        self.suppress = suppress
        self._claims = {
            meeting.meeting_id: WorkClaim(meeting, asyncio.Event()) for meeting in meetings
        }
        self._workers = {
            meeting_id: asyncio.create_task(self._run(claim))
            for meeting_id, claim in self._claims.items()
        }

    def fence(self, meeting_id: str) -> WorkClaim | None:
        claim = self._claims.get(meeting_id)
        if claim is None or claim.meeting.status != "active":
            return None
        if self.suppress != "fence":
            claim.meeting.fenced = True
            claim.meeting.queued_results.clear()
        return claim

    async def settle(self, claim: WorkClaim) -> None:
        await claim.quiesced.wait()
        meeting = claim.meeting
        if self.suppress != "cleanup":
            meeting.source_present = False
        if meeting.audio is None:
            meeting.audio = {"state": "unavailable"}
        elif meeting.audio["state"] == "available":
            meeting.audio = {**meeting.audio, "state": "partial"}
        meeting.status = "interrupted"

    async def _run(self, claim: WorkClaim) -> None:
        await claim.release.wait()
        meeting = claim.meeting
        if not meeting.fenced:
            meeting.committed_results.extend(meeting.queued_results)
            meeting.transcript.extend(meeting.queued_results)
            meeting.queued_results.clear()
        claim.quiesced.set()

    async def close(self) -> None:
        for claim in self._claims.values():
            claim.release.set()
        await asyncio.gather(*self._workers.values())


class LiveOwner(MeetingOwner):
    def fence_meeting(self, meeting_id: str) -> WorkClaim | None:
        return self.fence(meeting_id)

    async def interrupt_binding(
        self,
        claim: WorkClaim,
        control: object,
        reason: str,
    ) -> bool:
        del control
        assert reason == "interrupted_by_operator"
        claim.release.set()
        await self.settle(claim)
        return claim.meeting.status == "interrupted"


class FileOwner(MeetingOwner):
    def fence_meeting(self, meeting_id: str) -> WorkClaim | None:
        return self.fence(meeting_id)

    async def settle_meeting(self, claim: WorkClaim) -> bool:
        claim.release.set()
        await self.settle(claim)
        return claim.meeting.status == "interrupted"


class Store:
    def __init__(self, live: LiveOwner, files: FileOwner) -> None:
        self.live = live
        self.files = files

    async def operator_has_active_meeting(self, meeting_id: str) -> bool:
        claims = {**self.live._claims, **self.files._claims}
        claim = claims.get(meeting_id)
        return claim is not None and claim.meeting.status == "active"


class Control:
    def release(self, meeting_id: str) -> None:
        del meeting_id


async def run(suppress: str | None) -> dict[str, object]:
    live_target = MeetingState("live-target", "live", queued_results=["late-live"])
    live_peer = MeetingState("live-peer", "live", queued_results=["peer-live"])
    file_target = MeetingState("file-target", "file", queued_results=["late-file"])
    file_peer = MeetingState("file-peer", "file", queued_results=["peer-file"])
    cancelled_target = MeetingState(
        "cancel-target",
        "file",
        audio=None,
        queued_results=["late-cancelled"],
    )
    live = LiveOwner([live_target, live_peer], suppress=suppress)
    files = FileOwner([file_target, file_peer, cancelled_target], suppress=suppress)
    lifecycle = AccountLifecycle(Store(live, files), live=live, files=files)
    lifecycle.bind_live_control(Control())

    async def interrupt(meeting_id: str) -> dict[str, object]:
        return {
            "meeting_id": meeting_id,
            "interrupted": await lifecycle.interrupt_meeting(meeting_id),
        }

    live_result, live_join = await asyncio.gather(
        interrupt(live_target.meeting_id),
        interrupt(live_target.meeting_id),
    )
    file_result = await interrupt(file_target.meeting_id)

    # Other same-Account work remains owned and is deliberately allowed to finish.
    live._claims[live_peer.meeting_id].release.set()
    files._claims[file_peer.meeting_id].release.set()
    await asyncio.gather(
        live._claims[live_peer.meeting_id].quiesced.wait(),
        files._claims[file_peer.meeting_id].quiesced.wait(),
    )

    # Handler cancellation cannot abandon accepted settlement. The service owner joins it.
    cancelled_call = asyncio.create_task(interrupt(cancelled_target.meeting_id))
    await asyncio.sleep(0)
    cancelled_call.cancel()
    caller_cancelled = False
    try:
        await cancelled_call
    except asyncio.CancelledError:
        caller_cancelled = True
    files._claims[cancelled_target.meeting_id].release.set()
    await lifecycle.shutdown()

    repeated = await interrupt(live_target.meeting_id)
    unknown = await interrupt("opaque-unknown")
    await live.close()
    await files.close()

    states = {
        meeting.meeting_id: {
            "mode": meeting.mode,
            "status": meeting.status,
            "transcript": meeting.transcript,
            "audio": meeting.audio,
            "source_present": meeting.source_present,
            "queued_results": meeting.queued_results,
            "committed_results": meeting.committed_results,
            "fenced": meeting.fenced,
        }
        for meeting in (live_target, live_peer, file_target, file_peer, cancelled_target)
    }
    measurements = {
        "concurrent_live_results": [live_result, live_join],
        "file_result": file_result,
        "repeated_result": repeated,
        "unknown_result": unknown,
        "cancelled_handler": caller_cancelled,
        "owned_interrupt_tasks_after_join": len(lifecycle._interrupt_tasks),
    }
    verdict_checks = {
        "concurrent_join": live_result == live_join == {
            "meeting_id": "live-target",
            "interrupted": True,
        },
        "live_late_discarded": live_target.transcript == ["durable-prefix"]
        and not live_target.committed_results,
        "file_late_discarded": file_target.transcript == ["durable-prefix"]
        and not file_target.committed_results,
        "targets_terminal_clean": all(
            meeting.status == "interrupted" and not meeting.source_present
            for meeting in (live_target, file_target, cancelled_target)
        ),
        "audio_truth": live_target.audio == {
            "state": "partial",
            "path": "audio.mp3",
            "bytes": 48000,
            "duration_ms": 8000,
        }
        and cancelled_target.audio == {"state": "unavailable"},
        "peers_continue": live_peer.committed_results == ["peer-live"]
        and file_peer.committed_results == ["peer-file"]
        and live_peer.status == file_peer.status == "active",
        "idempotent_no_content": repeated == {
            "meeting_id": "live-target",
            "interrupted": False,
        }
        and unknown == {"meeting_id": "opaque-unknown", "interrupted": False},
        "handler_cancellation_owned": caller_cancelled
        and cancelled_target.status == "interrupted"
        and len(lifecycle._interrupt_tasks) == 0,
    }
    return {
        "structural_question": "Can one opaque host interrupt fence exactly one active Meeting and return only after existing owners make its durable prefix terminal?",
        "minimum_primitives": [
            "one existing Unix Operator Control command",
            "one synchronous per-Meeting owner claim",
            "existing Live/File serialized settlement",
            "one service-owned in-flight interrupt task",
        ],
        "invariants": [
            "claim grants no Account or content access",
            "queued and late target results cannot commit after claim",
            "unrelated work continues",
            "available becomes metadata-identical partial and absent becomes unavailable",
            "command completion implies durable terminal truth and source cleanup",
        ],
        "assumptions_unknowns": [
            "production owners already settle transcript/audio/cleanup truth",
            "production Live/File settlement implementations remain independently tested",
        ],
        "falsifier": "any late commit, peer cancellation, complete audio, surviving source, abandoned cancelled handler, or content-bearing response",
        "tool_decision": "the production AccountLifecycle interrupt owner plus thin Live/File adapters are necessary because claim-before-await and handler cancellation are the new policies; models, browsers, and network cannot decide them",
        "measurements": measurements,
        "full_state": states,
        "verdict_checks": verdict_checks,
        "verdict": "PASS" if all(verdict_checks.values()) else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suppress", choices=("fence", "cleanup"))
    args = parser.parse_args()
    result = asyncio.run(run(args.suppress))
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
