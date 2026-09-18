# WP15 real-decoder measurements — fresh continuation

The uninterrupted 600-second run passed finalization. The uninterrupted
1800-second rerun is UNMEASURED: 1382/1500 authorized calls are charged, leaving
118. A request for 2600 cumulative calls remains unanswered. The measured call
rate projects roughly 1060 additional calls for 1800 seconds; this is an estimate,
not permission or a completed measurement. Long-meeting durability is not accepted.

## F1 — authoritative 600-second result

Evidence: `real-1789711765822268000/` and `real-600-unpaused-console.txt`.
Production source: `826af986e498a183cffacdf35a8ddedba2d38d23`; local measurement
harness changes are committed with this report. Own stack 17875, own tunnel 18115,
isolated manifest with max_tape_bytes=57,600,000. System: looped Bill Ackman;
microphone: Keyu Jin at -10 dB for 300 seconds, then zeros. No post-Stop heartbeat.

- Capture: 600.005273 s wall time, zero pauses; 2400 two-lane frames.
- Accepted/accounted: 9,600,000 / 9,600,000 samples.
- Stop response: HTTP 202, stop_in_progress. Stop-to-final: 179.408107 s.
- Outcome: final; saved/reopened SQLite status: completed, not interrupted.
- Saved words: 2589; reopened SQLite words equal the terminal snapshot.
- Downloaded MP3: 600.000000 s, 3,600,765 bytes, 16 kHz mono.
- Decoder: 460 starts / 460 finishes; measured maximum one in flight (ceiling two).
- RSS: first capture 631.406 MiB; last capture sample 1057.562 MiB at 570.056 s;
  peak 1201.047 MiB; final 1200.516 MiB. 27 primary and 27 independent samples;
  the independent 30-second sampler also covers the blocking Stop request.
- Contention: 8/27 resource samples detect other traffic; shared running peak 2,
  waiting peak 0. These are shared-GPU timings, not isolated latency claims.

## F2 — tape evidence and limits

`tape-release.jsonl` records the production coordinator before and after release.
System, microphone, and mixed tapes each held 19,200,000 bytes, were complete,
had no gaps/degradation, and released to zero. Actual aggregate retained tape:
57,600,000 bytes before release, zero afterward.

The configured 57.6 MB bound is PER TAPE: three tapes expose aggregate configured
capacity 172.8 MB. It is not a 57.6 MB bound on the whole process or all tapes.
The 1800-second boundary, longer-duration RSS plateau, and behavior beyond that
boundary remain UNMEASURED. The 600-second RSS observations alone do not establish
a leak or a long-meeting plateau.

## F3 — every attempt retained; no budget reset

| Evidence suffix | Requested audio | Charged calls | Result |
| --- | ---: | ---: | --- |
| real-1789708595746118000 | 600 s | 0 | Setup failure: http variable shadowed http.cookiejar; fixed. |
| real-1789708635052538000 | 600 s | 194 | Stopped after confirmed foreign traffic; old queue-only guard missed it. |
| real-1789708923565536000 | 600 s | 460 | Final/completed, Stop 173.485438 s, 2589 words, MP3 600 s; 1440.764321 s paused. Not valid real-time timing. |
| real-1789711191163361000 | 1800 s | 268 | Stopped per Fable steering at 270 s audio; unfinished. 267 dispatched, one reservation waiting behind PAUSE. |
| real-1789711765822268000 | 600 s | 460 | Uninterrupted result in F1. |

Fable's later instruction supersedes the original pause rule: sibling GPU work
is authorized. The final WP15 runner samples preflight/running/waiting/completions
but never pauses for contention. Both stopped attempts retain their termination
reason, measurements, and call accounting. All owned processes are stopped.

The unpaused 1800-second command is prepared, with corpus shape and remaining
budget in `real-1800-unpaused-prepared.txt`. It has not been dispatched.
After explicit budget authorization, use the COMMON Python and environment:
`python prototypes/stop-lease/longrun.py --seconds 1800 --total-budget 2600`.
