# WP15 accepted Stop / helper lease — retained regression bench

Question: after accepted Stop, does helper abandonment still own the outcome?
Primitives: capture presence lease; accepted Stop; server-owned drain/refinement;
durable transcript/audio. Invariant: accepted Stop survives client departure;
a genuine worker failure remains explicit and preserves committed words.
Falsifier: post-acceptance lease expiry interrupts durable content.

Baseline 3d5fdfe0: production HTTP + coordinator + runtime + SQLite, stub ASR,
virtual lease clock (not latency measurement), 45-second held-work ordering:
6/8 final; drain/depart and drain/outage interrupted with helper_lease_expired.
All four held-terminal-refinement cases final. Deadline=0 returned 202 and survived.
The first invocation failed fixture import before any session; retained verbatim.

Diagnosis: LiveTransportControl.stop releases helper state only AFTER awaiting
adapter.stop. Runtime Stop already owns its task, but the still-armed 30-second
lease can abort that task's session. The caller's 30-second wait and lease timer
are independent; an older heartbeat expires first. Terminal refinement starts
after raw drain, when transport already releases capture, so it was not the cause.

Proposed minimum repair: release ONLY the helper failure coordinator after v2
capture closes successfully and before awaiting raw Stop. Retain other capture
registries until existing teardown. Rejected/unconsumed Stop keeps its lease.
Late heartbeat cannot rearm because existing release records the terminal owner.

Browser: captureClient.stop drains frame queues, sends a final stopped heartbeat,
POSTs Stop, then closes in finally. ControlPanel calls stop(5); snapshot polling
is read-only. No heartbeat-until-final contract is needed or intended: server
owns accepted Stop, including when the tab disappears. Failed delivery of Stop
before acceptance remains governed by the capture lease.

Commands (COMMON Python; PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.):
python prototypes/stop-lease/run.py --output evidence/mvpfix/wp15/prototype-before.json
python prototypes/stop-lease/run.py --delay 90 --output evidence/mvpfix/wp15/prototype-after.json
Use --wall-clock for actual 30 s lease / 45 or 90 s held stub work.
Bench retained as executable regression evidence for this WP; no production import.

## Repair and falsification results

Production repair: one existing `helper_failures.release(session_id)` call at the
successful capture-close boundary in live_transport.py, before raw Stop yields.
The first regression run failed 3/10 (depart/drain, outage/drain, failure/drain),
then the focused suite passed 130/130. The 90-second virtual-clock rerun passed
8/8. The clock is explicitly simulated, including the 35-second outage boundary.
Request cancellation adds two production HTTP cases: Starlette reports
`No response returned.` to the abandoned caller while server work proceeds.
The first harness treated that expected disconnected response as a test failure
(2 failed, 10 passed); corrected harness then passed 12/12. This was a harness
observation correction, not a second production repair. Restart verification now
compares the complete saved document, not only status or word count.

Real wall-clock stub controls (unchanged 30-second lease):
- Held raw drain, no post-Stop heartbeat, 45 s: final/completed; 45.088459 s total
  experiment time, three saved words, reopened completed.
- Held terminal refinement, no post-Stop heartbeat, 90 s: final/completed;
  90.096846 s total experiment time, three saved words, reopened completed.
These are controlled lifecycle measurements, not inference performance numbers.

Initial full gate: 1858 passed, 2 skipped, 37 subtests, 21 warnings, 145.02 s.
Frontend 27 files / 242 tests passed; typecheck and production build exit 0.
No generated frontend change. Full suite regenerates WP2's tracked screenshot;
restore that generated output from HEAD rather than include unrelated image churn.
The inherited .gitignore contained literal merge markers around WP1/WP6 ignores;
removed markers, retained both sides, added only WP15 scratch ignore.

The full suite uses its existing short /tmp sockets despite TMPDIR being confined
to .wp15/t; those disposable sockets are removed by their fixture teardown. No
other checkout, service, or source file was changed. Local test databases/audio
and all WP15 probe scratch remain in .wp15; no audio or credentials in evidence.

## Real-decoder duration boundary

COMMON caps cumulative WP15 requests at 200, unlike WP6's explicit exception.
WP6's integrated retained result records 1275 completed calls for four 600-second
sessions. This does not prove an exact WP15 denominator, but gives no basis to
promise 600 + 1800 seconds with 200 requests on the more expensive per-lane path.
An asynchronous request for up to 3000 total calls was sent before implementation;
unless explicitly answered, retain 200. Do not treat elapsed time as permission.

`longrun.py --seconds 600` and `--seconds 1800` are prepared, not live-validated.
They use only 18115, two-request ceiling, cumulative request accounting, three
quiet preflight samples, a private 57.6 MB manifest, real-time two-lane replay,
Stop deadline 30, no post-Stop heartbeat, 30 s RSS/shared-load samples, saved words,
MP3 probing, tape events, and read-only SQLite after app shutdown. Microphone:
Keyu Jin at -10 dB through 300 s, then digital zero; system: looped Bill Ackman.
A nonzero shared GPU queue ends the attempt and reports contamination. Zero queue
cannot exclude concurrent traffic; samples retain shared request completions.
No final or leak claim follows from preparation. Exhaustion/failure is recorded,
not silently retried. Higher --total-budget requires explicit authorization.

Final pre-reset full gate: **1860 passed, 2 skipped, 37 subtests passed,
21 warnings in 148.47 s**. Final virtual probe: **8/8 passed**, including
byte-for-byte equivalent saved document after reopening SQLite.
GPU read-only preflight: waiting=0 in 3/3 samples, running=1 in 1/3, shared
completions +16 across 10.0466 s; own inference requests 0. Tunnel closed.
600/1800-second metrics remain UNMEASURED pending explicit budget clarification.
