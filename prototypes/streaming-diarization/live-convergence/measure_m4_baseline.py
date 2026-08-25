"""Measure what a terminal pass must land on, before any terminal pass exists.

M4 (plan E4) gates the *terminal* surface against the **paired file arm** of the same
pass: WER within `.010` absolute (plan G8), DER within `.020` absolute (the owner-directed
prerelease companion). That comparator is not the pre-campaign baseline and not the rolling
surface -- it is the file arm the deployed service produced from identical audio bytes in
the same run -- so this driver re-reads it and reports, for every M4 case:

  * **the target**: the paired file arm's WER / DER / speaker accuracy / coverage;
  * **the distance**: what the rolling surface E2 shipped scores today, and therefore how
    far terminal has to move on each axis;
  * **the gate reading if terminal shipped nothing** -- i.e. whether today's surface already
    sits inside G8's `.010` and the `.020` DER companion. Where it does, the gate cannot
    detect a terminal pass at all, and the report says so rather than banking a pass;
  * **where converging to file is a REGRESSION**, per case per axis, with the arithmetic
    that says whether a no-regression gate on that axis could coexist with the convergence
    bound. On at least one axis it provably cannot, and a preregistration that discovers
    that after the fact is worthless;
  * **the terminal window plan** computed from production `plan_windows` and the deployed
    `WindowedRunner` geometry, so "runs through the existing 150/120 runner" is a checked
    number of windows per case rather than a sentence;
  * **the complete-tape budget** at each duration from the production sample rate and PCM
    width -- Appendix B Q10 asserts "<= ~10 MB PCM at the 5-minute cap" and that assertion
    decides whether the tape can live in memory;
  * **the accounting comparator** (accepted samples per session) G10 must equal;
  * **file-arm stability**: the same file arm measured pre-campaign and at the M2 exit, so
    the comparator's own provenance is checked instead of assumed.

The three-minute case (`lex_adam_frank`) is not in the M2 exit passes -- it is gated by plan
§12.2 but had never been run through the live path when this instrument was written
(precondition P-M4-A). Its pass therefore lives in its own root, given by `--three-minute-root`,
and whether it has a comparator is **read from that disk** rather than declared: an absent or
empty root reports `MISSING`, because a comparator table that quietly omits a gated case is
how a milestone gates two thirds of its corpus and reports a pass.

Usage:
  python measure_m4_baseline.py [--passes-root <dir>] [--three-minute-root <dir>]
                                [--output out.json]
  python measure_m4_baseline.py --selftest

No GPU, no service, no MOSS request: it reads checked-in passes.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluator_v2 import Segment as V2Segment, score_v2, speech_regions_from_wav  # noqa: E402
from verify_m2_exit import (  # noqa: E402
    CASE_DURATION_SEC,
    FIVE_MINUTE_CASE,
    RUNS,
    TRIO_CASES,
    case_paths,
    corpus_contract,
    load_reference_rows,
)
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    LIVE_SAMPLE_RATE,
    PCM16_BYTES_PER_SAMPLE,
)
from moss_transcribe_diarize.app.windowed_transcription import (  # noqa: E402
    WindowedRunner,
    plan_windows,
)

DEFAULT_PASSES = REPO / "evidence/live-convergence-0824/M2-e2-exit/passes"
BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824"
ARMS = ("file", "live")

#: The case plan §12.2 gates that this campaign has never run through the live path. Its
#: corpus paths are stated here rather than in `cases.json` because `cases.json` entries
#: carry checked-in baseline hypotheses and this case has none to point at yet.
THREE_MINUTE_CASE = "lex_adam_frank"
THREE_MINUTE_ROOT = REPO / "prototypes/streaming-diarization/data/real/calibration_diarization_3min"
#: Where that case's paired passes live once acquired (iteration 23, P-M4-A). It is a separate
#: root because the M2 exit predates the case; the layout inside is the single-case one
#: `verify_m2_exit.case_paths` reads for the five-minute case.
DEFAULT_THREE_MINUTE_PASSES = REPO / "evidence/live-convergence-0824/M4-three-minute/passes"

#: Plan G8 and the owner-directed prerelease companion, verbatim. Nothing here may move:
#: they are the milestone's bounds, and this driver only ever reports distances to them.
G8_WER_TOLERANCE = 0.010
TERMINAL_DER_TOLERANCE = 0.020


def single_case_pass_dir(root: Path, run: str) -> Path | None:
    """The pass directory for one run under a single-case pass root, found rather than named.

    `run_paired_case.sh` labels its output `<label>-A` / `<label>-B`; the label is the
    operator's, not this instrument's, so the run suffix is the contract and the label is
    read off the disk. Ambiguity is refused rather than resolved by picking one.
    """

    if not root.is_dir():
        return None
    matches = sorted(child for child in root.iterdir() if child.is_dir() and child.name.endswith(f"-{run}"))
    if len(matches) > 1:
        raise SystemExit(
            f"REFUSED: {root} holds {len(matches)} candidate pass directories for run {run}: "
            f"{[m.name for m in matches]}"
        )
    return matches[0] if matches else None


def three_minute_paths(root: Path, run: str) -> dict[str, Path]:
    """The five-file contract for the three-minute case, in the single-case layout."""

    pass_dir = single_case_pass_dir(root, run) or (root / f"missing-{run}")
    return {
        "results": pass_dir / "results.json",
        "file_hypothesis": pass_dir / "file-hypothesis.jsonl",
        "live_hypothesis": pass_dir / "live-hypothesis.jsonl",
        "trace": pass_dir / "live/run-001/trace.jsonl",
        "summary": pass_dir / "live/run-001/summary.json",
    }


def m4_cases(three_minute_root: Path = DEFAULT_THREE_MINUTE_PASSES) -> dict[str, dict]:
    """Every case plan §12.2 gates, as rescoped by Appendix B: trio + 3 min + 5 min."""

    contract = corpus_contract()
    cases: dict[str, dict] = {}
    for case in TRIO_CASES:
        cases[case] = {
            "duration_sec": CASE_DURATION_SEC.get(case, 60.0),
            "audio": REPO / contract[case]["audio"],
            "reference": REPO / contract[case]["reference"],
            "has_pass": True,
        }
    cases[THREE_MINUTE_CASE] = {
        "duration_sec": 180.0,
        "audio": THREE_MINUTE_ROOT / "samples" / THREE_MINUTE_CASE / "audio.wav",
        "reference": THREE_MINUTE_ROOT / "samples" / THREE_MINUTE_CASE / "reference.jsonl",
        # Read from disk: the case gates M4 whether or not it has a comparator, and P-M4-A is
        # satisfied only when every run named by RUNS is on disk under its own root.
        "has_pass": all(
            three_minute_paths(three_minute_root, run)["results"].exists() for run in RUNS
        ),
        "passes_root": three_minute_root,
    }
    cases[FIVE_MINUTE_CASE] = {
        "duration_sec": CASE_DURATION_SEC.get(FIVE_MINUTE_CASE, 300.0),
        "audio": REPO / contract[FIVE_MINUTE_CASE]["audio"],
        "reference": REPO / contract[FIVE_MINUTE_CASE]["reference"],
        "has_pass": True,
    }
    return cases


# ------------------------------------------------------------------ reading one arm


def arm_scores(results: Path, case: str) -> dict[str, dict]:
    """The deployed scorer's own numbers for both arms of one case, from one pass."""

    if not results.exists():
        return {}
    data = json.loads(results.read_text())
    if "results" in data:  # the five-minute driver writes a single case
        return data["results"]
    for node in data.get("cases", []):
        if node["case_id"] == case:
            return node["arms"]
    return {}


