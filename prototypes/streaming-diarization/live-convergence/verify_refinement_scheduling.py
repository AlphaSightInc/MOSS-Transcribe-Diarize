#!/usr/bin/env python3
"""Does the shipped `live_refinement` queue schedule the rolling witness without delaying the base?

Plan §10.5 step 3 adds M5's fourth admission method to `app/live_arbiter.py`. The rule it
implements is a scheduling rule, so the honest way to check it is to make every unit of work in
a session -- the 2.5 s canonical spans *and* the 10 s rolling windows -- go through the real
arbiter, and to watch what came out in what order:

    baseline spans -> InferenceArbiter.submit_live_canonical  ->|
                                                                |-> next_work() -> LiveSession
    RollingTranscriptConverger -> submit_live_refinement      ->|                -> apply_text_revision

Three sessions (the trio) share ONE arbiter and are interleaved span by span, so the per-session
rule is exercised across sessions rather than asserted about one. Appendix B deferred the
*two-session real-time stress* (G7 is single-session); this is the scheduling-correctness half of
plan §6 M5, which costs no GPU and no wall clock.

Zero MOSS requests by construction: the decoder is handed a runner that raises, so a cache miss
is a failure rather than a fresh GPU call. Reviewers can run this with no 4070 Ti.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_refinement_scheduling.py

Exit 0 iff every gate below passes.

- G1 scheduling changed no answer: per-case WER equals the grid's `10/10` arm to 6 dp and the
  trio means equal `.131861` / `.943916` (the grid records recall per arm, not per case)
- G2 a rolling witness was never dispatched while canonical work was waiting, and canonical work
  *was* dispatched ahead of a waiting witness (the gate is not vacuous)
- G3 one running witness per session: never two for one coalesce key, never more running than
  there are live sessions, every dispatched witness released, and both refinement depths zero at
  the end
- G4 every planned window was dispatched exactly once, in window order, for every case
- G5 no witness was coalesced or suppressed and no revision was refused -- with the converger as
  the only producer, a drop here would mean a window silently lost
- G6 zero fresh MOSS requests
- G7 each session emits exactly one coalesce key across all its windows -- coalescing is per
  session, not per window
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_session_text_authority as authority  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import InferenceTranscript  # noqa: E402
from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter  # noqa: E402
from moss_transcribe_diarize.app.live_session import LiveSession  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    RollingTranscriptConverger,
)

SAMPLE_RATE = bench.SAMPLE_RATE
GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"
DEFAULT_BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824/trio-60s"
SELECTED_ARM = authority.SELECTED_ARM
PLACES = authority.PLACES


class CacheMiss(RuntimeError):
    """The replay asked for a decode the grid never recorded. No GPU call is made."""


class _NoRunner:
    def transcribe(self, *args: Any, **kwargs: Any) -> Any:
        raise CacheMiss("the shipped scheduler asked for a window the grid did not decode.")


class _Case:
    """One live session's worth of state: audio, session, converger, and its span queue."""

    def __init__(self, name: str, *, baseline: Path):
        audio_path = bench.CORPUS / name / "audio.wav"
        self.name = name
        self.pcm = bench.read_pcm(audio_path)
        self.audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        self.total_samples = len(self.pcm) // 2
        self.duration = self.total_samples / SAMPLE_RATE
        self.spans = bench.load_baseline_spans(baseline / name / "live/run-001/trace.jsonl")
        self.session = LiveSession(max_retained_samples=self.total_samples)
        self.converger = RollingTranscriptConverger(epoch=self.session.epoch)
        self.pending_spans = list(self.spans)
        self.dispatched_windows: list[int] = []
        self.requests_by_id: dict[int, Any] = {}
        self.coalesce_keys: set[str] = set()
        self.refusals: list[str] = []
        self.applied = 0


