"""Does the measuring client see the surface the meeting ended on, or the one it left?

Plan §12.3 puts the terminal decode deliberately BEHIND the stop response. Iteration 27
measured what that costs the instrument on the deployed service (finding F1 of
`evidence/live-convergence-0824/M4-deployed-terminal/`): `run_service_replay` returned when
`POST /stop` answered, so `trace.jsonl` carried the ROLLING surface, the trace ended at
`terminal_finalization_started`, and the terminal numbers had to be recovered afterwards by
polling the session by hand. Every paired driver in this campaign calls that one client, so
the M4 exit would have scored five rolling transcripts and reported that terminal
convergence does not work.

This instrument answers one question: with the wait shipped, does a run report the terminal
surface -- and does it still cost nothing to the three meetings that get no terminal pass?

It runs the real client against an in-memory runtime with E4 wired (the same fixture
`tests/test_live_service_replay.py` uses), on a scripted clock, with a manual terminal
scheduler so the pass lands at a chosen poll rather than a raced one. Nothing decodes: zero
MOSS requests, no GPU, no service.

    python verify_replay_terminal_wait.py [--output gates.json]
    python verify_replay_terminal_wait.py --selftest

Exit 0 iff every gate passes (or, under `--selftest`, iff every gate reacts to its own defect).
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize import live_service_replay as R  # noqa: E402

# The fixture is the test module's, imported rather than restated: a client that behaves one
# way under `pytest` and another way here would be two clients.
import tests.test_live_service_replay as T  # noqa: E402

#: The four §7.4 events one landed terminal pass writes, in the order plan §12.3 requires.
TERMINAL_EVENT_ORDER = (
    "terminal_finalization_started",
    "text_revision_applied",
    "terminal_finalization_completed",
    "session_tape_released",
)

#: The three paired drivers of this campaign. They share one client, which is the whole
#: reason the wait belongs in the client: none of them is edited by this change.
PAIRED_DRIVERS = (
    "prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py",
    "prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py",
    "prototypes/streaming-diarization/live-convergence/remeasure_one_case.py",
)

#: What the caller asks for in the observations below, so "the artifact names the caller's
#: deadline" is checkable against a value no default could produce by accident.
CALLER_DEADLINE = 12.5


# ---------------------------------------------------------------- running the client


def replay(**kwargs) -> dict:
    """One replayed meeting, and everything an outside reader could learn from it."""

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        failure = None
        try:
            T._run_terminal_replay(root, finalization_deadline=CALLER_DEADLINE, **kwargs)
        except Exception as exc:  # the artifacts are written on the failure path too
            failure = {"type": type(exc).__name__, "message": str(exc),
                       "exit_code": getattr(exc, "exit_code", None),
                       "failure_kind": getattr(exc, "failure_kind", None)}
        run_dir = root / "out" / "run-001"
        trace = T._jsonl(run_dir / "trace.jsonl") if (run_dir / "trace.jsonl").exists() else []
        summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {}
        manifest_path = root / "out" / "replay-manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return {"failure": failure, "trace": trace, "summary": summary, "manifest": manifest}


def record(trace: list[dict], kind: str) -> dict | None:
    for entry in trace:
        if entry["kind"] == kind:
            return entry
    return None


def event_kinds(trace: list[dict]) -> list[str]:
    return [entry["event"]["kind"] for entry in trace if entry["kind"] == "service_event"]


def surface(trace: list[dict]) -> dict:
    """What the run published: the words, who owns them, and what the session called it."""

    terminal = record(trace, "terminal")
    if terminal is None or "snapshot" not in terminal:
        return {"status": None, "authorities": [], "words": [], "finalization_status": None}
    session = terminal["snapshot"]["session"]
    segments = session["effective_transcript"]
    return {
        "status": terminal["status"],
        "finalization_status": session["finalization_status"],
        "authorities": sorted({segment["authority"] for segment in segments}),
        "words": [word for segment in segments for word in segment["text"].split()],
        "text_revision_version": session["text_revision_version"],
    }


#: The summary fields a scorer reads. Compared between the pre-wait client and this one for
#: a meeting that gets no terminal pass; the rest of the summary carries per-event sequence
#: numbers that two identical runs already disagree about (the pump batches what is ready).
INERT_SUMMARY_FIELDS = (
    "status",
    "frame_count",
    "accepted_samples",
    "accounted_samples",
    "committed_prefix_hash",
    "canonical_decode_rtf_passed",
)


def inert_view(artifacts: dict) -> dict:
    """What a run says, with the orderings two identical runs already disagree about removed.

    Event *order* is run-to-run noise in this fixture -- the canonical pump batches whatever
    is ready -- so an order-sensitive comparison would report noise as a side effect. What is
    not noise: which records a run wrote, which events it saw, the surface it published, and
    the numbers a scorer reads. The new wait record is excluded by name because it is the one
    thing this change is supposed to add.
    """

    trace = artifacts["trace"]
    counts: dict[str, int] = {}
    for entry in trace:
        if entry["kind"] != "terminal_finalization_wait":
            counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    events: dict[str, int] = {}
    for kind in event_kinds(trace):
        events[kind] = events.get(kind, 0) + 1
    return {
        "record_kinds": sorted(counts.items()),
        "event_kinds": sorted(events.items()),
        "surface": surface(trace),
        "summary": {name: artifacts["summary"].get(name) for name in INERT_SUMMARY_FIELDS},
    }


# ---------------------------------------------------------------- the mutant clients

#: Bound once, at import, because the mutants below run while the module attribute is
#: replaced: a mutant that reached for `R._await_terminal_finalization` would call itself.
_SHIPPED_WAIT = R._await_terminal_finalization



def _wait_not_at_all(service, session_id, *, stop_snapshot, next_event_seq, sink, **kwargs):
    """The client as it was before this change: stop answered, so the run is over."""

    del service, session_id, kwargs
    return stop_snapshot, next_event_seq, {
        "stop_finalization_status": stop_snapshot.session.finalization_status,
        "finalization_status": stop_snapshot.session.finalization_status,
        "waited": False, "polls": 0, "elapsed_seconds": 0.0,
        "deadline_seconds": 0.0, "poll_seconds": 0.0,
        "text_revision_version": stop_snapshot.session.text_revision_version,
    }


def _wait_without_draining(service, session_id, *, stop_snapshot, next_event_seq, sink, **kwargs):
    """Waits for the status, never re-reads the stream: the surface lands, the story does not."""

    snapshot, _, wait = _SHIPPED_WAIT(
        service, session_id, stop_snapshot=stop_snapshot, next_event_seq=next_event_seq,
        sink=[], **kwargs
    )
    return snapshot, next_event_seq, wait


def _wait_reporting_the_stop_snapshot(service, session_id, *, stop_snapshot, **kwargs):
    """Waits correctly, then reports the surface as it was before the pass ran."""

    _, cursor, wait = _SHIPPED_WAIT(
        service, session_id, stop_snapshot=stop_snapshot, **kwargs
    )
    return stop_snapshot, cursor, wait


def _wait_swallowing_the_timeout(service, session_id, *, stop_snapshot, next_event_seq, **kwargs):
    """A pass that never answered, written up as a completed run."""

    try:
        return _SHIPPED_WAIT(
            service, session_id, stop_snapshot=stop_snapshot,
            next_event_seq=next_event_seq, **kwargs
        )
    except R.ServiceReplayFinalizationTimeout:
        return _wait_not_at_all(
            service, session_id, stop_snapshot=stop_snapshot,
            next_event_seq=next_event_seq, sink=kwargs["sink"]
        )


def _wait_on_its_own_deadline(service, session_id, **kwargs):
    """Ignores what the caller asked for and spends the module default instead."""

    kwargs["deadline_seconds"] = R.TERMINAL_FINALIZATION_DEADLINE_SECONDS
    return _SHIPPED_WAIT(service, session_id, **kwargs)


def _wait_always_claiming_it_waited(service, session_id, **kwargs):
    """Reports the wait it wishes it had done, rather than the one the stop response asked for."""

    snapshot, cursor, wait = _SHIPPED_WAIT(service, session_id, **kwargs)
    return snapshot, cursor, {**wait, "waited": True, "stop_finalization_status": "running"}


@contextlib.contextmanager
def patched(**overrides):
    original = {name: getattr(R, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(R, name, value)
        yield
    finally:
        for name, value in original.items():
            setattr(R, name, value)


# ---------------------------------------------------------------- observations


def observe() -> dict:
    """Four meetings and one control, through whatever client is installed right now."""

    landed = replay(finalizer=T._terminal_finalizer())
    none = replay(finalizer=None)
    unavailable = replay(finalizer=T._terminal_finalizer(), tape_bytes=None)
    never = replay(finalizer=T._terminal_finalizer(), delay_polls=None)
    # The reference the fix is measured against: the same fixture through the pre-fix client.
    with patched(_await_terminal_finalization=_wait_not_at_all):
        prefix_landed = replay(finalizer=T._terminal_finalizer())
        prefix_none = replay(finalizer=None)
    # Two shipped runs of the no-terminal meeting establish which fields move on their own,
    # so the inertness comparison below cannot mistake clock noise for a side effect.
    none_again = replay(finalizer=None)
    return {
        "landed": landed, "none": none, "unavailable": unavailable, "never": never,
        "prefix_landed": prefix_landed, "prefix_none": prefix_none, "none_again": none_again,
        "drivers": driver_facts(),
    }


def driver_facts() -> dict:
    """Which drivers call the client, and what they pass it -- parsed, not restated."""

    facts = {}
    for relative in PAIRED_DRIVERS:
        tree = ast.parse((REPO / relative).read_text())
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run_service_replay"
        ]
        facts[relative] = {
            "calls": len(calls),
            "keywords": sorted({kw.arg for call in calls for kw in call.keywords if kw.arg}),
        }
    return facts


# ---------------------------------------------------------------- gates


def run(obs: dict) -> dict:
    gates: list[dict] = []

    def gate(gate_id: str, claim: str, passed: bool, detail) -> None:
        gates.append({"id": gate_id, "claim": claim, "passed": bool(passed), "detail": detail})

    landed_wait = record(obs["landed"]["trace"], "terminal_finalization_wait") or {}
    none_wait = record(obs["none"]["trace"], "terminal_finalization_wait") or {}
    unavailable_wait = record(obs["unavailable"]["trace"], "terminal_finalization_wait") or {}
    stop_states = {
        "landed": landed_wait.get("stop_finalization_status"),
        "none": none_wait.get("stop_finalization_status"),
        "unavailable": unavailable_wait.get("stop_finalization_status"),
    }
    gate(
        "G-W1",
        "the stop response already names which meeting this is, and the run records it",
        stop_states == {"landed": "running", "none": "not_started", "unavailable": "unavailable"},
        stop_states,
    )

    before = surface(obs["prefix_landed"]["trace"])
    prefix_events = event_kinds(obs["prefix_landed"]["trace"])
    gate(
        "G-W2",
        "F1 reproduced: the pre-wait client publishes the rolling surface and stops reading "
        "at terminal_finalization_started",
        before["finalization_status"] == "running"
        and before["authorities"] == ["rolling"]
        and prefix_events[-1:] == ["terminal_finalization_started"],
        {"finalization_status": before["finalization_status"],
         "authorities": before["authorities"], "last_event": prefix_events[-1:]},
    )

    after = surface(obs["landed"]["trace"])
    gate(
        "G-W3",
        "the shipped client publishes the terminal surface instead",
        after["finalization_status"] == "final"
        and after["authorities"] == ["terminal"]
        and after["words"] != before["words"]
        and obs["landed"]["summary"].get("finalization_status") == "final",
        {"finalization_status": after["finalization_status"],
         "authorities": after["authorities"],
         "words_before": before["words"], "words_after": after["words"],
         "summary_status": obs["landed"]["summary"].get("finalization_status")},
    )

    kinds = event_kinds(obs["landed"]["trace"])
    # After `session_closed`, because `text_revision_applied` has two producers by design and
    # the rolling one has already written several by the time the meeting ends.
    closed = kinds.index("session_closed") if "session_closed" in kinds else None
    after_close = kinds[closed + 1:] if closed is not None else []
    order = [after_close.index(kind) for kind in TERMINAL_EVENT_ORDER if kind in after_close]
    gate(
        "G-W4",
        "the four events that made that surface reach the trace, after session_closed, in order",
        all(kind in after_close for kind in TERMINAL_EVENT_ORDER) and order == sorted(order),
        {"after_session_closed": after_close, "order": order},
    )

    shipped = inert_view(obs["none"])
    unexplained = sorted(
        key for key in set(shipped) | set(inert_view(obs["prefix_none"]))
        if shipped.get(key) != inert_view(obs["prefix_none"]).get(key)
    )
    self_noise = sorted(
        key for key in set(shipped) | set(inert_view(obs["none_again"]))
        if shipped.get(key) != inert_view(obs["none_again"]).get(key)
    )
    gate(
        "G-W5",
        "a deployment that runs no terminal pass is not waited on, and its run is otherwise "
        "the pre-wait client's",
        none_wait.get("waited") is False
        and none_wait.get("polls") == 0
        and obs["none"]["summary"].get("finalization_status") == "not_started"
        and not unexplained
        and not self_noise,
        {"waited": none_wait.get("waited"), "polls": none_wait.get("polls"),
         "differs_from_pre_wait_client": unexplained,
         "differs_between_two_shipped_runs": self_noise},
    )

    gate(
        "G-W6",
        "a pass that ends without a surface is an answer, not a wait",
        unavailable_wait.get("waited") is False
        and obs["unavailable"]["failure"] is None
        and obs["unavailable"]["summary"].get("status") == "succeeded"
        and obs["unavailable"]["summary"].get("finalization_status") == "unavailable"
        and surface(obs["unavailable"]["trace"])["authorities"] == ["rolling"],
        {"waited": unavailable_wait.get("waited"),
         "summary": {k: obs["unavailable"]["summary"].get(k)
                     for k in ("status", "finalization_status")},
         "failure": obs["unavailable"]["failure"]},
    )

    never = obs["never"]
    gate(
        "G-W7",
        "a pass that never answers fails the run by name rather than publishing the rolling "
        "surface as complete",
        (never["failure"] or {}).get("type") == "ServiceReplayFinalizationTimeout"
        and (never["failure"] or {}).get("exit_code") == 8
        and never["summary"].get("failure_kind") == "finalization_timeout"
        and never["summary"].get("status") == "failed"
        and record(never["trace"], "terminal_finalization_wait") is None
        and surface(never["trace"])["status"] == "failed",
        {"failure": never["failure"],
         "summary": {k: never["summary"].get(k) for k in ("status", "failure_kind")},
         "wait_record": record(never["trace"], "terminal_finalization_wait") is not None},
    )

    gate(
        "G-W8",
        "the deadline is the caller's, and every artifact names the one that was spent",
        obs["landed"]["manifest"].get("cli", {}).get("finalization_deadline") == CALLER_DEADLINE
        and landed_wait.get("deadline_seconds") == CALLER_DEADLINE
        and f"deadline {CALLER_DEADLINE:.3f}s" in (never["failure"] or {}).get("message", ""),
        {"manifest": obs["landed"]["manifest"].get("cli", {}).get("finalization_deadline"),
         "wait_record": landed_wait.get("deadline_seconds"),
         "timeout_message": (never["failure"] or {}).get("message")},
    )

    drivers = obs["drivers"]
    gate(
        "G-W9",
        "all three paired drivers inherit the wait unedited: each calls the shared client and "
        "none of them declares a deadline of its own",
        len(drivers) == len(PAIRED_DRIVERS)
        and all(row["calls"] >= 1 for row in drivers.values())
        and all("finalization_deadline" not in row["keywords"] for row in drivers.values()),
        drivers,
    )

    return {"gates": gates, "passed": all(entry["passed"] for entry in gates)}


# ---------------------------------------------------------------- selftest


REACTIONS = (
    ("G-W3", "the client does not wait at all (the defect this change repairs)",
     {"_await_terminal_finalization": _wait_not_at_all}),
    ("G-W3", "`running` counts as an already-terminal answer",
     {"TERMINAL_FINALIZATION_SETTLED": frozenset(
         {"not_started", "final", "failed", "unavailable", "running"})}),
    ("G-W3", "the wait reports the stop snapshot it started from",
     {"_await_terminal_finalization": _wait_reporting_the_stop_snapshot}),
    ("G-W4", "the wait never re-reads the event stream it waited through",
     {"_await_terminal_finalization": _wait_without_draining}),
    ("G-W7", "a timed-out pass is written up as a completed run",
     {"_await_terminal_finalization": _wait_swallowing_the_timeout}),
    ("G-W8", "the wait spends its own deadline rather than the caller's",
     {"_await_terminal_finalization": _wait_on_its_own_deadline}),
    ("G-W5", "`not_started` is not treated as an answer",
     {"TERMINAL_FINALIZATION_SETTLED": frozenset({"final", "failed", "unavailable"})}),
    ("G-W6", "`unavailable` is not treated as an answer",
     {"TERMINAL_FINALIZATION_SETTLED": frozenset({"not_started", "final", "failed"})}),
    ("G-W1", "the record claims a wait the stop response never asked for",
     {"_await_terminal_finalization": _wait_always_claiming_it_waited}),
)


def selftest() -> int:
    control = run(observe())
    if not control["passed"]:
        print("SELFTEST FAIL: the control observations do not pass their own gates")
        for entry in control["gates"]:
            if not entry["passed"]:
                print(f"  {entry['id']}: {json.dumps(entry['detail'], ensure_ascii=False)}")
        return 1
    failures = []
    for gate_id, description, overrides in REACTIONS:
        with patched(**overrides):
            report = run(observe())
        broken = {entry["id"] for entry in report["gates"] if not entry["passed"]}
        caught = gate_id in broken
        extra = sorted(broken - {gate_id})
        print(f"[{'PASS' if caught else 'FAIL'}] {gate_id} reacts to: {description}"
              + (f"  also: {extra}" if caught and extra else "")
              + ("  (nothing failed)" if not broken else ""))
        if not caught:
            failures.append((gate_id, description))
    print("PASS" if not failures else f"FAIL: unreactive gates {failures}")
    return 0 if not failures else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--selftest", action="store_true",
                        help="install a defective client per gate and require that gate to react")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    report = run(observe())
    for entry in report["gates"]:
        print(f"[{'PASS' if entry['passed'] else 'FAIL'}] {entry['id']} {entry['claim']}")
        if not entry["passed"]:
            print(f"       {json.dumps(entry['detail'], ensure_ascii=False)}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote: {args.output}")
    print("PASS" if report["passed"] else "FAIL")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