def deployed_axes(arm: dict) -> dict:
    """The four axes M4 gates or reports, from one arm of `results.json`."""

    scores = arm.get("scores") or {}
    diarization = scores.get("diarization") or {}
    speaker = scores.get("speaker") or {}
    tbsa = scores.get("tbsa") or {}
    return {
        "wer": tbsa.get("wer"),
        "text_coverage": tbsa.get("text_coverage"),
        "der": diarization.get("der"),
        "miss": diarization.get("miss"),
        "false_alarm": diarization.get("false_alarm"),
        "speaker_confusion": diarization.get("speaker_confusion"),
        "speaker_accuracy": speaker.get("speaker_accuracy"),
        "segments": (arm.get("meta") or {}).get("segments"),
    }


def v2_axes(reference: list[V2Segment], hypothesis_path: Path, regions) -> dict | None:
    """Evaluator v2's non-gameable axes for one arm, when its hypothesis is on disk.

    The deployed DER charges silence inside a gapless turn against whoever published a long
    segment (plan §3.4, the extent artifact). That is exactly the axis on which file mode
    and the rolling surface differ most, so a milestone that moves the surface *towards* file
    needs the extent-free reading beside the gated one.
    """

    if not hypothesis_path.exists():
        return None
    hypothesis = [V2Segment(**row) for row in load_reference_rows(hypothesis_path)]
    scored = score_v2(
        reference,
        hypothesis,
        speech_regions=regions,
        speech_regions_source="webrtcvad_mode1_10ms" if regions else "reference_intervals",
    )
    return {
        "wer": scored["wer"]["wer"],
        "content_recall": scored["content_recall"],
        "matched_word_speaker_accuracy": scored["matched_word_speaker"][
            "matched_word_speaker_accuracy"
        ],
        "der_reference_speech": scored["der_reference_speech"]["der"],
    }


