#!/usr/bin/env python3
"""Measure the live server's real frame-outcome contract, then check the client against it.

Question this probe answers
---------------------------
The x2 PRD turns on one fact that the capture client cannot observe from its own
comments: *which* HTTP 429 consumes the lane sequence and which does not. Get it
backwards in either direction and the lane wedges into `LiveV2OutOfOrderFrameError`
-> 409 forever. This probe measures the answer from the production ingress instead
of asserting it, and then fails if the browser client's committed contract table
disagrees with what it measured.

Method
------
1. Load the production `live_ingest` / `live_lane_contract` modules straight off
   disk (the package `__init__` drags in `transformers`, which a plain interpreter
   does not have; nothing here needs it).
2. Drive `LiveLaneIngress.accept` through one scenario per reachable outcome and
   record, for each: the raised exception, and `snapshot(lane).next_sequence`
   immediately before and after. The before/after pair IS the consumption fact.
3. Load `live_v2_ingress_failure_response` out of `live_transport.py` by source
   (that module imports starlette/fastapi, which a plain interpreter also does not
   have) and map each raised exception to its real (status, failure.code).
4. Parse `SERVER_FRAME_OUTCOMES` and `SERVER_SEQUENCE_CONSUMED` out of the
   committed TypeScript fake at
   `frontend/src/capture/laneIngressContract.ts` and compare.

One command:
    /opt/homebrew/bin/python3 evidence/phase1/x2-capture-client/probes/measure_frame_outcome_contract_probe.py

Exit 0 = the browser client's table matches the measured server. Exit 1 = drift on
either side.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
APP = REPO / "moss_transcribe_diarize" / "app"
CONTRACT_TS = REPO / "frontend" / "src" / "capture" / "laneIngressContract.ts"

PKG = "_moss_live_probe"


def _load_app_modules() -> types.ModuleType:
    """Import `live_ingest` without executing the heavyweight package __init__."""
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(APP)]
    sys.modules[PKG] = pkg
    for name in ("live_lane_contract", "live_ingest"):
        spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", APP / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{PKG}.{name}"] = module
        spec.loader.exec_module(module)
    return sys.modules[f"{PKG}.live_ingest"]


def _load_failure_response(ingest: types.ModuleType, contract: types.ModuleType):
    """Exec only the two response mappers out of live_transport.py.

    Importing that module needs starlette; the mapping functions themselves are
    plain dict builders over the exception types, so they are lifted by AST rather
    than reimplemented here -- a reimplementation would measure this probe, not the
    server.
    """
    source = (APP / "live_transport.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"live_v2_replay_conflict_response", "live_v2_ingress_failure_response"}
    picked = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    if len(picked) != len(wanted):
        raise SystemExit(f"live_transport.py no longer defines {sorted(wanted)}")
    namespace: dict = {
        "LiveV2OutOfOrderFrameError": contract.LiveV2OutOfOrderFrameError,
        "LiveV2PrunedReplayError": contract.LiveV2PrunedReplayError,
        "LiveV2LaneCapacityError": ingest.LiveV2LaneCapacityError,
        "LiveV2EpochDiscontinuityRequiredError": ingest.LiveV2EpochDiscontinuityRequiredError,
        "LiveV2StaleDeviceEpochError": ingest.LiveV2StaleDeviceEpochError,
        "Any": object,
    }
    exec(compile(ast.Module(body=picked, type_ignores=[]), "<live_transport>", "exec"), namespace)
    return namespace["live_v2_ingress_failure_response"]


def main() -> int:
    ingest = _load_app_modules()
    contract = sys.modules[f"{PKG}.live_lane_contract"]
    failure_response = _load_failure_response(ingest, contract)

    lane = contract.LiveLane.MICROPHONE
    frame_kwargs = dict(
        lane=lane,
        capture_timestamp_ns=0,
        silent=False,
        discontinuity=False,
        sample_rate=16_000,
    )

    def frame(sequence: int, *, samples: int = 8, epoch: int = 1, discontinuity: bool = False):
        kwargs = dict(frame_kwargs)
        kwargs.update(
            sequence=sequence,
            device_epoch=epoch,
            discontinuity=discontinuity,
            sample_count=samples,
            pcm=b"\x00\x00" * samples,
            capture_timestamp_ns=sequence * 1_000,
        )
        return contract.LiveV2Frame(**kwargs)

    measured: list[dict] = []

    def run(name: str, ingress, candidate) -> None:
        before = ingress.snapshot(lane).next_sequence
        raised = None
        try:
            ingress.accept(candidate)
        except Exception as exc:  # noqa: BLE001 - the raise IS the measurement
            raised = exc
        after = ingress.snapshot(lane).next_sequence
        if raised is None:
            status, code = 200, None
        else:
            status, body = failure_response(raised)
            code = body["failure"]["code"]
        measured.append(
            {
                "scenario": name,
                "status": status,
                "failure_code": code,
                "next_sequence_before": before,
                "next_sequence_after": after,
                "consumed": after != before,
                "exception": type(raised).__name__ if raised else None,
            }
        )

    # --- in-order accept, then the replay of an already-acked sequence -------------
    ingress = ingest.LiveLaneIngress(max_retained_samples=64)
    run("in_order_first_frame", ingress, frame(0))
    run("replay_of_acked_sequence", ingress, frame(0))

    # --- a gap ahead of what the lane expects --------------------------------------
    ingress = ingest.LiveLaneIngress(max_retained_samples=64)
    run("sequence_ahead_of_expected", ingress, frame(3))

    # --- epoch faults ---------------------------------------------------------------
    ingress = ingest.LiveLaneIngress(max_retained_samples=64)
    ingress.accept(frame(0, epoch=2))
    run("epoch_advance_without_discontinuity", ingress, frame(1, epoch=3))
    run("epoch_advance_with_discontinuity", ingress, frame(1, epoch=3, discontinuity=True))
    ingress = ingest.LiveLaneIngress(max_retained_samples=64)
    ingress.accept(frame(0, epoch=2))
    run("stale_device_epoch", ingress, frame(1, epoch=1))

    # --- lane retention capacity: the 429 that does NOT consume ---------------------
    ingress = ingest.LiveLaneIngress(max_retained_samples=16)
    ingress.accept(frame(0, samples=8))
    ingress.accept(frame(1, samples=8))
    run("lane_retention_capacity_reached", ingress, frame(2, samples=8))
    # ... and it stays unconsumed, so the very same sequence is what must be resent.
    ingress.release_retained_prefix(lane, 1)
    run("resent_after_capacity_released", ingress, frame(2, samples=8))

    # --- a frame larger than the whole lane budget ----------------------------------
    ingress = ingest.LiveLaneIngress(max_retained_samples=16)
    run("single_frame_exceeds_lane_budget", ingress, frame(0, samples=32))

    # --- pruned replay ---------------------------------------------------------------
    ingress = ingest.LiveLaneIngress(max_retained_samples=1_000_000, max_retained_acks=2)
    for sequence in range(4):
        ingress.accept(frame(sequence))
    run("pruned_replay", ingress, frame(0))

    print("== measured server frame outcomes ==")
    for row in measured:
        print(json.dumps(row, sort_keys=True))

    # The queue-backpressure 429 is raised by the mixer AFTER `v2_session.accept`
    # returns, so it cannot be produced from the ingress at all. That structural fact
    # is what makes it consumed; assert it from the transport source rather than
    # claiming it.
    transport = (APP / "live_transport.py").read_text(encoding="utf-8")
    accept_at = transport.index("ack = v2_session.accept(frame.v2_frame)")
    admit_at = transport.index("admit_available(", accept_at)
    backpressure_at = transport.index(
        "except (InferenceArbiterBackpressure, LiveSessionBackpressure) as exc:"
    )
    ordering_ok = accept_at < admit_at < backpressure_at
    has_failure_key = (
        "failure"
        not in transport[
            backpressure_at : transport.index("except LiveSessionClosed", backpressure_at)
        ]
    )
    print(
        json.dumps(
            {
                "scenario": "queue_backpressure_after_accept",
                "status": 429,
                "failure_code": None,
                "consumed": True,
                "accept_precedes_admit_precedes_backpressure_handler": ordering_ok,
                "backpressure_429_body_has_no_failure_key": has_failure_key,
            },
            sort_keys=True,
        )
    )

    failures: list[str] = []
    if not ordering_ok:
        failures.append(
            "live_transport.py no longer raises queue backpressure after v2_session.accept; "
            "the client's 'do not resend' mapping for the failure-less 429 is no longer safe"
        )
    if not has_failure_key:
        failures.append(
            "the queue-backpressure 429 now carries a failure key; the client distinguishes "
            "the two 429 sources by its absence"
        )

    # ------------------------------------------------------- compare with the client
    ts = CONTRACT_TS.read_text(encoding="utf-8")
    ts_outcomes = dict(
        (name, (int(status), None if code == "null" else code.strip('"')))
        for name, status, code in re.findall(
            r'\[\s*"([a-z0-9_]+)"\s*,\s*(\d+)\s*,\s*(null|"[a-z0-9_]+")\s*\]', ts
        )
    )
    ts_consumed = {
        name: value == "true"
        for name, value in re.findall(r'"([a-z0-9_]+)"\s*:\s*(true|false)', ts)
    }
    if not ts_outcomes or not ts_consumed:
        failures.append(f"could not parse the contract tables out of {CONTRACT_TS}")

    for row in measured:
        name = row["scenario"]
        if name not in ts_outcomes:
            failures.append(f"{CONTRACT_TS.name} does not carry measured scenario {name!r}")
            continue
        want = (row["status"], row["failure_code"])
        got = ts_outcomes[name]
        if want != got:
            failures.append(f"{name}: server says {want}, client table says {got}")
        if name in ts_consumed and ts_consumed[name] != row["consumed"]:
            failures.append(
                f"{name}: server consumed={row['consumed']}, client table says "
                f"consumed={ts_consumed[name]}"
            )

    extra = set(ts_outcomes) - {row["scenario"] for row in measured} - {
        "queue_backpressure_after_accept"
    }
    if extra:
        failures.append(f"client table invents scenarios the server cannot produce: {sorted(extra)}")

    print()
    if failures:
        print("PROBE FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(
        f"PROBE OK  {len(measured)} measured ingress scenarios + 1 structural transport check "
        f"agree with {CONTRACT_TS.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
