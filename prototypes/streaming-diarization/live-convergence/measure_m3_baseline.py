"""Measure the speaker surface the M2 exit actually serves, so M3's gates can name it.

M3's PRD gates were written against the *pre-campaign* live arm (trio DER .2235 / .1945 /
.1112, speaker accuracy .8437, five-minute DER .0947). The M2 exit measured the deployed
rolling surface at trio DER mean .111278 and speaker accuracy mean .888722 with **no E3 code
at all**: longer surface segments shrank the extent artifact plan §3.4 named. Gating E3
against a surface nobody serves any more would let M3 pass by doing nothing, so this driver
re-reads the M2 exit bundle and reports the comparator table M3 must be preregistered against:

  * DER **decomposed** into miss / false alarm / confusion, per case per arm. Only the
    confusion term is reachable by a speaker-authority change; miss is unpublished speech and
    belongs to the text surface. `miss + false_alarm` is therefore the floor no S1/S2 arm can
    go below, and it is what bounds E3's upside before any arm is written.
  * `score_live_speaker_accuracy`'s axis and evaluator v2's matched-word axis side by side
    (Appendix B's rescoped G4 requires both reported).
  * Unattributed (`S00`) seconds and segments -- plan §11.2's "S00 duration does not increase"
    needs a number to not increase from.
  * Two-speaker mixed-window collapse, counted on the *deployed* rolling geometry: a window
    where the reference carries two voices each above the production birth floor, and the
    published surface names only one of them.

Every rule this driver applies is read from production (`UNATTRIBUTED_SPEAKER`, the rolling
geometry, the album birth floor) rather than spelled here, so a production change moves the
measurement instead of silently disagreeing with it.

Usage:
  python measure_m3_baseline.py [--passes-root <dir>] [--output out.json]

No GPU, no service, no MOSS request: it reads the checked-in M2 exit passes.
"""
from __future__ import annotations

import argparse
import json
import sys
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
from moss_transcribe_diarize.live_surface import UNATTRIBUTED_SPEAKER  # noqa: E402
from moss_transcribe_diarize.app.live_identity_album import ALBUM_BIRTH_MIN_SECONDS  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
)

DEFAULT_PASSES = REPO / "evidence/live-convergence-0824/M2-e2-exit/passes"
SAMPLE_RATE = 16000
ARMS = ("file", "live")


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
    """DER decomposed, the speaker axis, and what the arm published, from results.json."""

    scores = arm.get("scores") or {}
    diarization = scores.get("diarization") or {}
    speaker = scores.get("speaker") or {}
    meta = arm.get("meta") or {}
    der = diarization.get("der")
    miss = diarization.get("miss")
    false_alarm = diarization.get("false_alarm")
    confusion = diarization.get("speaker_confusion")
    node = {
        "der": der,
        "miss": miss,
        "false_alarm": false_alarm,
        "speaker_confusion": confusion,
        "speaker_accuracy": speaker.get("speaker_accuracy"),
        "reference_coverage": speaker.get("reference_coverage"),
        "wer": (scores.get("tbsa") or {}).get("wer"),
        "reference_speaker_count": speaker.get("reference_speaker_count"),
        "hypothesis_speaker_count": speaker.get("hypothesis_speaker_count"),
        "speaker_correctness": speaker.get("speaker_correctness"),
        "published_speakers": meta.get("speakers") or meta.get("hyp_speakers"),
        "segments": meta.get("segments"),
    }
    if der is not None and miss is not None and false_alarm is not None:
        # What a speaker-authority change can and cannot reach. Confusion is a label the
        # album could have got right; miss is speech nobody published, which no embedding
        # recovers.
        node["der_confusion_free_floor"] = round(miss + false_alarm, 6)
        node["confusion_share_of_der"] = round(confusion / der, 6) if der else 0.0
    return node


def unattributed(hypothesis: list[V2Segment]) -> dict:
    """Seconds and segments the surface refused to name, and what it published in total."""

    published = sum(seg.end - seg.start for seg in hypothesis)
    unnamed = [seg for seg in hypothesis if seg.speaker == UNATTRIBUTED_SPEAKER]
    seconds = sum(seg.end - seg.start for seg in unnamed)
    return {
        "label": UNATTRIBUTED_SPEAKER,
        "seconds": round(seconds, 6),
        "segments": len(unnamed),
        "published_seconds": round(published, 6),
        "fraction_of_published": round(seconds / published, 6) if published else 0.0,
        "intervals": [[round(seg.start, 3), round(seg.end, 3)] for seg in unnamed],
    }


