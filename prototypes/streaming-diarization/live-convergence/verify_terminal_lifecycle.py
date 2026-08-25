#!/usr/bin/env python3
"""Does the RUNTIME give a meeting its last listener without taking the meeting away first?

The adapter is already measured: handed the paired file arm's own decode it publishes the
paired file arm's own surface, `0.000000` on five axes
(`verify_terminal_finalizer.py`, `evidence/live-convergence-0824/M4-terminal-finalizer/`).
That says nothing about the *meeting* getting one. Plan §12.3's lifecycle is a promise to a
reader who is still polling after Stop, and every part of it is a runtime fact:

    the meeting, frame by frame, through the real runtime   (verify_runtime_rolling.feed_meeting)
      -> runtime.stop() returns the meeting's accounting, `running`, tape still held
        -> a manual scheduler holds the pass still: this is the interval a reader polls
          -> the pass runs where production runs it -> LiveSession.apply_text_revision
            -> the tape is released, after the evidence, and nothing survives the meeting

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_terminal_lifecycle.py

Exit 0 iff every gate passes. Gates are fixed before the run. No GPU, no service: the base
decodes are the §10.2 grid's recorded answers and the terminal decode is the paired pass's
own file hypothesis, re-rendered by production's renderer.

Three arms per case, because "every ending has a word" is only checkable by ending badly:

  * `healthy`  -- a finalizer whose runner answers with the paired file arm's decode;
  * `decode_failure` -- a runner that raises, with meeting-shaped words in its message;
  * `no_tape`  -- a deployment that declared a finalizer and no tape capacity.

- L1 `[G-M4-6a]` the stop request does not decode: when `stop` returns, the pass has not
  started (zero terminal decode requests), `finalization_status == running`, the session is
  `closed`, and `accepted == accounted` already.
- L2 `[G-M4-6b]` the surface is readable and is the rolling one for the whole `running`
  interval: non-empty, every segment `rolling` or `provisional` authority, and the version a
  `since_version` poller holds has advanced, so the status change is deliverable.
- L3 `[G-M4-9a]` the pass replaces the surface exactly once: `final`, all-`terminal`
  authority, `canonical_through_sample == accepted_samples`, exactly one more text revision
  than the rolling arm had, and the committed chain (ADR-0005 D2) unmoved.
- L4 `[G-M4-1/2 conditional]` the published surface is the file arm's: WER, DER, coverage,
  text speaker accuracy and content recall equal the paired file arm's to 1e-12. The
  lifecycle costs the surface nothing -- the same reading `verify_terminal_finalizer.py`
  takes of the adapter, taken again with production driving.
- L5 `[G-M4-10]` the audio outlives the meeting by exactly one listener: `session_tape_released`
  comes AFTER the terminal evidence on the stream, in every arm; the released accounting
  reports zero retained bytes and the corpus digest; peak retained bytes <= the declared
  capacity.
- L6 `[G-M4-7]` a terminal failure preserves and exports the rolling surface with an explicit
  non-final status: `failed` with the pass's own reason, a surface identical to the one that
  same run was serving at stop, and the tape released anyway.
- L7 `[G-M4-9b]` a second pass cannot unfinalize what a reader was already shown: the session
  refuses `already_finalized` or the released tape refuses the read, the surface does not
  move, and the status stays `final`.
- L8 `[G-M4-13]` no terminal event carries a word of the meeting: every string in every
  terminal, revision and tape payload is a name from a vocabulary read out of the production
  sources, an exception type, or a digest -- and no published word appears in any of them.
- L9 zero fresh MOSS requests: base and terminal decodes are all replayed.

`no_tape` is the one arm with no terminal event pair: it never starts, and L5's ordering is
then the release against the `terminal_finalization_failed` that says why.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_runtime_rolling as runtime_rolling  # noqa: E402
import verify_rolling_events as rolling_events  # noqa: E402
import verify_terminal_finalizer as finalizer_bench  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    LiveServiceRuntime,
    _ManualTerminalScheduler,
)
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    LIVE_SAMPLE_RATE,
    UNATTRIBUTED_SPEAKER,
)
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    TerminalOutcome,
    TerminalTranscriptFinalizer,
)
from proto_context_arms import Segment  # noqa: E402

SAMPLE_RATE = LIVE_SAMPLE_RATE
GRID = REPO / "evidence/live-convergence-0824/M2-rolling-grid"
ARMS = ("healthy", "decode_failure", "no_tape")
SCORE_KEYS = finalizer_bench.SCORE_KEYS
PLACES = 12
#: The event kinds this verifier reads. Terminal and tape kinds are E4's; the revision kinds
#: are read too because the terminal producer writes them and a leak there is the same leak.
READ_KINDS = (
    "terminal_finalization_started",
    "terminal_finalization_completed",
    "terminal_finalization_failed",
    "text_revision_applied",
    "text_revision_refused",
    "session_tape_released",
)
DIGEST_SHAPE = re.compile(r"^[0-9a-f]{64}$")
#: Words a runner puts in the exception message it raises, so a payload that quoted the
#: message instead of the type would be caught by the same gate that catches a leaked
#: transcript. Not meeting words: the point is that NO answer text reaches an event.
FAILURE_MESSAGE = "[0][S01]the model rejected these words[60]"


class FailingRunner:
    """A whole-meeting runner that raises, with an answer-shaped message. Never decodes."""

    window_seconds = 150
    stride_seconds = 120
    model_path = "OpenMOSS-Team/MOSS-Transcribe-Diarize"

    def __init__(self):
        self.calls = 0

    def transcribe(self, audio_path, **kwargs: Any):
        self.calls += 1
        raise RuntimeError(f"terminal window 0 failed: {FAILURE_MESSAGE}")


def terminal_vocabulary() -> set[str]:
    """Every name an E4 payload may carry, read out of the production sources.

    The rolling verifier's vocabulary plus E4's: the outcome enum and the status word it maps
    to are read from the enum, and the two runtime methods that write terminal events are
    parsed for their string literals -- the same technique and the same reason. A reason name
    added to `_begin_terminal_locked` extends this set automatically; a payload that started
    carrying a word somebody said does not.
    """

    from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime

    names = rolling_events.payload_vocabulary()
    names |= {item.value for item in TerminalOutcome}
    names |= {item.finalization_status for item in TerminalOutcome}
    for method in (
        LiveServiceRuntime._begin_terminal_locked,
        LiveServiceRuntime._publish_terminal_locked,
        LiveServiceRuntime._release_tape_locked,
    ):
        names |= set(re.findall(r'"([a-z0-9_]+)"', inspect.getsource(method)))
    names |= {"RuntimeError"}  # an exception TYPE is a name; its message is not.
    return names


def surface_of(snapshot) -> list[list[Any]]:
    """The surface a reader is served, as JSON: bounds, label, words, authority."""

    speakers = tuple(snapshot.identity_snapshot.canonical_speakers)
    return [
        [
            item.start_sample,
            item.end_sample,
            runtime_rolling._label(item.canonical_speaker, speakers),
            item.text,
            item.authority,
        ]
        for item in snapshot.effective_transcript
    ]


def scores_of(surface: list[list[Any]], case: str, total: int) -> dict[str, Any]:
    hypothesis = bench.normalise(
        [Segment(item[0] / SAMPLE_RATE, item[1] / SAMPLE_RATE, item[2], item[3]) for item in surface],
        total / SAMPLE_RATE,
    )
    return bench.score(bench.load_reference(case), hypothesis)


def snapshot_report(snapshot) -> dict[str, Any]:
    return {
        "status": snapshot.status,
        "finalization_status": snapshot.finalization_status,
        "version": snapshot.version,
        "text_revision_version": snapshot.text_revision_version,
        "canonical_through_sample": snapshot.canonical_through_sample,
        "accepted_samples": snapshot.accepted_samples,
        "accounted_samples": snapshot.accounted_samples,
        "committed_prefix_hash": snapshot.committed_prefix_hash,
        "authorities": sorted({item.authority for item in snapshot.effective_transcript}),
        "segments": len(snapshot.effective_transcript),
    }


def run_arm(
    config: dict[str, Any],
    base_runner,
    case: str,
    arm: str,
    *,
    answers: dict[str, str],
    tape_bytes: int,
) -> dict[str, Any]:
    """One meeting through the real runtime, with production owning the terminal pass.

    The scheduler is manual so the `running` interval can be read rather than raced for;
    everything else -- when the pass starts, what it is handed, when the tape is released --
    is the runtime's own doing.
    """

    pcm = bench.read_pcm(bench.CORPUS / case / "audio.wav")
    total = len(pcm) // 2
    delegate = finalizer_bench.FileArmDelegate(answers)
    failing = FailingRunner()
    finalizer = (
        finalizer_bench.build_finalizer(answers, delegate)
        if arm != "decode_failure"
        else TerminalTranscriptFinalizer(runner=failing)
    )
    scheduler = _ManualTerminalScheduler()
    runtime = runtime_rolling.build_runtime(
        config,
        base_runner,
        rolling=True,
        tape_bytes=None if arm == "no_tape" else tape_bytes,
        terminal_finalizer=finalizer,
        terminal_scheduler=scheduler,
    )
    created = runtime.create()
    session_id = created.session_id
    runtime_rolling.feed_meeting(runtime, session_id, pcm=pcm, config=config, case=case)
    before_stop_version = runtime.snapshot(session_id).session.version

    asyncio.run(runtime.stop(session_id, config["bounds_config"]["stop_drain_deadline_seconds"]))

    at_stop = runtime.snapshot(session_id).session
    report: dict[str, Any] = {
        "arm": arm,
        "before_stop_version": before_stop_version,
        "at_stop": snapshot_report(at_stop),
        "at_stop_surface": surface_of(at_stop),
        "at_stop_scores": scores_of(surface_of(at_stop), case, total),
        "at_stop_pending_passes": scheduler.pending,
        "at_stop_terminal_requests": delegate.requests + failing.calls,
        "at_stop_kinds": [event.kind for event in runtime.events(session_id)],
        # What a reader polling with `since_version` is served during `running` -- the same
        # read the transport makes, so "readable" is exercised rather than asserted.
        "polled_during_running": None
        if runtime.snapshot(session_id, since_version=before_stop_version) is None
        else surface_of(runtime.snapshot(session_id, since_version=before_stop_version).session),
        "audio_sha256": hashlib.sha256(pcm).hexdigest(),
        "audio_samples": total,
        "declared_capacity_bytes": None if arm == "no_tape" else tape_bytes,
    }

    scheduler.drain()

    after = runtime.snapshot(session_id).session
    report["after"] = snapshot_report(after)
    report["after_surface"] = surface_of(after)
    report["after_scores"] = scores_of(surface_of(after), case, total)
    report["terminal_requests"] = delegate.requests + failing.calls
    report["fresh_requests"] = delegate.fresh_requests
    report["decoded_wav_sha256"] = delegate.last_audio_sha256
    report["terminal_kwargs"] = delegate.last_kwargs
    report["events"] = [
        {"seq": event.seq, "kind": event.kind, "payload": event.payload}
        for event in runtime.events(session_id)
        if event.kind in READ_KINDS
    ]
    report["terminal_failure"] = (
        None
        if runtime.snapshot(session_id).terminal_failure is None
        else runtime.snapshot(session_id).terminal_failure.message
    )

    # L7 -- the second pass, driven exactly where production drives the first one.
    state = runtime._sessions[session_id]
    if state.terminal_plan is not None and state.coordinator.tape is not None:
        runtime._run_terminal(state, state.terminal_plan, state.coordinator.tape)
        second = runtime.snapshot(session_id).session
        report["second_pass"] = {
            **snapshot_report(second),
            "surface_unchanged": surface_of(second) == report["after_surface"],
            "events": [
                {"kind": event.kind, "payload": event.payload}
                for event in runtime.events(session_id)
                if event.kind in READ_KINDS
            ][len(report["events"]):],
        }
    else:
        report["second_pass"] = None
    return report


def published_words(surface: list[list[Any]]) -> set[str]:
    """The words a reader was shown, as the leak gate's needles. Four letters and up."""

    words: set[str] = set()
    for item in surface:
        for word in re.findall(r"[A-Za-z]{4,}", str(item[3])):
            words.add(word.lower())
    return words


