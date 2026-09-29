"""Read round-2 receipts and emit one Q-LIVE..Q-UI/cost scorecard; no provider calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/report"))
from scorecard import passage_missing_seconds
from latency_probe import percentile


def read(path: Path | None):
    return json.loads(path.read_text(encoding="utf-8")) if path and path.is_file() else None


def check(value, bound, op, *, denominator=None, source=None):
    if value is None:
        status = "UNMEASURED"
    else:
        status = "PASS" if (value <= bound if op == "<=" else value >= bound) else "FAIL"
    return {"status": status, "value": value, "bound": bound, "operator": op,
            "denominator": denominator, "source": str(source) if source else None}


def combined(items):
    values = [item["status"] for item in items]
    return "FAIL" if "FAIL" in values else "PASS" if values and all(v == "PASS" for v in values) else "UNMEASURED"


IND_CASES = {
    "mono_javier_intro_50s", "interview_bill_ackman_60s", "interview_keyu_jin_60s",
    "interview_adam_frank_180s", "discussion_jamie_dimon_180s", "discussion_rtfl_90s",
    "benchmark_5m:lex_bill_ackman", "benchmark_5m:lex_javier_milei", "benchmark_5m:lex_keyu_jin",
    "benchmark_30m:lex_bill_ackman", "long60", "calibration:acquired_jamie_dimon_3min",
    "calibration:lex_adam_frank", "calibration:lex_shapiro_destiny",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality", type=Path)
    parser.add_argument("--long60", type=Path)
    parser.add_argument("--e1", type=Path)
    parser.add_argument("--ind", type=Path)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--live-voiceprint", type=Path)
    parser.add_argument("--mic", type=Path)
    parser.add_argument("--summary", type=Path, action="append", default=[])
    parser.add_argument("--ui", type=Path)
    parser.add_argument("--spend", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("--out must be new")
    args.out.mkdir(parents=True)

    qpath = args.quality / "content-free-metrics.json" if args.quality else None
    quality = read(qpath)
    cases = quality.get("per_case", []) if quality else []
    expected = {("mono_javier_intro_50s", 1), ("mono_javier_intro_50s", 2),
                ("interview_bill_ackman_60s", 1), ("interview_bill_ackman_60s", 2),
                ("interview_keyu_jin_60s", 1), ("interview_keyu_jin_60s", 2),
                ("interview_adam_frank_180s", 1), ("interview_adam_frank_180s", 2),
                ("discussion_jamie_dimon_180s", 1), ("discussion_jamie_dimon_180s", 2),
                ("discussion_rtfl_90s", 1), ("discussion_rtfl_90s", 2)}
    manifests = sorted(args.quality.glob("pass-*/*/replay-manifest.json")) if args.quality else []
    providers = [(read(path).get("descriptor") or {}).get("provider_name") for path in manifests]
    diagnostics_path = args.quality / "engine-diagnostics.json" if args.quality else None
    diagnostics = read(diagnostics_path)
    settings = [row.get("engine_settings") for row in (diagnostics or {}).get("cases", [])]
    complete_h1 = ({(row.get("case_id"), row.get("pass")) for row in cases} == expected
                   and len(cases) == 12 and len(providers) == 12
                   and all(isinstance(name, str) and "gemini" in name.lower() for name in providers)
                   and len(settings) == 12
                   and all(value == {"speaker_window": "balanced", "cleanup_after_stop": False}
                           for value in settings))
    settled = mean(row["metrics"]["settled"]["der"] for row in cases) if complete_h1 else None
    timed = read(args.quality / "h1-timed-segments.json") if args.quality else None
    missing = None
    unattributed_s = speech_s = longest_unattributed_s = None
    if complete_h1 and timed and len(timed.get("cases", [])) == 12:
        missing = 0
        unattributed_s = speech_s = longest_unattributed_s = 0.0
        for item in timed["cases"]:
            final = item["surfaces"]["post_stop_final"]
            _, gaps = passage_missing_seconds(item["reference"], final)
            missing += len(gaps)
            for row in final:
                if not str(row.get("text", "")).strip():
                    continue
                seconds = max(0.0, float(row["end"]) - float(row["start"]))
                speech_s += seconds
                if row.get("speaker") in {None, "S00", "Speaker TBD"}:
                    unattributed_s += seconds
                    longest_unattributed_s = max(longest_unattributed_s, seconds)
    long60 = read(args.long60)
    e1 = read(args.e1)
    qlive = {
        "accept6_settled_der": check(settled, .110, "<=", denominator="12 case-passes", source=qpath),
        "e1_labels_at_stop": check((e1 or {}).get("visual_metrics", {}).get("distinct_speaker_labels_at_stop"), 4, "<=", denominator="4 true speakers", source=args.e1),
        "long60_ids": check((long60 or {}).get("labels_at_stop") if (long60 or {}).get("engine_settings") == {"speaker_window":"balanced","cleanup_after_stop":False} else None, 6, "<=", denominator="5 true speakers", source=args.long60),
        "long60_settled_der": check((long60 or {}).get("score", {}).get("pre_stop_settled", {}).get("der") if (long60 or {}).get("engine_settings") == {"speaker_window":"balanced","cleanup_after_stop":False} else None, .08, "<=", denominator="one complete 43-minute reference", source=args.long60),
        "dropped_passage_seconds": check(missing, 0, "<=", denominator="12 case-passes, timed reference seconds", source=args.quality),
        "speakerless_percent": check(None if not speech_s else 100 * unattributed_s / speech_s, .5, "<=", denominator=speech_s, source=args.quality),
        "longest_speakerless_run_s": check(longest_unattributed_s, 2, "<=", denominator="12 case-passes", source=args.quality),
    }
    qlive["status"] = combined(list(qlive.values()))

    independent = read(args.ind)
    ind_cases = independent.get("cases", []) if independent else []
    qind = {"status": "UNMEASURED", "cases": len(ind_cases), "expected_cases": len(IND_CASES),
            "passed_cases": sum(bool(c.get("passes_plan_predicate")) for c in ind_cases),
            "source": str(args.ind) if args.ind else None,
            "partial_reference_cases": [c.get("clip_id") for c in ind_cases if c.get("partial_reference")],
            "note": "All fourteen cases, including partial references, use paired referenced-time scores"}
    if (len(ind_cases) == len(IND_CASES) and {c.get("clip_id") for c in ind_cases} == IND_CASES
            and all(c.get("score_scope") == "referenced_time_only" for c in ind_cases)):
        qind["status"] = "PASS" if qind["passed_cases"] == len(IND_CASES) else "FAIL"

    latency_paths = sorted(args.quality.glob("pass-*/*/latency.json")) if args.quality else []
    latency = [read(path) for path in latency_paths]
    word_delays = [v for row in latency for v in row.get("word_delay_seconds", []) if v is not None]
    label_delays = [v for row in latency for v in row.get("label_delay_seconds", []) if v is not None]
    tentative = (long60 or {}).get("tentative", {}) if (long60 or {}).get("engine_settings") == {"speaker_window":"balanced","cleanup_after_stop":False} else {}
    qspeed = {
        "words_p50_s": check(percentile(word_delays, .5) if complete_h1 and len(latency)==12 else None, 1, "<=", denominator=len(word_delays), source=args.quality),
        "speaker_p50_s": check(percentile(label_delays, .5) if complete_h1 and len(latency)==12 else None, 15, "<=", denominator=len(label_delays), source=args.quality),
        "guess_coverage": check(tentative.get("coverage"), .70, ">=", denominator=tentative.get("tbd_seconds"), source=args.long60),
        "guess_accuracy": check(tentative.get("accuracy"), .95, ">=", denominator=tentative.get("reference_scored_guess_seconds"), source=args.long60),
    }
    qspeed["status"] = combined(list(qspeed.values()))

    mic_variants = {}
    if args.mic:
        for variant in ("headphones", "speakers--20", "speakers--10"):
            path = args.mic / variant / "qmic.json" if args.mic.is_dir() else None
            if path and path.exists():
                mic_variants[variant] = read(path)
    qmic = {"status": "UNMEASURED", "source": str(args.mic) if args.mic else None,
            "variants": {}, "expected_variants": 3,
            "method": "WP2 word-match proxy; see each qmic.json"}
    for variant, receipt in mic_variants.items():
        born = receipt.get("system_born_local_ids")
        zero_born = len(born) == 0 if isinstance(born, list) else born == 0
        retention = (receipt.get("local_retention") or {}).get("fraction")
        echo = (receipt.get("echo") or {}).get("dropped_fraction") if variant != "headphones" else None
        checks = [zero_born, receipt.get("local_id_count") == 2,
                  isinstance(retention, (int, float)) and retention >= .9]
        if variant != "headphones":
            checks.append(isinstance(echo, (int, float)) and echo >= .9)
        qmic["variants"][variant] = {"status": "PASS" if all(checks) else "FAIL",
                                    "system_born_local_ids": born, "local_id_count": receipt.get("local_id_count"),
                                    "retention_fraction": retention, "echo_dropped_fraction": echo,
                                    "local_retained_words": (receipt.get("local_retention") or {}).get("retained"),
                                    "local_reference_words": (receipt.get("local_retention") or {}).get("reference_words")}
    if len(qmic["variants"]) == 3:
        qmic["status"] = "PASS" if all(v["status"] == "PASS" for v in qmic["variants"].values()) else "FAIL"
    file_data = read(args.file)
    file_cases = file_data.get("cases", []) if file_data and file_data.get("schema") == "moss.qfile.v1" else []
    file_aggregate = file_data.get("aggregate", {}) if file_cases else {}
    live_voiceprint = read(args.live_voiceprint)
    qfile = {
        "accept6_final_der": check(file_aggregate.get("accept6_der_macro") if file_aggregate.get("accept6_scored") == 6 else None, .110, "<=", denominator="six completed accept6 files", source=args.file),
        "long60_final_der": check(file_aggregate.get("long60_der") if file_aggregate.get("completed") == 7 else None, .06, "<=", denominator="one complete 43-minute reference", source=args.file),
        "file_voiceprint_saved": check(file_aggregate.get("enrolled") if file_aggregate.get("completed") == 7 else None, 1, ">=", denominator="seven completed files", source=args.file),
        "live_voiceprint_saved": check((live_voiceprint or {}).get("voiceprint_count"), 1, ">=", denominator="one named after-Stop Live speaker", source=args.live_voiceprint),
    }
    qfile["status"] = combined(list(qfile.values()))
    if file_aggregate.get("qfile_gate") == "FAIL":
        qfile["status"] = "FAIL"

    summaries = [read(path) for path in args.summary]
    summary_usage = [c["usage"] for d in summaries if d for c in d.get("checks", []) if isinstance(c.get("usage"), dict)]
    qsum = {"status": "UNMEASURED", "sources": [str(p) for p in args.summary],
            "five_key_checks": sum(sum(bool(c.get("five_keys_valid")) for c in d.get("checks", [])) for d in summaries if d),
            "wrong_owner_404": all(d.get("wrong_owner_status")==404 for d in summaries if d) if summaries else None,
            "rolling_intervals_ms": [v for d in summaries if d for v in d.get("rolling_intervals_ms", [])],
            "usage_calls": len(summary_usage),
            "usage_total_usd": round(sum(u["cost_usd"] for u in summary_usage), 9) if summary_usage else None}
    if ({d.get("case") for d in summaries if d} == {"e1", "long60"}
            and qsum["five_key_checks"] >= 2 and qsum["wrong_owner_404"]
            and qsum["rolling_intervals_ms"]):
        qsum["status"] = "OBSERVED"  # About-60-s cadence needs review of exact intervals.
    ui = read(args.ui)
    qui = {**ui, "status": ui.get("status", "UNMEASURED")} if ui else {"status": "UNMEASURED", "source": str(args.ui) if args.ui else None}

    meter = (diagnostics or {}).get("cases", [])
    cost_rows = [r.get("engine_diagnostics", {}) for r in meter]
    cost_usd = sum(r["cost_usd"] for r in cost_rows if isinstance(r.get("cost_usd"), (int,float)))
    output_usd = sum(r["output_cost_estimate_usd"] for r in cost_rows if isinstance(r.get("output_cost_estimate_usd"), (int,float)))
    duration_h = sum(float(r["duration_seconds"]) for r in cases)/3600 if complete_h1 else None
    spend = read(args.spend)
    qcost = {"status": "UNMEASURED", "metered_usd": cost_usd if cost_rows else None,
             "summary_usage_usd": qsum["usage_total_usd"],
             "output_estimate_usd": output_usd if any("output_cost_estimate_usd" in r for r in cost_rows) else None,
             "meeting_hours": duration_h,
             "metered_usd_per_meeting_hour": cost_usd/duration_h if duration_h else None,
             "with_output_estimate_usd_per_meeting_hour": (cost_usd+output_usd)/duration_h if duration_h and any("output_cost_estimate_usd" in r for r in cost_rows) else None,
             "round2_spend_usd": (spend or {}).get("round2_spend_usd"),
             "qualification_spend_usd": (spend or {}).get("qualification_spend_usd")}
    if qcost["with_output_estimate_usd_per_meeting_hour"] is not None and qcost["round2_spend_usd"] is not None:
        qcost["status"] = "PASS" if qcost["round2_spend_usd"] <= 50 and (qcost["qualification_spend_usd"] or 0) <= 20 else "FAIL"

    gates = {"Q-LIVE": qlive, "Q-IND": qind, "Q-SPEED": qspeed, "Q-MIC": qmic,
             "Q-FILE": qfile, "Q-SUM": qsum, "Q-UI": qui, "COST": qcost}
    result = {"schema": "gemini-r2-scorecard.v1", "gates": gates}
    (args.out / "scorecard.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = ["# Gemini round-2 scorecard", "", "| Gate | Status | Evidence |", "|---|---|---|"]
    for name, gate in gates.items():
        detail = ", ".join(f"{key}={value['value']} ({value['status']})" for key,value in gate.items() if isinstance(value, dict) and "value" in value)
        lines.append(f"| {name} | {gate['status']} | {detail or gate.get('source', '')} |")
    if ind_cases:
        lines.extend(["", "## Q-IND paired cases", "",
                      "| Case | Reference scope | Referenced / audio s | OFF IDs / DER | ON DER | Predicate |",
                      "|---|---|---:|---:|---:|---|"])
        for case in ind_cases:
            off, on = case["live_only"], case["cleanup_on"]
            scope = "partial-reference" if case.get("partial_reference") else "full-reference"
            lines.append(f"| {case['clip_id']} | {scope} | "
                         f"{case['reference_covered_seconds']:.3f} / {case['duration_seconds']:.3f} | "
                         f"{off['canonical_ids']} / {off['score']['der']:.6f} | "
                         f"{on['score']['der']:.6f} | "
                         f"{'PASS' if case['passes_plan_predicate'] else 'FAIL'} |")
    lines.extend(["", "UNMEASURED means the required exact population or receipt is absent. OBSERVED requires human review against the plan's qualitative cadence/UI wording."])
    (args.out / "scorecard.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({key: value["status"] for key, value in gates.items()}, indent=2))


if __name__ == "__main__":
    main()
