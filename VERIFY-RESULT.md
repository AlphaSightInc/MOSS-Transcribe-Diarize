# WP14 fresh-context verification — 2026-09-18

Tested branch `mvpfix/wp14-integrated-e2e` at
`b30ea628f7885b47f4aac9cec9d4b196ab8787b3`, clean on entry.
This is the user-requested fresh session: read VERIFY.md, AGENTS.md, COMMON.md,
WP14 brief, execution-plan sections 1–2, and the named WP14 evidence before testing.
No prior live run was treated as a fresh replication. No second `/new` was invoked.

## Verdict

Retained-evidence consistency: **PASS**. Product acceptance: **FAIL / INCOMPLETE**.
Literal first Python invocation: **FAIL** (one lease-test setup failure).
Unchanged targeted retry: **PASS**. Full unchanged repeat: **PASS** (1849 passed, 2 skipped, 37 subtests).
The first failure is retained, not replaced by a later result.
No product source, fixture, assertion, threshold, or lifecycle policy changed here.

## Fresh commands and controls

Executed VERIFY.md's commands in its stated order, sourcing
`evidence/mvpfix/wp14/environment.sh`. Imported package resolved to this worktree.
Python: `-q -ra -p no:cacheprovider -p evidence.mvpfix.wp14.local_scratch
--basetemp=runs/wp14/pytest-fresh tests`; frontend test/build used
`--configLoader native` and the test command used `--cache=false`.
Temporary paths, browser profiles and npm cache were directed inside this tree.

| Control | Fresh result | Log under evidence/mvpfix/wp14/ |
|---|---|---|
| Full Python, literal first run | 1 failed, 1848 passed, 2 skipped, 37 subtests passed; 21 warnings; 142.74 s | fresh-python.txt |
| Unchanged failing test alone | 1 passed; 1 warning; 3.13 s | fresh-lease-targeted.txt |
| Full Python, unchanged repeat | 1849 passed, 2 skipped, 37 subtests passed; 21 warnings; 142.49 s | fresh-python-repeat.txt |
| Full frontend | 242 passed, 27 files; 2.46 s | fresh-frontend.txt |
| Typecheck | exit 0 | fresh-typecheck.txt |
| Build | exit 0; regenerated assets identical | fresh-build.txt |
| Retained JSON/log verification | PASS | fresh-evidence.json; fresh_evidence.py |

Both Python skips are the ordinary exclusions: `tests/test_live_identity_real_corpus.py:60`
(operator-owned real identity corpus not provisioned) and
`tests/test_live_speaker_accuracy.py:44` (real F-cert corpus not provisioned).

F5 — First-run failure: `tests/phase2/test_owner_bound_live_meeting.py:2091` sets a
30 ms lease, creates a session, then feeds frames before its first heartbeat.
The initial system frame (sequence 0) received 409 at helper assertion line 474;
log explicitly reports `helper_lease_expired` before any lane was accepted.
The production lease starts at creation (`app/live_helper_failure.py:192`) and
expiry makes capture terminal (line 289). This test and product module are unchanged
from 8068afce. Hypotheses ranked before retry: wall-clock setup overrun, earlier-test
timing interaction, then lease regression. The unchanged isolated test and full-suite repeat passed.
Timing sensitivity is the leading explanation; precise scheduling cause unmeasured.
No fixture deadline was widened and no lifecycle assertion was relaxed.
Additional commands: same pytest options, `--basetemp=runs/wp14/pytest-lease-fresh`
with the full failed test node; then `--basetemp=runs/wp14/pytest-fresh-repeat tests`.

## Retained acceptance evidence, independently reconciled

`fresh_evidence.py` reads JSON/logs, recalculates row counts and word-error ratios,
compares each result row with its standalone file, and asserts the requested metrics.
Run: source the environment, then `"$WP14_PY" evidence/mvpfix/wp14/fresh_evidence.py`.
These are checks of retained measurements, not new browser/decoder measurements.

| Row | Surface | Verdict | Retained measurement |
|---|---|---|---|
| 1 | Fresh workspace | PASS | Signed in, ready, fresh profile |
| 2 | File transcription | PASS | 10/115 word errors = 8.69565% |
| 3 | URL transcription | PASS | 10/115 word errors = 8.69565% |
| 4 | Live capture + lane quality | FAIL | First text 3.323115 s; Stop→saved 8.094547 s; both lane cases fail |
| 5 | Rename | PASS | Both paths; history and post-Stop export updated |
| 6 | Exports | PASS | md/txt/json/srt/vtt each 6/6 turns; JSON lane=true |
| 7 | File audio | PASS | MP3 50/50 s, decodable |
| 8 | Interrupted audio | PASS | Partial MP3 29.904 s, decodable |
| 9 | Summaries | SKIP | no_configured_relay_models; 0 configured |
| 10 | Voiceprint recognition | FAIL | Bank contains name; recognition absent within 30 s; bound 4 s |
| 11 | History selection | PASS | Header visible, title matches |
| 12 | Mobile layout | PASS | 400 px viewport / 400 px scroll width |
| 13 | Connection outages | PASS | 3 s + 20 s recover; both frame sequences continuous |
| 14 | Repeat capture | PASS | 3/3 complete in same document; distinct IDs, sequence resets |

