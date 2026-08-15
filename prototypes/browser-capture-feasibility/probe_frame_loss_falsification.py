#!/usr/bin/env python3
"""PROTOTYPE: falsify the x1 frame-loss gate instead of only passing it.

Question: can the P0 assertion actually fail?  A gate that passes on the current tree
proves nothing unless the defect it claims to catch makes it fail.  This probe
re-introduces each historical defect into the REAL page source, runs the real transport
script, and scores it with the SAME assertion code the committed browser probe uses
(``probe_slow_post_characterization._lane_summary``).  A mutant that still passes is a
tautological gate and this probe fails.

It also covers two contracts the committed browser probes never assert:
  * a forced FIFO overflow must be reported truthfully (``dropped_frames`` on the
    heartbeat route and ``discontinuity`` on the next admitted frame), and
  * ``recreateSession`` must drain in-flight POSTs before resetting lane sequences.

Run:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
    prototypes/browser-capture-feasibility/probe_frame_loss_falsification.py \\
    --output evidence/phase1/x1-frame-drop/x1-review-frame-loss-falsification.json

Any interpreter with fastapi/uvicorn works; the committed run used the pyenv 3.12.10 ``python3``
because the repo ``.venv`` lives under a directory macOS was refusing to read at the time.

Scope and limits: this executes the committed ``capture_pipeline_page.html`` transport
script in a Node vm with stubbed browser APIs and a stubbed strict-v2 route
(``page_sender_harness.mjs``).  There is no AudioWorklet, no Chrome scheduler, no real
HTTP stack and no hidden-tab throttling, so it measures transport SEMANTICS only.  It does
not replace ``probe_slow_post_characterization.py``, ``probe_recreate_session.py`` or
``probe_g7_hidden_tab.py``; it answers the question those probes structurally cannot,
namely whether their central assertion is falsifiable.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from probe_slow_post_characterization import _lane_summary  # the committed gate's own math

HARNESS = HERE / "page_sender_harness.mjs"
LANES = ("system", "microphone")
_NODE_CANDIDATES = ("/opt/homebrew/bin/node", "/usr/local/bin/node")


def _node_binary(explicit: str | None) -> str:
    if explicit:
        return explicit
    for candidate in _NODE_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    found = shutil.which("node")
    if found:
        return found
    raise RuntimeError("node not found; supply --node-bin")


def _run_harness(node_bin: str, config: dict) -> dict:
    completed = subprocess.run(
        [node_bin, str(HARNESS), json.dumps(config)],
        cwd=str(HERE),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if not completed.stdout.strip():
        raise RuntimeError(f"harness produced no output: {completed.stderr[-800:]}")
    payload = json.loads(completed.stdout)
    if "error" in payload:
        raise RuntimeError(f"harness error for {config}: {payload['error'][:800]}")
    return payload


def _score_transport(run: dict) -> dict:
    """Apply the committed slow-POST gate's own assertion math to a harness run."""
    descriptor = run["config"]["descriptor"]
    frame_period_ms = descriptor["frame_samples"] / descriptor["sample_rate"] * 1_000
    telemetry = run["server"]["telemetry"]
    summaries = {}
    for lane in LANES:
        records = sorted(
            (record for record in telemetry if record.get("lane") == lane),
            key=lambda record: int(record.get("sequence", -1)),
        )
        summaries[lane] = _lane_summary(
            records,
            frame_period_ms=frame_period_ms,
            accepted=run["server"]["accepted_by_lane"][lane],
        )
    assertions = {
        "admitted_frames_approximately_match_elapsed_cadence": all(
            abs(summary["accepted_minus_elapsed_expected"]) <= 1 for summary in summaries.values()
        ),
        "per_lane_frame_posts_are_serial": all(
            run["server"]["per_lane_max_concurrent"].get(lane) == 1 for lane in LANES
        ),
        "wire_sequences_follow_admitted_worklet_order": all(
            summaries[lane]["wire_sequences"] == list(range(summaries[lane]["emitted_frames"]))
            for lane in LANES
        ),
    }
    trimmed = {}
    for lane, summary in summaries.items():
        trimmed[lane] = {k: v for k, v in summary.items() if k != "wire_sequences"}
        trimmed[lane]["wire_sequence_span"] = [
            summary["wire_sequences"][0] if summary["wire_sequences"] else None,
            summary["wire_sequences"][-1] if summary["wire_sequences"] else None,
        ]
    return {"lane_summaries": trimmed, "assertions": assertions}