# ------------------------------------------------------------------ derived quantities


def gate_reading(rolling: float | None, target: float | None, tolerance: float) -> dict | None:
    """What a `within-tolerance-of-file` gate says about the surface shipped TODAY.

    `inside` true means the gate is already satisfied by the rolling surface, so it cannot
    by itself demonstrate that a terminal pass did anything. That is a property of the gate
    worth knowing before the pass exists, not an excuse to weaken it.
    """

    if rolling is None or target is None:
        return None
    distance = rolling - target
    return {
        "target": round(target, 6),
        "rolling": round(rolling, 6),
        "signed_distance": round(distance, 6),
        "absolute_distance": round(abs(distance), 6),
        "tolerance": tolerance,
        "inside_without_terminal": abs(distance) <= tolerance + 1e-12,
    }


def convergence_conflict(
    rolling: float | None, target: float | None, tolerance: float, lower_is_better: bool
) -> dict | None:
    """Can `within tolerance of file` and `no worse than rolling` both hold on this axis?

    Converging to the file arm is only an improvement where the file arm is better. Where it
    is worse by more than the tolerance, the two readings are arithmetically incompatible:
    every value the convergence gate admits is worse than what the rolling surface already
    publishes. A campaign gate may only ever *strengthen* a PRD bound, so an axis that fails
    this check may not become a gate -- it becomes a recorded decision.
    """

    if rolling is None or target is None:
        return None
    file_is_worse = (target > rolling) if lower_is_better else (target < rolling)
    margin = abs(target - rolling)
    return {
        "file_arm_is_worse_than_rolling": bool(file_is_worse),
        "regression_if_terminal_equals_file": round(margin, 6) if file_is_worse else 0.0,
        # The best value the convergence bound admits, and whether it clears rolling.
        "no_regression_gate_satisfiable": not (file_is_worse and margin > tolerance + 1e-12),
    }


def terminal_window_plan(duration_sec: float) -> dict:
    """How the existing 150/120 runner will cover this case (plan §12.3 step 4).

    Read from production rather than restated: `WindowedRunner` decides both numbers, and a
    single-window case takes the un-windowed delegate path, which is why the trio's terminal
    pass is expected to reproduce file mode exactly rather than approximately.
    """

    window = float(WindowedRunner.window_seconds)
    stride = float(WindowedRunner.stride_seconds)
    windows = plan_windows(duration_sec, window_seconds=window, stride_seconds=stride)
    return {
        "window_seconds": window,
        "stride_seconds": stride,
        "window_count": len(windows),
        "windows": [[float(w.start), float(w.end)] for w in windows],
        "single_window_delegate_path": len(windows) == 1,
    }


