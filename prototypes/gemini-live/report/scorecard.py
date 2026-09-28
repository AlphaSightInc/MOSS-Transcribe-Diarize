"""Source-tagged D6 scorecard from retained MOSS and optional Gemini receipts.

One command is in NOTES.md. This program only reads JSON; it never calls a provider.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence")
BASELINE = EVIDENCE / "P62/moss-baseline.json"
MOSS_E1 = EVIDENCE / "P64/moss-real-E1-summary.json"
COMMON = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/briefs/COMMON-GEMINI.md")
H1_BOUNDS = {
    "immediate_wer": ("immediate", "wer"),
    "settled_wer": ("settled", "wer"),
    "recall": ("settled", "content_recall"),
    "time_speaker_attribution": ("settled", "tbsa"),
    "diarization_error_rate": ("settled", "der"),
    "matched_speaker_accuracy": ("settled", "matched_word_speaker_accuracy"),
    "reference_speech_der": ("settled", "reference_speech_der"),
    "final_wer": ("final", "wer"),
}
SURFACES = ("immediate", "settled", "final")
QUALITY_FIELDS = ("wer", "content_recall", "tbsa", "der", "matched_word_speaker_accuracy",
                  "reference_speech_der", "text_coverage", "text_speaker_accuracy",
                  "speaker_accuracy")
E1_FIELDS = {
    "labels_at_Stop": ("distinct_speaker_labels_at_stop", "count"),
    "uncertain_rows_at_Stop": ("uncertain_rows_at_stop", "count"),
    "slice_boundaries_per_min": ("visible_slice_boundaries_per_min", "per minute"),
    "relabels_per_min": ("relabel_events_per_min", "per minute"),
}
CORE_STRESS = ("long60", "concurrent2", "silence10", "music5", "overlap", "manyspk",
               "stop-early", "abort-mid")
REST_FAULTS = ("http_429", "http_500", "http_503", "latency_fixed", "latency_heavy_tail",
               "connection_reset", "response_truncate", "malformed_json", "stall")
WS_FAULTS = ("ws_close_1011", "ws_close_1007", "ws_goaway", "ws_connection_reset", "ws_stall")
STRESS_NAMES = CORE_STRESS + tuple("faults-" + x for x in REST_FAULTS + WS_FAULTS) + ("faults-google_down",)


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def cell(value, source: Path | None, key: str, population: str, *, note: str = "") -> dict:
    measured = value is not None and value != "UNMEASURED"
    return {"status": "MEASURED" if measured else "UNMEASURED", "value": value if measured else None,
            "source_path": str(source.resolve()) if source else None, "source_key": key,
            "population": population, "note": note}


def unknown(reason: str, source: Path | None = None) -> dict:
    return cell(None, source, "", "", note=reason)


def gate(measurement: dict, threshold: float, operator: str) -> dict:
    value = measurement["value"]
    status = "UNMEASURED" if value is None else ("PASS" if (
        value < threshold if operator == "<" else value <= threshold) else "FAIL")
    return {**measurement, "status": status, "threshold": threshold, "operator": operator}


def h1_population(data: dict, baseline: dict) -> tuple[bool, str]:
    cases = data.get("per_case") or []
    expected = {(row["case_id"], row["pass"]) for row in baseline["h1"]["per_case"]}
    actual = {(row.get("case_id"), row.get("pass")) for row in cases}
    if len(cases) != 12 or len(actual) != 12 or actual != expected:
        return False, "requires exactly the frozen 6 cases x 2 passes"
    if data.get("corpus_manifest_sha256") != baseline["h1"]["corpus_manifest_sha256"]:
        return False, "H1 reference manifest differs"
    if abs(float(data.get("duration_seconds", 0)) - baseline["h1"]["duration_seconds"]) > .01:
        return False, "H1 audio duration differs"
    return True, "frozen H1 population matched"


def quality_cells(data: dict, source: Path, label: str) -> dict:
    cases = data["per_case"]
    values = {}
    for surface in SURFACES:
        values[surface] = {}
        for field in QUALITY_FIELDS:
            observed = [row.get("metrics", {}).get(surface, {}).get(field) for row in cases]
            value = mean(observed) if len(observed) == 12 and all(isinstance(v, (int, float)) for v in observed) else None
            values[surface][field] = cell(value, source, f"per_case[*].metrics.{surface}.{field}:mean",
                                          f"{label}:H1 12 case-passes")
    return values


def provider_from_snapshot(path: Path) -> str | None:
    if not path.is_file():
        return None
    envelope = read(path)
    snapshot = envelope.get("snapshot") or envelope
    return (snapshot.get("descriptor") or {}).get("provider_name")


def gemini_quality(path: Path, baseline: dict) -> tuple[dict | None, dict]:
    source = path / "content-free-metrics.json" if path.is_dir() else path
    if not source.is_file():
        return None, {"source_path": str(source), "eligible": False, "reason": "quality file absent"}
    data = read(source)
    ok, reason = h1_population(data, baseline)
    if not ok:
        return None, {"source_path": str(source), "eligible": False, "reason": reason}
    run_dir = source.parent
    manifests = sorted(run_dir.glob("pass-*/*/replay-manifest.json"))
    providers = [(read(p).get("descriptor") or {}).get("provider_name") for p in manifests]
    if len(providers) != 12 or not all(isinstance(v, str) and "gemini" in v.lower() for v in providers):
        return None, {"source_path": str(source), "eligible": False,
                      "reason": "12 Gemini provider manifests required; isolated metrics or stub are diagnostic"}
    counters = h1_engine_counters(source, baseline)
    if not (isinstance(counters["calls"]["value"], (int, float)) and counters["calls"]["value"] > 0
            and isinstance(counters["cost_usd"]["value"], (int, float)) and counters["cost_usd"]["value"] > 0):
        return None, {"source_path": str(source.resolve()), "eligible": False,
                      "reason": "12 measured engine counters with positive Gemini calls and provider cost required"}
    return data, {"source_path": str(source.resolve()), "eligible": True,
                  "reason": "frozen H1 population, 12 Gemini descriptors, and paid runtime calls verified"}


def e1_receipt(path: Path, *, moss: bool = False) -> tuple[dict | None, dict]:
    if not path.is_file():
        return None, {"source_path": str(path), "eligible": False, "reason": "summary absent"}
    data = read(path)
    visual = data.get("visual_metrics") or {}
    if abs(float(visual.get("audio_seconds") or 0) - 302) > 1:
        return None, {"source_path": str(path), "eligible": False, "reason": "not full E1 duration"}
    if moss:
        valid = data.get("mode") == "recorded_dom_reduction" and data.get("status") == "RECORDED_REDUCED"
    else:
        provider = provider_from_snapshot(path.parent / "pre-stop-snapshot.json")
        final_path = path.parent / "final-snapshot.json"
        final = read(final_path) if final_path.is_file() else {}
        engine = ((final.get("snapshot") or {}).get("engine_diagnostics") or {})
        calls = engine.get("calls_by_kind") or {}
        valid = (data.get("mode") == "external_stack" and data.get("status") == "EXTERNAL_COMPLETE"
                 and isinstance(provider, str) and "gemini" in provider.lower()
                 and isinstance(calls, dict) and all(isinstance(v, (int, float)) for v in calls.values())
                 and sum(calls.values()) > 0
                 and isinstance(engine.get("cost_usd"), (int, float)) and engine["cost_usd"] > 0)
    return (data if valid else None), {"source_path": str(path.resolve()), "eligible": bool(valid),
                                        "reason": "E1 real DOM receipt" if valid else "stub or unverified provider"}


def visual_cells(data: dict | None, source: Path | None, label: str) -> dict:
    visual = (data or {}).get("visual_metrics") or {}
    out = {name: cell(visual.get(key), source if data else None, f"visual_metrics.{key}",
                      f"{label}:E1 302 seconds") for name, (key, _) in E1_FIELDS.items()}
    for name, key in (("words_visible_p50_s", "first_text_on_screen_latency_s"),
                      ("labelled_row_p50_s", "label_on_screen_latency_s")):
        item = visual.get(key) or {}
        value = item.get("p50") if item.get("observed_audio_seconds", 0) > 0 else None
        out[name] = cell(value, source if data else None, f"visual_metrics.{key}.p50",
                         f"{label}:E1 {item.get('observed_audio_seconds', 0)}/{item.get('total_audio_seconds', 302)} observed audio seconds",
                         note="DOM clock: " + str(visual.get("latency_precision", "UNMEASURED")))
        out[name]["observed_audio_seconds"] = item.get("observed_audio_seconds")
        out[name]["total_audio_seconds"] = item.get("total_audio_seconds")
    survival = visual.get("live_to_final_text_survival") or {}
    numerator = survival.get("surviving_lane_text_keys")
    denominator = survival.get("distinct_live_lane_text_keys")
    out["live_to_final_survival"] = cell(
        numerator / denominator if isinstance(numerator, int) and isinstance(denominator, int) and denominator else None,
        source if data else None, "visual_metrics.live_to_final_text_survival",
        f"{label}:E1 {numerator}/{denominator} exact lane+text keys" if denominator else f"{label}:E1",
        note="exact text-key survival, not semantic equivalence")
    out["live_to_final_survival"]["numerator"] = numerator
    out["live_to_final_survival"]["denominator"] = denominator
    return out


def passage_missing_seconds(reference: list[dict], words: list[dict]) -> tuple[int, list[int]]:
    """Count spoken one-second buckets with no timed word in the padded bucket."""
    spoken = {second for row in reference if str(row.get("text", "")).strip()
              for second in range(max(0, math.floor(float(row["start"]))), math.ceil(float(row["end"])))
              if float(row["start"]) < second + 1 and float(row["end"]) > second}
    missing = [second for second in sorted(spoken)
               if not any(str(w.get("text", "")).strip() and float(w["start"]) < second + 4
                          and float(w["end"]) > second - 3 for w in words)]
    return len(spoken), missing


def passage_gate(paths: list[Path], baseline: dict) -> tuple[dict, list[dict]]:
    expected = {(row["case_id"], row["pass"]) for row in baseline["h1"]["per_case"]}
    diagnostics = []
    for path in paths:
        data = read(path)
        cases = data.get("cases") or []
        actual = {(row.get("case_id"), row.get("pass")) for row in cases}
        if (data.get("corpus_manifest_sha256") != baseline["h1"]["corpus_manifest_sha256"]
                or len(cases) != 12 or actual != expected):
            diagnostics.append({"source_path": str(path.resolve()), "eligible": False,
                                "reason": "requires 12 timed-word case passes on frozen H1 manifest"})
            continue
        totals = {"settled": {"reference_seconds": 0, "missing_seconds": 0},
                  "final": {"reference_seconds": 0, "missing_seconds": 0}}
        segment_sidecar = data.get("schema") == "h1-timed-segments.v1"
        per_case = []
        for row in cases:
            surfaces = row.get("surfaces") or {}
            hypothesis = ({"settled": surfaces.get("pre_stop_settled"),
                           "final": surfaces.get("post_stop_final")}
                          if segment_sidecar else
                          {surface: row.get(surface + "_words") for surface in ("settled", "final")})
            if not isinstance(row.get("reference"), list) or not all(
                    isinstance(hypothesis[surface], list) for surface in ("settled", "final")):
                break
            item = {"case_id": row["case_id"], "pass": row["pass"]}
            for surface in ("settled", "final"):
                seconds, missing = passage_missing_seconds(row["reference"], hypothesis[surface])
                totals[surface]["reference_seconds"] += seconds
                totals[surface]["missing_seconds"] += len(missing)
                item[surface + "_missing_seconds"] = missing
            per_case.append(item)
        if len(per_case) != 12 or any(v["reference_seconds"] == 0 for v in totals.values()):
            diagnostics.append({"source_path": str(path.resolve()), "eligible": False,
                                "reason": "timed reference or hypothesis word rows missing"})
            continue
        missing = sum(v["missing_seconds"] for v in totals.values())
        measurement = cell(missing, path,
                           "cases[*].surfaces.{pre_stop_settled,post_stop_final} ±3s" if segment_sidecar
                           else "cases[*].{settled,final}_words ±3s", "H1 12 case-passes",
                           note="word-bearing segment bounds, not token offsets" if segment_sidecar else
                                "timed word offsets; both surfaces required")
        return {**measurement, "status": "PASS" if missing == 0 else "FAIL",
                "granularity": "word-bearing segment" if segment_sidecar else "timed word",
                "surfaces": totals, "per_case": per_case}, diagnostics
    return {**unknown("no complete timed-word H1 receipt for both Stop-settled and final"),
            "status": "UNMEASURED"}, diagnostics


def stress_receipt(path: Path) -> tuple[dict | None, dict]:
    data = read(path)
    providers = [provider_from_snapshot(path.parent / row["name"] / "final-snapshot.json")
                 for row in data.get("sessions") or []]
    eligible = bool(providers) and all(isinstance(v, str) and "gemini" in v.lower() for v in providers)
    eligible = eligible and (data.get("expectations") or {}).get("scope") == "full named scenario"
    eligible = eligible and isinstance(data.get("gemini_calls"), (int, float)) and data["gemini_calls"] > 0
    eligible = eligible and isinstance(data.get("timing_anomalies_per_call"), dict)
    eligible = eligible and all(isinstance(row.get("engine"), dict) for row in data.get("sessions") or [])
    return (data if eligible else None), {"source_path": str(path.resolve()), "eligible": bool(eligible),
                                          "reason": "full Gemini runtime scenario" if eligible else
                                          "stub, short smoke, or provider unverified"}


def ledger_summary(paths: list[Path]) -> list[dict]:
    result = []
    for path in paths:
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        known_cost = [row["cost_usd"] for row in rows if isinstance(row.get("cost_usd"), (int, float))]
        anomalies = [row["timing_anomalies"] for row in rows if isinstance(row.get("timing_anomalies"), dict)]
        result.append({"source_path": str(path.resolve()), "rows": len(rows),
                       "cost_usd_known": round(sum(known_cost), 6), "cost_rows": len(known_cost),
                       "anomaly_measured_calls": len(anomalies),
                       "clamped": sum(x.get("clamped", 0) for x in anomalies),
                       "dropped": sum(x.get("dropped", 0) for x in anomalies),
                       "scope": "provider experiments; not a meeting-hour cost denominator"})
    return result


def h1_engine_counters(quality_source: Path | None, baseline: dict) -> dict:
    names = ("calls", "errors", "retries", "clamped", "dropped", "clamped_per_call", "dropped_per_call", "cost_usd")
    absent = {name: unknown("no complete H1 Gemini engine diagnostics") for name in names}
    if quality_source is None:
        return absent
    path = quality_source.parent / "engine-diagnostics.json"
    if not path.is_file():
        return absent
    rows = read(path).get("cases") or []
    expected = {(row["case_id"], row["pass"]) for row in baseline["h1"]["per_case"]}
    if len(rows) != 12 or {(row.get("case_id"), row.get("pass")) for row in rows} != expected:
        return {name: unknown("engine diagnostics need all 12 H1 case-passes", path) for name in names}
    engines = [row.get("engine_diagnostics") for row in rows]
    if not all(isinstance(e, dict) and isinstance(e.get("calls_by_kind"), dict)
               and isinstance(e.get("errors_by_code"), dict)
               and isinstance(e.get("retries_by_code"), dict)
               and isinstance(e.get("timing_anomalies"), dict)
               and all(isinstance(v, (int, float)) for name in ("calls_by_kind", "errors_by_code", "retries_by_code")
                       for v in e[name].values()) for e in engines):
        return {name: unknown("runtime counters absent in at least one H1 case-pass", path) for name in names}
    calls = sum(sum(e["calls_by_kind"].values()) for e in engines)
    values = {
        "calls": calls,
        "errors": sum(sum(e["errors_by_code"].values()) for e in engines),
        "retries": sum(sum(e["retries_by_code"].values()) for e in engines),
        "clamped": sum(e["timing_anomalies"].get("clamped", 0) for e in engines),
        "dropped": sum(e["timing_anomalies"].get("dropped", 0) for e in engines),
        "cost_usd": sum(e["cost_usd"] for e in engines)
        if all(isinstance(e.get("cost_usd"), (int, float)) for e in engines) else None,
    }
    values["clamped_per_call"] = values["clamped"] / calls if calls else None
    values["dropped_per_call"] = values["dropped"] / calls if calls else None
    return {name: cell(value, path, f"cases[*].engine_diagnostics.{name}", "Gemini:H1 12 case-passes")
            for name, value in values.items()}


def display(value) -> str:
    if value is None:
        return "UNMEASURED"
    if isinstance(value, float):
        return f"{value:.6f}" if abs(value) < 1 else f"{value:.3f}"
    return str(value)


def md_cell(value: dict) -> str:
    source = value.get("source_path")
    label = display(value.get("value")) if value.get("value") is not None else value.get("status", "UNMEASURED")
    if isinstance(value.get("numerator"), int) and isinstance(value.get("denominator"), int) and value["denominator"]:
        label += f" ({value['numerator']}/{value['denominator']})"
    elif isinstance(value.get("observed_audio_seconds"), int) and isinstance(value.get("total_audio_seconds"), int):
        label += f" ({value['observed_audio_seconds']}/{value['total_audio_seconds']} s observed)"
    if source:
        return f"{label} ([source](<{source}>))"
    return label + " (source: none eligible)"


def markdown(card: dict) -> str:
    lines = ["# D6 scorecard", "", f"**Gemini product verdict: {card['decision']}**. Every hard bar needs a complete, verified runtime receipt before a PASS verdict.",
             "The MOSS baseline is recorded H1 evidence; loopback stubs prove plumbing only. A short Gemini SDK call is not a meeting.", "",
             "## D6 hard bars", "", "| Bar | Rule | MOSS context | Gemini |", "| --- | --- | --- | --- |"]
    for name, item in card["hard_bars"].items():
        rule = f"{item['operator']} {item['threshold']}"
        lines.append(f"| {name} | {rule} | {item['moss']['status']}: {md_cell(item['moss'])} | {item['gemini']['status']}: {md_cell(item['gemini'])} |")
    lines += ["", "Settled diarization error rate (DER) uses the D45b ruled value; raw MOSS settled DER is "
              + md_cell(card["quality"]["moss"]["settled"]["der_raw"])
              + " (about 0.171). No dropped passages requires timed reference and word-bearing rows for all 12 H1 case-passes on both Stop-settled and final surfaces. A segment sidecar proves coverage at segment granularity and can hide a gap inside a long segment.", "",
              "## D6 soft bars", "", "| Bar | Rule | MOSS context | Gemini |", "| --- | --- | --- | --- |"]
    for name, item in card["soft_bars"].items():
        lines.append(f"| {name} | {item['operator']} {item['threshold']} | {item['moss']['status']}: {md_cell(item['moss'])} | {item['gemini']['status']}: {md_cell(item['gemini'])} |")
    lines += ["", "## Eight H1 coordinates across three surfaces", "", "Each value is an unweighted mean of 12 case-passes. Repeated WER rows deliberately show the same underlying WER on each surface; the coordinate name identifies its official bound surface.", "",
              "| H1 coordinate | MOSS immediate | Gemini immediate | MOSS settled | Gemini settled | MOSS final | Gemini final |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for name, cells in card["h1_bound_surface_comparison"].items():
        lines.append("| " + name + " | " + " | ".join(md_cell(cells[surface][side])
            for surface in SURFACES for side in ("moss", "gemini")) + " |")
    lines += ["", "## Other H1 production metrics", "", "Only the eight coordinates above are H1 bounds; these rows expose the additional retained surface metrics and raw settled DER.", "",
              "| Metric | Surface | MOSS | Gemini |", "| --- | --- | --- | --- |"]
    for surface in SURFACES:
        for field in QUALITY_FIELDS + (("der_raw",) if surface == "settled" else ()):
            moss = card["quality"]["moss"][surface].get(field, unknown("missing"))
            gemini = card["quality"]["gemini"][surface].get(field, unknown("missing"))
            lines.append(f"| {field} | {surface} | {md_cell(moss)} | {md_cell(gemini)} |")
    lines += ["", "## E1 visible transcript", "", "| Metric | MOSS archived real E1 | Gemini |", "| --- | --- | --- |"]
    for name in card["e1"]["moss"]:
        lines.append(f"| {name} | {md_cell(card['e1']['moss'][name])} | {md_cell(card['e1']['gemini'][name])} |")
    lines += ["", "## Latency, cost, compute", "", "| Metric | MOSS | Gemini |", "| --- | --- | --- |"]
    for name, item in card["operations"].items():
        lines.append(f"| {name} | {md_cell(item['moss'])} | {md_cell(item['gemini'])} |")
    lines += ["", "Archived MOSS E1 DOM latency has an approximate first-frame origin; its numbers are context only and do not pass the soft bar. Gemini p50 uses observed audio seconds from a paced E1 run; unobserved seconds remain visible in the denominator."]
    lines += ["", "## Stress", "", "| Scenario | Expectation | Product result | Calls | Errors | Retries | Clamped/call | Dropped/call | Local stub observation |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in card["stress"]:
        product = row["product_status"] + (f" ({row['product_reason']})" if row["product_reason"] else "")
        product += (f" ([source](<{row['product_source']}>))" if row["product_source"] else " (source: none eligible)")
        stub = row["stub_status"] + (f" ([source](<{row['stub_source']}>))" if row["stub_source"] else " (source: none supplied)")
        counters = " | ".join(md_cell(row[key]) for key in
                              ("calls", "errors", "retries", "clamped_per_call", "dropped_per_call"))
        lines.append(f"| {row['scenario']} | {row['expectation']} | {product} | {counters} | {stub} |")
    lines += ["", "## Provider ledger context", "", "| Ledger | Rows | Known cost USD | Timed calls | Clamped/call | Dropped/call |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in card["ledgers"]:
        n = row["anomaly_measured_calls"]
        lines.append(f"| [source](<{row['source_path']}>) | {row['rows']} | {row['cost_usd_known']:.6f} ({row['cost_rows']} rows) | {n} | {display(row['clamped']/n) if n else 'UNMEASURED'} | {display(row['dropped']/n) if n else 'UNMEASURED'} |")
    lines += ["", "Ledgers combine experiments across populations and never supply the meeting-hour D6 denominator.", "",
              "## H1 runtime engine counters", "", "| Counter | Gemini H1 |", "| --- | --- |"]
    for name, value in card["h1_engine_counters"].items():
        lines.append(f"| {name} | {md_cell(value)} |")
    lines += ["", "The 12-case runtime counters are context for the quality run; its short clips do not supply a meeting-hour cost denominator.", "",
              "## Latency probe inputs", ""]
    for row in card["latency_inputs"]:
        lines.append(f"- [source](<{row['source_path']}>): {row['runs']} run summaries; "
                     f"words observed {row['word_observed_buckets']}/{row['total_audio_buckets']} seconds; "
                     f"labelled observed {row['label_observed_buckets']}/{row['total_audio_buckets']} seconds. "
                     "Per-run medians are diagnostic; the pooled p50 cannot be reconstructed.")
    lines += ["",
              "## Input eligibility", ""]
    for row in card["input_eligibility"]:
        lines.append(f"- {'ELIGIBLE' if row['eligible'] else 'EXCLUDED'}: [source](<{row['source_path']}>) — {row['reason']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--moss-e1", type=Path, default=MOSS_E1)
    parser.add_argument("--gemini-quality", type=Path, action="append", default=[], help="run_quality output directory; repeatable")
    parser.add_argument("--gemini-e1", type=Path, action="append", default=[], help="E1 summary.json; repeatable")
    parser.add_argument("--latency", type=Path, action="append", default=[], help="latency_probe output; repeatable")
    parser.add_argument("--stress", type=Path, action="append", default=[], help="stress summary.json; repeatable")
    parser.add_argument("--ledger", type=Path, action="append", default=[], help="provider ledger JSONL; repeatable")
    parser.add_argument("--passages", type=Path, action="append", default=[], help="complete timed-word H1 receipt; repeatable")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    baseline = read(args.baseline)
    valid, reason = h1_population(baseline["h1"], baseline)
    if not valid:
        raise SystemExit("MOSS baseline invalid: " + reason)
    source = args.baseline.resolve()
    moss_quality = quality_cells(baseline["h1"], source, "MOSS")
    for name, (surface, field) in H1_BOUNDS.items():
        actual = moss_quality[surface][field]["value"]
        recorded = baseline["h1"]["macro"][name]
        if actual is None or abs(actual - recorded) > 1e-9:
            raise SystemExit(f"MOSS baseline macro disagrees at {name}")
    moss_quality["settled"]["der_raw"] = cell(baseline["h1"]["macro"]["diarization_error_rate_raw"],
                                              source, "h1.macro.diarization_error_rate_raw", "MOSS:H1 12 case-passes")
    moss_e1_data, moss_e1_eligibility = e1_receipt(args.moss_e1, moss=True)
    gemini_quality_data = None
    quality_source = None
    eligibility = [moss_e1_eligibility]
    for path in args.gemini_quality:
        data, outcome = gemini_quality(path, baseline)
        eligibility.append(outcome)
        if data is not None and gemini_quality_data is None:
            gemini_quality_data = data
            quality_source = Path(outcome["source_path"])
    gemini_quality_cells = (quality_cells(gemini_quality_data, quality_source, "Gemini")
                            if gemini_quality_data else
                            {surface: {field: unknown("no complete Gemini H1 quality run")
                                       for field in QUALITY_FIELDS} for surface in SURFACES})
    gemini_quality_cells["settled"]["der_raw"] = (cell(gemini_quality_data["macro"].get("diarization_error_rate_raw"),
        quality_source, "macro.diarization_error_rate_raw", "Gemini:H1 12 case-passes")
        if gemini_quality_data else unknown("no complete Gemini H1 quality run"))
    gemini_e1_data = None
    gemini_e1_source = None
    for path in args.gemini_e1:
        data, outcome = e1_receipt(path)
        eligibility.append(outcome)
        if data is not None and gemini_e1_data is None:
            gemini_e1_data, gemini_e1_source = data, path
    moss_visual = visual_cells(moss_e1_data, args.moss_e1 if moss_e1_data else None, "MOSS")
    gemini_visual = visual_cells(gemini_e1_data, gemini_e1_source, "Gemini")
    gemini_latency_exact = ((gemini_e1_data or {}).get("visual_metrics") or {}).get("audio_clock_source") == "paced_sender_exact"
    if not gemini_latency_exact:
        for name in ("words_visible_p50_s", "labelled_row_p50_s"):
            gemini_visual[name] = unknown("paced sender clock absent", gemini_e1_source)
    moss_passages = {**unknown("archived H1 content-free receipt has no timed words", args.baseline),
                     "status": "UNMEASURED"}
    passage_paths = []
    if quality_source is not None:
        produced = quality_source.parent / "h1-timed-segments.json"
        if produced.is_file():
            passage_paths.append(produced)
        for path in args.passages:
            if path.resolve().parent == quality_source.resolve().parent and path not in passage_paths:
                passage_paths.append(path)
            else:
                eligibility.append({"source_path": str(path.resolve()), "eligible": False,
                                    "reason": "timed segments must accompany the eligible Gemini H1 quality run"})
    else:
        eligibility.extend({"source_path": str(path.resolve()), "eligible": False,
                            "reason": "no eligible Gemini H1 quality run to bind this sidecar"}
                           for path in args.passages)
    gemini_passages, passage_diagnostics = passage_gate(passage_paths, baseline)
    eligibility.extend(passage_diagnostics)
    moss_final_der = cell(baseline["h1"]["derived_from_per_case"]["final_der_macro"], source,
                          "h1.derived_from_per_case.final_der_macro", "MOSS:H1 12 case-passes")
    gemini_final_der = gemini_quality_cells["final"]["der"]
    hard = {
        "live_settled_DER": {"operator": "<", "threshold": .145,
            "moss": gate(moss_quality["settled"]["der"], .145, "<"),
            "gemini": gate(gemini_quality_cells["settled"]["der"], .145, "<")},
        "final_DER": {"operator": "<=", "threshold": .110,
            "moss": gate(moss_final_der, .110, "<="), "gemini": gate(gemini_final_der, .110, "<=")},
        "E1_labels_at_Stop": {"operator": "<=", "threshold": 5,
            "moss": gate(moss_visual["labels_at_Stop"], 5, "<="),
            "gemini": gate(gemini_visual["labels_at_Stop"], 5, "<=")},
        "dropped_reference_seconds": {"operator": "<=", "threshold": 0,
            "moss": gate(moss_passages, 0, "<="),
            "gemini": gate(gemini_passages, 0, "<=")},
    }
    stress_data = {}
    stub_data = {}
    for path in args.stress:
        data, outcome = stress_receipt(path)
        eligibility.append(outcome)
        name = read(path).get("scenario")
        if name in STRESS_NAMES:
            if data is not None:
                stress_data.setdefault(name, (data, path))
            else:
                stub_data.setdefault(name, (read(path), path))
    stress = []
    core_expectations = {
        "long60": "paced 3600 s; bounded queue, complete tape, terminal state",
        "concurrent2": "two 300 s tapes; third create 409 live_capacity_full",
        "silence10": "600 s silence accepted, retained, terminal",
        "music5": "300 s music accepted, retained, terminal",
        "overlap": "two 300 s overlap mixes accepted, retained, terminal",
        "manyspk": "K=6 public synthetic meeting accepted, retained, terminal",
        "stop-early": "5 s Stop bounded; retained tape, terminal state",
        "abort-mid": "abort bounded; retained or explicitly unavailable tape, terminal state",
    }
    for name in STRESS_NAMES:
        actual = stress_data.get(name)
        stub = stub_data.get(name)
        expected = ("injected fault observed; bounded queue, complete tape, visible terminal or recovery"
                    if name.startswith("faults-") else core_expectations[name])
        if name.startswith("faults-ws_"):
            expected += "; mandatory if Live words source wins"
        raw_status = actual[0].get("status", "PENDING") if actual else "PENDING"
        status = raw_status
        reason = ("PENDING_WORDS_SOURCE" if raw_status == "PENDING_WORDS_SOURCE"
                  or (name.startswith("faults-ws_") and not actual) else "")
        if reason:
            status = "PENDING"
        data = actual[0] if actual else {}
        timing = data.get("timing_anomalies_per_call") or {}
        if not isinstance(timing, dict):
            timing = {}
        counter_source = actual[1] if actual else None
        stress.append({"scenario": name, "expectation": expected,
                       "product_status": status, "product_reason": reason,
                       "product_source": str(actual[1].resolve()) if actual else None,
                       "calls": cell(data.get("gemini_calls"), counter_source, "gemini_calls", name),
                       "errors": cell(data.get("gemini_errors"), counter_source, "gemini_errors", name),
                       "retries": cell(data.get("retries"), counter_source, "retries", name),
                       "clamped_per_call": cell(timing.get("clamped"), counter_source,
                                                "timing_anomalies_per_call.clamped", name),
                       "dropped_per_call": cell(timing.get("dropped"), counter_source,
                                                "timing_anomalies_per_call.dropped", name),
                       "stub_status": stub[0].get("status", "PENDING") if stub else "PENDING",
                       "stub_source": str(stub[1].resolve()) if stub else None})
    # A quality run's per-case latency summaries contain medians, not bucket samples.
    # Retain them as evidence inputs; do not pool medians into a fabricated p50.
    latency_inputs = []
    for path in args.latency:
        lat = read(path)
        latency_inputs.append({"source_path": str(path.resolve()), "runs": len(lat.get("runs") or []),
                               "total_audio_buckets": lat.get("total_audio_buckets", "UNMEASURED"),
                               "word_observed_buckets": lat.get("word_observed_buckets", "UNMEASURED"),
                               "label_observed_buckets": lat.get("label_observed_buckets", "UNMEASURED")})
        eligibility.append({"source_path": str(path.resolve()), "eligible": False,
                            "reason": "per-run p50 retained; pooled second-level p50 unavailable without raw bucket delays"})
    cost_rows = []
    for data, path in stress_data.values():
        if data.get("scenario") not in ("long60", "concurrent2") or data.get("status") != "PASS":
            continue
        for session in data.get("sessions") or []:
            engine = session.get("engine")
            duration = session.get("sent_audio_s")
            if isinstance(engine, dict) and isinstance(engine.get("cost_usd"), (int, float)) and isinstance(duration, (int, float)) and duration > 0:
                cost_rows.append((engine["cost_usd"], duration, path))
    cost = (sum(row[0] for row in cost_rows) / sum(row[1] for row in cost_rows) * 3600) if cost_rows else None
    cost_source = cost_rows[0][2] if cost_rows else None
    if not cost_rows and gemini_e1_data is not None:
        final_path = gemini_e1_source.parent / "final-snapshot.json"
        final = read(final_path) if final_path.is_file() else {}
        engine = ((final.get("snapshot") or {}).get("engine_diagnostics") or {})
        seconds = gemini_e1_data.get("seconds")
        if isinstance(engine.get("cost_usd"), (int, float)) and isinstance(seconds, (int, float)) and seconds > 0:
            cost = engine["cost_usd"] / seconds * 3600
            cost_source = final_path
    cost_population = (f"Gemini:{len(cost_rows)} full non-fault meeting sessions" if cost_rows else
                       "Gemini:one paced E1 meeting" if cost is not None else "Gemini:meeting-hour unmeasured")
    gemini_cost = cell(cost, cost_source, "engine.cost_usd / meeting_audio_s * 3600", cost_population)
    soft = {
        "words_visible_p50_s": {"operator": "<=", "threshold": 5,
            "moss": gate(unknown("archived E1 latency origin is approximate", args.moss_e1), 5, "<="),
            "gemini": gate(gemini_visual["words_visible_p50_s"], 5, "<=")},
        "labelled_row_p50_s": {"operator": "<=", "threshold": 20,
            "moss": gate(unknown("archived E1 latency origin is approximate", args.moss_e1), 20, "<="),
            "gemini": gate(gemini_visual["labelled_row_p50_s"], 20, "<=")},
        "cost_usd_per_meeting_hour": {"operator": "<=", "threshold": 3,
            "moss": gate(unknown("recorded MOSS host cost not in retained receipt"), 3, "<="),
            "gemini": gate(gemini_cost, 3, "<=")},
    }
    operations = {
        "words_visible_p50_s": {"moss": moss_visual["words_visible_p50_s"],
                                "gemini": gemini_visual["words_visible_p50_s"]},
        "labelled_row_p50_s": {"moss": moss_visual["labelled_row_p50_s"],
                                 "gemini": gemini_visual["labelled_row_p50_s"]},
        "cost_usd_per_meeting_hour": {"moss": unknown("MOSS cost unmeasured"), "gemini": gemini_cost},
        "local_GPU_need": {"moss": cell("recorded self-hosted GPU path", COMMON, "D1,D5", "MOSS:architecture",
                                          note="recorded host baseline; no GPU used by this scorecard"),
                           "gemini": cell("0 local GPU for API runtime", COMMON, "D5", "Gemini:design decision",
                                          note="architecture, not measured cost")},
    }
    bound_view = {name: {surface: {"moss": moss_quality[surface][field],
                                   "gemini": gemini_quality_cells[surface][field]}
                         for surface in SURFACES}
                  for name, (_, field) in H1_BOUNDS.items()}
    card = {"schema": "moss-gemini-d6-scorecard.v1", "baseline_source": str(source),
            "baseline_h1_case_passes": 12, "hard_bars": hard, "soft_bars": soft,
            "h1_bound_surface_comparison": bound_view,
            "quality": {"moss": moss_quality, "gemini": gemini_quality_cells},
            "e1": {"moss": moss_visual, "gemini": gemini_visual}, "operations": operations,
            "stress": stress, "ledgers": ledger_summary(args.ledger),
            "h1_engine_counters": h1_engine_counters(quality_source, baseline),
            "latency_inputs": latency_inputs,
            "input_eligibility": eligibility,
            "decision": ("FAIL" if any(row["gemini"]["status"] == "FAIL" for row in hard.values()) else
                         "PASS" if all(row["gemini"]["status"] == "PASS" for row in hard.values()) else
                         "UNMEASURED")}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "scorecard.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
    (args.out_dir / "scorecard.md").write_text(markdown(card))
    print(json.dumps({"decision": card["decision"], "hard_gemini":
                      {key: item["gemini"]["status"] for key, item in hard.items()},
                      "quality_eligible": gemini_quality_data is not None,
                      "e1_eligible": gemini_e1_data is not None,
                      "stress_product_receipts": len(stress_data),
                      "out_dir": str(args.out_dir.resolve())}, indent=2))


if __name__ == "__main__":
    main()
