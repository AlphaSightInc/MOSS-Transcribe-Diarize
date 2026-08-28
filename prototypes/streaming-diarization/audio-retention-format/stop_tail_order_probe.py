#!/usr/bin/env python3
"""PROTOTYPE: measure Stop-tail persistence ordering on the real HTTP/runtime path."""

from __future__ import annotations

import asyncio
import json
import platform
import sqlite3
import sys
import tempfile
import threading
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


def public_stop_concurrency(root: Path) -> dict[str, object]:
    """Hold raw Stop after v2 closes and measure public concurrent/sequential outcomes."""

    database = root / "public-concurrent.sqlite3"
    sessions = asyncio.run(provision(database))
    app = make_app(database)
    outcomes: dict[str, object] = {}
    raw_stop_entered = threading.Event()
    shared_stop_entered = threading.Event()
    release_raw_stop = threading.Event()
    second_finished = threading.Event()

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        feed_two_lane_span(client, meeting_id)
        wait_snapshot(client, meeting_id, lambda body: body["meeting_transcript_version"] == 1)
        runtime = app.state.phase2_live.runtime
        original_runtime_stop = runtime.stop
        original_adapter_stop = app.state.phase2_live.stop
        raw_calls = 0
        adapter_calls = 0

        async def held_runtime_stop(session_id, deadline):
            nonlocal raw_calls
            raw_calls += 1
            raw_stop_entered.set()
            await asyncio.to_thread(release_raw_stop.wait)
            return await original_runtime_stop(session_id, deadline)

        async def observed_adapter_stop(binding, deadline, intent):
            nonlocal adapter_calls
            adapter_calls += 1
            if adapter_calls == 2:
                shared_stop_entered.set()
            return await original_adapter_stop(binding, deadline, intent)

        runtime.stop = held_runtime_stop
        app.state.phase2_live.stop = observed_adapter_stop

        def stop_request(name: str) -> None:
            try:
                outcomes[name] = client.post(
                    f"/api/live/sessions/{meeting_id}/stop",
                    json={"deadline": 2.0},
                )
            except BaseException as exc:  # pragma: no cover - printed probe state.
                outcomes[f"{name}_error"] = repr(exc)
            finally:
                if name == "second":
                    second_finished.set()

        first = threading.Thread(target=stop_request, args=("first",))
        first.start()
        if not raw_stop_entered.wait(timeout=2):
            raise RuntimeError("first public Stop never reached the held raw runtime")
        second = threading.Thread(target=stop_request, args=("second",))
        second.start()
        deadline = time.monotonic() + 2.0
        while (
            not second_finished.is_set()
            and not shared_stop_entered.is_set()
            and time.monotonic() < deadline
        ):
            time.sleep(0.001)
        second_returned_before_raw_outcome = second_finished.is_set()
        release_raw_stop.set()
        first.join(timeout=5)
        second.join(timeout=5)
        if first.is_alive() or second.is_alive():
            raise RuntimeError("public concurrent Stop probe did not quiesce")
        if "first_error" in outcomes or "second_error" in outcomes:
            raise RuntimeError(f"public concurrent Stop probe failed: {outcomes}")
        first_response = outcomes["first"]
        second_response = outcomes["second"]
        sequential_response = client.post(
            f"/api/live/sessions/{meeting_id}/stop",
            json={"deadline": 2.0},
        )
        return {
            "second_reached_shared_stop": shared_stop_entered.is_set(),
            "second_returned_before_raw_outcome": second_returned_before_raw_outcome,
            "raw_stop_calls": raw_calls,
            "adapter_stop_calls": adapter_calls,
            "first_status": first_response.status_code,
            "second_status": second_response.status_code,
            "first_raw_terminal_status": first_response.json().get("raw_terminal_status"),
            "second_raw_terminal_status": second_response.json().get(
                "raw_terminal_status"
            ),
            "second_failure": (second_response.json().get("failure") or {}).get("code"),
            "sequential_status": sequential_response.status_code,
        }


