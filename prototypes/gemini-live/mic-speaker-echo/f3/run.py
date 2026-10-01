"""R5-F3: everything at $0 from the recorded answers (one command, throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/mic-speaker-echo/f3/run.py

1. s6_patterns  rule H on each recorded pattern (the regression-test seeds)
2. s1_request   the ten production-request draws of R5-D, replayed (asserts R5-D's numbers)
3. s2_witness   rule H on 100 (live sample, whole-recording draw) pairs, with the parameter sweep
4. s3_engine    today vs rule H inside the production engine (cached runs; --rerun to replay them all, ~20 min)
5. s5_summary   request-variant table, product-side losses, every restored run, other cells, spend
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def step(*args, quiet_json=False):
    print("\n" + "=" * 20, " ".join(args), flush=True)
    out = subprocess.run([sys.executable, str(HERE / args[0]), *args[1:]], capture_output=True, text=True)
    lines = [l for l in out.stdout.splitlines() if not quiet_json or not l.startswith("    ")]
    print("\n".join(lines))
    if out.returncode:
        print(out.stderr[-2000:])
        raise SystemExit(out.returncode)
    return out.stdout


step("s6_patterns.py")
kept = []
for fixture in ("sys-zhlatin-en", "sys-zhlatin"):
    text = step("s1_request.py", fixture, "base", "0,1.5,3,5,8", quiet_json=True)
    kept += [json.loads(l) for l in text.splitlines() if l.startswith('{"draw"')]
lost_media_lab = sum("media" in r["names_missing"] for r in kept)
traditional = sum(r["script"] == "traditional" for r in kept)
dropped = sum(r["dropped"] + r["dropped_by_word_gate"] + r["repaired"] for r in kept)
print(f"R5-D baseline: {lost_media_lab} of {len(kept)} draws lose 'Media Lab', {traditional} of {len(kept)} traditional, "
      f"punctuation {min(r['zh_punctuation'] for r in kept)}-{max(r['zh_punctuation'] for r in kept)}, "
      f"parser + word gate + repair removed {dropped}")
assert (lost_media_lab, traditional, dropped) == (8, 1, 0), "the unpatched harness no longer reproduces R5-D's numbers"
step("s2_witness.py")
step("s3_engine.py", *sys.argv[1:])
step("s5_summary.py")
