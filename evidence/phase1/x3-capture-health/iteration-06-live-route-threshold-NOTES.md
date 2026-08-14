# Iteration 6 — capture-health live-route threshold probe

Question: given the measured Chrome worklet cadence, which server-observed conditions should
move a two-lane capture out of the healthy recording claim, and does the production route reset
each condition after recovery?

Run:

```bash
PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-06-live-route-threshold-probe.py \
  --write evidence/phase1/x3-capture-health/iteration-06-live-route-thresholds.json
```

The probe creates local `create_app` instances, pairs normally, and exercises the authenticated
v2 frame, helper-heartbeat, and snapshot routes. It records server-monotonic arrival times after
accepted frames, a real post-frame wait, four silent descriptor frames, four classified sequence
rejections, and four classified retention-capacity rejections. It then proves recovery only by a
subsequent accepted route frame (and, for capacity, the real peer-lane mixer drain first).

Verdict: at the measured descriptor geometry of 8,000 samples / 16 kHz, use 2,000 ms of absent
server arrival, 32,000 consecutive silent samples, or four consecutive classified rejection
outcomes as the non-healthy thresholds. Four frame periods are about 3.9 times the committed
Chrome hidden-tab p95 (506.5 ms), while all four conditions recover on production-route success.

Scope: the local route probe is not a Chrome run and does not cover real display capture or model
inference. Chrome cadence comes from the already-committed harness measurement named in the JSON.
Terminal-session reason reachability remains owned by x6.
