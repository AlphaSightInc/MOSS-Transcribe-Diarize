# WP15 — lease fix verified; 30-minute requirement incomplete

Branch: mvpfix/wp15-stop-lease-longrun. Tested production base: 826af986e498a183cffacdf35a8ddedba2d38d23.
Verification commit: containing commit; final SHA reported in pane.

- **F1 — defect/fix.** Helper lease could interrupt accepted Stop during raw drain.
  `moss_transcribe_diarize/app/live_transport.py:251` releases helper coordination
  after capture closes, before adapter.stop. Server owns completion; deadline bounds caller wait.
- **F2 — controls.** (a) continued heartbeats; (b) departure; (c) deadline=0 returns 202;
  (d) 35 s outage: 8/8 pass across drain/refinement, simulated 90 s lease time.
  Full suite covers 12 cases including failure/cancellation and identical SQLite reopen.
  Prior wall controls: 45.088459 / 90.096846 s total, final/completed, three words each.
- **F3 — uninterrupted 600 s.** Capture 600.005273 s; Stop→final 179.408107 s;
  final/completed, 2589 persisted words, MP3 600.000000 s; 460 calls, max one in flight.
  RSS first/last-capture/peak/final: 631.406 / 1057.562 / 1201.047 / 1200.516 MiB.
  27 primary + 27 independent samples; shared running/waiting peaks 2/0;
  sibling contention in 8/27 samples. Timings carry that caveat.
- **F4 — tape.** Three complete tapes, 19.2 MB each, all released to zero.
  57.6 MB is PER TAPE; aggregate configured capacity 172.8 MB.
- **F5 — 30 min UNMEASURED.** Paused attempt stopped at 270 s audio per Fable steering.
  Unpaused rerun needs budget: 1382/1500 charged, 118 remain; 2600 requested, unanswered.
  30-minute Stop→final, words, MP3, RSS plateau, and exact-bound tape behavior unmeasured.
  Long-meeting durability not accepted. Paused 600 s retained, not real-time timing.
- **F6 — fresh gates.** Python 1860 passed, 2 skipped, 37 subtests, 21 warnings, 148.19 s.
  Frontend 27 files / 242 tests, 2.45 s; typecheck/build exit 0, assets unchanged; prototype 8/8.
- **F7 — changes/limits.** Runner shadowing fix; contention recorded without pauses;
  independent RSS/per-tape accounting; all failed attempts retained.
  Changed prototypes/stop-lease/{longrun.py,NOTES.md}, prototypes/capacity-campaign/stack.py,
  REAL-DECODER.md, fresh evidence, VERIFY-RESULT.md, this report. Production fix inherited.
  Both generated WP2 screenshots restored. Owned stack/tunnel/sampler/probes stopped.
  No other checkout writes, push, merge, deploy, shared-service changes, or peer messages.

Evidence: `real-1789711765822268000/{result,audit}.json`, `rss.jsonl`, `tape-release.jsonl`;
all attempts and budget accounting in REAL-DECODER.md.