def mixed_window_collapse(
    reference: list[V2Segment],
    hypothesis: list[V2Segment],
    duration_sec: float,
    window_sec: float,
    hop_sec: float,
    floor_sec: float,
) -> dict:
    """Plan §11.2's collapse gate.

    A window is *mixed* when at least two reference speakers each hold `floor_sec` of it --
    the production birth floor, i.e. the least evidence that could name a second voice. It
    *collapses* when the surface publishes inside that window but names fewer distinct
    speakers than the reference carries there.

    `hop_sec` is why this is measured twice. At the deployed hop (the witness stride) the
    answer is about the windows this deployment really decodes -- and a reference turn that
    falls on a window boundary produces *no* mixed window at all, which is a fact about the
    alignment, not evidence of health. At the base-span hop the grid slides past every turn,
    so the screen sees mixed content wherever the audio has any.
    """

    def overlap(seg: V2Segment, start: float, end: float) -> float:
        return max(0.0, min(seg.end, end) - max(seg.start, start))

    collapsed: list[dict] = []
    mixed = 0
    start = 0.0
    while start < duration_sec - 1e-9:
        end = min(start + window_sec, duration_sec)
        ref_seconds: dict[str, float] = {}
        for seg in reference:
            got = overlap(seg, start, end)
            if got > 0:
                ref_seconds[seg.speaker] = ref_seconds.get(seg.speaker, 0.0) + got
        voices = sorted(name for name, secs in ref_seconds.items() if secs >= floor_sec)
        if len(voices) >= 2:
            mixed += 1
            names = {
                seg.speaker
                for seg in hypothesis
                if overlap(seg, start, end) > 0 and seg.speaker != UNATTRIBUTED_SPEAKER
            }
            published = any(overlap(seg, start, end) > 0 for seg in hypothesis)
            if published and len(names) < len(voices):
                collapsed.append(
                    {
                        "window": [round(start, 3), round(end, 3)],
                        "reference_voices": voices,
                        "published_speakers": sorted(names),
                    }
                )
        start += hop_sec
    return {
        "window_seconds": window_sec,
        "hop_seconds": hop_sec,
        "floor_seconds": floor_sec,
        "mixed_windows": mixed,
        "collapsed_windows": len(collapsed),
        "collapsed_detail": collapsed,
    }


def base_span_seconds(manifest: Path) -> float:
    """The deployed base-span cadence, read from the pass's own manifest.

    No fallback: a missing hard cap means the hop would silently become the stride and the
    sliding screen would quietly become the deployed one.
    """

    if not manifest.exists():
        raise SystemExit(f"no replay manifest beside the pass: {manifest}")
    bounds = (json.loads(manifest.read_text()).get("descriptor") or {}).get("bounds") or {}
    cap = bounds.get("hard_cap_samples")
    if not cap:
        raise SystemExit(f"manifest states no hard_cap_samples: {manifest}")
    return float(cap) / SAMPLE_RATE


# ------------------------------------------------------------------ the table