def tape_budget(duration_sec: float) -> dict:
    """Appendix B Q10's premise, in bytes, from the production sample rate and PCM width."""

    samples = int(round(duration_sec * LIVE_SAMPLE_RATE))
    return {
        "sample_rate": LIVE_SAMPLE_RATE,
        "bytes_per_sample": PCM16_BYTES_PER_SAMPLE,
        "samples": samples,
        "bytes": samples * PCM16_BYTES_PER_SAMPLE,
        "mib": round(samples * PCM16_BYTES_PER_SAMPLE / (1 << 20), 3),
    }


def wav_facts(path: Path) -> dict | None:
    """Duration and format of a corpus WAV, so a stated duration is never assumed."""

    if not path.exists():
        return None
    with wave.open(str(path)) as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
        return {
            "frames": frames,
            "sample_rate": rate,
            "channels": handle.getnchannels(),
            "sample_width_bytes": handle.getsampwidth(),
            "duration_sec": round(frames / rate, 6),
            "pcm_bytes": frames * handle.getnchannels() * handle.getsampwidth(),
        }


def accounting(summary_path: Path) -> dict | None:
    """The G10 comparator: what the session accepted, and what it accounted for."""

    if not summary_path.exists():
        return None
    data = json.loads(summary_path.read_text())
    accepted = data.get("accepted_samples")
    accounted = data.get("accounted_samples")
    return {
        "accepted_samples": accepted,
        "accounted_samples": accounted,
        "equal": accepted is not None and accepted == accounted,
        "accepted_seconds": round(accepted / LIVE_SAMPLE_RATE, 6) if accepted else None,
    }


def baseline_file_arm(case: str) -> dict | None:
    """The same file arm as the pre-campaign baseline measured it.

    G8's comparator is only as trustworthy as its stability: if the file arm moved during the
    campaign, every terminal delta is measured against a moving target.
    """

    if case == FIVE_MINUTE_CASE:
        path = BASELINE / "keyu-5m/results.json"
        if not path.exists():
            return None
        return deployed_axes((json.loads(path.read_text()).get("results") or {}).get("file", {}))
    path = BASELINE / "trio-60s/results.json"
    if not path.exists():
        return None
    for node in json.loads(path.read_text()).get("cases", []):
        if node["case_id"] == case:
            return deployed_axes(node["arms"]["file"])
    return None


# ------------------------------------------------------------------ the table


def measure(passes_root: Path, three_minute_root: Path = DEFAULT_THREE_MINUTE_PASSES) -> dict:
    cases = m4_cases(three_minute_root)
    report: dict = {
        "passes_root": str(passes_root),
        "three_minute_passes_root": str(three_minute_root),
        "g8_wer_tolerance": G8_WER_TOLERANCE,
        "terminal_der_tolerance": TERMINAL_DER_TOLERANCE,
        "cases": {},
    }
    for case, spec in cases.items():
        reference = [V2Segment(**row) for row in load_reference_rows(spec["reference"])]
        regions = speech_regions_from_wav(spec["audio"]) if spec["audio"].exists() else None
        node: dict = {
            "duration_sec": spec["duration_sec"],
            "reference_speakers": sorted({seg.speaker for seg in reference}),
            "reference_segments": len(reference),
            "audio": wav_facts(spec["audio"]),
            "terminal_window_plan": terminal_window_plan(spec["duration_sec"]),
            "tape_budget": tape_budget(spec["duration_sec"]),
            "comparator": "measured" if spec["has_pass"] else "MISSING",
            "runs": {},
        }
        if spec["has_pass"]:
            for run in RUNS:
                paths = (
                    three_minute_paths(spec["passes_root"], run)
                    if case == THREE_MINUTE_CASE
                    else case_paths(passes_root, case, run)
                )
                arms = arm_scores(paths["results"], case)
                run_node: dict = {}
                for arm in ARMS:
                    if arm in arms:
                        run_node[arm] = deployed_axes(arms[arm])
                for arm, key in (("file", "file_hypothesis"), ("live", "live_hypothesis")):
                    if arm in run_node:
                        scored = v2_axes(reference, paths[key], regions)
                        if scored:
                            run_node[arm]["v2"] = scored
                run_node["accounting"] = accounting(paths["summary"])
                node["runs"][run] = run_node
            node["runs_agree"] = _runs_agree(node["runs"])
            node["baseline_file_arm"] = baseline_file_arm(case)
            node["file_arm_stable"] = _file_arm_stable(node)
            node["terminal_targets"] = _targets(node)
        report["cases"][case] = node
    report["summary"] = summarize(report)
    return report


