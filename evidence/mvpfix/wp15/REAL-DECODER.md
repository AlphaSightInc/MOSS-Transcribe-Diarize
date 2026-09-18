# WP15 real-decoder measurements

600-second session: UNMEASURED.
1800-second session: UNMEASURED.
Stop-to-final, saved words, MP3 duration, RSS plateau, tape retention: UNMEASURED.

Reason: COMMON's cumulative 200-request cap conflicts with the expected work of
both per-lane durations. No budget increase received as of preparation. The
pending request asks for at most 3000 total calls, at most two in flight, still
only private tunnel 18115 and only quiet GPU. No inference requests dispatched.
This is a measurement limitation, not a claim that either duration fails.

Prepared command (COMMON Python, own cwd, PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.):
python prototypes/stop-lease/longrun.py --seconds 600
python prototypes/stop-lease/longrun.py --seconds 1800
Use --total-budget only after explicit authorization. The default stays 200.

`longrun-prepared.txt` establishes corpus availability and replay shape only.
`gpu-preflight.json` contains three read-only samples through an owned 18115
forward, then tunnel shutdown. A quiet sample grants no additional request budget.
