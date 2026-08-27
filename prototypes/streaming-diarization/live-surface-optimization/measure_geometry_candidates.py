"""PROTOTYPE: fresh five-case rolling geometry/context sweep; never production authority."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
CONVERGENCE = HERE.parent / "live-convergence"
CONTEXT = REPO / "prototypes/live-file-gap-context"
EVIDENCE = REPO / "evidence/live-surface-optimization-20260825"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(CONVERGENCE))
sys.path.insert(0, str(CONTEXT))

import compare_rolling_grid as grid  # noqa: E402
import proto_context_arms as bench  # noqa: E402
from evaluator_v2 import Segment as V2Segment  # noqa: E402
from evaluator_v2 import score_v2, speech_regions_from_wav  # noqa: E402
from moss_transcribe_diarize import live_speaker_accuracy as lsa  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment, calculate_diarization, calculate_tbsa  # noqa: E402

SAMPLE_RATE = 16_000
MATERIAL_WER_GAIN = 0.010
MAX_CASE_REGRESSION = 0.020
GEOMETRIES = ((10.0, 10.0), (15.0, 10.0), (10.0, 5.0), (8.0, 4.0), (6.0, 6.0))


class Case:
    def __init__(self, case_id: str, directory: Path, run_directory: str):
        self.case_id = case_id
        self.directory = directory
        self.run_directory = EVIDENCE / run_directory

    @property
    def audio(self) -> Path:
        return self.directory / "audio.wav"

    @property
    def reference(self) -> Path:
        return self.directory / "reference.jsonl"


DATA = REPO / "prototypes/streaming-diarization/data/real"
CASES = (
    Case("lex_bill_ackman", DATA / "benchmark_diarization_1min/samples/lex_bill_ackman", "pass-A-lex_bill_ackman"),
    Case("lex_javier_milei", DATA / "benchmark_diarization_1min/samples/lex_javier_milei", "pass-A-lex_javier_milei"),
    Case("lex_keyu_jin_1m", DATA / "benchmark_diarization_1min/samples/lex_keyu_jin", "pass-A-lex_keyu_jin_1m"),
    Case("lex_adam_frank_3m", DATA / "calibration_diarization_3min/samples/lex_adam_frank", "pass-A-lex_adam_frank_3m"),
    Case("lex_keyu_jin_5m", DATA / "benchmark_5m/lex_keyu_jin", "pass-A-lex_keyu_jin_5m"),
)
TRIO = frozenset(case.case_id for case in CASES[:3])


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def reference(case: Case) -> list[Segment]:
    return [
        Segment(float(row["start"]), float(row["end"]), str(row["speaker"]), str(row.get("text") or ""))
        for row in load_jsonl(case.reference)
    ]


def committed_spans(case: Case) -> list[dict[str, Any]]:
    capture = next(
        row for row in load_jsonl(case.run_directory / "snapshots.jsonl")
        if row["surface"] == "post_stop_final"
    )
    return [
        {
            "span_id": int(row["span_id"]),
            "start_sample": int(row["start_sample"]),
            "end_sample": int(row["end_sample"]),
            "transcript": row.get("revised_transcript") or row.get("transcript") or "",
        }
        for row in capture["snapshot"]["session"]["committed"]
    ]


def score(case: Case, ref: list[Segment], segments: list[Segment]) -> dict[str, Any]:
    tbsa = calculate_tbsa(ref, segments)
    diarization = calculate_diarization(ref, segments)
    ref_activity = lsa.load_reference_speaker_activity_jsonl(case.reference)
    speaker = lsa.score_live_speaker_accuracy(
        list(ref_activity),
        [lsa.SpeakerActivityInterval(row.start, row.end, row.speaker) for row in segments],
    )
    v2 = score_v2(
        [V2Segment(row.start, row.end, row.speaker, row.text) for row in ref],
        [V2Segment(row.start, row.end, row.speaker, row.text) for row in segments],
        speech_regions=speech_regions_from_wav(case.audio),
        speech_regions_source="webrtcvad_mode1_10ms",
    )
    return {
        "wer": tbsa["wer"],
        "tbsa": tbsa["composite"],
        "der": diarization["der"],
        "text_coverage": tbsa["text_coverage"],
        "content_recall": v2["content_recall"],
        "speaker_accuracy": speaker["speaker_accuracy"],
        "matched_word_speaker_accuracy": v2["matched_word_speaker"]["matched_word_speaker_accuracy"],
        "reference_speech_der": v2["der_reference_speech"]["der"],
        "segments": len(segments),
    }


def write_hypothesis(path: Path, segments: list[Segment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(
                {"start": row.start, "end": row.end, "speaker": row.speaker, "text": row.text},
                ensure_ascii=False,
            ) + "\n"
            for row in segments
        ),
        encoding="utf-8",
    )


def macro(cases: dict[str, Any], geometry: str, field: str, selected: set[str]) -> float:
    values = [cases[case]["arms"][geometry]["scores"][field] for case in selected]
    return round(sum(values) / len(values), 6)


def summarize(document: dict[str, Any]) -> dict[str, Any]:
    cases = document["cases"]
    all_ids = {case.case_id for case in CASES}
    arms = {}
    for window, stride in GEOMETRIES:
        name = f"{window:g}/{stride:g}:lexical"
        five_wer = macro(cases, name, "wer", all_ids)
        trio_wer = macro(cases, name, "wer", set(TRIO))
        comparator_five = round(sum(cases[c]["comparator"]["wer"] for c in all_ids) / len(all_ids), 6)
        comparator_trio = round(sum(cases[c]["comparator"]["wer"] for c in TRIO) / len(TRIO), 6)
        per_case = {}
        for case in CASES:
            scored = cases[case.case_id]["arms"][name]["scores"]
            baseline = cases[case.case_id]["comparator"]
            per_case[case.case_id] = {
                "wer": scored["wer"],
                "der": scored["der"],
                "matched_word_speaker_accuracy": scored["matched_word_speaker_accuracy"],
                "wer_delta": round(scored["wer"] - baseline["wer"], 6),
                "der_delta": round(scored["der"] - baseline["der"], 6),
            }
        no_harm = all(
            row["wer_delta"] <= MAX_CASE_REGRESSION and row["der_delta"] <= MAX_CASE_REGRESSION
            for row in per_case.values()
        )
        costs = [cases[c]["arms"][name]["cost"] for c in all_ids]
        projected_rtf = max(row["projected_base_plus_witness_rtf"] for row in costs)
        material = (
            comparator_five - five_wer >= MATERIAL_WER_GAIN
            and comparator_trio - trio_wer >= MATERIAL_WER_GAIN
        )
        arms[name] = {
            "five_case": {
                "wer": five_wer,
                "comparator_wer": comparator_five,
                "wer_gain": round(comparator_five - five_wer, 6),
                "der": macro(cases, name, "der", all_ids),
                "matched_word_speaker_accuracy": macro(cases, name, "matched_word_speaker_accuracy", all_ids),
                "content_recall": macro(cases, name, "content_recall", all_ids),
            },
            "trio": {
                "wer": trio_wer,
                "comparator_wer": comparator_trio,
                "wer_gain": round(comparator_trio - trio_wer, 6),
                "der": macro(cases, name, "der", set(TRIO)),
                "matched_word_speaker_accuracy": macro(cases, name, "matched_word_speaker_accuracy", set(TRIO)),
            },
            "per_case": per_case,
            "decoded_audio_work_ratio_mean": round(
                sum(row["decoded_audio_work_ratio"] for row in costs) / len(costs), 6
            ),
            "request_count": sum(row["requests"] for row in costs),
            "fresh_request_count": sum(row["fresh_requests"] for row in costs),
            "projected_combined_rtf_max": projected_rtf,
            "correction_age_floor_p95_max": max(
                cases[c]["arms"][name]["correction_age_floor"]["p95_seconds"] or 0.0
                for c in all_ids
            ),
            "material_wer_gain": material,
            "no_case_regression_over_0_02": no_harm,
            "eligible_for_deployed_shadow": material and no_harm and projected_rtf < 1.0,
            "eligible_for_production": False,
            "production_blockers": [
                "alternate-geometry correction p50/p95 on production event clocks unmeasured",
                "alternate-geometry live queue/refusal/stale-window behavior unmeasured",
                "offline full-WAV plan does not reproduce the current pre-Stop final-tail schedule",
            ],
        }
    eligible = [name for name, row in arms.items() if row["eligible_for_deployed_shadow"]]
    shadow = None
    if eligible:
        shadow = sorted(
            eligible,
            key=lambda name: (
                -arms[name]["five_case"]["wer_gain"],
                arms[name]["decoded_audio_work_ratio_mean"],
                name,
            ),
        )[0]
    return {
        "comparators": {
            "five_case_pre_stop_settled_wer": next(iter(arms.values()))["five_case"]["comparator_wer"],
            "trio_pre_stop_settled_wer": next(iter(arms.values()))["trio"]["comparator_wer"],
        },
        "arms": arms,
        "recommended_deployed_shadow": shadow,
        "recommended_production_change": None,
        "unmeasured": [
            "alternate-geometry event-clock correction latency",
            "alternate-geometry live queue and failure behavior",
            "actual peer live surfaces",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cache_dir.exists():
        raise SystemExit(f"REFUSED: fresh cache directory already exists: {args.cache_dir}")
    for case in CASES:
        for path in (case.audio, case.reference, case.run_directory / "run-result.json"):
            if not path.is_file():
                raise SystemExit(f"missing input: {path}")
    args.cache_dir.mkdir(parents=True)
    model = bench.discover_model(args.base_url, args.timeout_seconds)
    runner = bench.VllmRunner(
        base_url=args.base_url, model=model, api_key=None, timeout=args.timeout_seconds
    )
    decoder = bench.Decoder(runner=runner, model=model, cache_path=args.cache_dir / "decode-cache.json")
    document: dict[str, Any] = {
        "schema": "moss-live-surface-geometry.v1",
        "preregistration": str(HERE / "PREREGISTRATION-GEOMETRY.md"),
        "model": model,
        "base_url": args.base_url,
        "request_concurrency": 1,
        "cache_started_empty": True,
        "cases": {},
    }
    started = time.monotonic()
    for case in CASES:
        pcm = bench.read_pcm(case.audio)
        duration = len(pcm) / 2 / SAMPLE_RATE
        audio_sha = hashlib.sha256(case.audio.read_bytes()).hexdigest()
        ref = reference(case)
        timeline = bench.SpeakerTimeline(bench.load_jsonl_segments(case.run_directory / "pre_stop_settled.jsonl"))
        run_result = json.loads((case.run_directory / "run-result.json").read_text(encoding="utf-8"))
        comparator = run_result["surface_scores"]["pre_stop_settled"]
        base_decode_seconds = float(run_result["events"]["decode_seconds"]["base"])
        entry: dict[str, Any] = {"duration_seconds": duration, "comparator": comparator, "arms": {}}
        with tempfile.TemporaryDirectory(prefix="moss-surface-geometry-") as scratch_name:
            scratch = Path(scratch_name)
            decoder.take_accounting()
            with grid._TruthBlind():
                base_rows, base_report = grid.decode_base(
                    pcm=pcm,
                    audio_sha=audio_sha,
                    spans=committed_spans(case),
                    decoder=decoder,
                    scratch=scratch,
                )
            base_cost = decoder.take_accounting()
            base_segments = timeline.relabel(bench.rows_to_segments(base_rows, duration))
            entry["base_control"] = {
                "scores": score(case, ref, base_segments),
                "cost": base_cost,
            }
            log(
                f"case={case.case_id} base WER={entry['base_control']['scores']['wer']:.6f} "
                f"fresh={base_cost['fresh_requests']}/{base_cost['requests']}"
            )
            for window, stride in GEOMETRIES:
                name = f"{window:g}/{stride:g}:lexical"
                windows = grid.plan_windows(duration, window, stride)
                decoder.take_accounting()
                with grid._TruthBlind():
                    decoded = grid.decode_windows(
                        pcm=pcm,
                        audio_sha=audio_sha,
                        windows=windows,
                        decoder=decoder,
                        scratch=scratch,
                    )
                cost = decoder.take_accounting()
                with grid._TruthBlind():
                    word_windows = [
                        grid.word_rows_weighted(row["segments"], f"w{row['index']}", grid.WEIGHTS["lexical"])
                        for row in decoded
                    ]
                    merged, stitch_report, contributed = grid.stitch(
                        "lexical", decoded, word_windows, base_rows
                    )
                    segments = timeline.relabel(bench.rows_to_segments(merged, duration))
                scores = score(case, ref, segments)
                latency = grid.correction_age_floor(
                    base_spans=base_report,
                    windows=decoded,
                    base_rows=base_rows,
                    contributed=contributed,
                    stitch_report=stitch_report,
                )
                entry["arms"][name] = {
                    "scores": scores,
                    "cost": {
                        **cost,
                        "decoded_audio_work_ratio": round(cost["decode_audio_seconds"] / duration, 6),
                        "projected_base_plus_witness_rtf": round(
                            (base_decode_seconds + cost["wall_seconds_contended"]) / duration, 6
                        ),
                    },
                    "correction_age_floor": latency,
                    "decode_health": bench.decode_health(
                        [
                            {"health": row["decoded"]["health"], "classification": row["decoded"]["classification"]}
                            for row in decoded
                        ]
                    ),
                    "join_duplicates": sum(row["join_duplicate_run"] > 0 for row in stitch_report[1:]),
                }
                write_hypothesis(
                    args.output.parent / "geometry-hypotheses" / case.case_id / f"{name.replace('/', '_').replace(':', '-')}.jsonl",
                    segments,
                )
                log(
                    f"case={case.case_id} arm={name} WER={scores['wer']:.6f} DER={scores['der']:.6f} "
                    f"mws={scores['matched_word_speaker_accuracy']:.6f} work={cost['decode_audio_seconds']/duration:.3f}x "
                    f"fresh={cost['fresh_requests']}/{cost['requests']} floor_p95={latency['p95_seconds']}"
                )
        document["cases"][case.case_id] = entry
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    document["elapsed_seconds"] = round(time.monotonic() - started, 6)
    document["summary"] = summarize(document)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