def _lane_counters(run: dict) -> dict:
    return {lane: run["scenario"]["lanes"][lane] for lane in LANES}


def _last_heartbeat_lanes(run: dict) -> dict:
    heartbeats = run["server"]["heartbeats"]
    if not heartbeats:
        return {}
    return heartbeats[-1].get("lanes", {})


def _g7_cadence(run: dict) -> dict:
    """Score a harness run with probe_g7_hidden_tab's OWN cadence math.

    G7's assertion reads route ACCEPTANCES joined to post-ACK page telemetry, exactly the
    join `production_route_server.admitted_frames` performs. Rebuilding that join here is
    what lets the G7 assertion -- not just its slow-POST twin -- be falsified.
    """
    import probe_g7_hidden_tab as g7

    descriptor = run["config"]["descriptor"]
    telemetry = run["server"]["telemetry"]
    out = {}
    for lane in LANES:
        joined = []
        for accepted in run["server"]["acceptances"]:
            if accepted["lane"] != lane:
                continue
            emitted = next(
                (
                    record for record in telemetry
                    if record.get("lane") == lane
                    and record.get("wire_sequence") == accepted["sequence"]
                ),
                None,
            )
            if emitted is not None:
                joined.append({**accepted, "client_wall_ms": emitted["client_wall_ms"]})
        out[lane] = g7._admission_cadence(joined, descriptor)
    return out


def _g7_geometry() -> dict:
    """Check the G7 probe's production-geometry contract without launching a browser."""
    import probe_g7_hidden_tab as g7
    from probe_recreate_session import _json, _start_server, _stop_server
    from production_route_server import build_app

    missing_argument = subprocess.run(
        [sys.executable, str(HERE / "probe_g7_hidden_tab.py"), "--output", "/dev/null"],
        capture_output=True, text=True, timeout=60,
    )
    runtime = g7._runtime_at_descriptor_geometry(8000)
    app = build_app(runtime_factory_override=lambda: runtime)
    # The descriptor route refuses a non-loopback peer, so use the probes' own uvicorn
    # loopback server rather than an in-process test client.
    base_url, server, thread = _start_server(app)
    try:
        route = _json(
            f"{base_url}/api/live/descriptor"
            "?client_min_protocol_version=2&client_max_protocol_version=2"
        )["descriptor"]
        page_verdict = _json(f"{base_url}/prototype/verdict")["descriptor"]
    finally:
        _stop_server(app, server, thread)
    bounds = route.get("bounds", {})
    retained = bounds.get("max_retained_samples")
    return {
        "frame_samples_argument_is_required": (
            missing_argument.returncode != 0
            and "--frame-samples" in (missing_argument.stderr + missing_argument.stdout)
        ),
        "frame_samples_argument_error": missing_argument.stderr.strip().splitlines()[-1:],
        "route_descriptor_matches_prototype_verdict_descriptor": page_verdict == route,
        "route_descriptor_frame_samples": route.get("frame_samples"),
        "route_descriptor_sample_rate": route.get("sample_rate"),
        "route_descriptor_max_retained_samples": retained,
        # The page derives its FIFO bound from this field and now throws without it, so a
        # descriptor that omits it would break capture at load rather than at overflow.
        "descriptor_carries_the_bound_the_page_now_requires": isinstance(retained, int) and retained > 0,
        "derived_transport_queue_frames": None if not retained else retained // 8000,
        "frame_period_ms_at_production_geometry": route.get("frame_samples", 0)
        / max(route.get("sample_rate", 1), 1) * 1000,
    }


