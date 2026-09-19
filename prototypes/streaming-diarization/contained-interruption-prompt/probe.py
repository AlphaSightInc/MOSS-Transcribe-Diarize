"""THROWAWAY: paired prompt-only overlap probe; dry-run unless --execute is explicit."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT
from moss_transcribe_diarize.transcript_parser import parse_transcript


HERE = Path(__file__).resolve().parent
RETAINED = HERE.parent / "contained-interruption/source-backed"
RETAINED_RESULTS = RETAINED / "results.json"
OUTER_REFERENCE = (
    HERE.parents[2]
    / "evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/reference.jsonl"
)
REQUEST_LOG = Path("/Users/gao/Documents/Codex/2026-09-19/moss-round2/decoder-requests.jsonl")
APPENDIX = (
    "如果音频中有清晰可闻的短暂语音或多人同时说话，请转写每位说话人的可听内容；"
    "允许不同说话人的时间范围重叠。不要猜测或补充听不清的内容。"
)
VARIANT_PROMPT = f"{DEFAULT_PROMPT}\n{APPENDIX}"
TARGET_WORDS = ("how", "long", "do", "we", "think", "each", "one", "will", "take")
TARGET_START = 20.0
TARGET_END = 21.44


def sent_count() -> int:
    sent = 0
    for line in REQUEST_LOG.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") == "start":
            sent = max(sent, int(row["sent"]))
    return sent


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\w']+", text.casefold()))


def _edit_distance(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_word in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_word in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_word != right_word),
                )
            )
        previous = current
    return previous[-1]


def _wer(reference: str, hypothesis: str) -> float:
    reference_words = _tokens(reference)
    return _edit_distance(reference_words, _tokens(hypothesis)) / max(1, len(reference_words))


def _lcs_length(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    row = [0] * (len(right) + 1)
    for left_word in left:
        prior = 0
        for index, right_word in enumerate(right, start=1):
            saved = row[index]
            row[index] = prior + 1 if left_word == right_word else max(row[index], row[index - 1])
            prior = saved
    return row[-1]


def _segments(text: str) -> list[dict[str, object]]:
    return [
        {"start": item.start, "end": item.end, "speaker": item.speaker, "text": item.text}
        for item in parse_transcript(text)
    ]


def _case_state(row: dict[str, object]) -> dict[str, object]:
    segments = row.get("segments") or []
    speakers = sorted({str(item["speaker"]) for item in segments})
    durations: dict[str, float] = {}
    for item in segments:
        speaker = str(item["speaker"])
        durations[speaker] = durations.get(speaker, 0.0) + float(item["end"]) - float(item["start"])
    dominant = max(durations, key=durations.get) if durations else None
    target_rows = []
    for item in segments:
        if float(item["start"]) < TARGET_END and TARGET_START < float(item["end"]):
            target_rows.append(
                {
                    **item,
                    "target_lcs_words": _lcs_length(TARGET_WORDS, _tokens(str(item["text"]))),
                    "non_dominant": item["speaker"] != dominant,
                }
            )
    return {
        "speaker_count": len(speakers),
        "speakers": speakers,
        "dominant_speaker": dominant,
        "target_interval_segments": target_rows,
        "source_matching_non_dominant_turn": any(
            item["non_dominant"] and item["target_lcs_words"] >= 4 for item in target_rows
        ),
        "word_stream": " ".join(str(item["text"]) for item in segments),
    }


def matrix() -> list[dict[str, object]]:
    return [
        {
            "case": "outer_default_reacquisition",
            "audio": RETAINED / "outer_only.wav",
            "prompt_kind": "default",
            "prompt": DEFAULT_PROMPT,
        },
        {
            "case": "outer_variant",
            "audio": RETAINED / "outer_only.wav",
            "prompt_kind": "variant",
            "prompt": VARIANT_PROMPT,
        },
        {
            "case": "sequential_variant",
            "audio": RETAINED / "sequential_control.wav",
            "prompt_kind": "variant",
            "prompt": VARIANT_PROMPT,
        },
        {
            "case": "overlap_0db_variant",
            "audio": RETAINED / "overlap_sir_plus0db.wav",
            "prompt_kind": "variant",
            "prompt": VARIANT_PROMPT,
        },
        {
            "case": "overlap_plus3db_variant",
            "audio": RETAINED / "overlap_sir_plus3db.wav",
            "prompt_kind": "variant",
            "prompt": VARIANT_PROMPT,
        },
    ]


def analyze(decoded: list[dict[str, object]]) -> dict[str, object]:
    retained_rows = {
        row["case"]: row for row in json.loads(RETAINED_RESULTS.read_text())["decoded"]
    }
    new_rows = {row["case"]: row for row in decoded}
    default_rows = {
        "sequential": retained_rows["sequential_control"],
        "overlap_0db": retained_rows["overlap_sir_plus0db"],
        "overlap_plus3db": retained_rows["overlap_sir_plus3db"],
        "outer": new_rows["outer_default_reacquisition"],
    }
    variant_rows = {
        "sequential": new_rows["sequential_variant"],
        "overlap_0db": new_rows["overlap_0db_variant"],
        "overlap_plus3db": new_rows["overlap_plus3db_variant"],
        "outer": new_rows["outer_variant"],
    }
    comparisons = {
        name: {"default": _case_state(default_rows[name]), "variant": _case_state(variant_rows[name])}
        for name in variant_rows
    }
    reference_text = " ".join(
        json.loads(line)["text"] for line in OUTER_REFERENCE.read_text().splitlines() if line.strip()
    )
    outer_default_wer = _wer(reference_text, comparisons["outer"]["default"]["word_stream"])
    outer_variant_wer = _wer(reference_text, comparisons["outer"]["variant"]["word_stream"])
    controls = {
        "outer_stays_one_speaker": comparisons["outer"]["variant"]["speaker_count"] == 1,
        "outer_has_no_source_matching_interruption": not comparisons["outer"]["variant"][
            "source_matching_non_dominant_turn"
        ],
        "outer_wer_delta_at_most_0_01": outer_variant_wer - outer_default_wer <= 0.01,
        "sequential_source_turn_survives": comparisons["sequential"]["variant"][
            "source_matching_non_dominant_turn"
        ],
        "sequential_has_two_speakers": comparisons["sequential"]["variant"]["speaker_count"] == 2,
    }
    recovered = {
        name: comparisons[name]["variant"]["source_matching_non_dominant_turn"]
        for name in ("overlap_0db", "overlap_plus3db")
    }
    return {
        "prompt_appendix": APPENDIX,
        "comparisons": comparisons,
        "outer_wer": {
            "default": round(outer_default_wer, 6),
            "variant": round(outer_variant_wer, 6),
            "delta": round(outer_variant_wer - outer_default_wer, 6),
        },
        "controls": controls,
        "overlap_recovered": recovered,
        "candidate_supported": all(controls.values()) and any(recovered.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--lease-limit", type=int)
    args = parser.parse_args()
    plan = [
        {"case": item["case"], "audio": str(item["audio"]), "prompt_kind": item["prompt_kind"]}
        for item in matrix()
    ]
    if not args.execute:
        print(json.dumps({"mode": "dry_run", "requests": 0, "prompt_appendix": APPENDIX, "plan": plan}, indent=2, ensure_ascii=False))
        return 0
    if not args.endpoint or args.lease_limit is None:
        raise SystemExit("--execute requires --endpoint and --lease-limit from the granted GPU lease")

    before = sent_count()
    if before + len(plan) > args.lease_limit:
        raise RuntimeError(
            f"lease insufficient: sent={before}, needed={len(plan)}, limit={args.lease_limit}"
        )
    runner = VllmRunner(
        base_url=args.endpoint,
        model="OpenMOSS-Team/MOSS-Transcribe-Diarize",
        timeout=600.0,
    )
    decoded: list[dict[str, object]] = []
    output = HERE / "results.json"
    for item in matrix():
        try:
            result = runner.transcribe(
                item["audio"], prompt=item["prompt"], max_new_tokens=6000, decoding="greedy"
            )
            row = {
                "case": item["case"],
                "audio": str(item["audio"]),
                "prompt_kind": item["prompt_kind"],
                "raw_text": result.text,
                "generated_tokens": result.generated_tokens,
                "elapsed_sec": round(result.elapsed_sec, 6),
                "segments": _segments(result.text),
            }
        except EmptyTranscriptionError as error:
            row = {
                "case": item["case"],
                "audio": str(item["audio"]),
                "prompt_kind": item["prompt_kind"],
                "raw_text": error.text,
                "generated_tokens": error.generated_tokens,
                "segments": _segments(error.text),
                "error": type(error).__name__,
                "empty_cause": error.cause.value,
            }
        decoded.append(row)
        output.write_text(
            json.dumps(
                {
                    "sent_before": before,
                    "sent_after": sent_count(),
                    "prompt_appendix": APPENDIX,
                    "decoded": decoded,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        print(json.dumps({"completed": row, "requests_sent": sent_count() - before}, indent=2, ensure_ascii=False))

    verdict = analyze(decoded)
    (HERE / "analysis.json").write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
