#!/usr/bin/env python3
"""A0.3: does evaluator v2 measure words instead of timestamps?

One command:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/compare_evaluators.py \
      --manifest prototypes/streaming-diarization/data/real/benchmark_diarization_1min/manifest.json \
      --output /tmp/moss-live-evaluator-v2.json

With no `--manifest` every case in `cases.json` is scored, including the 5-minute case (its
corpus has no manifest file).  Exit 0 iff every prototype gate passes.

Gates (plan A0.3), each checked on every case in the corpus contract:

  Q1  self-score exactly 1.0 on every axis        reference scored against itself
  Q2  degenerate control earns nothing            one 60 s segment whose only word is "xx"
  Q3  invariance to same-speaker segment splits   every span cut in two, adjacent, same label
  Q4  live/file conclusions reproducible          saved hypotheses reproduce the checked-in
                                                  baseline exactly under the deployed scorer,
                                                  and v2 keeps file ahead of live

Q2 is the artifact test: the deployed scorer's text coverage and TBSA are reported beside the
v2 axes for the same degenerate hypothesis, so the gap between "credits timestamps" and
"credits words" is a number in the output, not a claim in a document.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.evaluation import Segment, _segment_order, _tokenize  # noqa: E402

from evaluator_v2 import (  # noqa: E402
    DEFAULT_SEAM_BAND_SEC,
    score_v2,
    speech_regions_from_wav,
)

HERE = Path(__file__).resolve().parent
DEGENERATE_WORD = "xx"
TOLERANCE = 1e-6


# ----------------------------------------------------------------- loading


def load_segments(path: Path) -> list[Segment]:
    segments: list[Segment] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        start, end = float(record["start"]), float(record["end"])
        if end <= start:
            raise ValueError(f"{path}:{line_number} has end <= start")
        segments.append(
            Segment(start=start, end=end, speaker=str(record["speaker"]), text=str(record["text"]))
        )
    if not segments:
        raise ValueError(f"{path} contains no segments")
    return segments


def load_baseline_scores(path: Path, case_id: str, arm: str) -> dict[str, Any] | None:
    """Read the checked-in deployed-scorer numbers for one case/arm.

    The baseline stores a multi-case file (`cases[]` with `arms`) and a single-case file
    (`results` keyed by arm); both shapes are read here so the reproduction gate covers every
    saved hypothesis, not only the trio.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("cases"), list):
        for entry in payload["cases"]:
            if entry.get("case_id") == case_id:
                return entry.get("arms", {}).get(arm, {}).get("scores")
        return None
    if isinstance(payload.get("results"), dict):
        return payload["results"].get(arm, {}).get("scores")
    return None


def load_cases(
    path: Path, manifest_filter: Path | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for case in payload["cases"]:
        if manifest_filter is not None:
            manifest = case.get("manifest")
            if manifest is None or (REPO / manifest).resolve() != manifest_filter:
                continue
        cases.append(case)
    if not cases:
        raise ValueError("no cases selected")
    return cases, payload.get("published_group_means", {})


def group_means(rows: list[dict[str, Any]], group: str) -> dict[str, dict[str, float]]:
    members = [row for row in rows if row["group"] == group]
    if not members:
        return {}
    return {
        arm: {
            key: round(statistics.fmean(axes(row["arms"][arm]["v2"])[key] for row in members), 6)
            for key in AXIS_KEYS
        }
        for arm in ("file", "live")
    }


# ----------------------------------------------------------------- hypothesis transforms


def degenerate_hypothesis(reference: Sequence[Segment]) -> list[Segment]:
    """The plan §3.4 control: one segment spanning the clip whose only word is "xx"."""
    start = min(segment.start for segment in reference)
    end = max(segment.end for segment in reference)
    speaker = sorted({segment.speaker for segment in reference})[0]
    return [Segment(start=start, end=end, speaker=speaker, text=DEGENERATE_WORD)]


def split_same_speaker(hypothesis: Sequence[Segment]) -> list[Segment]:
    """Cut every multi-word span into two adjacent spans with the same speaker label.

    The cut is char-proportional, so the two halves carry the words they would have carried
    anyway and no time is created or destroyed.
    """
    out: list[Segment] = []
    for segment in sorted(hypothesis, key=_segment_order):
        tokens = _tokenize(segment.text)
        words = segment.text.split()
        if len(tokens) < 2 or len(words) < 2:
            out.append(segment)
            continue
        cut_word = len(words) // 2
        head_text = " ".join(words[:cut_word])
        tail_text = " ".join(words[cut_word:])
        chars = len(head_text) + len(tail_text)
        fraction = len(head_text) / chars if chars else 0.5
        cut_time = segment.start + (segment.end - segment.start) * fraction
        if not (segment.start < cut_time < segment.end):
            out.append(segment)
            continue
        out.append(Segment(segment.start, cut_time, segment.speaker, head_text))
        out.append(Segment(cut_time, segment.end, segment.speaker, tail_text))
    return out


# ----------------------------------------------------------------- gates


AXIS_KEYS = ("wer", "content_recall", "matched_word_speaker_accuracy", "der_reference_speech")


def axes(score: dict[str, Any]) -> dict[str, float]:
    """The quality axes a gate compares: quantities a hypothesis can move."""
    return {
        "wer": score["wer"]["wer"],
        "content_recall": score["content_recall"],
        "matched_word_speaker_accuracy": score["matched_word_speaker"][
            "matched_word_speaker_accuracy"
        ],
        "der_reference_speech": score["der_reference_speech"]["der"],
    }


def close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=TOLERANCE)