def measure(passes_root: Path) -> dict:
    contract = corpus_contract()
    geometry_window = DEFAULT_ROLLING_GEOMETRY.window_samples / SAMPLE_RATE
    geometry_stride = DEFAULT_ROLLING_GEOMETRY.stride_samples / SAMPLE_RATE
    report: dict = {
        "passes_root": str(passes_root),
        "unattributed_label": UNATTRIBUTED_SPEAKER,
        "collapse_floor_seconds": ALBUM_BIRTH_MIN_SECONDS,
        "collapse_window_seconds": geometry_window,
        "collapse_hop_seconds_deployed": geometry_stride,
        "cases": {},
    }
    for case in list(TRIO_CASES) + [FIVE_MINUTE_CASE]:
        duration = CASE_DURATION_SEC.get(case, 60.0)
        reference = [
            V2Segment(**row) for row in load_reference_rows(REPO / contract[case]["reference"])
        ]
        audio = REPO / contract[case]["audio"]
        regions = speech_regions_from_wav(audio) if audio.exists() else None
        node: dict = {
            "duration_sec": duration,
            "reference_speakers": sorted({seg.speaker for seg in reference}),
            "runs": {},
        }
        for run in RUNS:
            paths = case_paths(passes_root, case, run)
            arms = arm_scores(paths["results"], case)
            run_node: dict = {}
            for arm in ARMS:
                if arm not in arms:
                    continue
                run_node[arm] = deployed_axes(arms[arm])
            live_hypothesis_path = paths["live_hypothesis"]
            if live_hypothesis_path.exists():
                hypothesis = [
                    V2Segment(**row) for row in load_reference_rows(live_hypothesis_path)
                ]
                scored = score_v2(
                    reference,
                    hypothesis,
                    speech_regions=regions,
                    speech_regions_source=(
                        "webrtcvad_mode1_10ms" if regions else "reference_intervals"
                    ),
                )
                live = run_node.setdefault("live", {})
                live["matched_word_speaker_accuracy"] = scored["matched_word_speaker"][
                    "matched_word_speaker_accuracy"
                ]
                live["v2_der_reference_speech"] = scored["der_reference_speech"]["der"]
                live["unattributed"] = unattributed(hypothesis)
                hop = base_span_seconds(paths["trace"].parent.parent / "replay-manifest.json")
                live["collapse_deployed"] = mixed_window_collapse(
                    reference,
                    hypothesis,
                    duration,
                    geometry_window,
                    geometry_stride,
                    ALBUM_BIRTH_MIN_SECONDS,
                )
                live["collapse_sliding"] = mixed_window_collapse(
                    reference,
                    hypothesis,
                    duration,
                    geometry_window,
                    hop,
                    ALBUM_BIRTH_MIN_SECONDS,
                )
            if "live" in run_node and "file" in run_node:
                live = run_node["live"]
                file_der = run_node["file"].get("der")
                if live.get("der") is not None and file_der is not None:
                    live["der_gap_to_file"] = round(live["der"] - file_der, 6)
            node["runs"][run] = run_node
        node["runs_agree"] = _runs_agree(node["runs"])
        report["cases"][case] = node
    report["summary"] = summarize(report)
    return report


def _runs_agree(runs: dict) -> bool:
    """Did the two passes of this case produce the same speaker surface, to 6 dp?"""

    seen = [
        json.dumps(_comparable(node), sort_keys=True)
        for node in runs.values()
        if node
    ]
    return len(set(seen)) <= 1 and bool(seen)


def _comparable(run_node: dict) -> dict:
    live = run_node.get("live") or {}
    return {
        key: live.get(key)
        for key in (
            "der",
            "miss",
            "speaker_confusion",
            "speaker_accuracy",
            "matched_word_speaker_accuracy",
        )
    } | {"unattributed_seconds": (live.get("unattributed") or {}).get("seconds")}


def _mean(values: list[float]) -> float | None:
    usable = [value for value in values if value is not None]
    return round(sum(usable) / len(usable), 6) if usable else None


def summarize(report: dict) -> dict:
    """Trio means and the five-minute case, on the live arm, plus E3's reachable headroom."""

    def live_of(case: str, run: str) -> dict:
        return (report["cases"][case]["runs"].get(run) or {}).get("live") or {}

    def axis(case: str, key: str) -> float | None:
        return _mean([live_of(case, run).get(key) for run in RUNS])

    per_case = {
        case: {
            "der": axis(case, "der"),
            "miss": axis(case, "miss"),
            "speaker_confusion": axis(case, "speaker_confusion"),
            "der_confusion_free_floor": axis(case, "der_confusion_free_floor"),
            "confusion_share_of_der": axis(case, "confusion_share_of_der"),
            "speaker_accuracy": axis(case, "speaker_accuracy"),
            "matched_word_speaker_accuracy": axis(case, "matched_word_speaker_accuracy"),
            "der_gap_to_file": axis(case, "der_gap_to_file"),
            "unattributed_seconds": _mean(
                [(live_of(case, run).get("unattributed") or {}).get("seconds") for run in RUNS]
            ),
            "collapsed_windows_deployed": _mean(
                [
                    (live_of(case, run).get("collapse_deployed") or {}).get("collapsed_windows")
                    for run in RUNS
                ]
            ),
            "mixed_windows_deployed": _mean(
                [
                    (live_of(case, run).get("collapse_deployed") or {}).get("mixed_windows")
                    for run in RUNS
                ]
            ),
            "collapsed_windows_sliding": _mean(
                [
                    (live_of(case, run).get("collapse_sliding") or {}).get("collapsed_windows")
                    for run in RUNS
                ]
            ),
            "mixed_windows_sliding": _mean(
                [
                    (live_of(case, run).get("collapse_sliding") or {}).get("mixed_windows")
                    for run in RUNS
                ]
            ),
        }
        for case in list(TRIO_CASES) + [FIVE_MINUTE_CASE]
    }
    trio = {
        key: _mean([per_case[case][key] for case in TRIO_CASES])
        for key in (
            "der",
            "der_confusion_free_floor",
            "speaker_accuracy",
            "matched_word_speaker_accuracy",
        )
    }
    trio["max_reachable_der_gain"] = (
        round(trio["der"] - trio["der_confusion_free_floor"], 6)
        if trio["der"] is not None and trio["der_confusion_free_floor"] is not None
        else None
    )
    five = per_case[FIVE_MINUTE_CASE]
    five_gain = (
        round(five["der"] - five["der_confusion_free_floor"], 6)
        if five["der"] is not None and five["der_confusion_free_floor"] is not None
        else None
    )
    return {
        "per_case": per_case,
        "trio_live": trio,
        "five_minute_max_reachable_der_gain": five_gain,
        "unattributed_seconds_total": _mean(
            [
                sum(
                    (per_case[case]["unattributed_seconds"] or 0.0)
                    for case in list(TRIO_CASES) + [FIVE_MINUTE_CASE]
                )
            ]
        ),
        "collapsed_windows_total_deployed": sum(
            int(per_case[case]["collapsed_windows_deployed"] or 0)
            for case in list(TRIO_CASES) + [FIVE_MINUTE_CASE]
        ),
        "collapsed_windows_total_sliding": sum(
            int(per_case[case]["collapsed_windows_sliding"] or 0)
            for case in list(TRIO_CASES) + [FIVE_MINUTE_CASE]
        ),
    }


