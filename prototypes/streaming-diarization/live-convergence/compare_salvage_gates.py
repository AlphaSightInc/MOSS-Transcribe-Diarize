"""Plan §9.1 — run gates O1 and O2 over the saved 184-span corpus and adjudicate.

Preregistration: `PREREGISTRATION-M1a.md`. Issues **zero** MOSS requests: every decode this
reads was already generated and saved. Exit 0 iff every preregistered gate passes.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/compare_salvage_gates.py --output /tmp/m1a.json
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from evaluator_v2 import score_v2  # noqa: E402
from salvage_gates import (  # noqa: E402
    GATE_O1,
    GATE_O2,
    PARSED,
    REFUSED_BOILERPLATE,
    SALVAGED,
    classify,
)

from moss_transcribe_diarize.app.live_provider_bundle import WebRtcSpeechProvider  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402
from moss_transcribe_diarize.evaluation import Segment, calculate_tbsa  # noqa: E402

SR = 16000
GATES = (GATE_O1, GATE_O2)
BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824/trio-60s"
EMPTYSPAN = REPO / "prototypes/live-file-gap-emptyspan"
CORPUS_1MIN = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
CORPUS_3MIN = REPO / "prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples"
TRIO = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
SECONDARY = "acquired_jamie_dimon"
SIM_CASE = "lex_adam_frank"
#: Deployed speech provider configuration (`evidence/phase1/w0-local-live/live-provider-manifest.json`).
VAD_MODE = 1
VAD_FRAME_SAMPLES = 160
#: A window whose speech ratio is this low is treated as digital silence for gate G3.
SILENCE_RATIO = 0.01


# --------------------------------------------------------------------------- corpus


def case_audio(case: str) -> Path:
    for root in (CORPUS_1MIN, CORPUS_3MIN):
        if (root / case).is_dir():
            return root / case / "audio.wav"
    raise FileNotFoundError(case)


def read_pcm(case: str) -> bytes:
    with wave.open(str(case_audio(case)), "rb") as handle:
        assert handle.getnchannels() == 1 and handle.getsampwidth() == 2
        assert handle.getframerate() == SR
        return handle.readframes(handle.getnframes())


def speech_ratio(pcm: bytes) -> float:
    """Recompute the span's speech ratio with the production provider (plan §6 M1, O2)."""
    if len(pcm) < 2:
        return 0.0
    import webrtcvad

    provider = WebRtcSpeechProvider(vad=webrtcvad.Vad(VAD_MODE), frame_samples=VAD_FRAME_SAMPLES)
    samples = len(pcm) // 2
    observations = provider.observe(
        frame=AudioFrame(sequence=0, pcm=pcm, sample_count=samples), start_sample=0, end_sample=samples
    )
    voiced = sum(o.end_sample - o.start_sample for o in observations if o.speech_present)
    return voiced / samples


