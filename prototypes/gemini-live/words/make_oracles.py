"""One full public-clip batch word-timestamp pass per acceptance clip for latency alignment."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402
from gemini_common import diarize_window, read_wav, spend  # noqa: E402
from run_suite import EXTENDED  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.2-STATUS.md")
IDS = ["discussion_jamie_dimon_180s", "discussion_rtfl_90s",
       "interview_adam_frank_180s", "interview_bill_ackman_60s",
       "interview_keyu_jin_60s", "mono_javier_intro_50s",
       "benchmark_5m:acquired_alphabet"]


def status(line: str) -> None:
    with STATUS.open("a") as f:
        f.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}] {line}\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=["base", "extended"], default="base")
    args = p.parse_args()
    for cid in IDS if args.set == "base" else EXTENDED:
        c = next(x for x in clips() if x.clip_id == cid)
        p = EVIDENCE / f"oracle-{cid.replace(':', '_')}.json"
        old_javier = EVIDENCE / "javier-full-word-oracle.json"
        if cid == "mono_javier_intro_50s" and not p.exists() and old_javier.exists():
            p.write_text(old_javier.read_text())
        if p.exists():
            status(f"Batch timestamp oracle {cid}: retained prior receipt {p}; no call.")
            continue
        try:
            pcm = read_wav(c.audio)
            r = diarize_window(pcm, diarize=False, ledger_lane="P52", max_attempts=3)
            d = {"clip": cid, "audio_s": len(pcm) / 16000,
                 "words": [{"text": w.text, "start": w.start, "end": w.end} for w in r.words],
                 "timing_anomalies": r.timing_anomalies, "cost_usd": r.cost_usd(),
                 "usage": r.usage, "cached": r.cached}
            p.write_text(json.dumps(d, indent=2) + "\n")
            status(f"Batch timestamp oracle {cid}: {len(r.words)} words, anomaly {r.timing_anomalies}, "
                   f"cost ${r.cost_usd():.6f}, cached={r.cached}; receipt {p}.")
        except Exception as exc:
            status(f"Batch timestamp oracle {cid}: FAILED {type(exc).__name__}: {str(exc)[:250]}; parking oracle suite.")
            break
    print(spend("P52"))


if __name__ == "__main__":
    main()