def check_case(case: str, arms: dict[str, Any], vocabulary: set[str], file_scores: dict[str, float]):
    failures: list[str] = []
    report: dict[str, Any] = {}
    for arm in ARMS:
        run = arms[arm]
        tag = f"{arm}/{case}"
        at_stop, after = run["at_stop"], run["after"]
        expects_pass = arm != "no_tape"

        # ---- L1: the stop request does not decode.
        if at_stop["status"] != "closed":
            failures.append(f"L1 {tag} session is {at_stop['status']} at stop")
        if at_stop["accepted_samples"] != at_stop["accounted_samples"]:
            failures.append(f"L1 {tag} accepted != accounted at stop")
        if run["at_stop_terminal_requests"] != 0:
            failures.append(f"L1 {tag} the stop request decoded {run['at_stop_terminal_requests']} times")
        if expects_pass:
            if at_stop["finalization_status"] != "running":
                failures.append(f"L1 {tag} stop returned {at_stop['finalization_status']}")
            if run["at_stop_pending_passes"] != 1:
                failures.append(f"L1 {tag} {run['at_stop_pending_passes']} passes were scheduled")
        elif at_stop["finalization_status"] != "unavailable":
            failures.append(f"L1 {tag} no-tape deployment says {at_stop['finalization_status']}")

        # ---- L2: readable, and the rolling surface, for the whole running interval.
        if not run["at_stop_surface"]:
            failures.append(f"L2 {tag} the surface is empty at stop")
        stale = {item[4] for item in run["at_stop_surface"]} - {"rolling", "provisional"}
        if stale:
            failures.append(f"L2 {tag} at stop the surface already carries {sorted(stale)}")
        if run["polled_during_running"] != run["at_stop_surface"]:
            failures.append(f"L2 {tag} a since_version poller is not served the stop surface")
        if at_stop["version"] <= run["before_stop_version"]:
            failures.append(f"L2 {tag} the status change did not move the snapshot version")

        # ---- L3: exactly one replacement, and only in the arm that produced one.
        if arm == "healthy":
            if after["finalization_status"] != "final":
                failures.append(f"L3 {tag} finalization_status is {after['finalization_status']}")
            if after["authorities"] != ["terminal"]:
                failures.append(f"L3 {tag} the surface is not all terminal: {after['authorities']}")
            if after["canonical_through_sample"] != after["accepted_samples"]:
                failures.append(f"L3 {tag} terminal owns {after['canonical_through_sample']} samples")
            if after["text_revision_version"] != at_stop["text_revision_version"] + 1:
                failures.append(f"L3 {tag} the pass wrote more than one revision")
            if after["committed_prefix_hash"] != at_stop["committed_prefix_hash"]:
                failures.append(f"L3 {tag} the terminal pass moved the committed chain")
            if run["decoded_wav_sha256"] != run["audio_sha256"]:
                failures.append(f"L3 {tag} the pass decoded audio that is not the meeting")

            # ---- L4: and the surface it published is the file arm's.
            for key in SCORE_KEYS:
                got, want = run["after_scores"][key], file_scores[key]
                if round(got - want, PLACES) != 0:
                    failures.append(f"L4 {tag} {key} {got:.6f} != file arm {want:.6f}")
        else:
            if after["finalization_status"] not in {"failed", "unavailable"}:
                failures.append(f"L6 {tag} a pass that published nothing says {after['finalization_status']}")

        # ---- L5: the release comes after the evidence, and nothing survives.
        kinds = [event["kind"] for event in run["events"]]
        if "session_tape_released" not in kinds and expects_pass:
            failures.append(f"L5 {tag} the tape was never released")
        if expects_pass:
            released_at = kinds.index("session_tape_released")
            evidence = [
                index
                for index, kind in enumerate(kinds)
                if kind.startswith("terminal_finalization_") and kind != "terminal_finalization_started"
            ]
            if not evidence or max(evidence) > released_at:
                failures.append(f"L5 {tag} the tape was released before its terminal evidence: {kinds}")
            if "terminal_finalization_started" not in kinds:
                failures.append(f"L5 {tag} the pass never announced itself")
            released = [
                event["payload"] for event in run["events"] if event["kind"] == "session_tape_released"
            ][0]
            if released["retained_bytes"] != 0:
                failures.append(f"L5 {tag} {released['retained_bytes']} bytes survived the meeting")
            if released["pcm_sha256"] != run["audio_sha256"]:
                failures.append(f"L5 {tag} the released tape is not the meeting's audio")
            if released["peak_retained_bytes"] > run["declared_capacity_bytes"]:
                failures.append(f"L5 {tag} peak retention exceeded the declared capacity")
        elif "terminal_finalization_failed" not in kinds:
            failures.append(f"L5 {tag} a deployment with no tape said nothing about it")

        # ---- L6: a failure preserves and exports the rolling surface.
        if arm != "healthy":
            if run["after_surface"] != run["at_stop_surface"]:
                failures.append(f"L6 {tag} the rolling surface did not survive the failed pass")
            if not run["after_surface"]:
                failures.append(f"L6 {tag} the preserved surface is empty")
            if run["after_scores"] != run["at_stop_scores"]:
                failures.append(f"L6 {tag} the preserved surface scores differently")
            reasons = {
                event["payload"].get("reason")
                for event in run["events"]
                if event["kind"] == "terminal_finalization_failed"
            }
            expected = {"RuntimeError"} if arm == "decode_failure" else {"no_retained_tape"}
            if reasons != expected:
                failures.append(f"L6 {tag} failure reasons {sorted(map(str, reasons))} != {sorted(expected)}")
        if run["terminal_failure"] is not None:
            failures.append(f"L6 {tag} the meeting ended terminal: {run['terminal_failure']}")

        # ---- L7: a second pass cannot unfinalize a published surface.
        second = run["second_pass"]
        if arm == "healthy":
            if second is None:
                failures.append(f"L7 {tag} no second pass could be driven")
            else:
                if second["finalization_status"] != "final":
                    failures.append(f"L7 {tag} a second pass moved the status to {second['finalization_status']}")
                if not second["surface_unchanged"]:
                    failures.append(f"L7 {tag} a second pass changed the published surface")
                if second["text_revision_version"] != after["text_revision_version"]:
                    failures.append(f"L7 {tag} a second pass wrote a revision")

        # ---- L8: no payload carries a word of the meeting.
        needles = published_words(run["after_surface"]) | published_words(run["at_stop_surface"])
        needles |= {word.lower() for word in re.findall(r"[A-Za-z]{4,}", FAILURE_MESSAGE)}
        for event in run["events"]:
            for value in finalizer_bench._strings(event["payload"]):
                if DIGEST_SHAPE.match(value):
                    continue
                if not rolling_events.NAME_SHAPE.match(value) and value not in vocabulary:
                    failures.append(f"L8 {tag} {event['kind']} carries a non-name string {value!r}")
                elif value not in vocabulary:
                    failures.append(f"L8 {tag} {event['kind']} carries unknown name {value!r}")
                if value.lower() in needles:
                    failures.append(f"L8 {tag} {event['kind']} carries a published word {value!r}")

        report[arm] = {
            "at_stop": at_stop,
            "after": after,
            "event_order": kinds,
            "scores": {
                "at_stop": {key: run["at_stop_scores"][key] for key in SCORE_KEYS},
                "after": {key: run["after_scores"][key] for key in SCORE_KEYS},
            },
            "second_pass": second,
        }
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    config = runtime_rolling.deployed_configuration()
    base_runner = runtime_rolling.ReplayRunner(
        runtime_rolling.load_replay_entries(cli.cache, names)
    )
    answers = finalizer_bench.file_answers(names)
    vocabulary = terminal_vocabulary()
    tape_bytes = 300 * SAMPLE_RATE * 2

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-terminal-lifecycle.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/app/live_service_runtime.py",
            "moss_transcribe_diarize/app/live_session.py",
            "moss_transcribe_diarize/app/live_coordinator.py",
            "moss_transcribe_diarize/app/live_transcript_convergence.py",
        ],
        "paired_pass": str(finalizer_bench.PAIRED.relative_to(REPO)),
        "payload_vocabulary": sorted(vocabulary),
        "arms": {arm: {} for arm in ARMS},
        "file_arm": {},
        "cases": {},
    }
    for case in names:
        document["file_arm"][case] = finalizer_bench.flat_scores(finalizer_bench.file_scores(case))
        for arm in ARMS:
            document["arms"][arm][case] = run_arm(
                config, base_runner, case, arm, answers=answers, tape_bytes=tape_bytes
            )

    failures: list[str] = []
    for case in names:
        arms = {arm: document["arms"][arm][case] for arm in ARMS}
        report, case_failures = check_case(case, arms, vocabulary, document["file_arm"][case])
        document["cases"][case] = report
        failures.extend(case_failures)

    fresh = sum(document["arms"][arm][case]["fresh_requests"] for arm in ARMS for case in names)
    document["decode_cost"] = {
        "base_requests": base_runner.requests,
        "base_fresh_requests": base_runner.fresh_requests,
        "terminal_fresh_requests": fresh,
    }
    if base_runner.fresh_requests or fresh:
        failures.append(
            f"L9 {base_runner.fresh_requests} base and {fresh} terminal decodes were not replayed"
        )
    document["failures"] = failures
    document["passed"] = not failures

    print(f"cases: {', '.join(names)}")
    for case in names:
        for arm in ARMS:
            run = document["cases"][case][arm]
            print(
                f"  {arm:<15} {case:<18} stop={run['at_stop']['finalization_status']:<11} "
                f"after={run['after']['finalization_status']:<11} "
                f"WER {run['scores']['at_stop']['wer']:.6f} -> {run['scores']['after']['wer']:.6f}"
            )
            print(f"    {' -> '.join(run['event_order'])}")
    print(f"file arm: {json.dumps(document['file_arm'], indent=2)}")
    if cli.output is not None:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(f"wrote {cli.output}")
    if failures:
        print(f"FAIL ({len(failures)})")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("PASS: the meeting keeps its reader, its surface, and its last listener.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