def run(cases: list[_Case], *, decoder: Any, scratch: Path) -> dict[str, Any]:
    """Drive every case through one arbiter and record what was dispatched, and when."""

    arbiter = InferenceArbiter()
    dispatches: list[dict[str, Any]] = []
    coalesced = 0
    suppressed = 0
    running_over_sessions = 0
    unreleased = 0
    max_canonical_depth = 0
    max_refinement_depth = 0
    canonical_ahead_of_waiting_witness = 0
    refinement_dispatched_with_canonical_waiting = 0

    def key_of(case: _Case, request: Any) -> str:
        """The converger's own key, namespaced by session because this driver shares an arbiter.

        In the runtime each session has its own `InferenceArbiter`, so the converger's
        `rolling:<epoch>` is unique where it is used. This driver deliberately puts three
        sessions on ONE arbiter to exercise the per-session rule, and all three are epoch 0 --
        so it namespaces the key rather than pretending the converger already carries a
        session identity. That is a real carry-forward for plan §10.5 step 4: whichever key
        the runtime submits must identify the session, not only the epoch.
        """

        case.coalesce_keys.add(request.coalesce_key)
        return f"{case.name}:{request.coalesce_key}"

    def submit(case: _Case, requests: tuple[Any, ...]) -> None:
        nonlocal coalesced, suppressed
        for request in requests:
            case.requests_by_id[request.id] = request
            admission = arbiter.submit_live_refinement(
                coalesce_key=key_of(case, request), payload=(case, request)
            )
            if not admission.accepted:
                suppressed += 1
                continue
            if admission.replaced_item_id is not None:
                coalesced += 1

    round_index = 0
    while any(case.pending_spans for case in cases):
        # One round: hand every still-running session its next span, then drain the arbiter
        # completely. Draining is what makes the ordering visible -- everything admitted in
        # this round leaves in priority order, not in submission order.
        for case in cases:
            if not case.pending_spans:
                continue
            span = case.pending_spans.pop(0)
            arbiter.submit_live_canonical(
                key=f"{case.name}:span-{span['span_id']}", payload=(case, span)
            )
        round_index += 1

        while True:
            before = arbiter.snapshot()
            max_canonical_depth = max(max_canonical_depth, before.live_canonical)
            max_refinement_depth = max(max_refinement_depth, before.live_refinement)
            item = arbiter.next_work()
            if item is None:
                break
            case, payload = item.payload
            after = arbiter.snapshot()
            dispatches.append(
                {
                    "round": round_index,
                    "kind": item.kind,
                    "case": case.name,
                    "canonical_waiting_before": before.live_canonical,
                    "refinement_waiting_before": before.live_refinement,
                    "refinement_running_after": after.live_refinement_running,
                }
            )
            if after.live_refinement_running > len(cases):
                running_over_sessions += 1
            if item.kind == InferenceArbiter.LIVE_CANONICAL:
                if before.live_refinement:
                    canonical_ahead_of_waiting_witness += 1
                span = payload
                authority.commit_span(case.session, span)
                requests = case.converger.accept_pcm(
                    span["start_sample"],
                    case.pcm[span["start_sample"] * 2 : span["end_sample"] * 2],
                )
                requests = requests + case.converger.observe_base(case.session.snapshot())
                submit(case, requests)
                continue

            if before.live_canonical:
                refinement_dispatched_with_canonical_waiting += 1
            request = payload
            case.dispatched_windows.append(request.window_index)
            decoded = decoder.decode(
                pcm=case.pcm,
                audio_sha=case.audio_sha,
                start_sample=request.start_sample,
                end_sample=request.end_sample,
                token_cap=request.token_cap,
                scratch=scratch,
            )
            proposal = case.converger.complete(
                request.id,
                InferenceTranscript(
                    transcript=decoded["transcript"],
                    elapsed_sec=float(decoded["elapsed_seconds"]),
                ),
            )
            # The witness stops being a running MOSS request the moment its decode is answered,
            # whatever the answer was -- a stale completion and a failed window release it too.
            if not arbiter.release_live_refinement(item_id=item.id):
                unreleased += 1
            if proposal is None:
                continue
            outcome = case.session.apply_text_revision(proposal)
            if outcome.applied:
                case.applied += 1
            else:
                case.refusals.append(outcome.refusal or "unknown")
            submit(case, case.converger.observe_base(case.session.snapshot()))

    final = arbiter.snapshot()
    return {
        "dispatches": dispatches,
        "rounds": round_index,
        "coalesced": coalesced,
        "suppressed": suppressed,
        "unreleased": unreleased,
        "running_over_sessions": running_over_sessions,
        "max_canonical_depth": max_canonical_depth,
        "max_refinement_depth": max_refinement_depth,
        "canonical_ahead_of_waiting_witness": canonical_ahead_of_waiting_witness,
        "refinement_dispatched_with_canonical_waiting": refinement_dispatched_with_canonical_waiting,
        "final_refinement_queued": final.live_refinement,
        "final_refinement_running": final.live_refinement_running,
        "final_canonical_queued": final.live_canonical,
    }


