"""R5-F2 in one command, $0: every number in NOTES.md from the recorded provider answers (throwaway).

    PYTHONDONTWRITEBYTECODE=1 PYTHON prototypes/gemini-live/mic-speaker-echo/f2/run_all.py [--with-sensitivity]

 1 fixtures.py     rebuild the lanes (public / generated audio)
 2 baseline.py     the unpatched engine must reproduce R5-D's 9 cells
 3 variant.py      today's rule and the candidate on 18 engine cells + 28 round-4 negative samples
 4 sweep.py        local speech 4-24 dB under the tab, short and long turns
 5 scan.py         the negative-lane gate on audio alone
 6 g5_preview.py   the grey microphone row
 7 c3_voice.py     voice match as evidence (rejected candidate C3)
 8 sensitivity.sh  ablations and one-step sensitivity (25 minutes; only with --with-sensitivity), then summary.py
Nothing here can reach the provider: no script is given the key, and replay refuses an unrecorded request.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = [["fixtures.py"], ["baseline.py"], ["variant.py", "final", "{}"], ["report.py"], ["vlong.py"], ["sweep.py"], ["scan.py"], ["g5_preview.py"],
         ["c3_voice.py"]]
for step in STEPS:
    print(f"\n===== {' '.join(step)} =====", flush=True)
    subprocess.run([sys.executable, str(HERE / step[0]), *step[1:]], check=True)
if "--with-sensitivity" in sys.argv:
    print("\n===== sensitivity.sh =====", flush=True)
    subprocess.run([str(HERE / "sensitivity.sh"), sys.executable], check=True)
    subprocess.run([sys.executable, str(HERE / "summary.py")], check=True)
