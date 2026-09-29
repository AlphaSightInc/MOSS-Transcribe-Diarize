"""Compare one paced server trace against the retained exact-window cache trace."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

RATE = 16000


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def first(rows, condition):
    return next((row for row in rows if condition(row)), None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cached-events", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.integration.resolve()))
    from moss_transcribe_diarize.app.gemini_provider import parse_words, repair_word_timestamps
    rows = load(args.out / "server-trace.jsonl")
    baseline = load(args.cached_events)
    baseline_sha = next((r.get("source_sha") for r in baseline if r.get("kind") == "preflight"), None)
    live_sha = next((r.get("sha") for r in rows if r.get("event") == "source"), None)
    if not baseline_sha or baseline_sha != live_sha:
        raise RuntimeError(f"source SHA mismatch: live={live_sha}, cached={baseline_sha}")
    requests = [r for r in rows if r["event"] == "request" and r.get("lane") == "system"
                and r.get("kind") == "rolling"]
    responses = [r for r in rows if r["event"] == "response" and r.get("lane") == "system"
                 and r.get("kind") == "rolling"]
    mappings = [r for r in rows if r["event"] == "mapping" and r.get("lane") == "system"]
    cached_mappings = [r for r in baseline if r.get("kind") == "registry_result"
                       and r.get("lane") == "system"]
    cache = args.integration / "prototypes/gemini-live/.cache"
    first_labels = None
    for response in responses:
        key = response["cache_key"]
        path = cache / key[:2] / f"{key}.json"
        if not path.is_file():
            continue
        raw = json.loads(path.read_text())["response"]
        duration = response["end_sample"] - response["start_sample"]
        parsed = parse_words(raw, audio_samples=duration)
        words, _ = repair_word_timestamps(parsed.words, duration)
        labels = dict(Counter(word.speaker for word in words))
        if labels != response["labels"]:
            first_labels = {"start_sample": response["start_sample"],
                            "end_sample": response["end_sample"],
                            "fresh_labels": response["labels"], "cached_labels": labels,
                            "fresh_word_count": response["word_count"],
                            "cached_word_count": len(words)}
            break
    first_mapping = None
    first_target_change = None
    response_by_window = {(r["start_sample"], r["end_sample"]): r for r in responses}
    if len(cached_mappings) < len(mappings):
        raise RuntimeError("cached mapping trace is shorter than live trace")
    for live, cached in zip(mappings, cached_mappings):
        if round(cached["window_start_s"] * RATE) != live["start_sample"]:
            raise RuntimeError(f"cached mapping schedule differs at {live['start_sample']}")
        if live["mapping"] != cached["mapping"]:
            if first_mapping is None:
                first_mapping = {"start_sample": live["start_sample"],
                                 "end_sample": live["end_sample"],
                                 "fresh_mapping": live["mapping"],
                                 "cached_mapping": cached["mapping"],
                                 "fresh_word_count": live["word_count"],
                                 "cached_word_count": cached["words"]}
            common = set(live["mapping"]) & set(cached["mapping"])
            changed = {label: {"fresh": live["mapping"][label],
                               "cached": cached["mapping"][label]}
                       for label in sorted(common)
                       if live["mapping"][label] != cached["mapping"][label]}
            if first_target_change is None and (
                    changed or set(live["mapping"].values()) != set(cached["mapping"].values())):
                response = response_by_window.get((live["start_sample"], live["end_sample"]))
                first_target_change = {"start_sample": live["start_sample"],
                                       "end_sample": live["end_sample"],
                                       "fresh_mapping": live["mapping"],
                                       "cached_mapping": cached["mapping"],
                                       "changed_common_labels": changed,
                                       "fresh_word_count": live["word_count"],
                                       "cached_word_count": cached["words"],
                                       "words_equal_cache": response["words_equal_cache"] if response else None,
                                       "cache_key": response["cache_key"] if response else None}
    first_schedule = None
    for index, request in enumerate(requests, 1):
        expected_end = index * 15 * RATE
        expected_start = max(0, expected_end - 90 * RATE)
        if (request["start_sample"], request["end_sample"]) != (expected_start, expected_end):
            first_schedule = {"call": index, "expected": [expected_start, expected_end],
                              "actual": [request["start_sample"], request["end_sample"]]}
            break
    final_path = args.out / "final-snapshot.json"
    final = json.loads(final_path.read_text())["snapshot"] if final_path.is_file() else None
    summary = {"source_sha": live_sha,
               "cached_events": str(args.cached_events),
               "system_requests": len(requests),
               "cache_hits": sum(r["cache_hit"] for r in requests),
               "first_cache_miss": first(requests, lambda r: not r["cache_hit"]),
               "first_schedule_difference": first_schedule,
               "system_responses": len(responses),
               "word_exact_cache_matches": sum(r["words_equal_cache"] is True for r in responses),
               "first_word_difference": first(responses, lambda r: r["words_equal_cache"] is False),
               "first_label_distribution_difference": first_labels,
               "system_mappings": len(mappings),
               "first_mapping_difference": first_mapping,
               "first_canonical_target_change": first_target_change,
               "final_status": final["session"]["status"] if final else None,
               "finalization_status": final["session"]["finalization_status"] if final else None,
               "accepted_samples": final["session"]["accepted_samples"] if final else None,
               "cost_usd": (final.get("engine_diagnostics") or {}).get("cost_usd") if final else None}
    (args.out / "analysis.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