def _comparable(run_node: dict) -> dict:
    return {
        arm: {k: v for k, v in (run_node.get(arm) or {}).items()}
        for arm in ARMS
        if run_node.get(arm)
    }


def _runs_agree(runs: dict) -> bool:
    seen = [json.dumps(_comparable(node), sort_keys=True) for node in runs.values() if node]
    return len(set(seen)) <= 1 and bool(seen)


def _file_arm_stable(node: dict) -> bool | None:
    """Did the pre-campaign file arm and the M2-exit file arm score identically?"""

    baseline = node.get("baseline_file_arm")
    if not baseline:
        return None
    for run in node["runs"].values():
        current = run.get("file")
        if not current:
            continue
        for axis in ("wer", "der", "speaker_accuracy", "text_coverage"):
            if baseline.get(axis) != current.get(axis):
                return False
    return True


def _targets(node: dict) -> dict:
    """Everything M4's gates will read off one case, computed before terminal exists."""

    run = node["runs"].get("A") or {}
    file_arm = run.get("file") or {}
    live_arm = run.get("live") or {}
    targets = {
        "wer": gate_reading(live_arm.get("wer"), file_arm.get("wer"), G8_WER_TOLERANCE),
        "der": gate_reading(live_arm.get("der"), file_arm.get("der"), TERMINAL_DER_TOLERANCE),
        "conflicts": {
            "der": convergence_conflict(
                live_arm.get("der"), file_arm.get("der"), TERMINAL_DER_TOLERANCE, True
            ),
            "wer": convergence_conflict(
                live_arm.get("wer"), file_arm.get("wer"), G8_WER_TOLERANCE, True
            ),
            "speaker_accuracy": convergence_conflict(
                live_arm.get("speaker_accuracy"),
                file_arm.get("speaker_accuracy"),
                TERMINAL_DER_TOLERANCE,
                False,
            ),
            "text_coverage": convergence_conflict(
                live_arm.get("text_coverage"),
                file_arm.get("text_coverage"),
                G8_WER_TOLERANCE,
                False,
            ),
        },
    }
    file_v2 = (file_arm.get("v2") or {})
    live_v2 = (live_arm.get("v2") or {})
    if file_v2 and live_v2:
        targets["v2_shift_if_terminal_equals_file"] = {
            axis: round(file_v2[axis] - live_v2[axis], 6)
            for axis in ("wer", "content_recall", "matched_word_speaker_accuracy", "der_reference_speech")
            if axis in file_v2 and axis in live_v2
        }
    return targets


#: Which way is better on each evaluator-v2 axis, so "regression" is read rather than guessed.
_V2_LOWER_IS_BETTER = ("wer", "der_reference_speech")


