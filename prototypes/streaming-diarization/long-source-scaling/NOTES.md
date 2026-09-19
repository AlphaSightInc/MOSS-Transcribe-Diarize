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

Word-producing deterministic speech at 5/15/30 minutes kept peak Python memory to
0.72/1.06/1.41 MB, retained events at the configured 1,000 cap, and kept snapshot/Stop below
0.03/0.9 ms. However, feed CPU grew 1×/7.07×/26.8× while output grew 1×/3×/6×. The interrupted
201-minute control reached 193.36 MB after 5:44 at about 100% CPU. The stack showed repeated
full base-surface parsing during publication. Verdict: source storage passes; transcript
surface construction is an O(duration²) blocker until its cache/invalidation seam is fixed
and the scaling receipt is rerun.

Machine receipts: `results.json`, `speech-scaling-results.json`.
