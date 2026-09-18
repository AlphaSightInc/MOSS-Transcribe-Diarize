# WP30 retained measurements

Q1 baseline, one process, both lanes active, 0.6 s stub. Before production release fix.

| Session | Post-final RSS MiB | Traced MiB | Stop-to-final s | Retained album entries | Retained sweep spans |
|---|---:|---:|---:|---:|---:|
| 1 | 991.81 | 60.63 | 313.107 | 40 | 480 |
| 2 | 1018.31 | 84.62 | 307.585 | 80 | 960 |
| 3 | 1072.12 | 90.54 | 307.382 | 120 | 1440 |
| 4 | 1095.23 | 96.06 | 296.630 | 160 | 1920 |
| 5 | 1078.31 | 91.46 | 289.222 | 200 | 2400 |
| 6 | 1121.73 | 94.32 | 289.839 | 240 | 2880 |

All six final; 14,400 acknowledged frames, 0 retries; 3,660 stub requests.
All 2,880 synthetic lane/time/text segments equal the independent oracle,
8,640/8,640 expected words; saved SQLite text equal to final output.
All 14,400 foreign probes 404. All tapes and source replay acknowledgements released.
Startup RSS 628.44 MiB; peak sampled RSS 1190.30 MiB. Immediate final RSS is
not a stable idle floor. Trace owners include surviving lane albums/sweep vectors,
retained final documents and cyclic HTTPS buffers; native RSS attribution remains
unmeasured. The highest first-to-second trace increase is sslproto.py:278,
21,238,281 bytes; do not attribute all RSS growth to lane evidence.

Q1 release prototype: four lane owners freed across two short final sessions;
all final snapshot/journal/match/count comparisons equal. Traced deltas 75,697
and 70,726 bytes after collecting unrelated pre-existing dead cycles.
Production lifecycle test fails on old code and passes on fixed code for final,
failed terminal and no terminal reader. No production garbage-collection call.

Q2/Q3 use 0.15 s stub, with production voice embedding and observed HTTPS costs.
Report actual capture wall time alongside audio duration; this is not a claim
that the input driver sustained browser-rate delivery under saturation.
Queues are sampled every 5 s, RSS every 30 s plus checkpoints; sampled maxima
are lower bounds on instantaneous peaks.

Q2, four simultaneous two-lane sessions, 600 s each, 0.15 s stub.
Production a565c23a (finalized lane release present).

| Session | First text s | Maximum capture update gap s | Capture wall s | Stop-to-final s | 429 retries |
|---|---:|---:|---:|---:|---:|
| 1 | 17.849 | 17.849 | 2240.020 | 1009.402 | 924 |
| 2 | 15.864 | 15.864 | 2238.458 | 1007.487 | 926 |
| 3 | 10.957 | 12.846 | 2235.210 | 1003.616 | 911 |
| 4 | 13.865 | 13.865 | 2237.311 | 1005.710 | 915 |

4/4 final. All 1,920 exact synthetic lane/time/text segments and 5,760 expected
words recovered; final output matches reopened SQLite. All 9,600 foreign probes
returned 404; 9,600 frames acknowledged. All 3,676 refusals are HTTP 429, code
canonical_queue_full, retryable=true. Canonical queue max 16/session;
pending_signals max 1. Canonical dispatch: 960 queued/started/processed;
2,871 contended pair observations, maximum skew 1, fairness gate passed.
Peak sampled RSS 1,557.08 MiB; immediate final 1,384.05 MiB / traced 91.36 MiB.
Final retained album entries, sweep spans, tape bytes and replay acknowledgements:
all zero. Session/history state intentionally remains readable.
Verdict: bounded handling, fair canonical dispatch and final durability passed;
real-time four-session capacity and fast Stop are falsified for this measured
instrumented fixture. No scheduling or policy change justified by these records.
First-text/update gaps are API-observed text changes, not browser paint times.
Capture wall time includes retries, HTTPS requests, polling and isolation probes;
production embedding plus tracing also consume local CPU. Timing transfer to an
un-instrumented deployment is unmeasured. Stop drains rolling work after canonical
queues empty; this is progress, not proof of acceptable latency.
