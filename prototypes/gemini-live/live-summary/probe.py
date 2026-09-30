"""Live (rolling) summary probe on public transcripts, production generator (issue #6/#10).

Run from the worktree root:
  <venv python> prototypes/gemini-live/live-summary/probe.py --label before
Writes results-<label>.json beside this file and appends spend to the r4-e ledger.

Input = what `/summary/live` sends: rows ended by the snapshot time (a row still being spoken is cut
proportionally, like a live effective transcript), speakers shown as live defaults "Speaker n".
Rubric (precommitted before any call; see NOTES.md):
  valid    validate_summary passes within the endpoint's 3 attempts
  lang     CJK share of letters over every output string; zh match >= .8, en match <= .05
  recall   precommitted facts (said before the snapshot) found in the VISIBLE pane text:
           `pane_before` = summary field only (what the rolling pane rendered), `pane_full` = whole document
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.phase2_llm import GeminiSummaryGenerator  # noqa: E402
from moss_transcribe_diarize.app import phase2_summary as ps  # noqa: E402

REAL = ROOT / "prototypes/streaming-diarization/data/real"
LEDGER = Path("/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/"
              "085787c1-1541-44db-ab6d-a5146fa7fe93/scratchpad/r4/e/ledger.jsonl")
CAP_USD = 0.90  # stop before the $1.00 brief cap

CASES = {
    "en_ackman_5m": (REAL / "benchmark_5m/lex_bill_ackman/reference.jsonl", "en", (90, 180, 300), [
        (47, r"Harvard|Claudine Gay"), (47, r"Graham|Intelligent Investor"),
        (104, r"price.{0,60}value|value.{0,60}price"), (134, r"voting machine|weighing machine"),
        (202, r"speculat"), (262, r"present value|cash ?flow|coupon|5%")]),
    "en_ackman_30m": (REAL / "benchmark_30m/lex_bill_ackman/reference.jsonl", "en", (600, 1200, 1800), [
        (47, r"Graham|Intelligent Investor"), (134, r"voting machine|weighing machine"),
        (380, r"Universal"), (659, r"\bAI\b|artificial intelligence|Taylor Swift"), (856, r"Chipotle"),
        (1144, r"moat|disrupt"), (1361, r"Restaurant Brands|Burger King"), (1493, r"Alphabet|Google")]),
    "zh_keyu_jin_5m": (HERE / "zh_keyu_jin.jsonl", "zh", (90, 180, 300), [
        (52, r"伦敦政治经济学院|伦敦政经|LSE|London School"), (52, r"新中国经济学|New China Playbook"),
        (96, r"市长经济|分散|去中心化|decentrali|mayor"), (140, r"权威|盲目服从|authority"),
        (221, r"创业|entrepreneur"), (300, r"社会主义|socialis")]),
    "zh_milei_5m": (HERE / "zh_javier_milei.jsonl", "zh", (90, 210, 300), [
        (62, r"阿根廷|Argentin"), (62, r"16年|16 years|财政盈余|fiscal surplus"),
        (62, r"通胀|通货膨胀|inflation"), (207, r"西班牙语|Spanish|口译|interpret|ElevenLabs"),
        (260, r"曲棍球|hockey|1800|人均GDP|per capita"), (300, r"95%|极端贫困|extreme poverty")]),
}
CJK = re.compile(r"[㐀-鿿豈-﫿]")
LATIN = re.compile(r"[A-Za-z]")


def live_document(path: Path, at: float) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    order: dict[str, str] = {}
    segments = []
    for row in rows:
        start, end, text = float(row["start"]), float(row["end"]), row["text"]
        if start >= at:
            break
        if end > at:  # still being spoken: the words heard so far
            cut = (at - start) / (end - start)
            if CJK.search(text):
                text = text[:int(len(text) * cut)]
            else:
                words = text.split()
                text = " ".join(words[:int(len(words) * cut)])
            end = at
        if not text.strip():
            continue
        name = order.setdefault(row["speaker"], f"Speaker {len(order) + 1}")
        segments.append({"id": f"seg_{len(segments) + 1:04d}", "start": start, "end": end, "speaker": name, "text": text})
    return {"segments": segments}


def strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    if isinstance(value, dict):
        return [s for key, item in value.items() if key != "timestamp" for s in strings(item)]
    return []


def score(doc: dict, lang: str, facts: list, at: float) -> dict:
    full = "\n".join(strings(doc))
    cjk, latin = len(CJK.findall(full)), len(LATIN.findall(full))
    share = cjk / max(1, cjk + latin)
    due = [pattern for said, pattern in facts if said <= at]
    hit = lambda text: sum(bool(re.search(p, text, re.IGNORECASE)) for p in due)  # noqa: E731
    return {"cjk_share": round(share, 3), "lang_match": share >= .8 if lang == "zh" else share <= .05,
            "facts_due": len(due), "recall_pane_before": hit(doc["summary"]), "recall_pane_full": hit(full),
            "visible_chars_before": len(doc["summary"]), "visible_chars_full": len(full),
            "topics": len(doc["topics"]), "details": len(doc["details"]), "data_refs": len(doc["data_references"])}


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["cost_usd"] or 0 for line in LEDGER.read_text().splitlines() if line.strip())


async def one(generator, document, *, model: str, language: str, label: str, case: str, at: float,
              previous=None) -> dict:
    duration = max((row["end"] for row in document["segments"]), default=0)
    kwargs = {"previous": previous} if previous is not None else {}
    attempts, total, result, error = 0, None, None, None
    started = time.monotonic()
    for _ in range(ps.SUMMARY_ATTEMPTS):
        if spent() > CAP_USD:
            raise SystemExit(f"ledger over ${CAP_USD}")
        attempts += 1
        try:
            doc, usage = await generator(document, model=model, language=language,
                                         prompt=ps.DEFAULT_SUMMARY_PROMPT, api_key=KEY, **kwargs)
        except ValueError as exc:
            usage, doc, error = getattr(exc, "usage", None), None, f"{type(exc).__name__}"
        with LEDGER.open("a") as ledger:
            ledger.write(json.dumps({"who": "r4-e", "label": label, "case": case, "at": at,
                                     "cost_usd": (usage or {}).get("cost_usd") or 0,
                                     "input_tokens": (usage or {}).get("input_tokens"),
                                     "output_tokens": (usage or {}).get("output_tokens")}) + "\n")
        total = ps._add_usage(total, usage)
        if doc is None:
            continue
        try:
            result = ps.validate_summary(doc, duration)
            error = None
            break
        except ValueError as exc:
            error = f"invalid: {exc}"
    return {"attempts": attempts, "valid": result is not None, "error": error, "usage": total,
            "latency_s": round(time.monotonic() - started, 2), "document": result}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--language", default="", help="Settings > Language ('' = Auto)")
    parser.add_argument("--carry", action="store_true", help="pass the previous snapshot's summary (if supported)")
    parser.add_argument("--model", default=ps.DEFAULT_SUMMARY_MODEL)
    parser.add_argument("--at", default="", help="snapshot seconds overriding each case's own")
    parser.add_argument("--auto-rule", default="", help="prototype: replace the Auto-language sentence")
    args = parser.parse_args()
    if args.auto_rule:
        import moss_transcribe_diarize.app.phase2_llm as llm
        explicit = llm.summary_language_rule
        llm.summary_language_rule = lambda language: explicit(language) if language.strip() else args.auto_rule
    generator = GeminiSummaryGenerator()
    carry = args.carry and "previous" in inspect.signature(generator.__call__).parameters
    rows = []
    for case in args.cases.split(","):
        path, lang, snapshots, facts = CASES[case]
        snapshots = tuple(float(x) for x in args.at.split(",")) if args.at else snapshots
        previous = None
        for at in snapshots:
            document = live_document(path, at)
            run = await one(generator, document, model=args.model, language=args.language, label=args.label, case=case, at=at,
                            previous=previous if carry else None)
            row = {"case": case, "at": at, "lang": lang, "segments": len(document["segments"]),
                   "whitespace_words": len(" ".join(r["text"] for r in document["segments"]).split()), **run}
            if run["document"] is not None:
                row["score"] = score(run["document"], lang, facts, at)
                previous = run["document"]
            rows.append(row)
            s = row.get("score", {})
            print(f"{case:15s} @{at:5.0f}s valid={run['valid']} att={run['attempts']} lat={run['latency_s']:5.1f}s "
                  f"in={run['usage'] and run['usage']['input_tokens']} out={run['usage'] and run['usage']['output_tokens']} "
                  f"cjk={s.get('cjk_share')} lang_ok={s.get('lang_match')} "
                  f"recall pane={s.get('recall_pane_before')}/{s.get('facts_due')} full={s.get('recall_pane_full')}/{s.get('facts_due')} "
                  f"| {(run['document'] or {}).get('summary', run['error'])[:90]!r}", flush=True)
    out = HERE / f"results-{args.label}.json"
    out.write_text(json.dumps({"label": args.label, "model": args.model, "language": args.language,
                               "carry": carry, "rows": rows}, ensure_ascii=False, indent=1))
    print(f"wrote {out.relative_to(ROOT)}; ledger total ${spent():.4f}")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
    from gemini_common import load_key  # noqa: E402
    KEY = load_key()
    asyncio.run(main())
