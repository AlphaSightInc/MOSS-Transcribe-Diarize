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

Evidence text logs preserve messages/counts; trailing whitespace and trailing blank
lines normalized after git diff --check flagged captured tool output formatting.

## Fresh continuation — real decoder authorized 2026-09-18

The new instruction explicitly raises the cumulative WP15 decoder cap to 1500,
with at most two requests in flight. This supersedes the earlier 200-call limit.
Production source remains 826af986; only measurement harnesses are being repaired.

First live attempt failed before inference (0 calls): the Stop response variable
`http` shadowed the imported `http.cookiejar`. Renamed it to `http_status`.
Second attempt consumed 194 calls before operator SIGINT: at 150 seconds shared
completions increased 206 while own starts were only 147, proving foreign traffic
despite zero sampled waiting requests. Its result and request log are retained.
The prepared queue-only guard did not implement WP6's foreign-load pause contract.

Reused the existing WP6 stack and its active/completed request accounting, PAUSE
sentinel, and pause/resume criterion. It now respects an explicitly supplied
base URL, so WP15 uses only 18115 while WP6's default stays 18106. Replay keeps
heartbeats alive during pauses and shifts wall pacing by paused time. The third
attempt exercised the control: two foreign intervals paused capture at 30 seconds
and stopped further decoder starts at 27. Final results are recorded below.

For the subsequent 1800-second run, preflight also requires unchanged completion
counts across quiet samples. Existing per-tape accounting is retained before and
after release: the public release event covers only the mixed tape, while this
per-lane build also allocates system and microphone tapes. This is measurement
instrumentation, not a retention-policy or production-lifecycle change.

600-second result (`real-1789708923565536000`): final/completed, Stop-to-final
173.485438 s, 2589 saved words, MP3 600.000000 s. All 9,600,000 samples accepted
and accounted. Capture wall time 2040.768805 s included 1440.764321 s paused for
foreign load; 53/75 resource samples marked foreign. Sampled terminal intervals
showed no foreign load. Thus this is a measured durability result, not a clean
uninterrupted 600-second capture timing result. No post-Stop heartbeat was sent.
460 decoder starts/finishes, maximum one in flight; SQLite after app shutdown
contained 2589 words equal to the terminal snapshot. RSS first/peak/final:
632.672 / 1244.781 / 1203.891 MiB (75 primary samples, 55 supplemental samples).
The supplemental 30-second sampler covered the blocking Stop request. Public
events retained by this probe did not include terminal completion/tape release;
600-second tape-release accounting is therefore unmeasured, not inferred.

The 1800-second run started with 846 of the 1500 authorized calls remaining.
Preflight: three idle samples, shared completions unchanged at 32034.
No increase beyond 1500 has been received; exhaustion remains a measurement
limit, not evidence of a production failure at that duration.

Fable steering supersedes the earlier pause policy: sibling WP load is authorized;
record contention without pausing real-time capture. The paused 1800-second attempt
was terminated at 270 seconds of captured audio, 268 charged request entries
(267 actually dispatched, one waiting behind PAUSE). The completed paused 600 s
result is retained only as finalization evidence, not real-time durability timing.
Pause logic was removed from the WP15 runner; each duration will be rerun once,
with running/waiting/completion metrics retained as contention caveats.

## Final fresh result (unpaused 600 s; 1800 s budget-blocked)

Authoritative real-time run: `real-1789711765822268000`. Capture 600.005273 s,
zero pauses; Stop-to-final 179.408107 s; final/completed, 2589 persisted words,
MP3 600.000000 s. Decoder 460 starts/finishes, maximum one in flight.
RSS first/last-capture/peak/final: 631.406/1057.562/1201.047/1200.516 MiB.
27 primary and 27 independent RSS samples; sibling contention in 8/27 resource
samples, shared running/waiting peaks 2/0. All three complete tapes held 19.2 MB
each and released to zero. Cap is 57.6 MB per tape, 172.8 MB aggregate configured
capacity. Longer-run plateau and the exact capacity boundary remain unmeasured.

Fresh Python: 1860 passed, 2 skipped, 37 subtests, 21 warnings, 148.19 s.
Frontend: 27 files / 242 tests, 2.45 s; typecheck/build exit 0, unchanged assets.
Fresh simulated 90-second stub controls: 8/8. Both generated WP2 screenshots
were restored (the geometry fixture writes both widths). All owned processes stop.

The unpaused 1800-second rerun was prepared but not dispatched: 1382/1500 charged
calls leaves 118, insufficient for its observed-rate projection (~1060 calls).
Requested 2600 cumulative calls; unanswered. Preserve the numeric cap; do not
spend the remainder on a knowingly incomplete rerun or call long-meeting durability
accepted. Full evidence, authority history and commands: REAL-DECODER.md and
VERIFY-RESULT.md. No push/merge/deploy/shared-service changes.
