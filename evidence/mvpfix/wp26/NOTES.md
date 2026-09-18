# WP26 — unassigned terminal turns

Base 625dbaa97b55fb5be66e06db9bfe4d8c985fd935; branch mvpfix/wp26-unassigned-terminal.
Prototype question, primitives, falsifier, provenance and verdict:
`prototypes/streaming-diarization/wp26/NOTES.md`.

## F1 — measured cause and fix

Retained 180 s system terminal output: three local labels compete for two
canonical voices. One local label loses the one-to-one overlap assignment.
The adapter incorrectly skipped the cropped fallback merely because labelled
overlap existed. `finalize_lanes` now probes if coverage is absent OR the mapped
speaker is None. Existing assigned mappings stay authoritative. No change to
the mono overlap mapper, thresholds, identity policy, nine-key frame protocol,
QUALITY_BOUNDS, two-Refresh sentinel, readiness or lifecycle checks.

Reconstructing 69 accepted causal preparations from original repeated public
PCM yields Lex crop scores .9404659566 (4.14 s) / .4899272409 (.72 s), versus
Ackman 0. Both pass existing score .35 / margin .1 and identify speaker-0004.
Time-nearest same-lane evidence agrees but is not needed and is not implemented.
Unsuccessful probes keep unattributed words; a guess must not override abstention.

Production fallback replay of the captured post-mapping proposal: 2/2 missing
turns recovered, 16 words / 4.86 s; 54/54 assigned system segments unchanged;
56/56 retain words, times and lanes. Probe durations .63730 + .11523 = .75253 s
on this machine. Not a measured increment to live Stop latency.
Original runtime album vectors, raw decoder labels and pre-terminal surface
are absent. References are reconstructed, and coverage for already assigned
segments derives from retained rows. The actual mapper conflict is independently
exercised by the synthetic three-label/two-identity regression through the real
terminal finalizer. No native-runtime replay or new API/Stop run claimed.

## F2 — census, exact populations

All 17 retained WP12 state databases and WP17's state database read immutable,
after confirming their WAL files were empty. No source DB writes. Count only
completed meetings; saved-store population includes recognition sessions.

| Population | Meetings affected/total | Unassigned/total segments | Words | Summed segment seconds |
|---|---:|---:|---:|---:|
| WP12 accepted overlap | 1/3 | 2/127 | 16/1546 | 4.86/493.27 |
| WP17 accepted overlap | 0/27 | 0/212 | 0/2370 | 0/714.71 |
| WP12 historical controls | 2/19 | 64/476 | 674/5362 | 190.69/1576.01 |

Historical controls are discarded acoustic/mono implementations, not current
defect prevalence. WP12 saved documents omit lane metadata: do not guess it.
Separate retained-surface census: WP12 accepted 2/127 over 3 runs; WP17 0/178
over 16 runs; WP12 controls 64/423 over 15 runs. These overlap the saved-store
population and must not be added. Full interval counts in survey.json.
This is a structural failure when decoder labels outnumber known identities;
the few looped public clips do not establish frequency in arbitrary meetings.

## P5 — same-lane simultaneous speech remains a model limitation

Alternating participants on one system lane require correct speaker attribution.
Simultaneous participants arrive already mixed into one waveform. This repair
can label emitted words; it cannot reconstruct omitted speech or split the mix.
Retained synthetic mono-waveform decoder measurements (p5-retained.json): parity
emits 184 words, retains 35/54 first-source and 39/41 second-source unique tokens.
Second source -10 dB: 134 words, retention 45/54 and 1/41. First source -10 dB:
76 words, retention 0/54 and 36/41. These token witnesses are not WER. Original
system/microphone names identify sources before mixing, not independent decoder
lanes in arm A. Same-tab conferencing capture and raw emitted timestamp/speaker
overlap are unmeasured. Product normalization preserves one owner per interval
within a lane and cannot represent two simultaneous speakers there.
Recommendation for the user's P5 decision: exclude reliable same-lane simultaneous
speech recovery from MVP acceptance; retain alternating within-lane diarization.
P5 is not decided by this code change. No separation model or new policy added.

## Validation and deviations

- Before fix: regression 2 failed (both prove the probe was skipped).
- Initial focused attempt: 104 passed / 2 failed / 19 subtests. Both failures
  imported `_browser_workspace_fixtures` without tests/phase2 on PYTHONPATH.
  Same unchanged fixtures with the established path: 106 passed / 19 subtests.
- Full Python: 1912 passed, 2 skipped, 37 subtests, 21 warnings; 153.27 s.
  Both skips require absent operator-provisioned identity/accuracy corpora.
- Frontend: 249 passed / 28 files. Typecheck and build pass; generated assets
  identical. Full raw log content retained, trailing whitespace normalized only.
- Test-only local_scratch.py copied from WP17, redirects socket/temp fixtures
  into this worktree; no assertion or production monkeypatch changed.
- Prototype scripted state output instead of interactive TUI; now absorbed into
  the standing replay bench. No provider calls: 0/400; no tunnel/server started.
- Initial exploratory searches used incorrect module/test filenames and one
  broad search hit generated JS; corrected without writes. No inference from
  those failed lookups. No push, merge, deploy, GitHub or other-worktree writes.
- Fresh verification belongs in docs/verify/wp26/ per existing layout rule,
  not root VERIFY.md. Actual /new result follows in VERIFY-RESULT.md.