def load_trace_spans(case: str) -> list[dict[str, Any]]:
    path = BASELINE / case / "live/run-001/trace.jsonl"
    frozen: dict[int, dict] = {}
    committed: dict[int, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("kind") == "service_event" and isinstance(record.get("event"), dict):
            event = record["event"]
            payload = event.get("payload") or {}
            if event.get("kind") == "span_frozen":
                frozen[payload["span_id"]] = payload
        elif record.get("kind") == "terminal":
            for item in record["snapshot"]["session"].get("committed", []):
                committed[item["span_id"]] = item
    return [
        {
            "case": case,
            "span_id": span_id,
            "start_sample": committed[span_id]["start_sample"],
            "end_sample": committed[span_id]["end_sample"],
            "freeze_reason": frozen.get(span_id, {}).get("reason", "stop_flush(untraced)"),
            "text": committed[span_id].get("transcript") or "",
            "text_source": "committed",
        }
        for span_id in sorted(committed)
    ]


def load_corpus() -> list[dict[str, Any]]:
    """The plan §9.2 corpus: 184 saved spans with their decodes, bounds and freeze reasons."""
    raw_decodes = {
        (row["case"], row["span_id"]): row["raw_text"]
        for row in json.loads((EMPTYSPAN / "out/d3.json").read_text(encoding="utf-8"))["raw"]
    }
    spans: list[dict[str, Any]] = []
    for case in (*TRIO, SECONDARY):
        for span in load_trace_spans(case):
            override = raw_decodes.get((case, span["span_id"]))
            if override is not None:
                span["text"] = override
                span["text_source"] = "raw_decode_validation_bypassed"
            span["tier"] = "trio" if case in TRIO else "secondary"
            spans.append(span)
    simulated = json.loads((EMPTYSPAN / f"out/p1-{SIM_CASE}.json").read_text(encoding="utf-8"))
    for span in simulated["spans"]:
        spans.append(
            {
                "case": SIM_CASE,
                "span_id": span["span_id"],
                "start_sample": round(span["start_s"] * SR),
                "end_sample": round(span["end_s"] * SR),
                "freeze_reason": span["reason"],
                "text": span["raw_text"],
                "text_source": "raw_decode_validation_bypassed",
                "tier": "three_minute",
            }
        )
    pcm_cache: dict[str, bytes] = {}
    prior_ratio = {
        (case, row["span_id"]): row["vad_speech_ratio"]
        for case, payload in json.loads((EMPTYSPAN / "out/d1.json").read_text(encoding="utf-8"))["cases"].items()
        for row in payload["rows"]
    }
    prior_ratio.update({(SIM_CASE, s["span_id"]): s["vad_speech_ratio"] for s in simulated["spans"]})
    for span in spans:
        pcm = pcm_cache.setdefault(span["case"], read_pcm(span["case"]))
        window = pcm[span["start_sample"] * 2 : span["end_sample"] * 2]
        span["sample_count"] = span["end_sample"] - span["start_sample"]
        span["speech_ratio"] = round(speech_ratio(window), 6)
        span["prior_speech_ratio"] = prior_ratio.get((span["case"], span["span_id"]))
        span["all_zero_pcm"] = not any(window)
    return spans


# ------------------------------------------------------------------- boilerplate corpus


def boilerplate_corpus() -> tuple[str, ...]:
    """Texts the decoder emitted for windows holding no speech, read from the saved corpus.

    Kept as *data* read from the measurement corpus rather than as literals inside the
    classifier: the general rule is "a decode the model has been seen to emit for non-speech",
    and which phrases those are is an observation about this decoder, not a rule.
    """
    raw = json.loads((EMPTYSPAN / "out/d3.json").read_text(encoding="utf-8"))["raw"]
    simulated = json.loads((EMPTYSPAN / f"out/p1-{SIM_CASE}.json").read_text(encoding="utf-8"))["spans"]
    d1 = json.loads((EMPTYSPAN / "out/d1.json").read_text(encoding="utf-8"))["cases"]
    silent: set[str] = set()
    zero_windows = {
        (case, row["span_id"])
        for case, payload in d1.items()
        for row in payload["rows"]
        if row["vad_speech_ratio"] == 0.0
    }
    zero_windows |= {(SIM_CASE, s["span_id"]) for s in simulated if s["vad_speech_ratio"] == 0.0}
    for row in raw:
        if (row["case"], row["span_id"]) in zero_windows:
            silent.add(_words(row["raw_text"]))
    for span in simulated:
        if (SIM_CASE, span["span_id"]) in zero_windows and span["parsed_segments"] == 0:
            silent.add(_words(span["raw_text"]))
    return tuple(sorted(text for text in silent if text))


def _words(text: str) -> str:
    out, depth = [], 0
    for char in text:
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(char)
    return " ".join("".join(out).lower().split())


def make_boilerplate_filter(corpus: Sequence[str]):
    lowered = tuple(text for text in corpus if text)

    def is_boilerplate(text: str) -> bool:
        normalised = " ".join(text.lower().split())
        return any(normalised == entry or entry in normalised for entry in lowered)

    return is_boilerplate


# ------------------------------------------------------------------------ constructed


def constructed_spans() -> list[dict[str, Any]]:
    """Plan §9.2's constructed two-speaker hard-cap spans; the saved corpus has none."""
    return [
        {
            "name": "same_speaker_two_chunks_no_timestamps",
            "text": "[S01] The difference between,[S01] you said the stock market.",
            "sample_count": 40000,
            "freeze_reason": "hard_cap",
            "speech_ratio": 0.9,
            "expect": SALVAGED,
            "expect_speakers": 1,
        },
        {
            "name": "two_speakers_interior_timestamp_present",
            # Zero-parse two-speaker hard cap: the decoder emitted the boundary between the
            # turns and omitted both outer bounds, the shape observed on bill span 02.
            "text": "[S01] I think so[1.20][S02] and I agree",
            "sample_count": 40000,
            "freeze_reason": "hard_cap",
            "speech_ratio": 0.9,
            "expect": SALVAGED,
            "expect_speakers": 2,
        },
        {
            "name": "two_speakers_no_interior_timestamp",
            "text": "[0.10][S01] I think so[S02] and I agree",
            "sample_count": 40000,
            "freeze_reason": "hard_cap",
            "speech_ratio": 0.9,
            "expect": "refused_interior_boundary",
            "expect_speakers": 0,
        },
        {
            "name": "two_speakers_no_timestamps_at_all",
            "text": "[S01] I think so[S02] and I agree",
            "sample_count": 40000,
            "freeze_reason": "hard_cap",
            "speech_ratio": 0.9,
            "expect": "refused_interior_boundary",
            "expect_speakers": 0,
        },
        {
            "name": "three_speakers_one_interior_timestamp_missing",
            "text": "[S01] first[1.00][S02] second[S03] third",
            "sample_count": 40000,
            "freeze_reason": "hard_cap",
            "speech_ratio": 0.9,
            "expect": "refused_interior_boundary",
            "expect_speakers": 0,
        },
    ]


# -------------------------------------------------------------------------- projection


def load_segments(path: Path) -> list[Segment]:
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        segments.append(
            Segment(float(record["start"]), float(record["end"]), str(record["speaker"]), str(record["text"]))
        )
    return segments


def reference_for(case: str) -> list[Segment]:
    return load_segments(case_audio(case).parent / "reference.jsonl")


def project(case: str, spans: Sequence[dict[str, Any]], gate: str, decisions) -> list[Segment]:
    """Substitute the gate's salvaged segments into the baseline live hypothesis.

    The speaker label is the nearest published live segment's, a stand-in for what
    `live_identity` would assign; the words and their window are the measured part.
    """
    hypothesis = load_segments(BASELINE / case / "live-hypothesis.jsonl")
    if not hypothesis:
        raise ValueError(f"{case} has no baseline live hypothesis")
    out = list(hypothesis)
    for span in spans:
        if span["case"] != case:
            continue
        outcome = decisions[(gate, span["case"], span["span_id"])]
        if outcome.disposition != SALVAGED:
            continue
        offset = span["start_sample"] / SR
        for segment in outcome.segments:
            start, end = offset + segment.start, offset + segment.end
            speaker = min(hypothesis, key=lambda h: abs(h.start - start)).speaker
            out.append(Segment(round(start, 2), round(end, 2), speaker, segment.text))
    return sorted(out, key=lambda s: (s.start, s.end, s.speaker, s.text))


def score(case: str, hypothesis: Sequence[Segment]) -> dict[str, float]:
    reference = reference_for(case)
    deployed = calculate_tbsa(reference, list(hypothesis))
    v2 = score_v2(reference, list(hypothesis))
    return {
        "wer": deployed["wer"],
        "text_coverage": deployed["text_coverage"],
        "text_speaker_accuracy": deployed["text_speaker_accuracy"],
        "composite": deployed["composite"],
        "v2_wer": v2["wer"]["wer"],
        "v2_content_recall": v2["content_recall"],
        "v2_matched_word_speaker": v2["matched_word_speaker"]["matched_word_speaker_accuracy"],
    }


# ------------------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    spans = load_corpus()
    corpus = boilerplate_corpus()
    is_boilerplate = make_boilerplate_filter(corpus)

    decisions: dict[tuple[str, str, int], Any] = {}
    for gate in GATES:
        for span in spans:
            decisions[(gate, span["case"], span["span_id"])] = classify(
                span["text"],
                sample_count=span["sample_count"],
                freeze_reason=span["freeze_reason"],
                speech_ratio=span["speech_ratio"],
                gate=gate,
                is_boilerplate=is_boilerplate,
            )
    # Same corpus, boilerplate filter disabled: measures the filter's marginal load.
    unfiltered = {
        (gate, span["case"], span["span_id"]): classify(
            span["text"],
            sample_count=span["sample_count"],
            freeze_reason=span["freeze_reason"],
            speech_ratio=span["speech_ratio"],
            gate=gate,
            is_boilerplate=None,
        )
        for gate in GATES
        for span in spans
    }

    rows = []
    for span in spans:
        key = (span["case"], span["span_id"])
        row = {
            **{k: span[k] for k in ("case", "tier", "span_id", "freeze_reason", "speech_ratio", "prior_speech_ratio", "all_zero_pcm", "text_source")},
            "duration_s": round(span["sample_count"] / SR, 3),
            "text": span["text"],
        }
        for gate in GATES:
            outcome = decisions[(gate, *key)]
            row[gate] = {
                "disposition": outcome.disposition,
                "reason": outcome.reason,
                "publishes": outcome.publishes,
                "rendered": outcome.rendered if outcome.disposition == SALVAGED else "",
                "segments": [[s.start, s.end, s.speaker, s.text] for s in outcome.segments]
                if outcome.disposition == SALVAGED
                else [],
            }
        rows.append(row)

    zero_parse = [r for r in rows if r[GATE_O1]["disposition"] != PARSED]
    disagreements = [
        r for r in rows if r[GATE_O1]["disposition"] != r[GATE_O2]["disposition"]
    ]

    # Partial-parse diagnostic: spans whose raw decode names more speaker turns than the
    # production parser emitted segments (words dropped without any empty-span signal).
    partial = [
        {
            "case": r["case"],
            "span_id": r["span_id"],
            "speaker_markers": r["text"].count("[S"),
            "parsed_segments": len(
                classify(
                    r["text"], sample_count=round(r["duration_s"] * SR), freeze_reason=r["freeze_reason"],
                    speech_ratio=r["speech_ratio"], gate=GATE_O1,
                ).segments
            ),
        }
        for r in rows
        if r[GATE_O1]["disposition"] == PARSED
    ]
    partial = [p for p in partial if p["speaker_markers"] > p["parsed_segments"]]

    constructed = []
    for case in constructed_spans():
        outcome = classify(
            case["text"],
            sample_count=case["sample_count"],
            freeze_reason=case["freeze_reason"],
            speech_ratio=case["speech_ratio"],
            gate=GATE_O1,
            is_boilerplate=is_boilerplate,
        )
        speakers = {s.speaker for s in outcome.segments}
        intervals = [[round(s.start, 3), round(s.end, 3), s.speaker] for s in outcome.segments]
        overlap = any(
            intervals[i][1] > intervals[i + 1][0] and intervals[i][2] != intervals[i + 1][2]
            for i in range(len(intervals) - 1)
        )
        constructed.append(
            {
                **{k: case[k] for k in ("name", "text", "expect", "expect_speakers")},
                "disposition": outcome.disposition,
                "reason": outcome.reason,
                "speakers": len(speakers),
                "intervals": intervals,
                "cross_speaker_overlap": overlap,
                "ok": outcome.disposition == case["expect"] and len(speakers) == case["expect_speakers"] and not overlap,
            }
        )

    projection: dict[str, Any] = {}
    baseline_cases = {case: score(case, load_segments(BASELINE / case / "live-hypothesis.jsonl")) for case in TRIO}
    file_cases = {case: score(case, load_segments(BASELINE / case / "file-hypothesis.jsonl")) for case in TRIO}
    projection["baseline_live"] = baseline_cases
    projection["file"] = file_cases
    for gate in GATES:
        per_case = {case: score(case, project(case, spans, gate, decisions)) for case in TRIO}
        projection[gate] = {
            "per_case": per_case,
            "trio_mean": {
                key: round(sum(per_case[c][key] for c in TRIO) / len(TRIO), 6) for key in per_case[TRIO[0]]
            },
            "regressions": [
                {"case": c, "metric": m, "baseline": baseline_cases[c][m], "projected": per_case[c][m]}
                for c in TRIO
                for m in ("wer", "v2_wer")
                if per_case[c][m] > baseline_cases[c][m] + 1e-9
            ],
        }
    projection["baseline_trio_mean"] = {
        key: round(sum(baseline_cases[c][key] for c in TRIO) / len(TRIO), 6) for key in baseline_cases[TRIO[0]]
    }
    projection["file_trio_mean"] = {
        key: round(sum(file_cases[c][key] for c in TRIO) / len(TRIO), 6) for key in file_cases[TRIO[0]]
    }

    # -------------------------------------------------------------------- gates
    ratio_deltas = [
        {"case": r["case"], "span_id": r["span_id"], "now": r["speech_ratio"], "prior": r["prior_speech_ratio"],
         "delta": round(abs(r["speech_ratio"] - r["prior_speech_ratio"]), 6)}
        for r in rows
        if r["prior_speech_ratio"] is not None and abs(r["speech_ratio"] - r["prior_speech_ratio"]) > 0.01
    ]
    published_boilerplate = {
        gate: [
            {"case": r["case"], "span_id": r["span_id"], "text": r["text"]}
            for r in rows
            if r[gate]["publishes"]
            and r[gate]["disposition"] == SALVAGED
            and is_boilerplate(" ".join(s[3] for s in r[gate]["segments"]))
        ]
        for gate in GATES
    }
    published_on_silence = {
        gate: [
            {"case": r["case"], "span_id": r["span_id"], "speech_ratio": r["speech_ratio"], "text": r["text"]}
            for r in rows
            if r[gate]["disposition"] == SALVAGED and (r["all_zero_pcm"] or r["speech_ratio"] < SILENCE_RATIO)
        ]
        for gate in GATES
    }
    boilerplate_marginal = {
        gate: [
            {"case": r["case"], "span_id": r["span_id"]}
            for r in rows
            if decisions[(gate, r["case"], r["span_id"])].disposition == REFUSED_BOILERPLATE
            and unfiltered[(gate, r["case"], r["span_id"])].disposition == SALVAGED
        ]
        for gate in GATES
    }

    gates = {
        "G1_corpus_fidelity": {
            "spans": len(rows),
            "expected_spans": 184,
            "speech_ratio_mismatches": ratio_deltas,
            "pass": len(rows) == 184 and not ratio_deltas,
        },
        "G2_no_boilerplate_published": {
            "per_gate": published_boilerplate,
            "boilerplate_corpus": list(corpus),
            "marginal_load": boilerplate_marginal,
            "pass": not any(published_boilerplate.values()),
        },
        "G3_no_words_on_digital_silence": {
            "per_gate": published_on_silence,
            "pass": not any(published_on_silence.values()),
        },
        "G4_fixed_point": {
            "checked": sum(1 for r in rows for g in GATES if r[g]["disposition"] == SALVAGED),
            "failures": [r for r in rows if any(r[g]["disposition"] == "refused_fixed_point" for g in GATES)],
            "pass": all(r[g]["disposition"] != "refused_fixed_point" for r in rows for g in GATES),
        },
        "G5_witness_owned_intervals": {
            "constructed": constructed,
            "pass": all(c["ok"] for c in constructed),
        },
        "G6_zero_extra_moss_requests": {"requests_issued": 0, "pass": True},
        "G7_no_case_wer_regression": {
            gate: projection[gate]["regressions"] for gate in GATES
        },
    }
    gates["G7_no_case_wer_regression"]["pass"] = not projection[GATE_O1]["regressions"]

    # How well does the freeze reason (O1's whole state) stand in for the speech ratio (O2's)?
    profile: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = profile.setdefault(
            row["freeze_reason"], {"spans": 0, "min_speech_ratio": 1.0, "max_speech_ratio": 0.0, "below_o2_floor": 0}
        )
        entry["spans"] += 1
        entry["min_speech_ratio"] = round(min(entry["min_speech_ratio"], row["speech_ratio"]), 6)
        entry["max_speech_ratio"] = round(max(entry["max_speech_ratio"], row["speech_ratio"]), 6)
        entry["below_o2_floor"] += int(row["speech_ratio"] < 0.5)

    result = {
        "corpus_spans": len(rows),
        "freeze_reason_speech_profile": profile,
        "zero_parse_spans": len(zero_parse),
        "disagreements": [
            {
                "case": r["case"],
                "span_id": r["span_id"],
                "freeze_reason": r["freeze_reason"],
                "speech_ratio": r["speech_ratio"],
                "duration_s": r["duration_s"],
                "text": r["text"],
                GATE_O1: r[GATE_O1]["disposition"],
                GATE_O2: r[GATE_O2]["disposition"],
            }
            for r in disagreements
        ],
        "partial_parse_spans": partial,
        "gates": gates,
        "projection": projection,
        "rows": rows,
    }

    _report(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nwrote {args.output}")
    failed = [name for name, payload in gates.items() if not payload["pass"]]
    print("\nGATES: " + ("all pass" if not failed else "FAILED " + ", ".join(failed)))
    return 0 if not failed else 1


def _report(result: dict[str, Any]) -> None:
    print(f"corpus: {result['corpus_spans']} spans, {result['zero_parse_spans']} parse to zero segments\n")
    print(f"{'case':22s} {'span':>4s} {'freeze':>18s} {'vad':>6s} {'dur':>5s}  {'O1':22s} {'O2':22s}")
    for row in result["rows"]:
        if row[GATE_O1]["disposition"] == PARSED and row[GATE_O2]["disposition"] == PARSED:
            continue
        print(
            f"{row['case']:22s} {row['span_id']:4d} {row['freeze_reason']:>18s} "
            f"{row['speech_ratio']:6.3f} {row['duration_s']:5.2f}  "
            f"{row[GATE_O1]['disposition']:22s} {row[GATE_O2]['disposition']:22s}"
        )
    print("\nfreeze reason vs speech ratio (does O1's state stand in for O2's?):")
    for reason, entry in sorted(result["freeze_reason_speech_profile"].items()):
        print(
            f"  {reason:22s} spans {entry['spans']:4d}  speech ratio "
            f"{entry['min_speech_ratio']:.3f}-{entry['max_speech_ratio']:.3f}  below O2 floor {entry['below_o2_floor']}"
        )
    print(f"\ndisagreements: {len(result['disagreements'])}")
    for row in result["disagreements"]:
        print(f"  {row['case']}#{row['span_id']}  {row[GATE_O1]} vs {row[GATE_O2]}   {row['text']!r}")
    print("\nconstructed two-speaker spans:")
    for case in result["gates"]["G5_witness_owned_intervals"]["constructed"]:
        print(f"  {'ok ' if case['ok'] else 'BAD'} {case['name']:44s} {case['disposition']:26s} {case['intervals']}")
    print("\nprojection (deployed evaluator, trio):")
    header = f"{'arm':22s} {'wer':>8s} {'coverage':>9s} {'tsa':>8s} {'composite':>10s} {'v2_recall':>10s}"
    print(header)
    for name in ("file_trio_mean", "baseline_trio_mean"):
        m = result["projection"][name]
        print(f"{name:22s} {m['wer']:8.4f} {m['text_coverage']:9.4f} {m['text_speaker_accuracy']:8.4f} {m['composite']:10.4f} {m['v2_content_recall']:10.4f}")
    for gate in GATES:
        m = result["projection"][gate]["trio_mean"]
        print(f"{gate:22s} {m['wer']:8.4f} {m['text_coverage']:9.4f} {m['text_speaker_accuracy']:8.4f} {m['composite']:10.4f} {m['v2_content_recall']:10.4f}")
    print("\nper-case WER (deployed evaluator):")
    for case in TRIO:
        base = result["projection"]["baseline_live"][case]["wer"]
        o1 = result["projection"][GATE_O1]["per_case"][case]["wer"]
        o2 = result["projection"][GATE_O2]["per_case"][case]["wer"]
        print(f"  {case:22s} baseline {base:.4f}   O1 {o1:.4f}   O2 {o2:.4f}")
    if result["partial_parse_spans"]:
        print(f"\npartial-parse spans (raw decode names more turns than the parser emitted): {len(result['partial_parse_spans'])}")
        for row in result["partial_parse_spans"][:10]:
            print(f"  {row['case']}#{row['span_id']}  markers {row['speaker_markers']} -> segments {row['parsed_segments']}")


if __name__ == "__main__":
    raise SystemExit(main())
