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
import threading
import time
from dataclasses import dataclass, field

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_coordinator import CanonicalWork
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
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


class _ScriptedSpeech:
    def __init__(self) -> None:
        self._speech = [True, False, True, False]

    def observe(
        self,
        *,
        frame: AudioFrame,
        start_sample: int,
        end_sample: int,
    ) -> tuple[SpeechObservation, ...]:
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self._speech.pop(0),
            ),
        )


class _HeldTargetDecoder:
    max_samples = 4_000

    def __init__(self, started: threading.Event, release: threading.Event) -> None:
        self.started = started
        self.release = release

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        if pcm.startswith(b"t"):
            self.started.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("probe did not release held target decode")
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]runtime[{seconds:g}]")


class _PreparedIdentity:
    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base_snapshot.version + 1,
                canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            ),
            relabeled_transcript="[0][S01]runtime[0.0625]",
            status="prepared",
        )


def _runtime_frame(sequence: int, marker: bytes) -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=marker * 2_000, sample_count=1_000)


def _runtime_queue_depth(runtime: LiveServiceRuntime, session_id: str) -> dict[str, int]:
    with runtime._lock:
        queues = runtime._sessions[session_id].arbiter.snapshot()
        return {
            "canonical": queues.live_canonical,
            "refinement": queues.live_refinement,
            "provisional": queues.live_provisional,
        }


def _aggregate_queue_depth(snapshot: dict[str, int | bool]) -> int:
    return sum(
        int(snapshot[key])
        for key in ("live_canonical", "live_refinement", "live_provisional")
    )


async def _runtime_discard_probe() -> dict[str, object]:
    """Measure the real per-session arbiter at the operator-interrupt boundary."""

    decode_started = threading.Event()
    release_decode = threading.Event()
    descriptor = LiveServiceDescriptor(
        source_revision="operator-interrupt-probe",
        provider_name="deterministic-probe",
        provider_revision="1",
        provider_manifest_hash=hash_config({"provider": "probe"}),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"hard_cap_samples": 4_000},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4_000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=1_000,
            max_queue_depth=8,
            max_retained_samples=8_000,
            max_identity_speakers=2,
            max_events=64,
            hard_cap_samples=4_000,
        ),
        frame_samples=1_000,
    )
    ids = iter(("runtime-target", "runtime-peer"))
    runtime = LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(
                min_speech_samples=1,
                min_silence_samples=1,
                hard_cap_samples=4_000,
            )
        ),
        speech_provider_factory=_ScriptedSpeech,
        decoder_factory=lambda: _HeldTargetDecoder(decode_started, release_decode),
        identity_preparer_factory=_PreparedIdentity,
        session_id_factory=lambda: next(ids),
    )
    target = runtime.create().session_id
    peer = runtime.create().session_id
    runtime.accept_frame(target, _runtime_frame(0, b"t"))
    runtime.accept_frame(target, _runtime_frame(1, b"t"))
    if not await asyncio.to_thread(decode_started.wait, 2):
        raise RuntimeError("target decode did not enter the held in-flight state")

    # One queued canonical item plus the runtime's other two live queue kinds. These are
    # deliberately queued behind the held target decode so abort must remove rather than run
    # them. The payloads are never dispatched; their queue/counter lifetime is the question.
    with runtime._lock:
        target_state = runtime._sessions[target]
        target_state.arbiter.submit_batch(
            key="unrelated-batch",
            payload={"probe": "batch"},
        )
        canonical = target_state.arbiter.submit_live_canonical(
            key=f"{target}:canonical-probe",
            payload=CanonicalWork(
                session_key=target,
                spans=(
                    FrozenSpan(
                        id=999,
                        epoch=0,
                        start_sample=1_000,
                        end_sample=2_000,
                        reason="operator_interrupt_probe",
                    ),
                ),
            ),
        )
        refinement = target_state.arbiter.submit_live_refinement(
            coalesce_key=f"{target}:rolling:0",
            payload={"probe": "refinement"},
        )
        target_state.arbiter.submit_live_provisional(
            coalesce_key=f"{target}:provisional",
            payload={"probe": "provisional"},
        )

    runtime.accept_frame(peer, _runtime_frame(0, b"p"))
    runtime.accept_frame(peer, _runtime_frame(1, b"p"))
    target_before = _runtime_queue_depth(runtime, target)
    aggregate_before = runtime._operator_queue_snapshot()
    started_before_claim = sum(
        event.kind == "canonical_started" for event in runtime.events(target)
    )

    # This is the exact production ordering under test: the process owner has installed its
    # no-await claim while an admitted SQLite transcript commit keeps async settlement held.
    # Before absorption the runtime has no synchronous fence, so the three target queues and
    # in-flight provider remain runnable until the later async abort.
    synchronous_fence = getattr(runtime, "_fence_session", None)
    if synchronous_fence is not None:
        synchronous_fence(target, "interrupted_by_operator")
    target_after_claim = _runtime_queue_depth(runtime, target)
    aggregate_after_claim = runtime._operator_queue_snapshot()

    release_decode.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        peer_snapshot = runtime.snapshot(peer)
        if peer_snapshot is not None and peer_snapshot.session.accounted_samples == 1_000:
            break
        await asyncio.sleep(0.005)
    else:
        raise RuntimeError("peer canonical work did not complete after target release")

    started_while_commit_held = sum(
        event.kind == "canonical_started" for event in runtime.events(target)
    )
    await runtime.abort(target, "interrupted_by_operator")
    target_after_release = _runtime_queue_depth(runtime, target)
    target_snapshot = runtime.snapshot(target)
    target_events = runtime.events(target)
    canonical_dispositions = [
        dict(event.payload)
        for event in target_events
        if event.kind == "canonical_discarded"
    ]
    refinement_dispositions = [
        dict(event.payload)
        for event in target_events
        if event.kind == "rolling_decode_completed"
        and event.payload.get("outcome") == "session_terminal"
    ]
    aggregate_before_repeat = runtime._operator_queue_snapshot()
    repeated = await runtime.abort(target, "interrupted_by_operator")
    aggregate_after_repeat = runtime._operator_queue_snapshot()
    assert target_snapshot is not None
    return {
        "target_queue_before": target_before,
        "target_queue_after_claim": target_after_claim,
        "target_queue_after_release": target_after_release,
        "aggregate_before": aggregate_before,
        "aggregate_after_claim": aggregate_after_claim,
        "aggregate_before_repeat": aggregate_before_repeat,
        "aggregate_after_repeat": aggregate_after_repeat,
        "batch_before": aggregate_before["batch"],
        "batch_after_claim": aggregate_after_claim["batch"],
        "canonical_dispositions": canonical_dispositions,
        "canonical_started_before_claim": started_before_claim,
        "canonical_started_while_commit_held": started_while_commit_held,
        "queued_canonical_item_id": canonical.item_id,
        "queued_refinement_item_id": refinement.item_id,
        "refinement_dispositions": refinement_dispositions,
        "synchronous_runtime_fence_available": synchronous_fence is not None,
        "target_accounted_samples": target_snapshot.session.accounted_samples,
        "target_status": target_snapshot.session.status,
        "peer_accounted_samples": runtime.snapshot(peer).session.accounted_samples,
        "repeated_status": repeated.session.status,
    }


