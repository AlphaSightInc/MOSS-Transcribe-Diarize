"""THROWAWAY P52 lane-aware words bench; public E1/M2 fixture only.

One command from worktree root:
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/words/lane_proto.py

Question: can a separate microphone stream retain three known local utterances while
timed batch words plus a simple echo guard prevent system echo/noise publication?
The full raw and filtered state is retained as JSON under evidence/P52.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import webrtcvad

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import Clip, clips  # noqa: E402
from gemini_common import diarize_window, read_wav, spend  # noqa: E402
from proto_words import run_live  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.2-STATUS.md")
FIXTURE = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture")
RATE = 16000
OPERATORS = {30: "they think that they're responsible for you",
             135: "deference to authority is not blind submission",
             248: "in exchange for some deference"}


def status(message: str) -> None:
    with STATUS.open("a") as f:
        f.write(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}] {message}\n")
    print(message, flush=True)


def tok(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.lower(), flags=re.UNICODE)


def word_token(text: str) -> str:
    return "".join(tok(text))


def live_args() -> SimpleNamespace:
    return SimpleNamespace(arm="w3", language_code="en", turn=0, sensitivity="high",
                           silence_ms=500, thinking=None, max_output=None,
                           tail_silence=2.0, limit=0.0, drain=12.0, quiet=True)


async def live_phase() -> None:
    cases = [("E1", FIXTURE / "E1-microphone.wav"),
             ("M2", FIXTURE / "M2-microphone.wav")]

    async def one(name: str, audio: Path) -> None:
        path = EVIDENCE / f"lane-live-{name}-mic.json"
        if path.exists():
            status(f"LANES W3 {name}: existing receipt reused {path}.")
            return
        d = await run_live(live_args(), Clip(f"lane-{name}-mic", "e1", audio, None))
        path.write_text(json.dumps(d, indent=2) + "\n")
        status(f"LANES W3 {name}: sent {d['sent_s']}/{d['audio_s']}s, "
               f"finals {d['selected_updates']}, visible updates {d['updates']}, "
               f"errors {d['errors']}, usage complete {d['cost_complete']}; {path}.")

    await asyncio.gather(*(one(*case) for case in cases))


def batch_phase() -> None:
    cases = [("system", FIXTURE / "system.wav", True),
             ("E1", FIXTURE / "E1-microphone.wav", False),
             ("M2", FIXTURE / "M2-microphone.wav", False)]
    ends = list(range(10, 301, 10)) + [302]
    for name, audio, diarize in cases:
        pcm = read_wav(audio)
        measured_costs = []
        new_costs = []
        anomalies = {"clamped": 0, "dropped": 0}
        anomaly_calls = 0
        cached = 0
        retained = 0
        for end_s in ends:
            start_s = max(0, end_s-30)
            path = EVIDENCE / f"lane-batch-{name}-{end_s:03}.json"
            if path.exists():
                d = json.loads(path.read_text())
                retained += 1
            else:
                result = diarize_window(pcm[start_s*RATE:end_s*RATE],
                                        diarize=diarize, word_timestamps=True,
                                        use_cache=True, ledger_lane="P52", max_attempts=3)
                d = {"lane": name, "start_s": start_s, "end_s": end_s,
                     "diarize": diarize, "cached": result.cached,
                     "words": [{"text": w.text, "speaker": w.speaker,
                                "start": start_s+w.start, "end": start_s+w.end}
                               for w in result.words],
                     "cost_usd": result.cost_usd(),
                     "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0}}
                path.write_text(json.dumps(d, indent=2) + "\n")
                new_costs.append(0 if d["cached"] else d["cost_usd"])
            measured_costs.append(0 if d["cached"] else d["cost_usd"])
            cached += int(d["cached"])
            for k in anomalies:
                anomalies[k] += d["timing_anomalies"][k]
            anomaly_calls += int(any(d["timing_anomalies"].values()))
        status(f"LANES batch {name}: {len(ends)} L30/S10 receipts, {retained} retained, "
               f"{cached} provider-cache hits, this-run cost ${sum(new_costs):.6f}, "
               f"measured uncached cost ${sum(measured_costs):.6f}, anomaly calls {anomaly_calls}/{len(ends)}, "
               f"anomalous words {anomalies}; "
               f"receipts lane-batch-{name}-*.json.")


def selected_words(lane: str) -> list[dict]:
    """One owner per 10 s strip; preserve Gemini word offsets and full raw receipts."""
    out = []
    previous_end = 0
    for end_s in list(range(10, 301, 10)) + [302]:
        d = json.loads((EVIDENCE / f"lane-batch-{lane}-{end_s:03}.json").read_text())
        for word in d["words"]:
            midpoint = (word["start"] + word["end"]) / 2
            if previous_end <= midpoint < end_s or (end_s == 302 and midpoint == 302):
                out.append(word)
        previous_end = end_s
    return sorted(out, key=lambda w: (w["start"], w["end"]))


def vad_voiced(pcm: np.ndarray) -> list[bool]:
    detector = webrtcvad.Vad(1)
    return [detector.is_speech(pcm[i:i+160].tobytes(), RATE)
            for i in range(0, len(pcm)-159, 160)]


def speech_supported(word: dict, voiced: list[bool]) -> bool:
    start = max(0, int((word["start"] - .2) * 100))
    end = min(len(voiced), int((word["end"] + .2) * 100) + 1)
    return any(voiced[start:end])


def one_edit(a: str, b: str) -> bool:
    if abs(len(a)-len(b)) > 1 or min(len(a), len(b)) < 4:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    i = j = errors = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            errors += 1
            j += 1
            if errors > 1:
                return False
    return True


def echoed(word: dict, system: list[dict], *, tolerance_s: float = 1.5,
           fuzzy: bool = False) -> bool:
    token = word_token(word["text"])
    midpoint = (word["start"] + word["end"]) / 2
    return bool(token and any((word_token(s["text"]) == token or
                               (fuzzy and one_edit(token, word_token(s["text"])))) and
                              abs((s["start"]+s["end"])/2 - midpoint) <= tolerance_s
                              for s in system))


def lcs(a: list[str], b: list[str]) -> int:
    prior = [0] * (len(b)+1)
    for x in a:
        current = [0]
        for j, y in enumerate(b, 1):
            current.append(prior[j-1]+1 if x == y else max(current[-1], prior[j]))
        prior = current
    return prior[-1]


def operator_recall(words: list[dict]) -> list[dict]:
    rows = []
    for at_s, phrase in OPERATORS.items():
        local = [w for w in words if at_s-.2 <= (w["start"]+w["end"])/2 <= at_s+3.2]
        reference = tok(phrase)
        matched = lcs(reference, [word_token(w["text"]) for w in local])
        rows.append({"at_s": at_s, "reference": phrase, "matched": matched,
                     "reference_words": len(reference), "recall": matched/len(reference),
                     "local_text": " ".join(w["text"] for w in local),
                     "local_words": local})
    return rows


def live_operator_visibility(receipt: dict) -> dict:
    updates = receipt["updates_full"]
    outcomes = []
    for at_s, phrase in OPERATORS.items():
        reference = tok(phrase)
        required = math.ceil(.7*len(reference))
        seen = []
        for u in updates:
            if not (at_s-1 <= u["audio_end_s"] <= at_s+40):
                continue
            matched = lcs(reference, tok(u["text"]))
            if matched >= required:
                seen.append({"kind": u["kind"], "wall_s": u["wall_s"],
                             "audio_end_s": u["audio_end_s"], "matched": matched,
                             "text": u["text"]})
        first = min(seen, key=lambda x: x["wall_s"]) if seen else None
        outcomes.append({"at_s": at_s, "required_words": required,
                         "first_70pct": first,
                         "latency_after_utterance_start_s": round(first["wall_s"]-at_s, 3) if first else None,
                         "latency_after_utterance_end_s": round(first["wall_s"]-(at_s+3), 3) if first else None})
    latencies = [u["latency_after_utterance_end_s"] for u in outcomes
                 if u["latency_after_utterance_end_s"] is not None]
    starts = [u["latency_after_utterance_start_s"] for u in outcomes
              if u["latency_after_utterance_start_s"] is not None]
    full = " ".join(u["text"] for u in receipt["hypothesis"])
    return {"final_words": len(tok(full)), "final_text": full,
            "operator_70pct_visible": sum(u["first_70pct"] is not None for u in outcomes),
            "operator_denominator": len(outcomes),
            "latency_after_start_p50_s": round(float(np.median(starts)), 3) if starts else None,
            "latency_after_end_p50_s": round(float(np.median(latencies)), 3) if latencies else None,
            "operators": outcomes}


def analyze_phase() -> dict:
    keyu = next(c for c in clips("gold9") if c.clip_id == "benchmark:lex_keyu_jin")
    keyu_pcm = read_wav(keyu.audio).astype(np.float64)
    keyu_text = " ".join(r["text"] for r in keyu.reference_segments()).lower()
    m2_pcm = read_wav(FIXTURE / "M2-microphone.wav").astype(np.float64)
    source_proof = []
    for at_s, source_s in ((30, 2), (135, 9), (248, 17)):
        mic = m2_pcm[at_s*RATE:(at_s+3)*RATE]
        source = keyu_pcm[source_s*RATE:(source_s+3)*RATE]
        source_proof.append({"at_s": at_s, "source_s": source_s,
                             "source_reference": str(keyu.reference),
                             "human_phrase_present": OPERATORS[at_s] in keyu_text,
                             "waveform_correlation": float(np.corrcoef(mic, source)[0, 1]),
                             "least_squares_gain": float(np.dot(mic, source)/np.dot(source, source))})
    system = selected_words("system")
    system_voiced = vad_voiced(read_wav(FIXTURE / "system.wav"))
    system_overlap = {str(at): {"voiced_frames": sum(system_voiced[at*100:(at+3)*100]),
                                "frames": 300} for at in OPERATORS}
    batch_costs = {}
    batch_anomalies = {}
    for lane in ("system", "E1", "M2"):
        calls = [json.loads((EVIDENCE / f"lane-batch-{lane}-{end_s:03}.json").read_text())
                 for end_s in list(range(10, 301, 10)) + [302]]
        cost = sum(d["cost_usd"] for d in calls if not d["cached"])
        batch_costs[lane] = {"measured_uncached_cost_usd": cost,
                             "measured_cost_per_meeting_hour_usd": cost/302*3600,
                             "window_audio_s": sum(d["end_s"]-d["start_s"] for d in calls),
                             "cached_calls": sum(d["cached"] for d in calls),
                             "calls": len(calls)}
        batch_anomalies[lane] = {"calls": sum(any(d["timing_anomalies"].values()) for d in calls),
                                 "clamped": sum(d["timing_anomalies"]["clamped"] for d in calls),
                                 "dropped": sum(d["timing_anomalies"]["dropped"] for d in calls)}
    results = {}
    for name in ("E1", "M2"):
        raw = selected_words(name)
        voiced = vad_voiced(read_wav(FIXTURE / f"{name}-microphone.wav"))
        inside_frames = [any(at*100 <= i < (at+3)*100 for at in OPERATORS)
                         for i in range(len(voiced))]
        outside_count = sum(not inside for inside in inside_frames)
        inside_count = len(voiced)-outside_count
        rows = [{**w, "speech_supported": speech_supported(w, voiced),
                 "echoed": echoed(w, system)} for w in raw]
        arms = {"raw": rows,
                "vad_only": [w for w in rows if w["speech_supported"]],
                "echo_only": [w for w in rows if not w["echoed"]],
                "guarded": [w for w in rows if w["speech_supported"] and not w["echoed"]]}
        alternatives = {
            "A1_exact_3s": [w for w in rows if w["speech_supported"] and
                            not echoed(w, system, tolerance_s=3.0)],
            "A2_one_edit_1p5s": [w for w in rows if w["speech_supported"] and
                                 not echoed(w, system, fuzzy=True)],
        }
        operators = {arm: operator_recall(words) for arm, words in arms.items()}
        outside = {arm: [w for w in words if not any(at <= (w["start"]+w["end"])/2 <= at+3
                                                     for at in OPERATORS)]
                   for arm, words in arms.items()}
        outside_tolerant = {arm: [w for w in words if not any(at-.2 <= (w["start"]+w["end"])/2 <= at+3.2
                                                              for at in OPERATORS)]
                            for arm, words in arms.items()}
        alternative_results = {}
        for arm, words in alternatives.items():
            out = [w for w in words if not any(at <= (w["start"]+w["end"])/2 <= at+3
                                                   for at in OPERATORS)]
            alternative_results[arm] = {"words": len(words), "outside_operator_words": len(out),
                                        "outside_operator_rate": len(out)/len(words) if words else 0,
                                        "operators": operator_recall(words)}
        results[name] = {"raw_words": len(rows),
                         "vad_signal": {"operator_voiced_frames": sum(v and inside for v, inside in zip(voiced, inside_frames)),
                                        "operator_frames": inside_count,
                                        "outside_voiced_frames": sum(v and not inside for v, inside in zip(voiced, inside_frames)),
                                        "outside_frames": outside_count},
                         "echoed_raw": sum(w["echoed"] for w in rows),
                         "vad_rejected": sum(not w["speech_supported"] for w in rows),
                         "arms": {arm: {"words": len(words),
                                        "echoed_remaining": sum(w["echoed"] for w in words),
                                        "echo_rate": sum(w["echoed"] for w in words)/len(words) if words else 0,
                                        "outside_operator_words": len(outside[arm]),
                                        "outside_operator_rate": len(outside[arm])/len(words) if words else 0,
                                        "outside_operator_words_tolerant": len(outside_tolerant[arm]),
                                        "outside_operator_text": " ".join(w["text"] for w in outside[arm]),
                                        "operators": operators[arm]}
                                  for arm, words in arms.items()},
                         "guard_alternatives": alternative_results,
                         "all_words": rows}
    live = {name: json.loads((EVIDENCE / f"lane-live-{name}-mic.json").read_text())
            for name in ("E1", "M2")}
    result = {"design": "separate W3 mic preview; L30/S10 batch word owner by trailing 10s strip; WebRTC mode1 gate + exact token echo guard ±1.5s",
              "source_proof": source_proof,
              "system_batch_words": len(system), "system_vad_during_operator": system_overlap,
              "cases": results,
              "batch_costs": batch_costs, "batch_timing_anomalies": batch_anomalies,
              "live": {name: live_operator_visibility(d) for name, d in live.items()},
              "live_receipts": {name: str(EVIDENCE / f"lane-live-{name}-mic.json") for name in live},
              "lane_spend": spend("P52")}
    path = EVIDENCE / "lane-analysis.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    for name, d in results.items():
        raw, guard = d["arms"]["raw"], d["arms"]["guarded"]
        status(f"LANES analyzed {name}: raw {raw['words']} words, echo {raw['echoed_remaining']} "
               f"({raw['echo_rate']:.1%}), guarded {guard['words']} words, residual echo "
               f"{guard['echoed_remaining']} by guard definition, independently outside operator "
               f"{guard['outside_operator_words']}/{guard['words']} "
               f"({guard['outside_operator_rate']:.1%}), operator recall "
               f"{[(x['matched'],x['reference_words']) for x in guard['operators']]}; {path}.")
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["all", "live", "batch", "analyze"], default="all")
    args = p.parse_args()
    if args.phase in ("all", "live"):
        asyncio.run(live_phase())
    if args.phase in ("all", "batch"):
        batch_phase()
    if args.phase in ("all", "analyze"):
        analyze_phase()


if __name__ == "__main__":
    main()
