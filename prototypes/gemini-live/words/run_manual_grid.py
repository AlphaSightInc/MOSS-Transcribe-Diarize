"""Finish W2/W3 N=2,3,5 manual-turn grid on one public 50 s clip."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.2-STATUS.md")
CASES = [("w2", 3), ("w2", 5), ("w3", 3)]


def status(line: str) -> None:
    with STATUS.open("a") as f:
        f.write(f"[{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}] {line}\n")


def main():
    for arm, turn in CASES:
        out = EVIDENCE / f"manual-grid-{arm}-{turn}s.json"
        log = out.with_suffix(".log")
        cmd = [sys.executable, str(HERE / "proto_words.py"), "--arm", arm,
               "--clip", "mono_javier_intro_50s", "--turn", str(turn),
               "--quiet", "--output", str(out)]
        if arm == "w2":
            cmd += ["--thinking", "0", "--max-output", "32"]
        with log.open("w") as f:
            proc = subprocess.run(cmd, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                                  stdout=f, stderr=subprocess.STDOUT)
        if proc.returncode or not out.exists():
            status(f"Manual grid {arm} N={turn}s FAILED exit={proc.returncode}, receipt {log}; parking grid.")
            break
        d = json.loads(out.read_text())
        status(f"Manual grid {arm} N={turn}s: sent {d['sent_s']}/{d['audio_s']} s, "
               f"WER {d['score']['wer']}, {d['selected_updates']} final chunks, "
               f"uncovered {d['dropped_reference_seconds']}/{d['reference_speech_seconds']} s, "
               f"audio_out_bytes {d['model_audio_bytes']}, usage_events {d['usage_observations']}, "
               f"errors {len(d['errors'])}; receipt {out}.")
    print("manual grid complete")


if __name__ == "__main__":
    main()