async def run(suppress: str | None) -> dict[str, object]:
    runtime_discard = await _runtime_discard_probe()
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
        "runtime_target_queue_discarded": runtime_discard["target_queue_before"] == {
            "canonical": 1,
            "refinement": 1,
            "provisional": 1,
        }
        and runtime_discard["target_queue_after_claim"] == {
            "canonical": 0,
            "refinement": 0,
            "provisional": 0,
        }
        and runtime_discard["target_queue_after_release"] == {
            "canonical": 0,
            "refinement": 0,
            "provisional": 0,
        },
        "runtime_aggregate_reconciled": _aggregate_queue_depth(
            runtime_discard["aggregate_before"]
        )
        == 4
        and _aggregate_queue_depth(runtime_discard["aggregate_after_claim"]) == 1
        and runtime_discard["batch_before"]
        == runtime_discard["batch_after_claim"]
        == 1,
        "runtime_late_result_and_peer": runtime_discard["target_accounted_samples"] == 0
        and runtime_discard["target_status"] == "aborted"
        and runtime_discard["peer_accounted_samples"] == 1_000,
        "runtime_claim_precedes_owner_await": runtime_discard[
            "synchronous_runtime_fence_available"
        ]
        and runtime_discard["canonical_started_before_claim"]
        == runtime_discard["canonical_started_while_commit_held"]
        == 1,
        "runtime_discard_events_terminal": runtime_discard["canonical_dispositions"]
        == [
            {
                "item_id": runtime_discard["queued_canonical_item_id"],
                "reason": "session_terminal",
                "span_count": 1,
            }
        ]
        and len(runtime_discard["refinement_dispositions"]) == 1
        and runtime_discard["refinement_dispositions"][0]["item_id"]
        == runtime_discard["queued_refinement_item_id"],
        "runtime_repeat_idempotent": runtime_discard["aggregate_before_repeat"]
        == runtime_discard["aggregate_after_repeat"]
        and runtime_discard["repeated_status"] == "aborted",
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
        "structural_question": (
            "Can one opaque host interrupt fence exactly one active Meeting and return only "
            "after existing owners make its durable prefix terminal?"
        ),
        "minimum_primitives": [
            "one existing Unix Operator Control command",
            "one synchronous per-Meeting owner claim",
            "one runtime-owned per-session arbiter discard",
            "existing Live/File serialized settlement",
            "one service-owned in-flight interrupt task",
        ],
        "invariants": [
            "claim grants no Account or content access",
            "canonical, refinement, and provisional target queues become zero before await",
            "discarded canonical and refinement admissions receive typed terminal dispositions",
            "queued and late target results cannot commit after claim",
            "runtime and operator queue counters reconcile without touching peer work",
            "unrelated work continues",
            "available becomes metadata-identical partial and absent becomes unavailable",
            "command completion implies durable terminal truth and source cleanup",
        ],
        "assumptions_unknowns": [
            "production owners already settle transcript/audio/cleanup truth",
            (
                "a running provider request cannot be cancelled and remains fenced by "
                "terminal authority"
            ),
        ],
        "falsifier": (
            "any target queue or counter survives abort, late target commit, peer cancellation, "
            "complete audio, surviving source, abandoned cancelled handler, or content-bearing "
            "response"
        ),
        "tool_decision": (
            "the real LiveServiceRuntime per-session arbiter is necessary to measure queue "
            "ownership/accounting; the production AccountLifecycle plus thin Live/File adapters "
            "measure claim-before-await and cancellation, while models, browsers, and network "
            "cannot decide either policy"
        ),
        "measurements": measurements,
        "runtime_discard": runtime_discard,
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
