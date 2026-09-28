"""Read retained P52 robustness receipts; no provider calls."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import webrtcvad

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from corpus import clips  # noqa: E402
from gemini_common import read_wav  # noqa: E402
from score import score  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
ACCEPT6 = ["discussion_jamie_dimon_180s", "discussion_rtfl_90s", "interview_adam_frank_180s",
           "interview_bill_ackman_60s", "interview_keyu_jin_60s", "mono_javier_intro_50s"]


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.lower(), flags=re.UNICODE)


def final_text(d: dict) -> str:
    return " ".join(row["text"] for row in d.get("hypothesis", []))


def receipt(case: str, language: str = "en-US") -> dict:
    return json.loads((EVIDENCE / f"robust-live-{case}-{language}.json").read_text())


def lcs_count(a: list[str], b: list[str]) -> int:
    prior = [0] * (len(b) + 1)
    for word in a:
        current = [0]
        for j, other in enumerate(b, 1):
            current.append(prior[j-1] + 1 if word == other else max(current[-1], prior[j]))
        prior = current
    return prior[-1]


def distinctive_bigram_recall(reference: list[str], other: list[str], hypothesis: list[str]) -> dict:
    a = Counter(zip(reference, reference[1:]))
    b = Counter(zip(other, other[1:]))
    h = Counter(zip(hypothesis, hypothesis[1:]))
    distinctive = a - b
    n = sum(distinctive.values())
    m = sum(min(k, h[phrase]) for phrase, k in distinctive.items())
    return {"matched": m, "reference": n, "fraction": m/n if n else None}


def duplicates(words: list[str]) -> dict:
    # A repeated four-word phrase that starts within 20 tokens of its previous occurrence.
    prior: dict[tuple[str, ...], int] = {}
    repeated = []
    for i in range(len(words)-3):
        phrase = tuple(words[i:i+4])
        if phrase in prior and i-prior[phrase] <= 20:
            repeated.append({"index": i, "phrase": " ".join(phrase), "distance_words": i-prior[phrase]})
        prior[phrase] = i
    return {"events": len(repeated), "opportunities": max(0, len(words)-3),
            "rate": len(repeated)/max(1, len(words)-3), "examples": repeated[:12]}


def nonspeech() -> dict:
    names = ["silence", "white_0.0003", "white_0.0010", "white_0.0030",
             "pink_0.0003", "pink_0.0010", "pink_0.0030", "music_like", "javier_gap20"]
    rows = []
    for name in names:
        for language in ("auto", "en-US"):
            d = receipt(name, language)
            full = final_text(d)
            final_tokens = tokens(full)
            interim = [u for u in d.get("updates_full", []) if u["kind"] == "interim_input_transcription"]
            interim_words = sorted({word for u in interim for word in tokens(u["text"])})
            central_gap_updates = ([u for u in d.get("updates_full", [])
                                    if 29 <= u["audio_end_s"] <= 42 and u["text"].strip()]
                                   if name == "javier_gap20" else [])
            row = {"case": name, "language": language, "source_s": d["source_audio_s"],
                   "sent_s": d["sent_s"], "final_word_units": len(final_tokens),
                   "final_words_per_source_min": len(final_tokens)/(d["source_audio_s"]/60),
                   "final_text": full, "foreign_script_final": bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", full)),
                   "interim_events": len(interim), "interim_any_text": bool(interim),
                   "interim_distinct_word_units": len(interim_words),
                   "interim_distinct_words_per_source_min": len(interim_words)/(d["source_audio_s"]/60),
                   "interim_texts": [u["text"] for u in interim],
                   "central_gap_update_texts": [u["text"] for u in central_gap_updates],
                   "errors": d["errors"]}
            if name == "javier_gap20":
                public = next(c for c in clips() if c.clip_id == "mono_javier_intro_50s")
                ref = [{**r, "start": r["start"]+(20 if r["start"] >= 25 else 0),
                        "end": r["end"]+(20 if r["end"] > 25 else 0), "speaker": "one"}
                       for r in public.reference_segments()]
                row["shifted_reference_wer"] = score(ref, d["hypothesis"])["wer"]
            rows.append(row)
    return {"cases": rows}


def accept6() -> dict:
    rows = []
    for name in ACCEPT6:
        for language in ("auto", "en-US"):
            d = receipt(name, language)
            rows.append({"case": name, "language": language, "wer": (d.get("score") or {}).get("wer"),
                         "source_s": d["source_audio_s"], "sent_s": d["sent_s"],
                         "final_words": len(tokens(final_text(d))), "errors": d["errors"]})
    return {"reference_set": "H1 #3 manifest-matching accept6, corpus.py a9634449",
            "cases": rows, "macro_wer": {lang: sum(r["wer"] for r in rows if r["language"] == lang)/6
                                         for lang in ("auto", "en-US")}}


def overlap() -> dict:
    c = {x.clip_id: x for x in clips("gold9")}
    a = tokens(" ".join(r["text"] for r in c["benchmark:lex_bill_ackman"].reference_segments()))
    b = tokens(" ".join(r["text"] for r in c["benchmark:lex_keyu_jin"].reference_segments()))
    rows = []
    for name in ("overlap_keyu_equal", "overlap_keyu_minus10"):
        live = receipt(name)
        batch = json.loads((EVIDENCE / f"robust-batch-{name}.json").read_text())
        for method, words, errors in (("W3 Live", tokens(final_text(live)), live["errors"]),
                                      ("batch", tokens(" ".join(w["text"] for w in batch["words"])), [])):
            rows.append({"case": name, "method": method, "output_words": len(words),
                         "bill_lcs": {"matched": lcs_count(a, words), "reference": len(a),
                                      "fraction": lcs_count(a, words)/len(a)},
                         "keyu_lcs": {"matched": lcs_count(b, words), "reference": len(b),
                                      "fraction": lcs_count(b, words)/len(b)},
                         "bill_distinctive_bigram": distinctive_bigram_recall(a, b, words),
                         "keyu_distinctive_bigram": distinctive_bigram_recall(b, a, words),
                         "timing_anomalies": batch["timing_anomalies"] if method == "batch" else None,
                         "errors": errors})
    for variant in ("language_en-US", "no_diarization"):
        batch = json.loads((EVIDENCE / f"robust-batch-overlap_keyu_minus10-{variant}.json").read_text())
        words = tokens(" ".join(w["text"] for w in batch["words"]))
        rows.append({"case": "overlap_keyu_minus10", "method": f"batch {variant}",
                     "output_words": len(words),
                     "bill_lcs": {"matched": lcs_count(a, words), "reference": len(a),
                                  "fraction": lcs_count(a, words)/len(a)},
                     "keyu_lcs": {"matched": lcs_count(b, words), "reference": len(b),
                                  "fraction": lcs_count(b, words)/len(b)},
                     "bill_distinctive_bigram": distinctive_bigram_recall(a, b, words),
                     "keyu_distinctive_bigram": distinctive_bigram_recall(b, a, words),
                     "timing_anomalies": batch["timing_anomalies"], "errors": []})
    rolling = []
    for name in ("overlap_keyu_equal", "overlap_keyu_minus10"):
        windows = [json.loads((EVIDENCE / f"robust-rolling-{name}-{end_s-30}-{end_s}.json").read_text())
                   for end_s in (30, 40, 50, 60)]
        by_window = [tokens(" ".join(w["text"] for w in window["words"])) for window in windows]
        max_bigrams: Counter = Counter()
        for words in by_window:
            for phrase, count in Counter(zip(words, words[1:])).items():
                max_bigrams[phrase] = max(max_bigrams[phrase], count)
        matches = {}
        for label, ref, other in (("bill", a, b), ("keyu", b, a)):
            distinct = Counter(zip(ref, ref[1:])) - Counter(zip(other, other[1:]))
            n = sum(distinct.values())
            m = sum(min(count, max_bigrams[phrase]) for phrase, count in distinct.items())
            matches[label] = {"matched": m, "reference": n, "fraction": m/n if n else None}
        rolling.append({"case": name, "method": "30s/10s rolling optimistic union",
                        "windows": len(windows), "bill_distinctive_bigram": matches["bill"],
                        "keyu_distinctive_bigram": matches["keyu"],
                        "timing_anomalies_per_call": [w["timing_anomalies"] for w in windows]})
    return {"reference_set": "gold9 complete benchmark lex Bill+Keyu 60s", "cases": rows,
            "rolling_union": rolling}


def e1() -> dict:
    system = receipt("e1_system")
    mixed = receipt("e1_mixed")
    gap = receipt("e1_gap20")
    rows = []
    for name, d in (("system", system), ("mixed", mixed)):
        word_list = tokens(final_text(d))
        rows.append({"case": name, "words": len(word_list),
                     "words_per_source_min": len(word_list)/(d["source_audio_s"]/60),
                     "duplicate_4gram": duplicates(word_list), "errors": d["errors"]})
    utterances = []
    # The synthetic operator voice is drawn from the public Keyu clip at source 2/9/17 s.
    # These phrases occur verbatim in its complete human transcript; the 3 s slice boundaries
    # are fixture metadata rather than independent word timing.
    human_phrases = {30: "they think that they're responsible for you",
                     135: "deference to authority is not blind submission",
                     248: "in exchange for some deference"}
    keyu = next(c for c in clips("gold9") if c.clip_id == "benchmark:lex_keyu_jin")
    keyu_text = " ".join(r["text"] for r in keyu.reference_segments()).lower()
    for at_s in (30, 135, 248):
        if human_phrases[at_s] not in keyu_text:
            raise ValueError("operator phrase absent from Keyu human reference")
        oracle = json.loads((EVIDENCE / f"robust-e1-operator-{at_s}.json").read_text())
        expected = tokens(oracle["text"])
        human = tokens(human_phrases[at_s])
        both = []
        for name, d in (("system", system), ("mixed", mixed)):
            chunks = [u for u in d["hypothesis"] if at_s-4 <= u["end"] <= at_s+10]
            nearby = tokens(" ".join(u["text"] for u in chunks))
            visible = [u for u in d["updates_full"] if at_s-1 <= u["audio_end_s"] <= at_s+8]
            visible_texts = [u["text"] for u in visible]
            visible_tokens = tokens(" ".join(visible_texts))
            whole = tokens(final_text(d))
            both.append({"case": name, "nearby_text": " ".join(u["text"] for u in chunks),
                         "nearby_words": len(nearby), "oracle_lcs": lcs_count(expected, nearby),
                         "oracle_words": len(expected),
                         "oracle_bigram_nearby": distinctive_bigram_recall(expected, [], nearby),
                         "oracle_bigram_whole": distinctive_bigram_recall(expected, [], whole),
                         "visible_update_count_nearby": len(visible),
                         "visible_bigram_nearby": distinctive_bigram_recall(expected, [], visible_tokens),
                         "visible_texts_nearby": visible_texts,
                         "human_phrase_bigram_whole": distinctive_bigram_recall(human, [], whole),
                         "human_phrase_bigram_nearby": distinctive_bigram_recall(human, [], nearby),
                         "final_event_ends_with_phrase": [u["end"] for u in d["hypothesis"]
                                                          if distinctive_bigram_recall(human, [], tokens(u["text"]))["matched"] >= 2]})
        utterances.append({"at_s": at_s, "human_source_phrase": human_phrases[at_s],
                           "human_source": str(keyu.reference),
                           "model_only_oracle": oracle["text"],
                           "oracle_timing_anomalies": oracle["timing_anomalies"], "nearby": both})
    gap_updates = [u for u in gap["updates_full"] if 24 <= u["audio_end_s"] <= 36 and u["text"].strip()]
    quiet = {}
    for name, path in (("system", next(c for c in clips() if c.clip_id == "e1").audio),
                       ("mixed", EVIDENCE / "robust_audio/e1_mixed.wav")):
        pcm = read_wav(path)
        vad = webrtcvad.Vad(1)
        unvoiced = [not vad.is_speech(pcm[i:i+160].tobytes(), 16000)
                    for i in range(0, len(pcm)-159, 160)]
        runs = []
        length = 0
        for low in unvoiced + [False]:
            if low:
                length += 1
            elif length:
                runs.append(length)
                length = 0
        quiet[name] = {"vad": "WebRTC mode 1, 10ms frames",
                       "unvoiced_fraction": sum(unvoiced)/len(unvoiced),
                       "longest_unvoiced_s": max(runs, default=0)/100,
                       "stretches_at_least_2s": sum(n >= 200 for n in runs)}
    return {"fixture": "public E1 system+microphone, 302s, no human transcript",
            "cases": rows, "utterances": utterances,
            "natural_quiet": quiet,
            "derived_gap20": {"source": "mixed E1 180-220s with 20s digital zero inserted at 20-40s",
                              "central_gap_updates": [u["text"] for u in gap_updates],
                              "final_text": final_text(gap), "errors": gap["errors"]}}


def main() -> None:
    result = {"nonspeech": nonspeech(), "accept6": accept6(), "e1": e1(), "overlap": overlap()}
    path = EVIDENCE / "robust-analysis.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
