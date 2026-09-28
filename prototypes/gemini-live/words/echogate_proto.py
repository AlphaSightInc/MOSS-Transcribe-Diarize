"""P52 acoustic echo-gate prototype; one command from worktree root:

PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/words/echogate_proto.py

Question: can same-span lane RMS reject returned system speech without losing
the three known local utterances? Falsifier: >30% E1 phrase-word loss, any M2
operator word loss, or >5% surviving words outside operator intervals.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path

import numpy as np

from lane_proto import (EVIDENCE, FIXTURE, OPERATORS, RATE, echoed, operator_recall,
                        selected_words, speech_supported, status, vad_voiced)
from corpus import clips
from gemini_common import diarize_window, read_wav

DBS = (6, 10, 15, 20)
ENDS = list(range(10, 301, 10)) + [302]
VARIANTS = ("E1", "M2", "echo_m15", "echo_m10", "voice_g01")


def rms(pcm: np.ndarray) -> float:
    return math.sqrt(float(np.mean(np.square(pcm, dtype=np.float64)))) if len(pcm) else 0.0


def float_audio() -> dict[str, np.ndarray]:
    """Reconstruct harder cases from the measured E1 parts; retain no audio artifact."""
    system = read_wav(FIXTURE / "system.wav").astype(np.float64)
    e1 = read_wav(FIXTURE / "E1-microphone.wav").astype(np.float64)
    m2 = read_wav(FIXTURE / "M2-microphone.wav").astype(np.float64)
    delayed = np.concatenate((np.zeros(480), system[:-480]))
    keyu = next(c for c in clips("gold9") if c.clip_id == "benchmark:lex_keyu_jin")
    source = read_wav(keyu.audio).astype(np.float64)
    operator = np.zeros_like(e1)
    for t, source_t in ((30, 2), (135, 9), (248, 17)):
        operator[t*RATE:(t+3)*RATE] = source[source_t*RATE:(source_t+3)*RATE]
    old_echo = 10 ** (-25 / 20)
    signals = {
        "E1": e1,
        "M2": m2,
        "echo_m15": e1 + (10 ** (-15 / 20) - old_echo) * delayed,
        "echo_m10": e1 + (10 ** (-10 / 20) - old_echo) * delayed,
        "voice_g01": e1 - .2 * operator,
    }
    return {name: np.clip(np.rint(x), -32768, 32767).astype(np.int16)
            for name, x in signals.items()}


def fixture_proof(signals: dict[str, np.ndarray]) -> dict:
    system = read_wav(FIXTURE / "system.wav").astype(np.float64)
    delayed = np.concatenate((np.zeros(480), system[:-480]))
    e1 = signals["E1"].astype(np.float64)
    outside = np.ones(len(system), dtype=bool)
    for t in OPERATORS:
        outside[t*RATE:(t+3)*RATE] = False
    residual = e1 - 10 ** (-25 / 20) * delayed
    return {
        "echo_delay_ms": 30, "echo_source_db": -25,
        "system_rms_outside_operator": rms(system[outside]),
        "e1_mic_rms_outside_operator": rms(e1[outside]),
        "e1_residual_rms_outside_operator": rms(residual[outside]),
        "m2_mic_rms_outside_operator": rms(signals["M2"].astype(np.float64)[outside]),
        "variant_peak_samples": {name: int(np.max(np.abs(pcm.astype(np.int32))))
                                 for name, pcm in signals.items()},
    }


def batch_variant(name: str, pcm: np.ndarray, *, allow_provider: bool,
                  new_spend: list[float]) -> list[dict]:
    if name in ("E1", "M2"):
        return selected_words(name)
    if not allow_provider:
        return []
    previous_end = 0
    words: list[dict] = []
    for end_s in ENDS:
        start_s = max(0, end_s - 30)
        path = EVIDENCE / f"echogate-batch-{name}-{end_s:03}.json"
        if path.exists():
            receipt = json.loads(path.read_text())
        else:
            if new_spend[0] >= 0.95:
                raise RuntimeError("ECHOGATE incremental spend guard reached $0.95")
            result = diarize_window(pcm[start_s*RATE:end_s*RATE], diarize=False,
                                    word_timestamps=True, use_cache=True,
                                    ledger_lane="P52", max_attempts=3)
            receipt = {"case": name, "start_s": start_s, "end_s": end_s,
                       "cached": result.cached, "cost_usd": result.cost_usd(),
                       "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0},
                       "words": [{"text": w.text, "speaker": w.speaker,
                                  "start": start_s + w.start, "end": start_s + w.end}
                                 for w in result.words]}
            path.write_text(json.dumps(receipt, indent=2) + "\n")
            if not result.cached:
                new_spend[0] += result.cost_usd()
            status(f"ECHOGATE {name} window {start_s}-{end_s}s: {len(result.words)} words, "
                   f"cached={result.cached}, anomalies={receipt['timing_anomalies']}, "
                   f"incremental spend ${new_spend[0]:.6f}.")
        for word in receipt["words"]:
            middle = (word["start"] + word["end"]) / 2
            if previous_end <= middle < end_s or (end_s == 302 and middle == 302):
                words.append(word)
        previous_end = end_s
    return sorted(words, key=lambda w: (w["start"], w["end"]))


def batch_receipt_summary(name: str) -> dict:
    lane = name if name in ("E1", "M2") else None
    receipts = [json.loads((EVIDENCE / (f"lane-batch-{lane}-{end_s:03}.json" if lane
                                      else f"echogate-batch-{name}-{end_s:03}.json")).read_text())
                for end_s in ENDS]
    return {"calls": len(receipts), "cached_calls": sum(bool(r["cached"]) for r in receipts),
            "uncached_cost_usd": sum(r["cost_usd"] for r in receipts if not r["cached"]),
            "anomalous_calls": sum(any(r["timing_anomalies"].values()) for r in receipts),
            "clamped_words": sum(r["timing_anomalies"]["clamped"] for r in receipts),
            "dropped_words": sum(r["timing_anomalies"]["dropped"] for r in receipts)}


def acoustic_features(word: dict, mic: np.ndarray, system: np.ndarray,
                      system_voiced: list[bool]) -> dict:
    start = max(0, min(len(mic)-1, round(word["start"] * RATE)))
    end = min(len(mic), max(start + 1, round(word["end"] * RATE)))
    mic_rms = rms(mic[start:end])
    first_vad = max(0, min(len(system_voiced)-1, start // 160))
    last_vad = min(len(system_voiced), max(first_vad+1, (end+159)//160))
    voiced = any(system_voiced[first_vad:last_vad])
    choices = []
    duration = end-start
    for lag_ms in range(0, 101, 10):
        source_start = max(0, start - lag_ms * RATE // 1000)
        source_end = min(len(system), source_start + duration)
        choices.append((rms(system[source_start:source_end]), lag_ms))
    sys_rms, lag_ms = max(choices)
    ratio_db = 20 * math.log10(max(mic_rms, 1e-12) / max(sys_rms, 1e-12))
    return {"system_voiced": voiced, "mic_rms": mic_rms, "system_rms": sys_rms,
            "best_lag_ms": lag_ms, "mic_minus_system_db": ratio_db}


def inside(word: dict) -> bool:
    middle = (word["start"] + word["end"]) / 2
    return any(t <= middle <= t+3 for t in OPERATORS)


def summarize(rows: list[dict]) -> dict:
    stray = sum(not row["inside_operator"] for row in rows)
    recall = operator_recall(rows)
    return {"words": len(rows), "outside_operator_words": stray,
            "outside_operator_rate": stray/len(rows) if rows else None,
            "operator_recall": [{"at_s": r["at_s"], "matched": r["matched"],
                                 "reference_words": r["reference_words"]} for r in recall],
            "operator_word_rows": {str(t): sum(t <= (w["start"]+w["end"])/2 <= t+3 for w in rows)
                                   for t in OPERATORS}}


def analyze_case(name: str, mic: np.ndarray, system: np.ndarray,
                 system_voiced: list[bool], system_words: list[dict], words: list[dict]) -> dict:
    mic_voiced = vad_voiced(mic)
    tagged = []
    for w in words:
        tagged.append({**w, "inside_operator": inside(w),
                       "mic_speech_supported": speech_supported(w, mic_voiced),
                       "text_echoed": echoed(w, system_words),
                       **acoustic_features(w, mic, system, system_voiced)})
    arms = {"raw": tagged,
            "text_only": [w for w in tagged if w["mic_speech_supported"] and not w["text_echoed"]]}
    for db in DBS:
        acoustic = [w for w in tagged if w["mic_speech_supported"] and
                    (not w["system_voiced"] or w["mic_minus_system_db"] >= -db)]
        arms[f"acoustic_D{db}"] = acoustic
        arms[f"combined_D{db}"] = [w for w in acoustic if not w["text_echoed"]]
    metrics = {arm: summarize(rows) for arm, rows in arms.items()}
    raw_operator = metrics["raw"]["operator_word_rows"]
    for arm, d in metrics.items():
        d["operator_row_retention"] = {t: (d["operator_word_rows"][t] / raw_operator[t]
                                           if raw_operator[t] else None)
                                       for t in raw_operator}
        d["source_operator_pass"] = all(r["matched"] / r["reference_words"] >= .70
                                        for r in d["operator_recall"])
        d["m2_all_operator_words_pass"] = all(d["operator_word_rows"][t] == raw_operator[t]
                                           for t in raw_operator)
        d["stray_pass"] = d["outside_operator_rate"] is not None and d["outside_operator_rate"] <= .05
    return {"name": name, "audio_seconds": len(mic)/RATE,
            "raw_system_unvoiced_words": sum(not w["system_voiced"] for w in tagged),
            "raw_mic_vad_rejected": sum(not w["mic_speech_supported"] for w in tagged),
            "raw_operator_ratio_db": [round(w["mic_minus_system_db"], 3) for w in tagged if w["inside_operator"]],
            "raw_stray_ratio_db": [round(w["mic_minus_system_db"], 3) for w in tagged if not w["inside_operator"]],
            "arms": metrics,
            "words": tagged}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("baseline", "harder", "all"), default="all")
    args = parser.parse_args()
    signals = float_audio()
    system = read_wav(FIXTURE / "system.wav")
    system_voiced = vad_voiced(system)
    system_words = selected_words("system")
    result = {"schema": "p52-echogate-v1", "question": "same-span lane energy vs echo",
              "rule": "system WebRTC mode1 unvoiced over word OR mic RMS >= max system RMS over 0..100ms earlier lag minus D dB",
              "thresholds_db": list(DBS), "fixture_proof": fixture_proof(signals),
              "system_voiced_frames": sum(system_voiced), "system_frames": len(system_voiced),
              "cases": {}, "batch_receipts": {}, "new_provider_spend_this_run_usd": 0.0,
              "hard_variant_uncached_cost_usd": 0.0, "combined_all_cases_pass": {}}
    new_spend = [0.0]
    cases = ("E1", "M2") if args.phase == "baseline" else VARIANTS
    for name in cases:
        words = batch_variant(name, signals[name], allow_provider=True, new_spend=new_spend)
        result["cases"][name] = analyze_case(name, signals[name], system, system_voiced,
                                             system_words, words)
        result["batch_receipts"][name] = batch_receipt_summary(name)
        result["new_provider_spend_this_run_usd"] = new_spend[0]
        result["hard_variant_uncached_cost_usd"] = sum(
            r["uncached_cost_usd"] for key, r in result["batch_receipts"].items()
            if key not in ("E1", "M2"))
        if len(result["cases"]) == len(VARIANTS):
            result["combined_all_cases_pass"] = {
                str(db): all(
                    result["cases"][key]["arms"][f"combined_D{db}"]["stray_pass"] and
                    (result["cases"][key]["arms"][f"combined_D{db}"]["m2_all_operator_words_pass"]
                     if key == "M2" else
                     result["cases"][key]["arms"][f"combined_D{db}"]["source_operator_pass"])
                    for key in VARIANTS)
                for db in DBS}
        path = EVIDENCE / "echogate-analysis.json"
        path.write_text(json.dumps(result, indent=2) + "\n")
        print(name, json.dumps({arm: {"stray": f"{m['outside_operator_words']}/{m['words']}",
                                        "source_recall": [f"{r['matched']}/{r['reference_words']}"
                                                          for r in m["operator_recall"]],
                                        "source_pass": m["source_operator_pass"]}
                                for arm, m in result["cases"][name]["arms"].items()},
                               sort_keys=True), flush=True)
        status(f"ECHOGATE {name} analyzed: raw {len(words)} words; new provider spend ${new_spend[0]:.6f}; {path}.")


if __name__ == "__main__":
    main()
