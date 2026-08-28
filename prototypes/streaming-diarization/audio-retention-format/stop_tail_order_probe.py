#!/usr/bin/env python3
"""PROTOTYPE: measure Stop-tail persistence ordering on the real HTTP/runtime path."""

from __future__ import annotations

import asyncio
import json
import platform
import sqlite3
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from tests.phase2.test_owner_bound_live_meeting import (
    _ManualTerminalScheduler,
    feed_two_lane_span,
    make_app,
    provision,
    session,
    wait_snapshot,
)


def run_case(root: Path, *, disable_intent_latch: bool) -> dict[str, object]:
    database = root / ("rejected.sqlite3" if disable_intent_latch else "candidate.sqlite3")
    sessions = asyncio.run(provision(database))
    terminal_scheduler = _ManualTerminalScheduler()
    app = make_app(
        database,
        terminal_text="[0][S01]undurable terminal words[0.000375]",
        terminal_scheduler=terminal_scheduler,
    )
    trace: list[dict[str, object]] = []
    started = time.monotonic()

    def record(kind: str, **fields: object) -> None:
        trace.append(
            {
                "elapsed_ms": round((time.monotonic() - started) * 1_000, 3),
                "kind": kind,
                **fields,
            }
        )

    with TestClient(app, base_url="https://moss.test") as client:
        if disable_intent_latch:
            app.state.phase2_live.begin_stop = lambda meeting_id: None

            async def raw_stop_without_latch(binding, deadline, intent):
                del intent
                return await app.state.phase2_live.runtime.stop(
                    binding.handle.meeting_id,
                    deadline,
                )

            app.state.phase2_live.stop = raw_stop_without_latch
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        durable_prefix = wait_snapshot(
            client,
            meeting_id,
            lambda body: body["meeting_transcript_version"] == 1,
        )
        binding = app.state.phase2_live._bindings[meeting_id]
        runtime = app.state.phase2_live.runtime

        async def fail_stop_tail_commit(document, *, terminal=False):
            del document, terminal
            snapshot = runtime.snapshot(meeting_id)
            status = None if snapshot is None else snapshot.session.status
            record("commit_enter", raw_session_status=status)
            record("commit_fail", raw_session_status=status)
            raise sqlite3.OperationalError("injected Stop-tail persistence failure")

        binding.handle.commit_transcript = fail_stop_tail_commit
        record("stop_request")
        response = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        record("stop_response", status_code=response.status_code)

        deadline = time.monotonic() + 2.0
        meeting: dict[str, object] | None = None
        while time.monotonic() < deadline:
            meeting = client.get(f"/api/meetings/{meeting_id}").json()
            if meeting["status"] == "interrupted" and binding.terminal_persisted:
                break
            time.sleep(0.005)
        public = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        raw = runtime.snapshot(meeting_id)
        stage_path = database.parent / "meetings" / "sub-a" / meeting_id / ".live-mix.pcm"
        return {
            "mode": (
                "rejected_without_intent_latch"
                if disable_intent_latch
                else "production_intent_latch"
            ),
            "python": platform.python_version(),
            "stop": {
                "status_code": response.status_code,
                "body": response.json(),
            },
            "last_durable_prefix_preserved": (
                public["snapshot"]["session"]["effective_transcript"]
                == durable_prefix["snapshot"]["session"]["effective_transcript"]
            ),
            "public": public,
            "raw": None if raw is None else raw.to_dict(),
            "meeting": meeting,
            "binding": {
                "capture_fenced": binding.capture_fenced,
                "persistence_failure": binding.persistence_failure,
                "terminal_persisted": binding.terminal_persisted,
            },
            "raw_stage_exists": stage_path.exists(),
            "terminal_finalizer_pending": terminal_scheduler.pending,
            "trace": trace,
        }