def public_v2_terminal_conflicts(root: Path) -> dict[str, object]:
    """Prove already failed/aborted v2 capture remains a public terminal conflict."""

    from moss_transcribe_diarize.app.live_lane_contract import LiveLane

    outcomes: dict[str, object] = {}
    for terminal in ("failed", "aborted"):
        database = root / f"v2-{terminal}.sqlite3"
        sessions = asyncio.run(provision(database))
        app = make_app(database)
        with TestClient(app, base_url="https://moss.test") as client:
            session(client, sessions["a"])
            meeting_id = client.post("/api/live/sessions").json()["id"]
            v2_session = app.state.live_v2_sessions.get(meeting_id)
            if terminal == "failed":
                v2_session.fail_lane(LiveLane.MICROPHONE, "probe_failure")
                client.portal.call(v2_session.stop, 0.0)
            else:
                v2_session.abort("probe_abort")
            response = client.post(
                f"/api/live/sessions/{meeting_id}/stop",
                json={"deadline": 2.0},
            )
            outcomes[terminal] = {
                "status": response.status_code,
                "failure": (response.json().get("failure") or {}).get("code"),
                "v2_status": (response.json().get("v2_session") or {}).get("status"),
            }
    return outcomes


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


def derive_verdict(output: dict[str, object]) -> dict[str, object]:
    """Gate every measured contract boundary; keep failures visible in printed JSON."""

    cases = output["cases"]
    assert isinstance(cases, list)
    rejected, candidate = cases
    assert isinstance(rejected, dict) and isinstance(candidate, dict)
    claims = output["preauth_claims"]
    lifetime = output["attempt_lifetime"]
    assert isinstance(claims, dict) and isinstance(lifetime, dict)

    rejected_owner_bit = claims["rejected_owner_bit"]
    entrant_count = claims["entrant_count_candidate"]
    all_unauthorized = lifetime["all_unauthorized"]
    assert isinstance(rejected_owner_bit, dict)
    assert isinstance(entrant_count, dict)
    assert isinstance(all_unauthorized, dict)

    joined_after_foreign = entrant_count["joined_after_foreign_release"]
    joined_after_owner = entrant_count["joined_after_owner_release"]
    assert isinstance(joined_after_foreign, dict)
    assert isinstance(joined_after_owner, dict)

    candidate_stop = candidate["stop"]
    candidate_public = candidate["public"]
    candidate_raw = candidate["raw"]
    candidate_meeting = candidate["meeting"]
    candidate_binding = candidate["binding"]
    public_concurrency = output["public_stop_concurrency"]
    terminal_conflicts = output["public_v2_terminal_conflicts"]
    assert isinstance(candidate_stop, dict)
    assert isinstance(candidate_public, dict)
    assert isinstance(candidate_raw, dict)
    assert isinstance(candidate_meeting, dict)
    assert isinstance(candidate_binding, dict)
    assert isinstance(public_concurrency, dict)
    assert isinstance(terminal_conflicts, dict)
    rejected_binding = rejected["binding"]
    rejected_meeting = rejected["meeting"]
    rejected_raw = rejected["raw"]
    assert isinstance(rejected_binding, dict)
    assert isinstance(rejected_meeting, dict)
    assert isinstance(rejected_raw, dict)
    python_line = ".".join(str(candidate["python"]).split(".")[:2])
    rejected_scheduler_outcome = {
        "3.10": (409, "aborted"),
        "3.12": (200, "closed"),
    }.get(python_line)

    checks = {
        "rejected_control_exposes_scheduler_outcome": rejected_scheduler_outcome
        == (rejected["stop"]["status_code"], rejected_raw["session"]["status"]),
        "rejected_control_still_settles_truthfully": rejected["last_durable_prefix_preserved"]
        is True
        and rejected_meeting["status"] == "interrupted"
        and rejected_meeting["audio"]["state"] == "partial"
        and rejected_binding["terminal_persisted"] is True
        and rejected["raw_stage_exists"] is False,
        "rejected_owner_bit_reproduced": rejected_owner_bit
        == {
            "foreign_claim_owned_attempt": True,
            "authorized_join_owned_attempt": False,
            "identity_cleared_by_foreign_release": True,
        },
        "foreign_release_retains_joined_owner": joined_after_foreign
        == {"entrants": 1, "started": False, "identity_retained": True},
        "owner_release_waits_for_runtime_outcome": joined_after_owner
        == {
            "entrants": 0,
            "started": True,
            "identity_retained_until_runtime_outcome": True,
        },
        "runtime_outcome_clears_joined_attempt": entrant_count[
            "cleared_by_runtime_outcome"
        ]
        is True,
        "all_unauthorized_claims_clear": entrant_count[
            "all_unauthorized_release_clears"
        ]
        is True,
        "duplicate_claim_release_is_noop": entrant_count["duplicate_release_is_noop"]
        is True,
        "concurrent_stops_share_snapshot": lifetime["concurrent_shared_snapshot"] is True,
        "concurrent_stops_call_runtime_once": lifetime["calls_after_concurrent"] == 1,
        "sequential_stop_reaches_runtime": lifetime["sequential_reached_runtime"] is True,
        "timeout_reaches_runtime": lifetime["timeout_reached_runtime"] is True,
        "timeout_allows_retry": lifetime["retry_result"] == "retried",
        "attempt_lifetime_calls_are_exact": lifetime["total_runtime_calls"] == 4,
        "attempt_lifetime_clears": lifetime["latch_cleared"] is True,
        "one_unauthorized_release_retains_peer": all_unauthorized[
            "retained_after_one_rejection"
        ]
        is True,
        "duplicate_unauthorized_release_preserves_count": all_unauthorized[
            "duplicate_release_entrants"
        ]
        == 1,
        "last_unauthorized_release_clears": all_unauthorized[
            "cleared_after_last_rejection"
        ]
        is True,
        "production_stop_returns_200": candidate_stop["status_code"] == 200,
        "production_stop_reports_closed_raw_capture": candidate_stop["body"][
            "raw_terminal_status"
        ]
        == "closed",
        "last_durable_prefix_is_preserved": candidate["last_durable_prefix_preserved"]
        is True,
        "public_snapshot_is_closed": candidate_public["snapshot"]["session"]["status"]
        == "closed",
        "raw_snapshot_is_closed": candidate_raw["session"]["status"] == "closed",
        "terminal_meeting_is_interrupted": candidate_meeting["status"] == "interrupted",
        "retained_audio_is_partial": candidate_meeting["audio"]["state"] == "partial",
        "capture_is_fenced": candidate_binding["capture_fenced"] is True,
        "persistence_failure_is_explicit": candidate_binding["persistence_failure"]
        == "transcript_persistence_failed",
        "terminal_state_is_durable": candidate_binding["terminal_persisted"] is True,
        "raw_stage_is_absent": candidate["raw_stage_exists"] is False,
        "held_terminal_finalizer_remains_pending": candidate["terminal_finalizer_pending"]
        == 1,
        "concurrent_public_stop_reaches_shared_attempt": public_concurrency[
            "second_reached_shared_stop"
        ]
        is True,
        "concurrent_public_stop_waits_for_raw_outcome": public_concurrency[
            "second_returned_before_raw_outcome"
        ]
        is False,
        "concurrent_public_stop_calls_raw_once": public_concurrency["raw_stop_calls"] == 1,
        "concurrent_public_stop_calls_adapter_twice": public_concurrency[
            "adapter_stop_calls"
        ]
        == 2,
        "concurrent_public_stops_both_return_200": public_concurrency["first_status"]
        == public_concurrency["second_status"]
        == 200,
        "concurrent_public_stops_both_report_closed": public_concurrency[
            "first_raw_terminal_status"
        ]
        == public_concurrency["second_raw_terminal_status"]
        == "closed",
        "concurrent_public_stop_has_no_terminal_failure": public_concurrency[
            "second_failure"
        ]
        is None,
        "sequential_public_stop_remains_conflict": public_concurrency[
            "sequential_status"
        ]
        == 409,
        "failed_v2_remains_conflict": terminal_conflicts["failed"]
        == {"status": 409, "failure": "v2_session_terminal", "v2_status": "failed"},
        "aborted_v2_remains_conflict": terminal_conflicts["aborted"]
        == {"status": 409, "failure": "v2_session_terminal", "v2_status": "aborted"},
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
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
            "public_stop_concurrency": public_stop_concurrency(root),
            "public_v2_terminal_conflicts": public_v2_terminal_conflicts(root),
        }
        output["verdict"] = derive_verdict(output)
        print(json.dumps(output, indent=2, sort_keys=True))
        if output["verdict"]["status"] != "PASS":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
