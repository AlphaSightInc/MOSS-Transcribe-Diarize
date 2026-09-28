"""P52 paced accept6 + acquired_alphabet suite; appends status after each clip."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "common"))
from corpus import clips  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.2-STATUS.md")
CLIPS = ["discussion_jamie_dimon_180s", "discussion_rtfl_90s",
         "interview_adam_frank_180s", "interview_bill_ackman_60s",
         "interview_keyu_jin_60s", "mono_javier_intro_50s",
         "benchmark_5m:acquired_alphabet"]
EXTENDED = [c.clip_id for c in clips("gold9")] + [
    "benchmark_5m:lex_bill_ackman", "benchmark_5m:lex_keyu_jin",
    "benchmark_5m:lex_javier_milei"]


def status(line: str) -> None:
    with STATUS.open("a") as f:
        f.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}] {line}\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--arm", choices=["w1", "w2", "w3", "w4"], required=True)
    p.add_argument("--set", choices=["base", "extended"], default="base")
    p.add_argument("--subset", choices=["all", "gold9", "lex5m"], default="all")
    p.add_argument("--turn", type=int, default=0)
    p.add_argument("--window", type=int, default=8)
    p.add_argument("--stride", type=int, default=2)
    p.add_argument("--silence-ms", type=int, default=200)
    p.add_argument("--thinking", type=int)
    p.add_argument("--max-output", type=int)
    p.add_argument("--tail-silence", type=float, default=0.0)
    args = p.parse_args()
    variant = f"{args.arm}-{args.set}-t{args.turn}-l{args.window}-s{args.stride}-vad{args.silence_ms}-tail{args.tail_silence:g}"
    if args.subset != "all":
        variant += f"-{args.subset}"
    if args.set == "base" and args.subset != "all":
        p.error("--subset applies only to --set extended")
    selected = CLIPS if args.set == "base" else (
        [c.clip_id for c in clips("gold9")] if args.subset == "gold9" else
        EXTENDED[-3:] if args.subset == "lex5m" else EXTENDED)
    results = []
    for clip in selected:
        tag = clip.replace(":", "_")
        out = EVIDENCE / f"suite-{variant}-{tag}.json"
        log = out.with_suffix(".log")
        cmd = [sys.executable, str(HERE / "proto_words.py"), "--arm", args.arm,
               "--clip", clip, "--quiet", "--output", str(out), "--drain", "12",
               "--turn", str(args.turn), "--window", str(args.window),
               "--stride", str(args.stride), "--silence-ms", str(args.silence_ms),
               "--tail-silence", str(args.tail_silence)]
        if args.thinking is not None:
            cmd += ["--thinking", str(args.thinking)]
        if args.max_output is not None:
            cmd += ["--max-output", str(args.max_output)]
        with log.open("w") as f:
            proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                  stdout=f, stderr=subprocess.STDOUT)
        if proc.returncode or not out.exists():
            status(f"{variant} {clip}: FAILED exit={proc.returncode}; receipt {log}; stopping suite.")
            break
        d = json.loads(out.read_text())
        results.append({"clip": clip, "wer": (d.get("score") or {}).get("wer"),
                        "updates": d.get("selected_updates"), "sent_s": d.get("sent_s"),
                        "audio_s": d.get("audio_s"), "cost_usd": d.get("cost_usd"),
                        "cost_complete": d.get("cost_complete"),
                        "model_audio_bytes": d.get("model_audio_bytes"),
                        "dropped_reference_seconds": d.get("dropped_reference_seconds"),
                        "reference_speech_seconds": d.get("reference_speech_seconds"),
                        "latency_p50_s": d.get("latency_p50_s"), "errors": d.get("errors") or d.get("window_errors"),
                        "timing_anomaly_calls": d.get("timing_anomaly_calls"),
                        "timing_clamped_words": d.get("timing_clamped_words"),
                        "timing_dropped_words": d.get("timing_dropped_words")})
        r = results[-1]
        status(f"{variant} {clip}: sent {r['sent_s'] or r['audio_s']}/{r['audio_s']} s, "
               f"WER {r['wer']}, updates {r['updates']}, model_audio_bytes {r['model_audio_bytes']}, "
               f"observed cost {r['cost_usd']} (complete={r['cost_complete']}), "
               f"uncovered seconds {r['dropped_reference_seconds']}/{r['reference_speech_seconds']}, "
               f"errors {r['errors']}, "
               f"timing anomaly calls {r['timing_anomaly_calls']}, clamped/dropped "
               f"{r['timing_clamped_words']}/{r['timing_dropped_words']}; receipt {out}.")
    summary = EVIDENCE / f"suite-{variant}-summary.json"
    summary.write_text(json.dumps(results, indent=2) + "\n")
    print(summary)


if __name__ == "__main__":
    main()