async def stop_attempt_lifetime() -> dict[str, object]:
    from moss_transcribe_diarize.app.live_session import LiveSessionClosed
    from moss_transcribe_diarize.app.phase2_live import Phase2LiveMeetings

    first_snapshot = object()

    class Runtime:
        def __init__(self) -> None:
            self.calls = 0
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def stop(self, session_id: str, deadline: float):
            del session_id, deadline
            self.calls += 1
            if self.calls == 1:
                self.entered.set()
                await self.release.wait()
                return first_snapshot
            if self.calls == 2:
                raise LiveSessionClosed("already closed")
            if self.calls == 3:
                raise TimeoutError("first retry attempt timed out")
            return "retried"

    runtime = Runtime()
    live = Phase2LiveMeetings(runtime, audio_archive=None, audio_stages=None)
    binding = SimpleNamespace(raw_stop_attempt=None, handle=SimpleNamespace(meeting_id="m"))
    live._bindings["m"] = binding

    first_intent = live.begin_stop("m")
    first = asyncio.create_task(live.stop(binding, 1.0, first_intent))
    await runtime.entered.wait()
    concurrent_intent = live.begin_stop("m")
    concurrent = asyncio.create_task(live.stop(binding, 1.0, concurrent_intent))
    runtime.release.set()
    concurrent_results = await asyncio.gather(first, concurrent)
    live.release_stop(first_intent)
    live.release_stop(concurrent_intent)

    sequential_error = None
    sequential_intent = live.begin_stop("m")
    try:
        await live.stop(binding, 1.0, sequential_intent)
    except LiveSessionClosed as exc:
        sequential_error = str(exc)
    live.release_stop(sequential_intent)

    timeout_error = None
    timeout_intent = live.begin_stop("m")
    try:
        await live.stop(binding, 0.0, timeout_intent)
    except TimeoutError as exc:
        timeout_error = str(exc)
    live.release_stop(timeout_intent)
    retry_intent = live.begin_stop("m")
    retried = await live.stop(binding, 1.0, retry_intent)
    live.release_stop(retry_intent)

    anonymous = live.begin_stop("m")
    foreign = live.begin_stop("m")
    assert anonymous is not None and foreign is not None
    all_rejected_attempt = anonymous.attempt
    live.release_stop(anonymous)
    retained_after_one_rejection = binding.raw_stop_attempt is all_rejected_attempt
    live.release_stop(anonymous)
    duplicate_release_entrants = all_rejected_attempt.entrants
    live.release_stop(foreign)
    return {
        "concurrent_shared_snapshot": concurrent_results == [first_snapshot, first_snapshot],
        "calls_after_concurrent": 1,
        "sequential_reached_runtime": sequential_error == "already closed",
        "timeout_reached_runtime": timeout_error == "first retry attempt timed out",
        "retry_result": retried,
        "total_runtime_calls": runtime.calls,
        "latch_cleared": binding.raw_stop_attempt is None,
        "all_unauthorized": {
            "retained_after_one_rejection": retained_after_one_rejection,
            "duplicate_release_entrants": duplicate_release_entrants,
            "cleared_after_last_rejection": binding.raw_stop_attempt is None,
        },
    }