Total: **11 PASS / 2 FAIL / 1 SKIP / 14 rows**.

F1 — Lane quality (WP1/WP12): alternation final/reopened system 9/106 errors
(8.49057%); overlap 13/106 (12.2642%). Both microphone cases: **10 additions /
48 reference words**, zero substitutions/omissions, 58 output words; 20.8333%
word-error rate versus 9.5074% final bound. The immediate 16.6655% bound also fails.
Evidence: `evidence/mvpfix/wp14/workspace-final/row-04.json:75` and `:230`;
reopened values repeat at `:120` and `:275`. Initial standalone counts match.
Each case has two lexical attribution errors, zero speaker-lane conflicts;
duplicate counts are two (alternation) and one (overlap).
Production entries: `moss_transcribe_diarize/app/live_lane_decode.py:40` / `:136`;
quality predicate: `moss_transcribe_diarize/lane_word_oracle.py:77`.
Origin of extra words is not isolated; additions are not all established lane leakage.
Initial overlap expected_failure=true belongs to the faulty old comparator;
final expected_failure=false. Retained overlap-falsifier.txt records rejection of
that old comparator by the new assertion; source diff preserves missing-lane controls.

F2 — Voiceprint (WP12): `workspace-final/row-10.json:6` shows bank_contains_name=true,
recognition_seconds=null; `voiceprint-finding.json:4` records no visible recognition
within 30 s and `:5` records **zero durable speaker links** for the same capture.
This corroborates absent automatic recognition beyond DOM timing alone.
Observation entry `moss_transcribe_diarize/app/live_provider_bundle.py:774`;
publication `app/phase2_live.py:623`; match rule `app/phase2_voiceprint_match.py:35`.
Observation/score root cause remains unisolated. One substantive post-harness-fix
measurement; no substantive rerun at the original 400-request ceiling.

F3 — Hidden/background: both native headed attempts (minimize; second tab to front)
returned hidden=false in browser-corrected/campaign-results.json. **UNMEASURED**:
no 60-second hidden acceptance, frame-cadence or hidden-continuity claim.
Requires a browser/host setup that actually becomes hidden while capturing.

F4 — Lease UI: sole product-source change since 8068afce is readable expiry wording
at `frontend/src/components/ControlPanel.tsx:107`, with adjusted message expectations
and regenerated app.js/app.js.map. Harness changes correct desktop navigation,
summary SKIP, overlap acceptance and script heartbeats; browser bench adds cases 15/16.
No quality bounds, identity values, readiness, nine-key frame protocol, sentinel,
or lifecycle transitions changed.
25 s retained run: both lanes resume; 3/3 acknowledged commits unchanged;
27 published words → 253 saved words, 26/27 retained in order, one removed/revised;
Stop→saved **76.951584 s** (not characterized as fast).
Final 35 s shipped-UI run: interrupted, readable Reset capture instruction,
30/30 words and 3/3 commits retained, accepted samples unchanged at 159232,
no resumed frames; next capture completed in the same page.
Evidence: `browser-ui-final/campaign-results.json:15` through `:34`.

## Budget, coverage, deviations and cleanup

Exactly **400** decoder starts, sequential indices **1..400**. Stack recipe uses
BoundedSemaphore(2); all 10 retained GPU waiting-counter samples are zero.
Fresh session: **0 additional requests / 100 additional maximum**. VERIFY.md
explicitly requires no live rerun, so no tunnel/service was started or budget reset.
The original **400/400** ceiling remains the provenance of the incomplete runs.
Lifecycle: **7/7 PASS**. Reshare: **3/6**, BUDGET_BLOCKED at the original ceiling:
frame 39 and Stop return 409, finalization not_started; 30 words/5 segments extend
past both switch boundaries. Raw failure cause not retained; budget exhaustion
coincides, so neither independent product-defect adjudication nor passing acceptance.
Summary execution requires configured relay models; microphone fidelity/echo remains
outside synthetic browser readiness evidence. Voiceprint rerun and uncontaminated
reshare acceptance remain unfinished; no new live work required by VERIFY.md.

Preserved earlier deviations: scripted state prototype rather than interactive TUI;
first old suite stopped after 352 passes to redirect hardcoded /tmp sockets, so
outside-tree byte-for-byte isolation was not established for that earlier run;
failed tooling/collection attempts retained; substantive identity retry absent;
reshare ceiling blocked. Fresh deviation: initial full-suite lease-test failure,
followed by bounded unchanged targeted and full-suite retries, all logs retained.

Cleanup controls: restored only the three specified WP2 geometry screenshots;
`git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets` and
`git diff --check` passed. `lsof -nP -iTCP:17874 -iTCP:18114 -sTCP:LISTEN`
returned no output, exit 1. No source changes outside the worktree, no push/merge/
deploy, no peer messages, no shared-service changes. Fresh commit contains only
this result, the WP14 notes update, offline evidence verifier and fresh logs/results.
Log trailing whitespace was normalized after capture; failures and counts preserved.
