# WP2 prototype verdict
Question: can downstream consumers preserve lane-tagged overlapping speech, four independent speakers, and legacy mono?
Hypothesis: optional lane + chronological ordering + separate labelled cues suffice; no new storage table or identity policy.
Falsifier: dropped speech/identity/lane, clipped cue times, unreadable mobile rows, or legacy breakage.

Corpus: complete public Bill Ackman (5 segments) + Keyu Jin (4), each at original relative timestamps; 2 speakers per lane, 4 IDs (Lex occurs independently twice). Legacy = Ackman without lane.
One command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <brief-python> evidence/mvpfix/wp2/prototype.py`.
UI: same prefix + `evidence/mvpfix/wp2/prototype-ui.py`; browser intercepts existing workspace route with `?variant=A/B/C`, bottom switcher and arrows. No services/provider/audio.

Measured baseline: SQLite commit, GET, history preserve 9/9 tagged and 5/5 legacy segments exactly. Frontend normalization preserves 9 rows/4 IDs but 0/9 lanes; tied initial rows reverse because end precedes lane. Legacy preserves 5/5 rows and 2 IDs. All five exporters run, but lane absent. Summary labels/text retained; no explicit sorting. Candidate direct preservation/sort keeps 9/9 lanes, 4/4 IDs; legacy 5/5.
UI all 9 combinations (390/400/1280 px × A/B/C) render 9 rows without horizontal overflow. 390 row widths: A 324, B 162, C 312 px. Reviewed all three mobile screenshots. Select A chronological interleave + lane badge. B splits reading order and crowds text; C adds redundant overlap labels. No human visual acceptance claimed.
Exports: independent cues, unchanged start/end, speaker + lane prefix; md/txt include lane beside speaker to match A; legacy formatting unchanged.
Verdict: minimum design supported; baseline implementation requires lane preservation and ordering changes. This is consumer feasibility, not upstream/live qualification.
Initial failed attempt: production requires SQLite 3.53.4, interpreter has 3.50.4. Semantic rerun uses exact override already in tests/phase2/conftest.py; production guard unchanged. Initial screenshot framing missed pane; rerun scrolled into pane.
Prototype code will be absorbed into a repeatable consumer evidence probe; UI variant shell removed after decision.

## Implementation evidence
The throwaway data prototype is absorbed as `consumer_probe.py` + `consumer_probe.mjs`; it now asserts field conservation. UI variants/switcher were removed; screenshots and measured layout states remain. `docs/design-lane-consumers.md` records the selected behavior.
Final probe: tagged 9/9 rows, 9/9 lanes, 4/4 IDs; legacy 5/5 rows, 2/2 IDs. No provider calls.
Live consumer additionally uses `effective_transcript` when published (including empty arrays), both on snapshot and identity-finalized events. Missing field retains legacy text-snapshot support. This prevents replaying obsolete mono text after a tagged publication. Upstream production is still WP1's responsibility.
Full frontend: 218/218 tests across 25 files; typecheck passes; build passes (65 ms build phase). Focused Python: 48/48 (13.21 s), including three corpus geometry widths and unmodified geometry/sentinel suites. Latest logs: `frontend-isolated-2.log`, `typecheck-isolated-2.log`, `build-isolated-2.log`, `python-complete.log`, `consumer-final.log`.

Failed/intermediate attempts retained:
- SQLite exact-runtime refusal; semantic override matches the existing test suite.
- Frontend initial: 204 passed, 2 failed (old provisional-last assertions incompatible with mandated chronological order). Updated tests; 212, 214, 215, 217 then 218 pass as coverage grew.
- Typecheck: test-only inferred string lane / nullable meeting / implicit-any errors, then one async callback returned boolean. Fixed test typing; final pass.
- Python initial: 44 passed, 1 failed (Unix socket path too long). Isolated runner uses worktree-relative socket addresses; 48/48 pass.
- New geometry initial: 0/3 (test had not opened Voiceprints before two-Refresh assertion). Matched the existing sentinel's setup, left original sentinel untouched; 3/3 pass.
- Cache-isolation attempt with runner config loader failed because old config used `__dirname`. Config now uses native ESM `import.meta.dirname`, checkout-local cache; `--configLoader native --cache=false` tests and native build pass.

Scope deviations: initial standard test/build invocation wrote transient Vite cache/config artifacts through the prescribed shared node_modules symlink; existing lifecycle tests briefly created /tmp socket files (self-cleaned). No shared source/service changed. Later tooling avoids shared caches/config bundles and routes all scratch/socket paths inside this worktree. No push/merge/GitHub/deploy, decoder, tunnel or persistent server. No changes to QUALITY_BOUNDS, identity policy, readiness thresholds, ingress frame keys, lifecycle checks, or two-Refresh sentinel.
Limits: no live WP1 integration, real voiceprint recognition, external subtitle-player rendering, production SQLite runtime qualification, or human visual sign-off claimed. UI tests accept a shared voiceprint result for independent lane IDs; they do not measure encoder behavior.

## Fresh-context lead correction
Lead review identified the initial 204/206 frontend failures as an existing product
contract, not assertions superseded by lane ordering. Rewriting those expectations
was incorrect. Restored both original test files verbatim from 37979e53; retained
all new lane tests. Restored committed-before-provisional as the FIRST comparator
key, followed by start, system-before-microphone, then end. No new policy introduced.
Fresh restored-test falsifier: 216/218 passed, exactly the two original tests failed
(2.69 s). Corrected implementation: 218/218 across 25 files (2.33 s); typecheck passes.
Native production builds twice, unchanged source: all 17 asset-file SHA-256 values
identical. Hashes are retained solely for the lead-requested byte comparison.
The first hash glob included two directories and exited 1; corrected to file-only
recursive enumeration, then compared successfully. Both builds themselves passed.