def run_gates(rows: list[dict[str, Any]], published: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []

    q1 = []
    for row in rows:
        self_axes = axes(row["self_score"])
        legacy = row["self_score"]["legacy"]
        ok = (
            close(self_axes["wer"], 0.0)
            and close(self_axes["content_recall"], 1.0)
            and close(self_axes["matched_word_speaker_accuracy"], 1.0)
            and close(self_axes["der_reference_speech"], 0.0)
            and close(legacy["tbsa"]["composite"], 1.0)
            and close(legacy["diarization"]["der"], 0.0)
        )
        if not ok:
            failures.append(f"Q1 {row['case_id']}: self-score not perfect {self_axes}")
        q1.append({"case_id": row["case_id"], "axes": self_axes, "pass": ok})

    q2 = []
    for row in rows:
        control = row["degenerate"]
        ok = (
            close(control["content_recall"], 0.0)
            and control["recovered_words"] == 0
            and close(control["matched_word_speaker"]["matched_word_speaker_accuracy"], 0.0)
            and control["matched_word_speaker"]["credited_words"] == 0
        )
        if not ok:
            failures.append(f"Q2 {row['case_id']}: degenerate control earned credit")
        q2.append(
            {
                "case_id": row["case_id"],
                "v2_content_recall": control["content_recall"],
                "v2_matched_word_speaker_accuracy": control["matched_word_speaker"][
                    "matched_word_speaker_accuracy"
                ],
                "v2_wer": control["wer"]["wer"],
                "legacy_text_coverage": control["legacy"]["tbsa"]["text_coverage"],
                "legacy_text_speaker_accuracy": control["legacy"]["tbsa"]["text_speaker_accuracy"],
                "legacy_tbsa": control["legacy"]["tbsa"]["composite"],
                "legacy_der": control["legacy"]["diarization"]["der"],
                "pass": ok,
            }
        )

    q3 = []
    for row in rows:
        for arm, arm_row in row["arms"].items():
            before, after = axes(arm_row["v2"]), axes(arm_row["v2_split"])
            ok = all(close(before[key], after[key]) for key in before)
            if not ok:
                failures.append(f"Q3 {row['case_id']}/{arm}: split moved the score {before} {after}")
            q3.append(
                {
                    "case_id": row["case_id"],
                    "arm": arm,
                    "segments": arm_row["v2"]["extent"]["hypothesis_segments"],
                    "split_segments": arm_row["v2_split"]["extent"]["hypothesis_segments"],
                    "axes_before": before,
                    "axes_after": after,
                    "pass": ok,
                }
            )

    q4_repro = []
    for row in rows:
        for arm, arm_row in row["arms"].items():
            baseline = arm_row.get("baseline_scores")
            if baseline is None:
                q4_repro.append({"case_id": row["case_id"], "arm": arm, "pass": None})
                continue
            legacy = arm_row["v2"]["legacy"]
            deltas = {
                "tbsa": legacy["tbsa"]["composite"] - baseline["tbsa"]["composite"],
                "wer": legacy["tbsa"]["wer"] - baseline["tbsa"]["wer"],
                "der": legacy["diarization"]["der"] - baseline["diarization"]["der"],
            }
            ok = all(close(value, 0.0) for value in deltas.values())
            if not ok:
                failures.append(f"Q4 {row['case_id']}/{arm}: legacy recomputation drifted {deltas}")
            q4_repro.append(
                {"case_id": row["case_id"], "arm": arm, "deltas": deltas, "pass": ok}
            )

    # The saved conclusion is "file mode beats live mode on every primary case".  Under v2
    # that means file is no worse on any axis and strictly better on at least one -- an
    # exact tie on an axis (Milei: both arms recover the same 115 of 125 reference words, and
    # live's extra errors are all insertions) is the same conclusion, not a reversed one.
    q4_conclusion = []
    for row in rows:
        if row["tier"] != "primary":
            continue
        file_axes, live_axes = axes(row["arms"]["file"]["v2"]), axes(row["arms"]["live"]["v2"])
        better = {
            "wer": live_axes["wer"] - file_axes["wer"],
            "content_recall": file_axes["content_recall"] - live_axes["content_recall"],
            "matched_word_speaker_accuracy": file_axes["matched_word_speaker_accuracy"]
            - live_axes["matched_word_speaker_accuracy"],
            "der_reference_speech": live_axes["der_reference_speech"]
            - file_axes["der_reference_speech"],
        }
        never_worse = all(value >= -TOLERANCE for value in better.values())
        strictly_better = any(value > TOLERANCE for value in better.values())
        ok = never_worse and strictly_better
        if not ok:
            failures.append(
                f"Q4 {row['case_id']}: v2 no longer reproduces the file-beats-live conclusion "
                f"{better}"
            )
        q4_conclusion.append(
            {
                "case_id": row["case_id"],
                "file": file_axes,
                "live": live_axes,
                "file_advantage": {key: round(value, 6) for key, value in better.items()},
                "tied_axes": [key for key, value in better.items() if close(value, 0.0)],
                "pass": ok,
            }
        )

    # The strongest reproduction check available offline: the campaign plan already published
    # means for these exact saved hypotheses.  Evaluator v2 computes WER and content recall by
    # a different route than the arm that produced them, so agreement to the published decimals
    # says the new lens sees the same corpus, not a different one.
    q4_published = []
    for group, expected in published.items():
        if not isinstance(expected, dict) or "decimals" not in expected:
            continue
        actual = group_means(rows, group)
        if not actual:
            continue
        decimals = int(expected["decimals"])
        for arm, arm_expected in expected.items():
            if arm not in actual:
                continue
            for key, value in arm_expected.items():
                observed = round(actual[arm][key], decimals)
                ok = close(observed, round(float(value), decimals))
                if not ok:
                    failures.append(
                        f"Q4 published {group}/{arm}/{key}: {observed} != {value} "
                        f"({expected.get('source', 'unsourced')})"
                    )
                q4_published.append(
                    {
                        "group": group,
                        "arm": arm,
                        "metric": key,
                        "published": float(value),
                        "observed": observed,
                        "pass": ok,
                    }
                )

    return {
        "Q1_self_score": q1,
        "Q2_degenerate_control": q2,
        "Q3_split_invariance": q3,
        "Q4_reproduction": {
            "legacy_recomputation": q4_repro,
            "v2_conclusion": q4_conclusion,
            "published_means": q4_published,
        },
        "failures": failures,
        "pass": not failures,
    }


# ----------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--manifest",
        default=None,
        help="restrict to cases drawn from this corpus manifest (default: every case)",
    )
    parser.add_argument("--cases", default=str(HERE / "cases.json"))
    parser.add_argument("--output", default=None)
    parser.add_argument("--seam-band", type=float, default=DEFAULT_SEAM_BAND_SEC)
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="score DER over reference intervals instead of VAD speech regions",
    )
    args = parser.parse_args(argv)

    manifest_filter = Path(args.manifest).resolve() if args.manifest else None
    cases, published = load_cases(Path(args.cases), manifest_filter)

    rows: list[dict[str, Any]] = []
    for case in cases:
        reference = load_segments(REPO / case["reference"])
        audio = REPO / case["audio"]
        if args.no_vad or not audio.exists():
            regions, source = None, "reference_intervals"
        else:
            regions, source = speech_regions_from_wav(audio), "webrtcvad_mode1_10ms"

        def score(hypothesis: Sequence[Segment]) -> dict[str, Any]:
            return score_v2(
                reference,
                hypothesis,
                speech_regions=regions,
                speech_regions_source=source,
                seam_band_sec=args.seam_band,
            )

        arms: dict[str, Any] = {}
        for arm, relative in case["hypotheses"].items():
            hypothesis = load_segments(REPO / relative)
            arms[arm] = {
                "hypothesis_path": relative,
                "v2": score(hypothesis),
                "v2_split": score(split_same_speaker(hypothesis)),
                "baseline_scores": load_baseline_scores(
                    REPO / case["baseline_scores"], case["case_id"], arm
                ),
            }
        rows.append(
            {
                "case_id": case["case_id"],
                "tier": case["tier"],
                "group": case["group"],
                "reference_segments": len(reference),
                "reference_seconds": round(
                    max(s.end for s in reference) - min(s.start for s in reference), 3
                ),
                "speech_regions_source": source,
                "self_score": score(reference),
                "degenerate": score(degenerate_hypothesis(reference)),
                "arms": arms,
            }
        )

    gates = run_gates(rows, published)
    means = {
        group: group_means(rows, group)
        for group in sorted({row["group"] for row in rows})
    }

    payload = {
        "prototype": "evaluator-v2 (plan A0.3)",
        "seam_band_seconds": args.seam_band,
        "speech_regions": "webrtcvad mode 1, 10 ms frames (deployed live VAD settings)",
        "group_means": means,
        "gates": gates,
        "cases": rows,
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(f"cases: {', '.join(row['case_id'] for row in rows)}")
    print("")
    header = f"{'case':<22}{'arm':<6}{'WER':>8}{'recall':>9}{'mwSPK':>8}{'DERspx':>8}{'seamWER':>9}{'intWER':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        for arm in ("file", "live"):
            score = row["arms"][arm]["v2"]
            seam = score["seam_profile"]
            print(
                f"{row['case_id']:<22}{arm:<6}"
                f"{score['wer']['wer']:>8.4f}{score['content_recall']:>9.4f}"
                f"{score['matched_word_speaker']['matched_word_speaker_accuracy']:>8.4f}"
                f"{score['der_reference_speech']['der']:>8.4f}"
                f"{seam['boundary']['wer']:>9.4f}{seam['interior']['wer']:>8.4f}"
            )
    print("")
    for group, arms in means.items():
        for arm in ("file", "live"):
            print(f"{group:>12} mean {arm:<5} {arms[arm]}")
    print("")
    for row in gates["Q2_degenerate_control"]:
        print(
            f"Q2 {row['case_id']:<22} v2 recall {row['v2_content_recall']:.4f} "
            f"v2 mwSPK {row['v2_matched_word_speaker_accuracy']:.4f} "
            f"| legacy coverage {row['legacy_text_coverage']:.4f} "
            f"legacy TBSA {row['legacy_tbsa']:.4f} legacy DER {row['legacy_der']:.4f}"
        )
    print("")
    for name in ("Q1_self_score", "Q3_split_invariance"):
        entries = gates[name]
        print(f"{name}: {sum(1 for e in entries if e['pass'])}/{len(entries)} pass")
    repro = gates["Q4_reproduction"]
    checked = [entry for entry in repro["legacy_recomputation"] if entry["pass"] is not None]
    print(
        f"Q4_reproduction: {sum(1 for e in checked if e['pass'])}/{len(checked)} legacy "
        f"recomputations exact; "
        f"{sum(1 for e in repro['v2_conclusion'] if e['pass'])}"
        f"/{len(repro['v2_conclusion'])} v2 conclusions hold; "
        f"{sum(1 for e in repro['published_means'] if e['pass'])}"
        f"/{len(repro['published_means'])} published means reproduced"
    )
    for entry in repro["v2_conclusion"]:
        if entry["tied_axes"]:
            print(f"  note {entry['case_id']}: tied axes {entry['tied_axes']}")
    print("")
    if gates["failures"]:
        for failure in gates["failures"]:
            print(f"FAIL {failure}")
        return 1
    print("ALL GATES PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