def score_case(case: _Case) -> dict[str, Any]:
    snapshot = case.session.snapshot()
    hypothesis = bench.normalise(
        [
            Segment(
                item.start_sample / SAMPLE_RATE,
                item.end_sample / SAMPLE_RATE,
                authority.label_of_canonical(item.canonical_speaker),
                item.text,
            )
            for item in snapshot.effective_transcript
        ],
        case.duration,
    )
    return {
        "scores": bench.score(bench.load_reference(case.name), hypothesis),
        "spans": len(case.spans),
        "applied": case.applied,
        "refusals": case.refusals,
        "dispatched_windows": case.dispatched_windows,
        "coalesce_keys": sorted(case.coalesce_keys),
        "text_revision_version": snapshot.text_revision_version,
        "canonical_through_sample": snapshot.canonical_through_sample,
        "rolling_status": case.converger.accounting().status.value,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--grid", type=Path, default=GRID / "grid.json")
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    grid = json.loads(cli.grid.read_text(encoding="utf-8"))
    expected = grid["summary"]["arms"][SELECTED_ARM]
    names = [item for item in cli.cases.split(",") if item]
    decoder = bench.Decoder(runner=_NoRunner(), model=grid["vllm"]["model"], cache_path=cli.cache)

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-refinement-scheduling.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": ["moss_transcribe_diarize/app/live_arbiter.py"],
        "grid": {
            "path": str(cli.grid.relative_to(REPO)),
            "sha256": hashlib.sha256(cli.grid.read_bytes()).hexdigest(),
            "arm": SELECTED_ARM,
        },
        "sessions": len(names),
        "cases": {},
    }

    decoder.take_accounting()
    cases = [_Case(name, baseline=cli.baseline) for name in names]
    with tempfile.TemporaryDirectory(prefix="moss-scheduling-verify-") as temporary:
        scheduling = run(cases, decoder=decoder, scratch=Path(temporary))
    for case in cases:
        document["cases"][case.name] = score_case(case)
    document["scheduling"] = {
        key: value for key, value in scheduling.items() if key != "dispatches"
    }
    document["dispatch_kinds"] = [
        {"round": item["round"], "kind": item["kind"], "case": item["case"]}
        for item in scheduling["dispatches"]
    ]
    document["decode_cost"] = decoder.take_accounting()

    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    for name in names:
        entry = document["cases"][name]
        want = expected["per_case"][name]
        if not close(entry["scores"]["wer"], want["wer_mean"]):
            failures.append(
                f"G1 {name} wer {entry['scores']['wer']:.6f} != grid {want['wer_mean']:.6f}"
            )
        if entry["dispatched_windows"] != list(range(expected["windows_per_case"])):
            failures.append(
                f"G4 {name} dispatched windows {entry['dispatched_windows']} != "
                f"{list(range(expected['windows_per_case']))}"
            )
        if len(entry["coalesce_keys"]) != 1:
            failures.append(
                f"G7 {name} emitted {entry['coalesce_keys']} coalesce keys; one witness per "
                "session needs exactly one key per session"
            )
        if entry["applied"] != expected["windows_per_case"] or entry["refusals"]:
            failures.append(
                f"G5 {name} applied {entry['applied']} of {expected['windows_per_case']} "
                f"windows, refusals {entry['refusals']}"
            )

    schedule = document["scheduling"]
    if schedule["refinement_dispatched_with_canonical_waiting"]:
        failures.append(
            f"G2 {schedule['refinement_dispatched_with_canonical_waiting']} witnesses ran while "
            "canonical work was waiting"
        )
    if not schedule["canonical_ahead_of_waiting_witness"]:
        failures.append(
            "G2 no canonical span was ever dispatched ahead of a waiting witness, so the "
            "priority was never exercised"
        )
    if schedule["running_over_sessions"] or schedule["unreleased"]:
        failures.append(
            f"G3 {schedule['running_over_sessions']} dispatches exceeded one witness per session, "
            f"{schedule['unreleased']} releases matched no running witness"
        )
    if schedule["final_refinement_running"] or schedule["final_refinement_queued"]:
        failures.append(
            f"G3 session ended with {schedule['final_refinement_running']} running and "
            f"{schedule['final_refinement_queued']} queued witnesses"
        )
    if schedule["coalesced"] or schedule["suppressed"]:
        failures.append(
            f"G5 {schedule['coalesced']} witnesses coalesced and {schedule['suppressed']} "
            "suppressed, so a planned window was dropped"
        )
    if document["decode_cost"].get("fresh_requests"):
        failures.append(f"G6 {document['decode_cost']['fresh_requests']} fresh MOSS requests")

    mean_wer = sum(document["cases"][name]["scores"]["wer"] for name in names) / len(names)
    mean_recall = sum(
        document["cases"][name]["scores"]["content_recall"] for name in names
    ) / len(names)
    document["trio"] = {"wer_mean": mean_wer, "content_recall_mean": mean_recall}
    if len(names) == len(bench.CASES):
        if not close(mean_wer, expected["wer"]["mean"]):
            failures.append(f"G1 trio wer {mean_wer:.6f} != grid {expected['wer']['mean']:.6f}")
        if not close(mean_recall, expected["content_recall"]["mean"]):
            failures.append(
                f"G1 trio recall {mean_recall:.6f} != grid {expected['content_recall']['mean']:.6f}"
            )

    document["failures"] = failures
    document["passed"] = not failures

    for name in names:
        entry = document["cases"][name]
        print(
            f"{name:<18} wer={entry['scores']['wer']:.6f} "
            f"(grid {expected['per_case'][name]['wer_mean']:.6f}) "
            f"recall={entry['scores']['content_recall']:.6f} "
            f"windows={entry['dispatched_windows']} status={entry['rolling_status']}"
        )
    print(
        f"{'TRIO':<18} wer={mean_wer:.6f} (grid {expected['wer']['mean']:.6f}) "
        f"recall={mean_recall:.6f} (grid {expected['content_recall']['mean']:.6f})"
    )
    print(
        f"schedule: {len(document['dispatch_kinds'])} dispatches over {schedule['rounds']} rounds; "
        f"canonical ahead of a waiting witness {schedule['canonical_ahead_of_waiting_witness']}x; "
        f"witness ahead of waiting canonical {schedule['refinement_dispatched_with_canonical_waiting']}x; "
        f"max depths canonical={schedule['max_canonical_depth']} "
        f"refinement={schedule['max_refinement_depth']}; "
        f"coalesced={schedule['coalesced']} suppressed={schedule['suppressed']} "
        f"unreleased={schedule['unreleased']}"
    )
    print(f"decode cost: {document['decode_cost']}")
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"FAIL {failure}")
    print("PASS" if not failures else f"FAILED {len(failures)} gate(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
