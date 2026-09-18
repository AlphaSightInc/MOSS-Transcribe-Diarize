# WP15 fresh verification result

PASS: lifecycle controls, full Python/frontend gates, uninterrupted 600-second
real-decoder finalization. INCOMPLETE: uninterrupted 1800-second run, 30-minute
memory plateau, and tape behavior at the 57.6 MB per-tape boundary.

Source: `mvpfix/wp15-stop-lease-longrun` at
`826af986e498a183cffacdf35a8ddedba2d38d23`. Initial checkout clean. Import resolved
inside this exact WP15 worktree using prescribed auto-mvp-0911 Python,
PYTHONPATH=., PYTHONDONTWRITEBYTECODE=1, and TMPDIR=$PWD/.wp15/t.
Production code unchanged this turn; harness repairs and evidence are committed.

## F1 — defect and contract

The helper lease stayed armed while accepted Stop awaited raw draining, allowing
helper departure to abort server-owned completion. `moss_transcribe_diarize/app/live_transport.py:251`
releases only helper failure coordination after capture closes successfully and
before adapter.stop. Refused/unconsumed Stop and pre-acceptance expiry retain
existing behavior. The browser sends a final stopped heartbeat then Stop;
polling does not renew a lease. Deadline expiration bounds only the caller wait.
ADR-0004 records the boundary.

## F2 — fresh gates, all exit 0

| Command | Actual result | Evidence in evidence/mvpfix/wp15/ |
| --- | --- | --- |
| python -m pytest -q -p no:cacheprovider tests | 1860 passed, 2 skipped, 37 subtests passed; 21 warnings; 148.19 s | fresh-python-full.txt |
| npm --prefix frontend test -- --run | 27 files / 242 tests passed; 2.45 s | fresh-frontend-full.txt |
| npm --prefix frontend run typecheck | exit 0 | fresh-frontend-typecheck.txt |
| npm --prefix frontend run build | exit 0; Vite build 72 ms; assets identical | fresh-frontend-build.txt |
| python prototypes/stop-lease/run.py --delay 90 --output evidence/mvpfix/wp15/fresh-prototype.json | 8/8 passed | fresh-prototype.json, fresh-prototype.txt |

Stub controls (a) continued heartbeat, (b) departure, (c) deadline=0 with truthful
202, and (d) 35-second outage pass at raw-drain and terminal-refinement stages.
These are simulated lease-time controls, not 90-second inference measurements.
Full suite includes the 12-case accepted-Stop matrix with genuine failed refinement
and caller cancellation; identical saved document after SQLite reopen is asserted.

Prior wall-clock stub artifacts were read: 45.088459 s held-drain and 90.096846 s
held-terminal total experiment time; final/completed, three saved words each.
They were not rerun or relabeled as decoder latency.

## F3 — real decoder and remaining authority

Unpaused 600 s: capture 600.005273 s; Stop-to-final 179.408107 s; final/completed;
2589 persisted words; MP3 600.000000 s; 460 calls, max one in flight.
RSS first/peak/final: 631.406 / 1201.047 / 1200.516 MiB. Sibling contention in
8/27 resource samples; shared running/waiting maxima 2/0. Not isolated latency.
All three tapes complete: each 19.2 MB before release, zero after. The 57.6 MB cap
is per tape (aggregate configured capacity 172.8 MB), not process memory.
Full measurements/attempts: `evidence/mvpfix/wp15/REAL-DECODER.md`.

Initial explicit authority raised COMMON's 200-call cap to 1500. Later steering
removed pauses and authorized one unpaused rerun, without replacing the numeric
cap. Used 1382 charged calls; 118 remain. Requested 2600 total; no answer received.
The unpaused 1800-second rerun is UNMEASURED, not a product failure. Do not call
WP15's complete long-meeting durability requirement accepted.

## F4 — deviations and cleanup

- Fixed prepared-runner UnboundLocalError before inference; retained failure.
- Initially followed WP6 pause rule; later Fable steering rejects paused cadence.
  Retained those results separately and reran 600 s once without pauses.
- Reused WP6 accounting/stack with explicit 18115 support; added existing per-tape
  accounting capture and independent RSS sampling through blocking Stop.
- Full Python suite regenerated BOTH WP2 screenshots, not only 1280 predicted in
  VERIFY.md. Traced to tests/phase2/test_lane_consumer_geometry.py:44; restored both
  from HEAD. Frontend assets unchanged.
- Normalized trailing whitespace/blank EOF in new text logs only. Existing short
  /tmp fixture sockets were created/removed by the suite, as VERIFY.md documents.
- No push, merge, deploy, shared-service restart, or peer message. Owned stack,
  tunnel, sampler, and probes stopped; final cleanup evidence retained.
