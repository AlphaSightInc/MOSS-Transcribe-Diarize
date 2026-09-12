# Acceptance helper lifetime — 2026-09-11

Question: does waiting on unrelated file/URL work starve an acceptance-owned live
Meeting's 30-second helper lease? Primitives: one session, one serialized heartbeat
sequence, one independently scheduled owner, explicit owner shutdown. The wait
must not control helper presence. Terminal/revoked sessions must not be recreated;
frame retry/sequence and server lease policy remain unchanged.

Baseline: the corrected two wait tests fail against 484d2324 (zero heartbeats while
waiting). Fix: send immediately on creation, then every five seconds independently
of blocking caller requests. Explicit and scheduled sends share a lock/sequence;
borrowed replay adapters share the original helper rather than reset its sequence.
A lost response reserves its sequence because the server may have accepted it.
Stop/abort/cleanup/close retire owned helpers; revocation retires the revoked
workspace's helpers without attempting cleanup through revoked authority.

Falsifier: a real 35-second idle wait expires the 30-second lease, or sequence
validation rejects concurrent sends. Both are tested on the actual client path.

Run from the worktree root, against an existing local stack with a 30-second lease:

```sh
.venv/bin/python prototypes/streaming-diarization/acceptance-helper/measure_wait.py --ca /path/to/localstack/cert.pem --out /tmp/helper-wait.json
```

Measured on https://127.0.0.1:17861: **35.004 seconds**, zero frames, seven successful
heartbeats (sequences 0–6), maximum gap **5.013 seconds**, session still active.
`results.json` retains the observation. Fresh workspace, own empty session aborted
in cleanup; database not reset. No decoder request needed. The client was the
working tree based on 484d2324; existing local server b76b5b5c was untouched.

Verdict: fixed acceptance starvation; no server lease change. Unit tests also cover
concurrent sends, ambiguous acknowledgements, shutdown and revoked-owner cleanup.