def summarize(report: dict) -> dict:
    scored = [c for c, node in report["cases"].items() if node["comparator"] == "measured"]
    trio = [c for c in scored if c in TRIO_CASES]

    def mean(cases: list[str], arm: str, axis: str) -> float | None:
        values = [
            ((report["cases"][c]["runs"].get("A") or {}).get(arm) or {}).get(axis)
            for c in cases
        ]
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 6) if values else None

    regressions = {}
    for case in scored:
        conflicts = (report["cases"][case].get("terminal_targets") or {}).get("conflicts") or {}
        hits = {
            axis: node
            for axis, node in conflicts.items()
            if node and node["file_arm_is_worse_than_rolling"]
        }
        if hits:
            regressions[case] = hits
    unsatisfiable = {
        case: [axis for axis, node in axes.items() if not node["no_regression_gate_satisfiable"]]
        for case, axes in regressions.items()
    }
    # The extent-free reading of the same question. The deployed DER charges silence inside a
    # gapless turn (plan §3.4), which is precisely where file mode's long segments differ from
    # the rolling surface's short ones -- so "does converging to file cost real speaker
    # quality, or only metric extent?" is answerable only on evaluator v2's axes.
    v2_regressions = {}
    for case in scored:
        shift = (report["cases"][case].get("terminal_targets") or {}).get(
            "v2_shift_if_terminal_equals_file"
        )
        if not shift:
            continue
        worse = {
            axis: value
            for axis, value in shift.items()
            if (value > 0 if axis in _V2_LOWER_IS_BETTER else value < 0)
        }
        if worse:
            v2_regressions[case] = worse

    return {
        "cases_gated": list(report["cases"]),
        "cases_with_comparator": scored,
        "cases_missing_comparator": [
            c for c, node in report["cases"].items() if node["comparator"] != "measured"
        ],
        "trio_mean": {
            arm: {
                axis: mean(trio, arm, axis)
                for axis in ("wer", "der", "speaker_accuracy", "text_coverage")
            }
            for arm in ARMS
        },
        "gates_already_inside_without_terminal": {
            case: {
                axis: node["inside_without_terminal"]
                for axis, node in (
                    (report["cases"][case].get("terminal_targets") or {})
                ).items()
                if axis in ("wer", "der") and node
            }
            for case in scored
        },
        "converging_to_file_regresses": regressions,
        "axes_where_no_regression_gate_is_unsatisfiable": {
            case: axes for case, axes in unsatisfiable.items() if axes
        },
        "file_arm_stable_since_precampaign": {
            case: report["cases"][case].get("file_arm_stable") for case in scored
        },
        "accounting_equal": {
            case: all(
                (run.get("accounting") or {}).get("equal")
                for run in report["cases"][case]["runs"].values()
                if run.get("accounting")
            )
            for case in scored
        },
        "tape_budget_max_mib": max(
            node["tape_budget"]["mib"] for node in report["cases"].values()
        ),
        "v2_axes_regressing_if_terminal_equals_file": v2_regressions,
        "terminal_windows": {
            case: node["terminal_window_plan"]["window_count"]
            for case, node in report["cases"].items()
        },
    }


# ------------------------------------------------------------------ rendering


def _fmt(value: float | None, places: int = 6) -> str:
    return "-" if value is None else f"{value:.{places}f}"


