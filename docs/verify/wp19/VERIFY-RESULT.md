# WP19 fresh-context verification — PASS

Fresh session for the prescribed post-/new verification; /new not repeated.
Tested clean branch `mvpfix/wp19-file-identity-album` at
`30418b2e7c5d15bedf835cb10f95dddf1803ee09`.
All commands ran from the named WP19 worktree, with the environment and Python
interpreter in VERIFY.md. Import resolved inside this tree. No product/test edits.

## Contract and verdict

Question: does File album identity survive a fresh import and replay?
Minimum primitives: window-local voices, one canonical reference per speaker,
retained evidence, speaker-only relabeling. The album connects recurring voices;
the retained evidence lets later admissions repair earlier labels.
Invariants: words/times, decoder windows, live identity policy, and saved schema.
Falsifiers: perfect voices split, replay/reference mismatch, suite failure, or
save/enroll/export integration failure. Each prescribed check addresses these.
Unknowns remain below; no new algorithm, threshold, or policy was introduced.

Prototype verdict reconfirmed: recurring voices no longer compete with multiple
past occurrences. Existing measured composition passes within this corpus/scope.

## A1–A5

- **A1 PASS:** 1 voice × 3 windows → 1 identity; 2 × 3 → 2.
  Fresh probe and suite assertions preserve every segment's text/time.
- **A2 PASS:** A/B/A → S01/S02/S01; unknown 0.6 s voice → S00.
  Separate tests cover known short matches, admission, and returning voices.
- **A3 PASS:** six-minute CPU album replay used retained real decoder responses.
  3 identities / 3 truth voices; 84/92 segments = 91.3043%;
  322.11/338.04 reference-overlap seconds = 95.2875%; 0 abstentions/unscored.
  All six required fields match retained results exactly: identities, mapping,
  segments, correct_segments, all 92 rows, text_time_unchanged.
  Fresh resolver time including embedding: **62.804387 s / 3 windows**.
  Thirty-minute retained album output was freshly rescored against reference.jsonl:
  3 identities / 3 truth voices; 420/464 = 90.5172%;
  1592.97/1684.98 overlap seconds = 94.5394%; 0 abstentions/unscored.
  All 464 attribution rows and all computed fields match retained evidence.
  Same-input legacy controls freshly reproduce **7 → 3** and **31 → 3**
  identities, with exact stitched words/times. A single global one-to-one mapping
  defines accuracy; this measures speaker attribution, not transcription accuracy.
- **A4 PASS:** full suite covers album admission/provisional replacement, ambiguity,
  retrospective relabeling, provider failure, isolation, and existing live oracles.
  Real FileMeetingTasks/WindowedRunner/WAV-MP3 archive save → restart → reopen →
  rename/enroll/private-bank path passes with fake decoder and perfect vectors.
  Five frontend serializers (md/txt/json/srt/vtt) pass on the retained synthetic
  saved artifact. The fresh backend test independently exercises that integration;
  its artifact was not regenerated for the frontend run.
- **A5 PASS:** full Python **1889 passed, 2 skipped, 37 subtests, 21 warnings**,
  **157.94 s**, exit 0. Full frontend **249 passed / 28 files**, **2.72 s**, exit 0.
  Typecheck exit 0. **15-window resolver 332.007926 s including embedding** is
  the retained original measurement; not rerun in this fresh session. No timing
  threshold was specified.

## Wiring and lease determinism

`phase2_web_cli.py` passes `--file-identity` and the live-provider manifest to
`build_file_runner`. Account File vLLM defaults to `AlbumIdentityResolver`
inside `WindowedRunner`; **`--file-identity legacy`** restores the previous
resolver for one release. Live terminal uses a shallow runner copy with the same
decoder and explicit legacy identity. Composition test verifies both resolvers
and decoder identity. Single-window/HF behavior, window decoding, live identity
modules, and saved schema are unchanged. Enrollment reconstructs requested
speaker evidence from retained audio and uses existing admission/bank logic.

Fresh lease proof: **20/20 consecutive separate pytest processes**, all exit 0.
The existing FakeTimer controls scheduling while the test retains the **30 ms**
policy and invokes the real expiry callback after capture and heartbeat renewal.
Assertions establish two timer handles, cancellation of the first, interruption,
preserved transcript/version, and subsequent frame rejection (409).
Original 20/20 retained records also pass the offline evidence verifier.
Fresh per-process command/output/timing: `fresh-lease-20.json`.

## Commands and retained evidence

Executed every command in VERIFY.md, including full suites, typecheck, fake probe,
six-minute replay, offline verifier, layout, diff whitespace/stat/product-boundary
inspection, and listener check. Layout and diff checks exit 0. `lsof` on 18119
exits 1 with no output: no listener. No tunnel/server was started; all test/replay
processes completed. The scratch plugin confines fixture paths/sockets only.

Committed fresh evidence in `evidence/mvpfix/wp19/`: full suite logs, typecheck,
fake/replay logs and JSON, field equality, offline verifier, lease records, and
`fresh-summary.json`. Existing COMMANDS.md and VERIFY.md contain reproducible
commands; fresh lease records retain the additional exact commands.

Fresh decoder requests: **0**. Original retained campaign: **18 serial requests**
on owned port 18119, **93.561772 s**, **21,176 generated tokens**; within the user's
150-request cap. Dollar cost unmeasured. No shared-service operation.

## Limits, errors, deviations

Remaining wrong speaker attribution: **8/92** and **44/464** segments;
**15.93 s** and **92.01 s** incorrect reference-overlap duration.
The resolver cannot repair wrong local decoder diarization. Repeated public clips
measure recurrence, not broader corpus quality or concurrent capacity.
No fresh decoder campaign or 30-minute embedding run, as prescribed by VERIFY.md.
No real-browser click campaign or real acoustic enrollment acceptance. Retained
MP3 prototype: PCM/MP3 cosine .969589; 5 s eligible, .6 s refused.
No new word-accuracy, capacity, deployment, or currency-cost measurement.

Packaging check initially flagged trailing blank lines in two copied npm logs;
trimmed in committed copies (raw scratch logs retained); final diff check passes.
No fresh acceptance failures or waivers. Prior authoring failures remain recorded
in test-summary.json (nonexistent server export route; JSON double-counting).
Deviation: added fresh 20-process lease proof beyond the literal replay checklist.
Earlier prototype used unattended state output; frontend changes are tests only,
so no asset build was required. No push, merge, rebase, deploy, GitHub, peer
messages, GPU calls, or shared-service changes. Writes confined to this worktree.
