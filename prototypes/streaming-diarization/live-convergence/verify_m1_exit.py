"""Score the M1 (plan E1) exit gates on two fresh paired passes of the deployed service.

The gates, the aggregation and the comparators are fixed in
`evidence/live-convergence-0824/M1-salvage-production/PREREGISTRATION.md`, written before any
measurement pass. Nothing here may be re-decided after a number is seen.

  G-M1-1  trio live WER mean <= .190                    (projection .1885)
  G-M1-2  no per-case live WER regression               (baseline live .2614/.1440/.1942)
  G-M1-3  file mode byte-identical                      (checked-in 2026-08-24 baseline)
  G-M1-4  zero extra MOSS requests                      (canonical_processed per case == M0d)
  G-M1-5  no refusal boilerplate, no digital-silence words published
  G-M1-6  identity preparation receives only salvager-emitted intervals

G-M1-5 and G-M1-6 are read out of the replay traces plus the published transcripts, not
asserted: a span's freeze reason, its salvage disposition and every second it published are
all in the artifacts. The refusal corpus G-M1-5 searches for is loaded from the measurement
data (`prototypes/live-file-gap-emptyspan/out/d3.json`), never written here as literals.

Usage:
  python verify_m1_exit.py --fresh-root /tmp/m1-exit-<stamp> [--output out.json]

Exit 0 iff every gate passes.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_span_bounds import classify_live_transcript  # noqa: E402

BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824"
M0D = REPO / "evidence/live-convergence-0824/M0d-paired-reacquisition"
M0E_TRACE = REPO / "evidence/live-convergence-0824/M0e-trace-completeness/run-5m/trace.jsonl.gz"
EMPTYSPAN_CORPUS = REPO / "prototypes/live-file-gap-emptyspan/out/d3.json"
SAMPLE_RATE = 16000

# Preregistered, from the PRD. Not tunable here.
TRIO_WER_BOUND = 0.190
# The PRD writes the per-case comparators to 4 dp (.2614 / .1440 / .1942). They are read here
# from the artifact those digits were rounded from, so an unchanged case compares equal
# instead of losing to its own rounding -- `lex_keyu_jin` is .194245, and .194245 > .1942.
PRD_BASELINE_LIVE_WER_4DP = {"lex_bill_ackman": 0.2614, "lex_javier_milei": 0.1440, "lex_keyu_jin": 0.1942}
RUNS = ("A", "B")


def baseline_live_wer() -> dict[str, float]:
    data = json.loads((BASELINE / "trio-60s/results.json").read_text())
    measured = {
        case["case_id"]: case["arms"]["live"]["scores"]["tbsa"]["wer"]
        for case in data["cases"]
        if case["tier"] == "primary"
    }
    for case, stated in PRD_BASELINE_LIVE_WER_4DP.items():
        if round(measured[case], 4) != stated:
            raise SystemExit(
                f"baseline artifact disagrees with the PRD comparator for {case}: "
                f"{measured[case]} does not round to {stated}"
            )
    return measured


def sha256_bytes(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def normalise_words(text: str) -> list[str]:
    """Words only -- the surface a gate about *published words* has to compare on."""
    return re.findall(r"[^\W_]+", (text or "").lower(), flags=re.UNICODE)


def trace_lines(trace: Path):
    if not trace.exists():
        return []
    if trace.suffix == ".gz":
        with gzip.open(trace, "rt") as handle:
            return handle.read().splitlines()
    return trace.read_text().splitlines()


def trace_spans(trace: Path) -> dict[int, dict]:
    """Per span: its freeze bounds+reason and the decode disposition that followed."""
    spans: dict[int, dict] = {}
    for line in trace_lines(trace):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") != "service_event":
            continue
        event = entry.get("event") or {}
        payload = event.get("payload") or {}
        span_id = payload.get("span_id")
        if span_id is None:
            continue
        node = spans.setdefault(int(span_id), {"span_id": int(span_id)})
        if event.get("kind") == "span_frozen":
            node["frozen"] = True
            node["bounds_from"] = "span_frozen"
            node["start_sample"] = payload.get("start_sample")
            node["end_sample"] = payload.get("end_sample")
            node["reason"] = payload.get("reason")
        elif event.get("kind") == "canonical_processed":
            node["decoded"] = True
            # The last span of a meeting is flushed on stop and its `span_frozen` event is not
            # in the trace. It is still placeable: `canonical_processed` carries the committed
            # sample count and the span's own length, which are its two bounds.
            node.setdefault("start_sample", None)
            if node["start_sample"] is None and payload.get("committed_samples") is not None:
                node["end_sample"] = int(payload["committed_samples"])
                node["start_sample"] = node["end_sample"] - int(payload.get("frozen_span_sample_count") or 0)
                node["bounds_from"] = "canonical_processed"
            node["salvage"] = payload.get("canonical_decode_salvage")
            node["salvage_field_present"] = "canonical_decode_salvage" in payload
            node["empty_reason"] = payload.get("empty_reason")
            node["identity_status"] = payload.get("identity_status")
            node["generated_tokens"] = payload.get("canonical_decode_generated_tokens")
    for node in spans.values():
        if node.get("start_sample") is not None:
            node["start_sec"] = round(node["start_sample"] / SAMPLE_RATE, 6)
            node["end_sec"] = round(node["end_sample"] / SAMPLE_RATE, 6)
    return spans


def decode_corpus() -> dict[tuple[str, int], dict]:
    """The saved zero-parse decodes, keyed by the span they came from.

    The words are read from the measurement data, never written down here: a table of the
    decoder's apologies in this file would be exactly the locale-specific literal the shipped
    module deliberately does not carry.
    """
    if not EMPTYSPAN_CORPUS.exists():
        return {}
    corpus: dict[tuple[str, int], dict] = {}
    for row in json.loads(EMPTYSPAN_CORPUS.read_text()).get("raw") or []:
        if not row.get("live_would_be_empty"):
            continue
        words = normalise_words(re.sub(r"\[[^\]]*\]", " ", row.get("raw_text") or ""))
        if not words:
            continue
        corpus[(row.get("case"), int(row.get("span_id")))] = {
            "case": row.get("case"),
            "span_id": int(row.get("span_id")),
            "raw_text": row.get("raw_text"),
            "words": words,
        }
    return corpus


def contains_subsequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


def salvaged_intervals(case: str, span: dict) -> list[tuple[float, float, str]] | None:
    """Re-derive what the classifier emitted for a salvaged span, from the saved decode.

    Returns None when this span's raw decode is not in the corpus, in which case the
    intervals cannot be reproduced and the caller says so instead of guessing.
    """
    if not EMPTYSPAN_CORPUS.exists():
        return None
    raw = json.loads(EMPTYSPAN_CORPUS.read_text()).get("raw") or []
    for row in raw:
        if row.get("case") != case or int(row.get("span_id", -1)) != span["span_id"]:
            continue
        outcome = classify_live_transcript(
            row.get("raw_text") or "",
            sample_count=int(span["end_sample"]) - int(span["start_sample"]),
            freeze_reason=span.get("reason") or "",
        )
        if not outcome.publishes:
            return []
        offset = span["start_sample"] / SAMPLE_RATE
        return [
            (round(seg.start + offset, 2), round(seg.end + offset, 2), seg.speaker)
            for seg in outcome.segments
        ]
    return None


def collect(fresh_root: Path) -> dict:
    baseline_results = json.loads((BASELINE / "trio-60s/results.json").read_text())
    trio_cases = [c["case_id"] for c in baseline_results["cases"] if c["tier"] == "primary"]
    all_trio_cases = [c["case_id"] for c in baseline_results["cases"]]

    report: dict = {"trio_cases": trio_cases, "all_trio_cases": all_trio_cases, "passes": {}}
    for run in RUNS:
        trio = fresh_root / f"trio-{run}"
        node: dict = {"cases": {}}
        results_path = trio / "results.json"
        if results_path.exists():
            data = json.loads(results_path.read_text())
            node["provenance"] = data["provenance"]
            for case in data["cases"]:
                node["cases"][case["case_id"]] = {
                    "tier": case["tier"],
                    "live_wer": case["arms"]["live"]["scores"]["tbsa"]["wer"],
                    "file_wer": case["arms"]["file"]["scores"]["tbsa"]["wer"],
                    "live_der": case["arms"]["live"]["scores"]["diarization"]["der"],
                    "live_segments": case["arms"]["live"]["meta"].get("hyp_segments"),
                }
        for case in all_trio_cases:
            case_node = node["cases"].setdefault(case, {})
            case_node["file_sha256"] = sha256_bytes(trio / case / "file-hypothesis.jsonl")
            case_node["live_rows"] = rows(trio / case / "live-hypothesis.jsonl")
            case_node["spans"] = trace_spans(trio / case / "live/run-001/trace.jsonl")
        report["passes"][f"trio-{run}"] = node

        five = fresh_root / f"keyu5m-{run}"
        five_node: dict = {"cases": {}}
        five_results = five / "results.json"
        if five_results.exists():
            data = json.loads(five_results.read_text())
            five_node["cases"]["keyu-5m"] = {
                "tier": "five_minute",
                "live_wer": data["results"]["live"]["scores"]["tbsa"]["wer"],
                "file_wer": data["results"]["file"]["scores"]["tbsa"]["wer"],
                "live_der": data["results"]["live"]["scores"]["diarization"]["der"],
                "live_segments": data["results"]["live"]["meta"].get("hyp_segments"),
            }
        case_node = five_node["cases"].setdefault("keyu-5m", {})
        case_node["file_sha256"] = sha256_bytes(five / "file-hypothesis.jsonl")
        case_node["live_rows"] = rows(five / "live-hypothesis.jsonl")
        case_node["spans"] = trace_spans(five / "live/run-001/trace.jsonl")
        report["passes"][f"keyu5m-{run}"] = five_node
    return report


def pass_for(report: dict, case: str, run: str) -> dict:
    key = f"keyu5m-{run}" if case == "keyu-5m" else f"trio-{run}"
    return report["passes"].get(key, {}).get("cases", {}).get(case, {})


def evaluate(report: dict) -> dict:
    trio_cases = report["trio_cases"]
    scored_cases = trio_cases + ["keyu-5m"]
    gates: dict[str, dict] = {}

    # --- means (aggregation fixed by the preregistration: mean of the two passes) ---
    means: dict[str, dict] = {}
    for case in scored_cases:
        wers = [pass_for(report, case, run).get("live_wer") for run in RUNS]
        ders = [pass_for(report, case, run).get("live_der") for run in RUNS]
        if any(w is None for w in wers):
            means[case] = {"live_wer_mean": None, "per_pass": wers}
            continue
        means[case] = {
            "live_wer_mean": round(sum(wers) / len(wers), 6),
            "live_wer_per_pass": [round(w, 6) for w in wers],
            "live_der_mean": None if any(d is None for d in ders) else round(sum(ders) / len(ders), 6),
            "live_der_per_pass": [None if d is None else round(d, 6) for d in ders],
        }
    trio_means = [means[c]["live_wer_mean"] for c in trio_cases]
    trio_mean = None if any(m is None for m in trio_means) else round(sum(trio_means) / len(trio_means), 6)

    gates["G_M1_1_trio_live_wer_bound"] = {
        "pass": trio_mean is not None and trio_mean <= TRIO_WER_BOUND,
        "trio_live_wer_mean": trio_mean,
        "bound": TRIO_WER_BOUND,
        "projection": 0.1885,
        "per_case": {c: means[c] for c in trio_cases},
    }

    comparators = baseline_live_wer()
    per_case_regression = {}
    for case in trio_cases:
        mean = means[case]["live_wer_mean"]
        base = comparators[case]
        per_case_regression[case] = {
            "baseline_live_wer": base,
            "prd_states": PRD_BASELINE_LIVE_WER_4DP[case],
            "measured_mean": mean,
            "delta": None if mean is None else round(mean - base, 6),
            "no_regression": mean is not None and mean <= base,
        }
    gates["G_M1_2_no_per_case_regression"] = {
        "pass": all(v["no_regression"] for v in per_case_regression.values()),
        "per_case": per_case_regression,
    }

    # --- G-M1-3 file mode byte-identical to the checked-in baseline ---
    g3: dict[str, dict] = {}
    for case in report["all_trio_cases"]:
        base = sha256_bytes(BASELINE / "trio-60s" / case / "file-hypothesis.jsonl")
        node = {"baseline_sha256": base}
        for run in RUNS:
            node[run] = pass_for(report, case, run).get("file_sha256")
        node["identical"] = base is not None and all(node[run] == base for run in RUNS)
        g3[case] = node
    base5 = sha256_bytes(BASELINE / "keyu-5m/file-hypothesis.jsonl")
    node5 = {"baseline_sha256": base5}
    for run in RUNS:
        node5[run] = pass_for(report, "keyu-5m", run).get("file_sha256")
    node5["identical"] = base5 is not None and all(node5[run] == base5 for run in RUNS)
    g3["keyu-5m"] = node5
    gates["G_M1_3_file_mode_byte_identical"] = {
        "pass": all(v["identical"] for v in g3.values()),
        "per_case": g3,
    }

    # --- G-M1-4 decode count per case unchanged: one decode request per processed span ---
    m0d = json.loads((M0D / "gates.json").read_text())
    expected_counts = {
        key.split("/")[0]: value["canonical_processed"]
        for key, value in m0d["gates"]["G4_service_runs_campaign_code"]["per_run"].items()
    }
    # M0d read the 5-minute count off a trace the replay client had silently truncated (the F3
    # defect, fixed in iteration 5), so its 115 is an artifact of the instrument, not a decode
    # count. The comparator is the first complete 5-minute trace, from M0e.
    m0d_five_minute_truncated = expected_counts.get("keyu-5m")
    expected_counts["keyu-5m"] = sum(
        1 for span in trace_spans(M0E_TRACE).values() if span.get("decoded")
    )
    g4: dict[str, dict] = {}
    for case in report["all_trio_cases"] + ["keyu-5m"]:
        expected = expected_counts.get(case)
        node = {"comparator_decodes": expected}
        for run in RUNS:
            node[run] = sum(
                1 for span in (pass_for(report, case, run).get("spans") or {}).values() if span.get("decoded")
            )
        node["equal"] = expected is not None and all(node[run] == expected for run in RUNS)
        g4[case] = node
    gates["G_M1_4_zero_extra_moss_requests"] = {
        "pass": all(v["equal"] for v in g4.values()),
        "note": "one decode request per span; the count is the trace's canonical_processed events",
        "comparator": "M0d passes; keyu-5m from the M0e complete trace",
        "m0d_five_minute_count_from_truncated_trace": m0d_five_minute_truncated,
        "per_case": g4,
    }

    # --- G-M1-5 a refused span publishes nothing; a salvaged one publishes its own words ---
    #
    # Anchored to the span, not to the whole transcript: the corpus holds a one-word decode
    # (`[0.00][S01]And.`), and "and" appearing somewhere in a minute of speech says nothing
    # about whether that span published. What the gate actually claims is that the span the
    # classifier refused contributed no seconds and no words, and that is exactly checkable.
    # The salvaged spans are the positive control -- their corpus words must be found, or the
    # search is not looking at anything.
    corpus = decode_corpus()
    missing_salvaged_words: list[dict] = []
    refused_publishing: list[dict] = []
    silence_salvages: list[dict] = []
    salvage_field_missing: list[str] = []
    unplaceable_spans: list[str] = []
    disposition_counts: dict[str, int] = {}
    salvaged_controls = 0
    for case in report["all_trio_cases"] + ["keyu-5m"]:
        for run in RUNS:
            node = pass_for(report, case, run)
            spans = node.get("spans") or {}
            published = node.get("live_rows") or []
            all_words = normalise_words(" ".join(row.get("text") or "" for row in published))
            for span in spans.values():
                disposition = span.get("salvage")
                key = disposition or ("none" if span.get("salvage_field_present") else "field_absent")
                disposition_counts[key] = disposition_counts.get(key, 0) + 1
                if not span.get("salvage_field_present"):
                    salvage_field_missing.append(f"{case}/{run}#{span['span_id']}")
                if span.get("start_sec") is None:
                    unplaceable_spans.append(f"{case}/{run}#{span['span_id']}")
                    continue
                if disposition == "salvaged" and span.get("reason") != "hard_cap":
                    silence_salvages.append({"case": case, "run": run, "span": span})
                if disposition and disposition.startswith("refused"):
                    inside = [
                        row
                        for row in published
                        if row.get("start", 0) >= span["start_sec"] - 1e-6
                        and row.get("end", 0) <= span["end_sec"] + 1e-6
                    ]
                    if inside:
                        refused_publishing.append(
                            {"case": case, "run": run, "span_id": span["span_id"], "rows": inside}
                        )
                entry = corpus.get((case, span["span_id"]))
                if entry is not None and disposition == "salvaged":
                    salvaged_controls += 1
                    if not contains_subsequence(all_words, entry["words"]):
                        missing_salvaged_words.append(
                            {"case": case, "run": run, "span_id": span["span_id"], "words": entry["words"]}
                        )
    gates["G_M1_5_no_refused_words_published"] = {
        "pass": not refused_publishing
        and not missing_salvaged_words
        and not silence_salvages
        and not salvage_field_missing
        and not unplaceable_spans
        and salvaged_controls > 0,
        "refused_span_published_rows": refused_publishing,
        "salvaged_spans_whose_corpus_words_are_missing": missing_salvaged_words,
        "salvage_on_non_hard_cap_freeze": silence_salvages,
        "spans_missing_salvage_field": salvage_field_missing[:10],
        "spans_without_bounds": unplaceable_spans[:10],
        "positive_control_salvaged_spans_found": salvaged_controls,
        "disposition_histogram": disposition_counts,
    }

    # --- G-M1-6 identity saw exactly the salvager's intervals ---
    checks: list[dict] = []
    for case in report["all_trio_cases"] + ["keyu-5m"]:
        for run in RUNS:
            node = pass_for(report, case, run)
            published = node.get("live_rows") or []
            for span in (node.get("spans") or {}).values():
                if span.get("salvage") != "salvaged":
                    continue
                emitted = salvaged_intervals(case, span)
                observed = [
                    (round(row["start"], 2), round(row["end"], 2), row.get("speaker"))
                    for row in published
                    if row.get("start", 0) >= span["start_sec"] - 1e-6
                    and row.get("end", 0) <= span["end_sec"] + 1e-6
                ]
                within = all(
                    span["start_sec"] - 1e-6 <= start and end <= span["end_sec"] + 1e-6
                    for start, end, _ in observed
                )
                checks.append(
                    {
                        "case": case,
                        "run": run,
                        "span_id": span["span_id"],
                        "freeze_reason": span.get("reason"),
                        "identity_status": span.get("identity_status"),
                        "classifier_intervals": emitted,
                        "published_intervals": observed,
                        "reproducible": emitted is not None,
                        "intervals_match": emitted is not None
                        and [(s, e) for s, e, _ in emitted] == [(s, e) for s, e, _ in observed],
                        "within_span_bounds": within,
                        "identity_prepared": span.get("identity_status") == "prepared",
                    }
                )
    reproducible = [c for c in checks if c["reproducible"]]
    gates["G_M1_6_identity_sees_only_salvaged_intervals"] = {
        "pass": bool(checks)
        and all(c["within_span_bounds"] and c["identity_prepared"] for c in checks)
        and all(c["intervals_match"] for c in reproducible),
        "salvaged_spans": len(checks),
        "reproducible_from_corpus": len(reproducible),
        "note": (
            "identity_preparer.prepare() is handed the published transcript text, so the "
            "intervals it parses are exactly the ones published for the span; a salvaged "
            "span whose raw decode is in the corpus is additionally re-derived here"
        ),
        "checks": checks,
    }
    gates["_five_minute_report_only"] = {
        "pass": True,
        "note": "reported, not gated (PREREGISTRATION: no prediction for the 5-minute case)",
        "keyu-5m": means.get("keyu-5m"),
    }
    return gates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = collect(args.fresh_root.resolve())
    gates = evaluate(report)
    slim = {
        name: {k: v for k, v in gate.items() if k != "checks"} if name.startswith("G_M1_6") else gate
        for name, gate in gates.items()
    }
    if args.output:
        args.output.write_text(
            json.dumps(
                {"fresh_root": str(args.fresh_root.resolve()), "gates": gates},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    ok = True
    for name, gate in slim.items():
        if name.startswith("_"):
            continue
        ok = ok and gate["pass"]
        print(f"[{'PASS' if gate['pass'] else 'FAIL'}] {name}")
        for line in json.dumps({k: v for k, v in gate.items() if k != "pass"}, indent=2).splitlines():
            print("    " + line)
    print("\n-- reported, not gated --")
    print(json.dumps(gates["_five_minute_report_only"], indent=2))
    print("\nALL GATES PASS" if ok else "\nGATE FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
