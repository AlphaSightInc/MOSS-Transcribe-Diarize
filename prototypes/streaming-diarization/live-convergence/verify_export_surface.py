#!/usr/bin/env python3
"""Does the EXPORT carry the surface the reader was shown -- and only what the switch promised?

Plan §10.5 step 7, the last item of E2's production sequence: "keep exports on current commits
until terminal/effective export tests pass, then switch export once in the same reviewed
change". §14 T3 states the property the switch has to make true: *export text equals visible
effective text*.

The export is `moss_transcribe_diarize.live_speaker_accuracy.hypothesis_from_live_snapshot` --
the one place that turns a served live snapshot into the transcript the campaign scores, the
F-certification harness reads, and `remeasure_live_vs_file.py` saves as `live-hypothesis.jsonl`.
Before this change it re-derived that transcript from the committed spans; a reader who watched
a rolling correction replace ten seconds of words still got the superseded ones in the file.

Three readings of one meeting are compared here, all produced by production code:

    audio frames -> LiveServiceRuntime -> snapshot().to_dict()
                                             |-> hypothesis_from_live_snapshot  (the export)
                                             |-> the same, surface removed      (the fallback)
                                             `-> the served portal page -> the DOM (the screen)

Zero MOSS requests by construction: the decoder replays the §10.2 grid's recorded answers
through the production response validator (step 4's driver). Node is required for the screen.
Reviewers can run this with no GPU:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_export_surface.py

Exit 0 iff every gate passes. Gates, fixed before the run:

- G1 the switch does not move a session nobody revised: on the base arm, the exported segments
  equal the committed reading of the SAME payload word for word and speaker for speaker, with
  every timestamp inside one sample (`6.25e-5` s), and the scores agree to 6 dp.
- G2 the base arm still reproduces the published live trio THROUGH THE EXPORT: per-case WER to
  6 dp and the trio means `.199870` / `.913490`.
- G3 the rolling arm reproduces the §10.4 selected arm through the export: per-case WER to
  6 dp and the trio means `.131861` / `.943916`. This is the point of the switch -- the number
  a paired rerun reports is now the arm the reader is reading.
- G4 export text equals visible effective text (§14 T3): for every case and both arms, the
  exported sequence equals the transcript node of the served portal page, parsed back with the
  production parser -- same speaker, same words, same seconds.
- G5 the fallback is byte-identical on real pre-surface artifacts: every checked-in
  `live-hypothesis.jsonl` under `prototypes/live-file-gap-baseline-20260824/` is reproduced
  byte for byte from its own trace by the switched export.
- G6 zero fresh MOSS requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_portal_surface as portal  # noqa: E402
import verify_runtime_rolling as runtime_rolling  # noqa: E402
import verify_session_text_authority as authority  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import hypothesis_from_live_snapshot  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402

PLACES = authority.PLACES
SELECTED_ARM = authority.SELECTED_ARM
GRID = runtime_rolling.GRID
SAMPLE_RATE = runtime_rolling.SAMPLE_RATE
BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824"
ONE_SAMPLE_SEC = 1.0 / SAMPLE_RATE

# What each checked-in baseline bundle covers. The durations are the ones its own driver
# declared when the file was written; a different number here would compare two different
# exports and call the difference a regression.
BASELINE_CASES = (
    ("trio-60s/acquired_jamie_dimon", 60.0),
    ("trio-60s/lex_bill_ackman", 60.0),
    ("trio-60s/lex_javier_milei", 60.0),
    ("trio-60s/lex_keyu_jin", 60.0),
    ("keyu-5m", 300.0),
)


def exported(payload: dict[str, Any], duration_sec: float) -> tuple[Segment, ...]:
    """The production export of one served snapshot."""

    return hypothesis_from_live_snapshot(
        {"snapshot": payload}, corpus_start_sample=0, corpus_duration_sec=duration_sec
    )


def without_surface(payload: dict[str, Any]) -> dict[str, Any]:
    """The same snapshot as it would have been served before §7.3 existed."""

    session = {
        key: value for key, value in payload["session"].items() if key != "effective_transcript"
    }
    return {**payload, "session": session}


def dom_segments(payload: dict[str, Any]) -> list[Segment]:
    """What the served portal page puts on the screen, read back off the DOM."""

    transcript = portal.render_surfaces([payload])[-1]
    return [
        Segment(item.start, item.end, item.speaker, item.text)
        for row in transcript.split("\n\n")
        for item in parse_transcript(row)
    ]


def compare(
    label: str, left: tuple[Segment, ...] | list[Segment], right: tuple[Segment, ...] | list[Segment]
) -> list[str]:
    """Segment-for-segment equality, with one sample of slack on the clock."""

    failures = []
    if len(left) != len(right):
        return [f"{label}: {len(left)} segments vs {len(right)}"]
    for index, (a, b) in enumerate(zip(left, right)):
        if a.text != b.text:
            failures.append(f"{label}: segment {index} text {a.text!r} vs {b.text!r}")
        elif a.speaker != b.speaker:
            failures.append(f"{label}: segment {index} speaker {a.speaker} vs {b.speaker}")
        elif abs(a.start - b.start) > ONE_SAMPLE_SEC or abs(a.end - b.end) > ONE_SAMPLE_SEC:
            failures.append(
                f"{label}: segment {index} [{a.start:.6f},{a.end:.6f}] vs "
                f"[{b.start:.6f},{b.end:.6f}] is more than one sample apart"
            )
        if len(failures) >= 3:
            break
    return failures


def scores(case: str, segments: tuple[Segment, ...] | list[Segment], duration_sec: float):
    return bench.score(
        bench.load_reference(case), bench.normalise(list(segments), duration_sec)
    )


def baseline_rows(path: Path) -> str:
    """The exact bytes `remeasure_live_vs_file.py` writes for a hypothesis."""

    return path.read_text(encoding="utf-8")


def rebuild_baseline(bundle: Path, duration_sec: float) -> str:
    """Re-derive a checked-in `live-hypothesis.jsonl` from its own trace, through the export."""

    snapshot = None
    for line in (bundle / "live/run-001/trace.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item.get("kind") == "terminal":
            snapshot = item.get("snapshot")
    if snapshot is None:
        raise RuntimeError(f"{bundle} has no terminal snapshot")
    rows = exported(snapshot, duration_sec)
    return "".join(
        json.dumps(
            {"start": row.start, "end": row.end, "speaker": row.speaker, "text": row.text},
            ensure_ascii=False,
        )
        + "\n"
        for row in rows
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--grid", type=Path, default=GRID / "grid.json")
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    grid = json.loads(cli.grid.read_text(encoding="utf-8"))
    rolling_expected = grid["summary"]["arms"][SELECTED_ARM]
    base_expected = dict(grid["summary"]["base_control"])
    base_expected["per_case"] = {
        case: {"wer_mean": grid["baseline_live"][case]["wer"]} for case in names
    }
    config = runtime_rolling.deployed_configuration()
    runner = runtime_rolling.ReplayRunner(runtime_rolling.load_replay_entries(cli.cache, names))

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-export-surface.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/live_speaker_accuracy.py",
            "moss_transcribe_diarize/live_surface.py",
            "moss_transcribe_diarize/live_replay.py",
        ],
        "grid": {
            "path": str(cli.grid.relative_to(REPO)),
            "sha256": hashlib.sha256(cli.grid.read_bytes()).hexdigest(),
            "arm": SELECTED_ARM,
        },
        "arms": {"base": {}, "rolling": {}},
        "baseline_fallback": {},
    }
    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    for case in names:
        # The driver's own denominator: the corpus audio, not the samples a session accepted.
        seconds = len(bench.read_pcm(bench.CORPUS / case / "audio.wav")) // 2 / SAMPLE_RATE
        for arm_name, rolling in (("base", False), ("rolling", True)):
            result = runtime_rolling.run_case(config, runner, case, rolling=rolling, collect_events=True)
            payload = result["service_snapshot"]
            rows = exported(payload, seconds)
            arm: dict[str, Any] = {
                "segments": len(rows),
                "scores": scores(case, rows, seconds),
                "driver_scores": result["scores"],
                "text_revision_version": payload["session"]["text_revision_version"],
                "provisional": payload["session"].get("provisional"),
            }

            # ---- G1: the switch does not move a session nobody revised.
            if arm_name == "base":
                fallback = exported(without_surface(payload), seconds)
                arm["fallback_segments"] = len(fallback)
                arm["fallback_scores"] = scores(case, fallback, seconds)
                failures.extend(compare(f"G1 {case}", rows, fallback))
                for metric in ("wer", "content_recall"):
                    if not close(arm["scores"][metric], arm["fallback_scores"][metric]):
                        failures.append(
                            f"G1 {case} {metric} {arm['scores'][metric]:.6f} != committed "
                            f"reading {arm['fallback_scores'][metric]:.6f}"
                        )

            # ---- G2/G3: the export reports the arm the grid selected.
            want = (
                base_expected["per_case"][case]["wer_mean"]
                if arm_name == "base"
                else rolling_expected["per_case"][case]["wer_mean"]
            )
            gate = "G2" if arm_name == "base" else "G3"
            if not close(arm["scores"]["wer"], want):
                failures.append(
                    f"{gate} {case} {arm_name} export wer {arm['scores']['wer']:.6f} != grid {want:.6f}"
                )

            # ---- G4: export text equals visible effective text.
            if payload["session"].get("provisional"):
                failures.append(
                    f"G4 {case}/{arm_name} the terminal snapshot still carries a provisional tail; "
                    "the screen would show a row the export cannot"
                )
            screen = dom_segments(payload)
            arm["dom_segments"] = len(screen)
            failures.extend(compare(f"G4 {case}/{arm_name} export-vs-screen", rows, screen))

            document["arms"][arm_name][case] = arm

    document["decode_cost"] = {"requests": runner.requests, "fresh_requests": runner.fresh_requests}

    # ---- G2/G3 trio means.
    for arm_name, expected in (("base", base_expected), ("rolling", rolling_expected)):
        arm = document["arms"][arm_name]
        mean_wer = sum(arm[case]["scores"]["wer"] for case in names) / len(names)
        mean_recall = sum(arm[case]["scores"]["content_recall"] for case in names) / len(names)
        document["arms"][arm_name]["_trio"] = {
            "wer_mean": mean_wer,
            "content_recall_mean": mean_recall,
        }
        if len(names) == len(bench.CASES):
            gate = "G2" if arm_name == "base" else "G3"
            if not close(mean_wer, expected["wer"]["mean"]):
                failures.append(
                    f"{gate} trio {arm_name} export wer {mean_wer:.6f} != grid "
                    f"{expected['wer']['mean']:.6f}"
                )
            if not close(mean_recall, expected["content_recall"]["mean"]):
                failures.append(
                    f"{gate} trio {arm_name} export recall {mean_recall:.6f} != grid "
                    f"{expected['content_recall']['mean']:.6f}"
                )

    # ---- G5: the fallback reproduces every checked-in pre-surface hypothesis, byte for byte.
    for relative, duration in BASELINE_CASES:
        bundle = BASELINE / relative
        checked_in = bundle / "live-hypothesis.jsonl"
        rebuilt = rebuild_baseline(bundle, duration)
        want = baseline_rows(checked_in)
        node = {
            "duration_sec": duration,
            "rows": rebuilt.count("\n"),
            "sha256": hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
            "checked_in_sha256": hashlib.sha256(want.encode("utf-8")).hexdigest(),
        }
        node["identical"] = node["sha256"] == node["checked_in_sha256"]
        if not node["identical"]:
            failures.append(f"G5 {relative} export no longer reproduces its checked-in hypothesis")
        document["baseline_fallback"][relative] = node

    # ---- G6: no fresh decode.
    if runner.fresh_requests:
        failures.append(f"G6 {runner.fresh_requests} fresh MOSS requests were made")

    document["failures"] = failures
    document["passed"] = not failures
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for case in names:
        for arm_name in ("base", "rolling"):
            arm = document["arms"][arm_name][case]
            print(
                f"{case:<18} {arm_name:<7} export_segments={arm['segments']:<3} "
                f"dom={arm['dom_segments']:<3} wer={arm['scores']['wer']:.6f} "
                f"recall={arm['scores']['content_recall']:.6f}"
            )
    for arm_name, expected in (("base", base_expected), ("rolling", rolling_expected)):
        trio = document["arms"][arm_name]["_trio"]
        print(
            f"{'TRIO ' + arm_name:<18} wer={trio['wer_mean']:.6f} (grid {expected['wer']['mean']:.6f}) "
            f"recall={trio['content_recall_mean']:.6f} "
            f"(grid {expected['content_recall']['mean']:.6f})"
        )
    for relative, node in document["baseline_fallback"].items():
        print(
            f"{'FALLBACK ' + relative:<40} rows={node['rows']:<4} "
            f"{'identical' if node['identical'] else 'DIFFERENT'}"
        )
    print(
        f"{document['decode_cost']['requests']} replayed decodes, "
        f"{document['decode_cost']['fresh_requests']} fresh (no GPU)"
    )
    for failure in failures:
        print(f"FAIL {failure}")
    print("PASS" if not failures else f"FAILED {len(failures)} gate checks")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
