# Verdict — long-source scaling

## Structural result

The production 150/120-second window geometry has no 200-minute threshold. Ordered source
storage is the duration primitive; transcript windows are bounded views over it. Storage may
grow linearly with duration, but Python audio memory and per-window inference remain bounded.

## Measured evidence

- File plans at 199/200/201/400 minutes contain 100/100/101/200 windows, cover the full tail,
  retain contiguous ownership, and never exceed 150 seconds per window. Planning peak Python
  allocation was 18–38 KB.
- Interrupted three-window decoding resumed from two atomic records without re-decoding the
  prefix. Re-extracting prefix audio only for resolvers that require it restored identical
  text and identity; missing prefix audio was the falsifying control.
- The owner-bound File application completed 101 accelerated windows for 201 minutes, saved
  the exact final segment at `[12,059, 12,060]`, and returned that tail after app/database
  reopen.
- Actual live runtime at 201 minutes retained 192,960,000 samples / 385,920,000 bytes. Stop
  ran 101 terminal windows, published `final`, and released the tape. Abort released the same
  complete source without terminal work. Peak traced Python memory was 6.85/6.86 MB.
- The 57,600,000-byte control refused exactly one 32,000-byte frame after 30 minutes and
  reported terminal `unavailable`; it did not silently publish a partial terminal result.
- Buffered flush and close failure controls reproduced acceptance/raise faults before repair.
  The tape now types seek/write/flush/close failures as `tape_storage_failed`; release remains
  non-throwing. Known gaps and cached digital silence refuse before terminal WAV creation.
- The currently consumed host manifest contains 9,600,000 bytes (five minutes). An isolated
  candidate manifest with 460,800,000 bytes (240 minutes) passed the same
  `LiveProviderBundleConfig.from_manifest` path used by `phase2_web_cli`. No shared manifest
  was edited and the candidate was not launched.

At 240 minutes, the declared byte budget is per PCM tape, not a promise of unlimited disk.
For a two-lane meeting, mixed + two lane tapes + Phase-2 durable stage + terminal WAV + all
overlapping window scratch project to about 2.88 GB per active meeting; two simultaneous
meetings project to about 5.76 GB before saved MP3/output. Disk exhaustion is an explicit
typed failure, never completion.

## Narrow qualification boundary

The 201-minute run uses nonzero PCM and the production runtime/lifecycle, but deterministic
empty canonical answers and deterministic terminal text. It proves source custody, scheduling,
Stop/abort, terminal geometry, and memory behavior—not acoustic quality or real decoder
throughput. Decoder requests: zero.

Before repair, word-producing deterministic speech at 5/15/30 minutes kept peak Python memory to
0.72/1.06/1.41 MB, retained events at the configured 1,000 cap, and kept snapshot/Stop below
0.03/0.9 ms. However, feed CPU grew 1×/7.07×/26.8× while output grew 1×/3×/6×. The interrupted
201-minute control reached 193.36 MB after 5:44 at about 100% CPU. The stack showed repeated
full base-surface parsing during publication. Verdict: source storage passes; transcript
surface construction was an O(duration²) blocker.

The narrow repair caches each committed span's parsed base segments, appends only the new
span while canonical label meaning is stable, rebuilds on label revision or changed label
meaning, and fast-returns the base when no text-revision overlay exists. It does not change
overlap admission or revision validation. The red unit control counted 65 transcript parses
for 10 commits; green counts 20 (one validation and one surface parse per commit).

After repair, 5/15/30/201 minutes produced 120/360/720/4,824 segments in
0.064/0.188/0.381/3.105 seconds of accelerated feed CPU. Output grew 6× from 5→30 minutes
while CPU grew 5.95×; output grew 6.7× from 30→201 minutes while CPU grew 8.14×, far below
the former quadratic 44.9× shape. The 201-minute point used 4.42 MB peak Python, a
~0.034 ms snapshot, and ~0.84 ms Stop. This is measured near-output-proportional growth over
5/30/201 minutes, not a strict asymptotic claim: immutable tuple append still copies the
accumulated segment references, so arbitrary-duration behavior remains unmeasured. Verdict:
the tested duration control/state passes; acoustic quality and real-decoder throughput remain
deliberately unmeasured without this lane's GPU lease.

A follow-up authority falsifier extended the existing partial-terminal test from a nonzero
start to a zero-start proposal whose end stopped short of the committed frontier. Before the
repair, that short proposal was accepted and finalized the partial surface. The central
terminal guard now requires exact ownership of `[0, committed_end)`; both partial shapes are
refused as `terminal_must_replace_full_surface`. The focused live revision/session/terminal/
window suite passed 110 tests plus 19 subtests. No external trigger or decoder was used.

Machine receipts: `results.json`, `speech-scaling-before.json`,
`speech-scaling-results.json`.

Final product denominator: `pytest -q tests` = 1,986 passed, 5 skipped, 37 subtests.
The broader repository run produced 2,105 passes, 5 skips and six failures: three preserved
prototype controls (intentional L15 product-tree hash drift; two unavailable legacy 92-row
archive tests), plus three initially stale test adapters. The latter were corrected to expect
File `checkpoint_dir` and implement the explicit terminal `has_signal`/`write_wav` seam; their
focused rerun passed 4/4. No production compatibility fallback was restored.

All memory numbers above are traced Python allocations from `tracemalloc`, not whole-process
resident set size (RSS), ffmpeg memory, kernel cache, or aggregate concurrent-service memory.