def render(report: dict) -> str:
    lines: list[str] = []
    summary = report["summary"]
    lines.append(f"passes root : {report['passes_root']}")
    lines.append(f"3-min root  : {report['three_minute_passes_root']}")
    lines.append(
        f"tolerances  : WER {report['g8_wer_tolerance']:.3f} (plan G8), "
        f"DER {report['terminal_der_tolerance']:.3f} (owner prerelease companion)"
    )
    lines.append("")
    header = (
        f"{'case':<18}{'arm':<6}{'WER':>10}{'DER':>10}{'spk_acc':>10}{'cov':>10}"
        f"{'v2_WER':>10}{'v2_recall':>11}{'v2_word_spk':>13}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for case, node in report["cases"].items():
        if node["comparator"] != "measured":
            lines.append(
                f"{case:<18}{'--':<6}NO LIVE PASS IN THIS CAMPAIGN - comparator must be acquired"
            )
            continue
        run = node["runs"].get("A") or {}
        for arm in ARMS:
            data = run.get(arm) or {}
            if not data:
                continue
            v2 = data.get("v2") or {}
            lines.append(
                f"{case:<18}{arm:<6}{_fmt(data.get('wer')):>10}{_fmt(data.get('der')):>10}"
                f"{_fmt(data.get('speaker_accuracy')):>10}{_fmt(data.get('text_coverage')):>10}"
                f"{_fmt(v2.get('wer')):>10}{_fmt(v2.get('content_recall')):>11}"
                f"{_fmt(v2.get('matched_word_speaker_accuracy')):>13}"
            )
        targets = node.get("terminal_targets") or {}
        for axis in ("wer", "der"):
            reading = targets.get(axis)
            if not reading:
                continue
            verdict = "ALREADY INSIDE" if reading["inside_without_terminal"] else "must move"
            lines.append(
                f"{'':<18}{'':<6}terminal {axis.upper()} target {reading['target']:.6f}, "
                f"rolling {reading['rolling']:.6f}, distance {reading['signed_distance']:+.6f} "
                f"(tol {reading['tolerance']:.3f}) -> {verdict}"
            )
    lines.append("")
    trio = summary["trio_mean"]
    lines.append(
        f"TRIO mean   file  WER {_fmt(trio['file']['wer'])}  DER {_fmt(trio['file']['der'])}  "
        f"spk {_fmt(trio['file']['speaker_accuracy'])}  cov {_fmt(trio['file']['text_coverage'])}"
    )
    lines.append(
        f"TRIO mean   live  WER {_fmt(trio['live']['wer'])}  DER {_fmt(trio['live']['der'])}  "
        f"spk {_fmt(trio['live']['speaker_accuracy'])}  cov {_fmt(trio['live']['text_coverage'])}"
    )
    lines.append("")
    for case, axes in summary["converging_to_file_regresses"].items():
        for axis, node in axes.items():
            state = (
                "a no-regression gate on this axis is UNSATISFIABLE beside the convergence bound"
                if not node["no_regression_gate_satisfiable"]
                else "a no-regression gate is still satisfiable"
            )
            lines.append(
                f"REGRESSION  {case} {axis}: terminal==file costs "
                f"{node['regression_if_terminal_equals_file']:.6f} -> {state}"
            )
    lines.append("")
    v2_bad = summary["v2_axes_regressing_if_terminal_equals_file"]
    for case in summary["cases_with_comparator"]:
        shift = (report["cases"][case].get("terminal_targets") or {}).get(
            "v2_shift_if_terminal_equals_file"
        ) or {}
        if not shift:
            continue
        worse = v2_bad.get(case) or {}
        lines.append(
            f"v2 shift    {case}: "
            + "  ".join(f"{axis} {value:+.6f}" for axis, value in sorted(shift.items()))
            + (f"   WORSE ON: {', '.join(sorted(worse))}" if worse else "   worse on nothing")
        )
    lines.append("")
    lines.append(
        "terminal windows (150/120): "
        + ", ".join(f"{case} {count}" for case, count in summary["terminal_windows"].items())
    )
    lines.append(
        f"complete-tape budget, largest case: {summary['tape_budget_max_mib']:.3f} MiB "
        "(Appendix B Q10 asserts <= ~10 MB)"
    )
    lines.append(
        "file arm stable since pre-campaign: "
        + ", ".join(
            f"{c}={'no-precampaign-baseline' if v is None else v}"
            for c, v in summary["file_arm_stable_since_precampaign"].items()
        )
    )
    lines.append(
        "two fresh passes agree: "
        + ", ".join(
            f"{c}={report['cases'][c].get('runs_agree')}"
            for c in summary["cases_with_comparator"]
        )
    )
    lines.append(
        "accepted == accounted: "
        + ", ".join(f"{c}={v}" for c, v in summary["accounting_equal"].items())
    )
    missing = summary["cases_missing_comparator"]
    lines.append(
        f"MISSING COMPARATOR: {', '.join(missing) if missing else 'none'} "
        "(gated by plan §12.2 as rescoped by Appendix B; must be acquired before it can gate)"
    )
    return "\n".join(lines)


# ------------------------------------------------------------------ self-test


def selftest() -> int:
    """Prove every derived quantity reacts before a terminal number is measured against it."""

    failures: list[str] = []

    def check(name: str, got, want) -> None:
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    inside = gate_reading(0.100, 0.095, 0.010)
    check("distance inside the tolerance", inside["inside_without_terminal"], True)
    check("signed distance keeps its direction", inside["signed_distance"], 0.005)
    outside = gate_reading(0.200, 0.150, 0.010)
    check("distance outside the tolerance", outside["inside_without_terminal"], False)
    check("absolute distance", outside["absolute_distance"], 0.05)
    edge = gate_reading(0.160, 0.150, 0.010)
    check("exactly at the tolerance is inside", edge["inside_without_terminal"], True)
    check("no comparator -> no reading", gate_reading(None, 0.1, 0.01), None)

    better = convergence_conflict(0.20, 0.15, 0.010, True)
    check("file better -> no regression", better["file_arm_is_worse_than_rolling"], False)
    check("file better -> gate satisfiable", better["no_regression_gate_satisfiable"], True)
    worse_small = convergence_conflict(0.100, 0.105, 0.020, True)
    check("file slightly worse -> regression named", worse_small["file_arm_is_worse_than_rolling"], True)
    check(
        "small regression still admits a no-regression gate",
        worse_small["no_regression_gate_satisfiable"],
        True,
    )
    worse_big = convergence_conflict(0.100, 0.150, 0.020, True)
    check(
        "regression beyond the tolerance makes the gate unsatisfiable",
        worse_big["no_regression_gate_satisfiable"],
        False,
    )
    check("regression magnitude", worse_big["regression_if_terminal_equals_file"], 0.05)
    higher = convergence_conflict(0.90, 0.85, 0.020, False)
    check(
        "higher-is-better axis reads the other way",
        (higher["file_arm_is_worse_than_rolling"], higher["no_regression_gate_satisfiable"]),
        (True, False),
    )

    check("60 s is one window", terminal_window_plan(60.0)["window_count"], 1)
    check("60 s takes the delegate path", terminal_window_plan(60.0)["single_window_delegate_path"], True)
    check("180 s is two windows", terminal_window_plan(180.0)["window_count"], 2)
    check("300 s is three windows", terminal_window_plan(300.0)["window_count"], 3)
    check(
        "the plan reads production geometry",
        (
            terminal_window_plan(60.0)["window_seconds"],
            terminal_window_plan(60.0)["stride_seconds"],
        ),
        (float(WindowedRunner.window_seconds), float(WindowedRunner.stride_seconds)),
    )

    budget = tape_budget(300.0)
    check("five minutes of PCM16 at the live rate", budget["bytes"], 300 * LIVE_SAMPLE_RATE * 2)
    check("and it is under ten megabytes", budget["mib"] < 10.0, True)

    check(
        "v2 direction table names both lower-is-better axes",
        sorted(_V2_LOWER_IS_BETTER),
        ["der_reference_speech", "wer"],
    )
    check(
        "accounting equality is read, not assumed",
        accounting(Path("/nonexistent/summary.json")),
        None,
    )

    # The three-minute comparator is read off the disk, in both directions (P-M4-A).
    check(
        "an absent pass root has no pass directory",
        single_case_pass_dir(Path("/nonexistent/three-minute"), "A"),
        None,
    )
    scratch = Path(tempfile.mkdtemp(prefix="m4-baseline-selftest-"))
    try:
        check(
            "an empty pass root leaves the case MISSING",
            m4_cases(scratch)[THREE_MINUTE_CASE]["has_pass"],
            False,
        )
        for run in RUNS:
            target = scratch / f"anylabel-{run}"
            target.mkdir()
            (target / "results.json").write_text("{}")
        check(
            "both runs on disk make the case gateable, whatever the label",
            m4_cases(scratch)[THREE_MINUTE_CASE]["has_pass"],
            True,
        )
        check(
            "and its five-file contract points inside that directory",
            three_minute_paths(scratch, RUNS[0])["summary"].parents[2].name,
            f"anylabel-{RUNS[0]}",
        )
        (scratch / f"otherlabel-{RUNS[0]}").mkdir()
        ambiguous = False
        try:
            single_case_pass_dir(scratch, RUNS[0])
        except SystemExit:
            ambiguous = True
        check("two candidate pass directories are refused, not picked from", ambiguous, True)
        check(
            "one missing run is not a comparator",
            m4_cases(scratch / "nothing-here")[THREE_MINUTE_CASE]["has_pass"],
            False,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    for line in failures:
        print(f"FAIL {line}")
    print(f"selftest: {'PASS' if not failures else 'FAIL'} ({len(failures)} failures)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes-root", type=Path, default=DEFAULT_PASSES)
    parser.add_argument("--three-minute-root", type=Path, default=DEFAULT_THREE_MINUTE_PASSES)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--selftest", action="store_true", help="prove the derived quantities react")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    report = measure(args.passes_root.resolve(), args.three_minute_root.resolve())
    print(render(report))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