def _run(node_bin: str) -> dict:
    findings: dict = {}

    # --- 1. the P0 gate, scored on the real page and on the historical defect ------------
    baseline = _run_harness(node_bin, {"frames": 50, "frameDelayMs": 100, "settleMs": 4000})
    defect = _run_harness(
        node_bin,
        {"frames": 50, "frameDelayMs": 100, "settleMs": 4000, "mutation": "inflight_drop"},
    )
    baseline_score = _score_transport(baseline)
    defect_score = _score_transport(defect)
    baseline_g7 = _g7_cadence(baseline)
    defect_g7 = _g7_cadence(defect)
    findings["p0_frame_loss_gate"] = {
        "baseline": {**baseline_score, "lane_counters": _lane_counters(baseline)},
        "inflight_drop_mutant": {**defect_score, "lane_counters": _lane_counters(defect)},
        "mutation_applied": defect["mutation_applied"],
        "g7_cadence_baseline": baseline_g7,
        "g7_cadence_inflight_drop_mutant": defect_g7,
    }

    # --- 2. a forced overflow must be reported truthfully --------------------------------
    overflow_descriptor = {
        "sample_rate": 16000,
        "frame_samples": 1000,
        "bounds": {"max_frame_samples": 16000, "max_retained_samples": 4000, "max_queue_depth": 64},
    }
    overflow = _run_harness(
        node_bin,
        {"frames": 60, "frameDelayMs": 150, "settleMs": 4000, "descriptor": overflow_descriptor},
    )
    lying = _run_harness(
        node_bin,
        {
            "frames": 60, "frameDelayMs": 150, "settleMs": 4000,
            "descriptor": overflow_descriptor, "mutation": "heartbeat_zero",
        },
    )
    overflow_accept = overflow["server"]["acceptances"]
    findings["overflow_is_reported_truthfully"] = {
        "lane_counters": _lane_counters(overflow),
        "last_heartbeat_lanes": _last_heartbeat_lanes(overflow),
        "frame_capacity": overflow["scenario"]["lanes"]["system"]["frame_capacity"],
        "admitted_frames_flagged_discontinuous": sum(
            1 for record in overflow_accept if record.get("discontinuity")
        ),
        "heartbeat_zero_mutant_last_heartbeat_lanes": _last_heartbeat_lanes(lying),
        "heartbeat_zero_mutant_dropped_frames": {
            lane: lying["scenario"]["lanes"][lane]["dropped_frames"] for lane in LANES
        },
    }

    # --- 3. recreateSession must drain before resetting sequence -------------------------
    # Only the microphone lane's first ADMITTED response is held, so the forced system-lane
    # 409 lands while that peer POST is still resolving -- the exact race recreateSession
    # has to survive. A uniform delay would resolve the peer first and never reach it.
    recreate_config = {
        "scenario": "recreate", "search": "?x1_recreate_probe=1", "frameDelayMs": 600,
        "delayFirstAcceptedLane": "microphone",
        "failCreateAttempts": [2], "sessionIds": ["old-session", "new-session", "third-session"],
    }
    recreate = _run_harness(node_bin, recreate_config)
    no_drain = _run_harness(node_bin, {**recreate_config, "mutation": "no_drain"})
    findings["recreate_drains_before_reset"] = {
        "recreate": recreate["scenario"],
        "sessions": recreate["server"]["next_sequence_by_lane"],
        "frame_status_counts": recreate["server"]["frame_status_counts"],
        "held_response_lane": recreate["server"]["held_response_lane"],
        "no_drain_mutant": no_drain["scenario"],
        "no_drain_mutant_sessions": no_drain["server"]["next_sequence_by_lane"],
        "no_drain_mutant_frame_status_counts": no_drain["server"]["frame_status_counts"],
    }

    # --- 4. G7 production geometry, verified without a browser ----------------------------
    # probe_g7_hidden_tab.py needs Chrome for the hidden-tab half, but the half that
    # regressed in a843bb4 -- the route geometry the page is measured against -- does not.
    # Check it directly so a 1000-sample run can never again be submitted as an 8000 one.
    findings["g7_production_geometry"] = _g7_geometry()

    # --- gate -----------------------------------------------------------------------------
    overflow_counters = _lane_counters(overflow)
    overflow_heartbeat = _last_heartbeat_lanes(overflow)
    recreate_scenario = recreate["scenario"]
    gate = {
        # The committed gate must hold on the page as it stands...
        "committed_gate_passes_on_current_page": all(baseline_score["assertions"].values()),
        # ...and must NOT hold once the historical drop guard is back. If this is false the
        # gate is a tautology and the P0 could return unnoticed.
        "committed_gate_fails_on_the_historical_drop_guard": not defect_score["assertions"][
            "admitted_frames_approximately_match_elapsed_cadence"
        ],
        # The defect really did lose audio, and really was invisible in the lane counters --
        # this is what makes the previous assertion a meaningful catch rather than noise.
        # The G7 twin of that assertion, scored with probe_g7_hidden_tab's own function.
        "g7_cadence_assertion_holds_on_current_page": all(
            abs(baseline_g7[lane]["accepted_minus_elapsed_expected"]) <= 1 for lane in LANES
        ),
        "g7_cadence_assertion_fails_on_the_historical_drop_guard": all(
            abs(defect_g7[lane]["accepted_minus_elapsed_expected"]) > 1 for lane in LANES
        ),
        "historical_drop_guard_loses_audio_silently": (
            defect["scenario"]["lanes"]["system"]["dropped_frames"] == 0
            and defect["scenario"]["lanes"]["system"]["sent"]
            < defect["scenario"]["lanes"]["system"]["emitted"] * 0.75
        ),
        # A drop that the page cannot avoid must be counted and flagged, not hidden.
        "forced_overflow_increments_dropped_frames": all(
            overflow_counters[lane]["dropped_frames"] > 0 for lane in LANES
        ),
        "forced_overflow_is_reported_on_the_heartbeat_route": all(
            overflow_heartbeat.get(lane, {}).get("dropped_frames", 0) > 0 for lane in LANES
        ),
        "forced_overflow_marks_discontinuity_on_the_next_admitted_frame": (
            findings["overflow_is_reported_truthfully"]["admitted_frames_flagged_discontinuous"] > 0
        ),
        # ...and the heartbeat report is load-bearing: hardcoding zero must break the check.
        "heartbeat_truthfulness_check_fails_when_the_report_is_hardcoded": all(
            _last_heartbeat_lanes(lying).get(lane, {}).get("dropped_frames", 0) == 0
            for lane in LANES
        )
        and all(lying["scenario"]["lanes"][lane]["dropped_frames"] > 0 for lane in LANES),
        # recreateSession: peer POST still resolving when the button is pressed.
        "recreate_completed": bool(recreate_scenario.get("completed")),
        "recreate_holds_old_session_until_the_peer_post_drains": (
            recreate_scenario["during_drain"]["live_session_id"] == "old-session"
            and recreate_scenario["during_drain"]["lanes"]["microphone"]["send_in_flight"]
        ),
        "failed_recreate_leaves_its_button_enabled": (
            recreate_scenario["failed_recreate"]["session_recreate_required"]
            and not recreate_scenario["failed_recreate"]["recreate_disabled"]
        ),
        "recreate_resumes_the_fresh_session_without_sequence_poisoning": (
            recreate_scenario["recovered"]["live_session_id"] == "new-session"
            and recreate_scenario["resumed"]["lanes"]["system"]["seq"] == 1
            and recreate_scenario["resumed"]["lanes"]["microphone"]["seq"] == 1
            and all(
                session["next"] == {"system": 1, "microphone": 1}
                for session in recreate["server"]["next_sequence_by_lane"]
                if session["id"] == "new-session"
            )
        ),
        # And the drain is load-bearing: removing it must break the recovery. Without the
        # drain the old session's resolving POST advances the lane sequence after the reset,
        # so the fresh session never gets a clean resume.
        "removing_the_drain_breaks_the_recreate": not no_drain["scenario"].get("completed"),
        # G7 geometry, checkable without Chrome.
        "g7_frame_samples_argument_is_required": findings["g7_production_geometry"][
            "frame_samples_argument_is_required"
        ],
        "g7_route_advertises_production_frame_samples": (
            findings["g7_production_geometry"]["route_descriptor_frame_samples"] == 8000
        ),
        "descriptor_carries_the_bound_the_page_now_requires": findings["g7_production_geometry"][
            "descriptor_carries_the_bound_the_page_now_requires"
        ],
    }
    return {"findings": findings, "gate": gate}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node-bin")
    args = parser.parse_args()

    result: dict = {
        "probe": "prototypes/browser-capture-feasibility/probe_frame_loss_falsification.py",
        "harness": "prototypes/browser-capture-feasibility/page_sender_harness.mjs",
        "question": (
            "does the x1 frame-loss gate fail when the historical defects are put back into the "
            "real page source, and are forced drops reported truthfully"
        ),
        "scope": (
            "the committed capture_pipeline_page.html transport script executed in a Node vm "
            "against a stubbed strict-v2 route; no AudioWorklet, no Chrome, no real HTTP, no "
            "hidden-tab throttling -- transport semantics only"
        ),
        "passed": False,
    }
    try:
        result.update(_run(_node_binary(args.node_bin)))
        result["passed"] = all(result["gate"].values())
        if not result["passed"]:
            result["error"] = "falsification gate failed: " + ", ".join(
                name for name, ok in result["gate"].items() if not ok
            )
    except Exception as exc:
        result["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result.get("gate", result), indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
