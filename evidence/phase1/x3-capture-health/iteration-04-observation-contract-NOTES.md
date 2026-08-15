# Iteration 4 — capture-health observation contract prototype

Question: can `LiveV2SessionSnapshot` alone support the required server-authoritative
recency, sustained-silence, sequence-gap, and backpressure judgments?

Run:

```bash
PYTHONPATH=. .venv/bin/python evidence/phase1/x3-capture-health/iteration-04-observation-contract-probe.py \
  --write evidence/phase1/x3-capture-health/iteration-04-observation-contract.json
```

Verdict: **no**. The real v2 acceptance path retains cumulative lane accounting and lane
health. It drops a server arrival clock, silence history once a frame is accounted, and the
history of both out-of-order and capacity rejections. The raw output records equal snapshots
for silent versus voiced frames, after elapsed server time, and after repeated rejections.

The proposal is intentionally limited to the observation carrier in
`docs/design-capture-health-observation-contract.md`. It introduces no status policy or
threshold; those require a separate measured decision.
