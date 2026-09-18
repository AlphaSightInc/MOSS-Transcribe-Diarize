# WP22 — fresh verification: scoped PASS; R1/R2 OPEN

Branch `mvpfix/wp22-memory-longrun`; inspected `977d036edd43620c4272b036f27bc7dbb08b2ed6`.
Final verification SHA: commit containing this report, supplied in final pane response.
Fresh session `01a0b383-f517-7f00-a7d5-ddc67e28aad2`, MOSS:3.3 (%21).
Real-run source `a28eecd9`; accepted WP12 `1745b96f` already merged before C.

F1 — Question: retained audio/history or native encoder workspace? Prototype accepts
memory-pattern caching as a contributor to native retention with varying audio lengths.
Fix: `moss_transcribe_diarize/app/speaker_identity.py:626-629`, disable memory patterns.
18 probes: 1,451,147,264→995,377,152 RSS bytes; 80: 871,596,032→664,567,808.
Vectors **98/98 exact**, max difference 0; retained arrays independently re-compared.
Arena-off/shrink rejected. CPU/provider/model/features/threads/policies unchanged.
Fresh production constructor: **80/80 exact**, max difference 0, inference 63.305835 s;
end RSS 664,633,344 bytes, sampled max 666,845,184; no universal RSS threshold.
Stub A/B audit: 1440 segments/4320 synthetic words exact; 28,800,000 samples committed.
30-min RSS before/after 667,467,776/623,951,872 bytes; all tapes/pending PCM released.
Both lane terminal passes failed from R1; this is not successful refinement.

F2 — Retained real 30-minute run re-audited: final/completed; Stop→final 101.697916 s.
Capture 1800.001202 s; 7200 frames; 28,800,000 accepted/accounted samples; no pauses.
6269 saved words exactly equal terminal snapshot/reopened SQLite; audit JSON exact.
MP3 1800 s, 16 kHz mono, 10,800,693 bytes. 1080/2600 requests; peak two concurrent.
Foreign traffic 36/65 samples; contended timing, not isolated capacity qualification.
Three complete tapes, 57,600,000 bytes each: **172,800,000→0 bytes**, no refusal.
RSS near 5/15/30 min **932.4375/981/973.25 MiB** at 296.093/896.373/1796.800 s.
Post-final **1148.953125 MiB**, sampled peak 1277.484375; start 616, warm 30 s 901.640625.

F3 — Fresh full gates: Python **1911 passed, 2 skipped, 37 subtests**, 153.70 s;
frontend **249 tests/28 files**, 2.62 s; typecheck/build exit 0; assets unchanged.
First-attempt passes. Historical red 1 failed/1 passed; 58 focused passed; baseline
1889/2/37, final fix 1890/2/37, merged/post-real 1911/2/37; old failures retained.

R1 — OPEN, pre-existing exhausted-tape terminal failure. Paths below under app/:
`live_tape.py:291,323` exhausts/refuses read → `live_lane_decode.py:250-254` catches;
`:319-328` calls `_refused` without `gaps` required by
`live_transcript_convergence.py:1053-1059` → TypeError →
`live_service_runtime.py:1198-1203,1221-1227` reports failed/finalizer_defect.
Its finally `:1207-1212` → `:1998-2012` → `live_coordinator.py:1135-1148` releases tapes.
Canonical content survives. Real C's larger tape did not exhaust. No R1 repair here.
R2 — OPEN: post-final RSS exceeds start/warm baseline. Full release and residual
ownership unresolved; long post-final decay, repeated/four-session safety unmeasured.

F4 — Limits: 569 system/55 mic segments; 56 system unattributed; mic ends 299.88 s.
Mic -10 dB first 300 s then zeros; no silent-tail words. Human word/speaker accuracy,
isolated capacity, operator/device fidelity and deployment qualification unmeasured.
Saved equality is durability agreement; no identity-policy tuning.
Files: existing encoder fix/two regression tests/design doc/bench; this commit only
`docs/verify/wp22/VERIFY-RESULT.md`, this report and `evidence/mvpfix/wp22/fresh-*`.
No new real/stub 30-minute capture; VERIFY requires retained audits plus native probe.
Prior deviations: scripted prototype, accelerated stub A/B, SQLite-version bypass in C.
No new deviation; only own worktree modified; no GPU/tunnel/push/merge/deploy/message.
Verification processes exited; ports 18122/17882 clear; no audio/vectors committed.