def render(report: dict) -> str:
    lines: list[str] = []
    summary = report["summary"]
    lines.append(f"passes root : {report['passes_root']}")
    lines.append(
        f"collapse    : {report['collapse_window_seconds']:.1f} s windows "
        f"(hop {report['collapse_hop_seconds_deployed']:.1f} s deployed / base-span sliding), "
        f"{report['collapse_floor_seconds']:.1f} s voice floor, "
        f"unattributed label {report['unattributed_label']}"
    )
    lines.append("")
    header = (
        f"{'case':<18}{'arm':<6}{'DER':>9}{'miss':>9}{'conf':>9}{'floor':>9}"
        f"{'spk_acc':>9}{'v2_spk':>9}{'S00_s':>8}{'clps/dep':>10}{'clps/slide':>12}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for case, node in report["cases"].items():
        run = node["runs"].get("A") or {}
        for arm in ARMS:
            data = run.get(arm) or {}
            if not data:
                continue
            unattr = data.get("unattributed") or {}
            lines.append(
                f"{case:<18}{arm:<6}"
                f"{_fmt(data.get('der')):>9}{_fmt(data.get('miss')):>9}"
                f"{_fmt(data.get('speaker_confusion')):>9}"
                f"{_fmt(data.get('der_confusion_free_floor')):>9}"
                f"{_fmt(data.get('speaker_accuracy')):>9}"
                f"{_fmt(data.get('matched_word_speaker_accuracy')):>9}"
                f"{_fmt(unattr.get('seconds'), 2):>8}"
                f"{_collapse_cell(data.get('collapse_deployed')):>10}"
                f"{_collapse_cell(data.get('collapse_sliding')):>12}"
            )
        lines.append(f"{'':<18}{'':<6}runs agree: {node['runs_agree']}")
    lines.append("")
    trio = summary["trio_live"]
    lines.append(
        f"TRIO live   DER {trio['der']:.6f}  confusion-free floor {trio['der_confusion_free_floor']:.6f}"
        f"  -> most any speaker-authority arm can win: {trio['max_reachable_der_gain']:.6f}"
    )
    lines.append(
        f"TRIO live   speaker_accuracy {trio['speaker_accuracy']:.6f}"
        f"  matched-word {trio['matched_word_speaker_accuracy']:.6f}"
    )
    five = summary["per_case"]["keyu-5m"]
    lines.append(
        f"5-MIN live  DER {five['der']:.6f}  floor {five['der_confusion_free_floor']:.6f}"
        f"  -> reachable {summary['five_minute_max_reachable_der_gain']:.6f}"
    )
    lines.append(
        "collapsed two-speaker windows across all four cases: "
        f"{summary['collapsed_windows_total_deployed']} at the deployed hop, "
        f"{summary['collapsed_windows_total_sliding']} on the sliding screen"
    )
    return "\n".join(lines)


def _collapse_cell(collapse: dict | None) -> str:
    if not collapse:
        return ""
    return f"{collapse['collapsed_windows']}/{collapse['mixed_windows']}"


def _fmt(value: float | None, places: int = 6) -> str:
    return "-" if value is None else f"{value:.{places}f}"


# ------------------------------------------------------------------ self-test

def _seg(start: float, end: float, speaker: str, text: str = "w") -> V2Segment:
    return V2Segment(start=start, end=end, speaker=speaker, text=text)


def selftest() -> int:
    """Prove the two derived quantities react, before any arm is measured against them.

    Iterations 11-18 kept finding the same failure mode: a probe that reported nothing
    because it was broken, not because the thing it watched was healthy.
    """

    failures: list[str] = []

    def check(name: str, got, want) -> None:
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    floor = ALBUM_BIRTH_MIN_SECONDS
    reference = [_seg(0.0, 5.0, "A"), _seg(5.0, 10.0, "B")]

    both = mixed_window_collapse(
        reference, [_seg(0.0, 5.0, "S01"), _seg(5.0, 10.0, "S02")], 10.0, 10.0, 10.0, floor
    )
    check("two voices named -> not collapsed", (both["mixed_windows"], both["collapsed_windows"]), (1, 0))

    one = mixed_window_collapse(reference, [_seg(0.0, 10.0, "S01")], 10.0, 10.0, 10.0, floor)
    check("one name over two voices -> collapsed", (one["mixed_windows"], one["collapsed_windows"]), (1, 1))

    unnamed = mixed_window_collapse(
        reference,
        [_seg(0.0, 5.0, "S01"), _seg(5.0, 10.0, UNATTRIBUTED_SPEAKER)],
        10.0,
        10.0,
        10.0,
        floor,
    )
    check(
        "unattributed is not a name",
        (unnamed["mixed_windows"], unnamed["collapsed_windows"]),
        (1, 1),
    )

    silent = mixed_window_collapse(reference, [], 10.0, 10.0, 10.0, floor)
    check(
        "nothing published -> mixed but not collapsed",
        (silent["mixed_windows"], silent["collapsed_windows"]),
        (1, 0),
    )

    short = mixed_window_collapse(
        [_seg(0.0, 9.5, "A"), _seg(9.5, 10.0, "B")],
        [_seg(0.0, 10.0, "S01")],
        10.0,
        10.0,
        10.0,
        floor,
    )
    check("a voice below the birth floor is not a second voice", short["mixed_windows"], 0)

    hop = mixed_window_collapse(
        [_seg(0.0, 10.0, "A"), _seg(10.0, 20.0, "B")],
        [_seg(0.0, 20.0, "S01")],
        20.0,
        10.0,
        10.0,
        floor,
    )
    check("a turn on the window boundary hides from the deployed grid", hop["mixed_windows"], 0)
    slid = mixed_window_collapse(
        [_seg(0.0, 10.0, "A"), _seg(10.0, 20.0, "B")],
        [_seg(0.0, 20.0, "S01")],
        20.0,
        10.0,
        2.5,
        floor,
    )
    check("the sliding screen sees it", (slid["mixed_windows"] > 0, slid["collapsed_windows"] > 0), (True, True))

    unattr = unattributed([_seg(0.0, 3.0, "S01"), _seg(3.0, 4.0, UNATTRIBUTED_SPEAKER)])
    check("S00 seconds", unattr["seconds"], 1.0)
    check("S00 fraction", unattr["fraction_of_published"], 0.25)

    axes = deployed_axes(
        {
            "scores": {
                "diarization": {"der": 0.1, "miss": 0.06, "false_alarm": 0.01, "speaker_confusion": 0.03},
                "speaker": {"speaker_accuracy": 0.9},
                "tbsa": {"wer": 0.2},
            },
            "meta": {"segments": 3, "speakers": ["S01"]},
        }
    )
    check("confusion-free floor", axes["der_confusion_free_floor"], 0.07)
    check("confusion share", axes["confusion_share_of_der"], 0.3)

    for line in failures:
        print(f"FAIL {line}")
    print(f"selftest: {'PASS' if not failures else 'FAIL'} ({len(failures)} failures)")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes-root", type=Path, default=DEFAULT_PASSES)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="prove the derived quantities react, then exit",
    )
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    report = measure(args.passes_root.resolve())
    print(render(report))
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