def preauth_claim_prototype() -> dict[str, object]:
    """Compare the rejected owner bit with the minimum entrant-count reducer."""

    @dataclass
    class RejectedClaim:
        attempt: object
        owner: bool

    rejected_attempt = object()
    rejected_current: object | None = rejected_attempt
    rejected_foreign = RejectedClaim(rejected_attempt, owner=True)
    rejected_owner = RejectedClaim(rejected_attempt, owner=False)
    if rejected_foreign.owner:
        rejected_current = None

    @dataclass
    class Attempt:
        entrants: int = 0
        started: bool = False
        cleared: bool = False

    @dataclass
    class Claim:
        attempt: Attempt
        released: bool = False

    class Claims:
        def __init__(self) -> None:
            self.current: Attempt | None = None

        def begin(self) -> Claim:
            if self.current is None:
                self.current = Attempt()
            self.current.entrants += 1
            return Claim(self.current)

        def release(self, claim: Claim) -> None:
            if claim.released:
                return
            claim.released = True
            claim.attempt.entrants -= 1
            if claim.attempt.entrants == 0 and not claim.attempt.started:
                claim.attempt.cleared = True
                if self.current is claim.attempt:
                    self.current = None

        def start(self, claim: Claim) -> None:
            claim.attempt.started = True

        def complete(self, claim: Claim) -> None:
            claim.attempt.cleared = True
            if self.current is claim.attempt:
                self.current = None

    joined = Claims()
    foreign = joined.begin()
    owner = joined.begin()
    joined.release(foreign)
    joined_after_foreign_release = {
        "entrants": owner.attempt.entrants,
        "started": owner.attempt.started,
        "identity_retained": joined.current is owner.attempt,
    }
    joined.start(owner)
    joined.release(owner)
    joined_after_owner_release = {
        "entrants": owner.attempt.entrants,
        "started": owner.attempt.started,
        "identity_retained_until_runtime_outcome": joined.current is owner.attempt,
    }
    joined.complete(owner)

    all_rejected = Claims()
    anonymous = all_rejected.begin()
    foreign_only = all_rejected.begin()
    all_rejected.release(anonymous)
    all_rejected.release(foreign_only)

    return {
        "rejected_owner_bit": {
            "foreign_claim_owned_attempt": rejected_foreign.owner,
            "authorized_join_owned_attempt": rejected_owner.owner,
            "identity_cleared_by_foreign_release": rejected_current is None,
        },
        "entrant_count_candidate": {
            "joined_after_foreign_release": joined_after_foreign_release,
            "joined_after_owner_release": joined_after_owner_release,
            "cleared_by_runtime_outcome": joined.current is None,
            "all_unauthorized_release_clears": all_rejected.current is None,
            "duplicate_release_is_noop": (
                all_rejected.release(foreign_only) is None
                and foreign_only.attempt.entrants == 0
            ),
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="moss-stop-order-") as temporary:
        root = Path(temporary)
        output = {
            "structural_question": (
                "How can concurrent pre-authorization Stop entrants share one scheduling "
                "intent without one rejected entrant cancelling an authorized Stop outcome?"
            ),
            "minimum_primitives": [
                "route-entry intent latch: the only boundary before authorization yields",
                "entrant count: the only fact distinguishing one rejected request from all requests",
                "started raw Stop: authority-bound conversion from intent to mutation",
                "single raw outcome: releases the persistence fence and clears attempt identity",
            ],
            "invariants": [
                "route entry grants no account authority and performs no mutation",
                "each request releases exactly one entrant claim",
                "only zero entrants on an unstarted attempt may abandon it",
                "after any authorized start only the raw runtime outcome clears the attempt",
                "accepted Stop returns 200 after terminal durability",
                "last durable transcript prefix survives persistence failure",
                "Meeting ends interrupted with partial or unavailable audio",
                "no raw stage survives the response",
                "Python task wake order cannot change the public result",
            ],
            "assumptions_unknowns": [
                "Python task wake order differs and must not become product policy",
                "a route-entry intent remains scheduling state only until owner-bound adapter.stop",
            ],
            "falsifier": (
                "a foreign, anonymous, or cancelled entrant clears a joined authorized Stop; "
                "all rejected entrants leak; concurrent owners duplicate raw Stop; timeout blocks retry; "
                "or either Python returns before terminal durability or retains raw PCM"
            ),
            "tool_decision": (
                "use a minimal entrant-count reducer to select claim semantics, then the production "
                "route-entry in-flight intent latch and HTTP/runtime/publication/archive path to "
                "falsify authorization, scheduling, durability, and cleanup boundaries"
            ),
            "preauth_claims": preauth_claim_prototype(),
            "cases": [
                run_case(root, disable_intent_latch=True),
                run_case(root, disable_intent_latch=False),
            ],
            "attempt_lifetime": asyncio.run(stop_attempt_lifetime()),
        }
        print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
