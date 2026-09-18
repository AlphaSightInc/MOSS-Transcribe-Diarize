# WP14 — integrated acceptance, local only

Base: 8068afce47e72d061f41447bb5d683e7ee4196ac.
Question, primitives, invariants, falsifiers: prototypes/browser-stress/NOTES.md WP14.
All measurements use this checkout; own TLS service 17874, own tunnel 18114;
400 decoder-request ceiling and semaphore 2. No deployment or qualification claim.

## Initial evidence and corrections

- Workspace initial: 7 PASS / 7 FAIL / 14 selected. Repeated all seven failed rows
  once: same failures. Row 5 never reached because row 4 failed before capture.
- Desktop nav is visually hidden at frontend/src/styles/index.css:3610; original
  tests/e2e/verify_workspace.py:237 clicked it unconditionally. The desktop controls
  are visible; corrected harness clicks nav only when visible. Mobile unchanged.
- No configured summary relay returned FAIL with a scrubbed/null reason. Now SKIP
  with fixed metadata reason_code=no_configured_relay_models; no key requested.
- Integrated overlap no longer represents the old mono mixer's negative control.
  Initial lane result: both cases failed quality; old accepted_case nevertheless
  accepted overlap. Corrected both cases to require existing quality predicates.
  Test still deliberately removes a lane on each surface: missing speech must fail.
- Legacy lifecycle/reshare scripts lacked heartbeat sends. Added published helper
  health alongside each replayed frame; frame payloads and Stop deadline unchanged.
- Bench extended with cases 15–16. Public corpus/system playback; synthetic microphone
  is readiness evidence only. No microphone fidelity or echo claim.

## Failed tooling attempts / deviations

- Browser executable absent from default Playwright cache. Installed Chromium only
  into runs/wp14/browsers; wrapper selects it, with fresh temporary profiles. No user
  Chrome session used. Temporary files and TLS material remain ignored in this tree.
- Initial Python full-suite run stopped at 352 passed after discovering hardcoded
  /tmp socket fixtures. Subsequent run uses the existing WP11 test-only redirection
  plugin copied into WP14. First run may have created temporary sockets outside the
  tree (then cleaned by tests); strict byte-for-byte outside-tree isolation is not
  established. No other checkout source was edited or repaired.
- A broad string replacement briefly introduced SyntaxError in the before-reset
  evidence branch. Harness: 3 collection errors; whole suite: 5 collection errors.
  Corrected locally; original failed logs retained. No decoder calls from failures.
- Scripted state probe instead of prototype TUI, because native capture/lease state
  and actual saved transcript are the question. No new production algorithm/policy.

## Browser intermediate verdict

Case 15: UNMEASURED. Headed Playwright Chromium (local bundle), default renderer/
background/occlusion disabling flags removed; CDP getWindowForTarget then native
windowState=minimized: hidden=false. Second same-context tab, bring_to_front:
hidden=false. Restored native window, capture completed. No 60-second hidden
continuity claim. Exact attempts retained in browser-corrected/campaign-results.json.
Case 16 first measured pass: 25s frames resumed on both lanes, UI explicitly said
connection restored, meeting completed. The prototype mistakenly counted text on
CanonicalCommit objects (whose field is serialized transcript), giving zero before
words. Corrected to effective_transcript, and independently compare acknowledged
(span_id, transcript) pairs before/after. Existing terminal re-decoding may revise
words, so report lexical removals/revisions separately from acknowledgement loss.
35s: interrupted, helper_lease_expired in UI, no frames accepted after expiration,
new capture completed in the same document. Rerun both intervals for corrected
word comparison; initial raw FAIL is preserved, not silently reclassified.

Whole Python suite after harness fixes: 1849 passed, 2 skipped, 37 subtests;
frontend 242 passed / 27 files; typecheck and build passed. A deliberate mutation
restoring the legacy overlap comparator is rejected by the new regression assertion
(overlap-falsifier.txt). No bounds or product lifecycle assertions were changed.

The first navigation correction (`is_visible`) also timed out: a clipped 1px link
still counts visible to Playwright. The final harness goes directly to capture
controls (Playwright scrolls actual controls into view), matching the WP5 bench.
The complete intermediate 14-row run is retained in workspace-corrected/.

Lease UI repair: the measured terminal code helper_lease_expired was accurate but
not a reader explanation. ControlPanel now says recording was interrupted because
the connection was lost too long, and tells the user to Reset capture. Existing
terminal/recovery lifecycle tests retained their assertions; only the expected
message changed. Before source fix: 2 tests failed; after: frontend 242/242.
Shipped assets rebuilt. No timers, transitions, capture thresholds or provider code
changed. The final 35s browser pass must verify these shipped bytes.

The 25s corrected probe: both lanes resume, 3/3 original canonical commits retained
byte-for-byte, accepted samples 158848 -> 720000, meeting completed. Published text
27 -> saved 253 words; 26/27 old words align in order (1 removed or revised during
normal terminal re-decoding). Stop -> saved 76.9516s: measured, not called fast.
The pre-repair 35s repeat: 48/48 words retained; accepted samples unchanged 158720;
interrupted with helper_lease_expired, same-document new capture completed.

## Final workspace run

`workspace-final/results.json`: 11 PASS / 2 FAIL / 1 SKIP, denominator 14.
File and URL: each 115 reference words, 111 output words, 10 edits, WER 8.69565%.
Live first text 3.323115s <= 4s; Stop -> terminal 8.094547s. Both rename paths pass.
Exports: md/txt/json/srt/vtt each 6/6 turns, all words/labels/timing/identity checks;
JSON source-lane check true. File MP3 50s/50s, decodable. Interrupted capture saved
partial audio. Mobile width/scroll 400/400. Repeat capture 3/3 completed in the same
document, frame sequence resets to zero, distinct history IDs, exported each.
Outages 3s/20s both recover; maximum heartbeat gaps 3.496187s/20.496439s;
both frame streams continuous, durable completed status and audio preserved.

F1 (WP1/WP12): actual lane quality fails on initial standalone and workspace repeat,
with identical numerical results. Alternation final/reopened: system 9/106 edits
(8.49057%); microphone 10/48 additions (20.8333%). Overlap: system 13/106 edits
(12.2642%); microphone 10/48 additions (20.8333%). Final bound remains 9.5074%.
Immediate WER bound 16.6655% also violated. Zero speaker-lane conflicts, but two
lexical attribution errors on each case; duplicate counts 2 alternating / 1 overlap.
Source entry: app/live_lane_decode.py:40 (per-lane decode) and :136 (revision
projection); evaluator lane_word_oracle.py:77-82. Decoder-vs-reference origin of the
extra words is not isolated here. Do not call every addition lane leakage. No decode,
identity or threshold fix attempted in WP14. Full per-surface counts retained.

F2 (WP12): row 10 finds enrolled name in bank, but no visible recognition within
30s (existing bound 4s). Local persisted meeting_speakers has zero auto links for
that capture, so this is not merely a missed DOM timing event. Matching observation
entry: live_provider_bundle.py:774; durable publication: phase2_live.py:623;
threshold rule: phase2_voiceprint_match.py:35. Underlying observation/score cause
not isolated. No identity policy change. All initial failed rows were rerun once;
the substantive post-harness-fix identity failure has only one measurement because
remaining required live checks must fit the per-WP 400-call cap. This is a coverage
limitation, not a flake/defect adjudication claim.

F3: hidden/background remains UNMEASURED after both required native tricks. Need a
browser/host setup that actually reports hidden while capturing; do not substitute
visible capture or synthetic document.hidden changes. F4: raw lease-code UI repaired
in 1b1fc692; final shipped-asset browser evidence is separate from unit controls.

## Remaining required scripts and budget

Final shipped UI 35s: PASS; interrupted with readable reset instruction, 30/30
published words and 3/3 acknowledged commits retained, accepted samples unchanged,
same-document recovery capture completed. `browser-ui-final/campaign-results.json`.
Lifecycle: 7/7 PASS. Reshare: 3/6 PASS — 30 words/5 segments, last sample 259840,
past both switch boundaries (112000 and 208000). Last frame 39 rejected (409), Stop
409, finalization not_started. Request ledger reached exactly 400/400 at this step;
stack wrapper rejects additional decoder requests. Treat this run as BUDGET_BLOCKED,
not an independent product defect or acceptance pass. Failure coincides with budget
exhaustion; raw failure reason was not retained by the legacy script. No additional
live rerun authorized within the cap. This and the substantive voiceprint rerun are
unfinished acceptance coverage, explicitly bounded by the brief's request limit.

The two failed quality surfaces were measured twice (standalone initial and row 4).
All original failed workspace rows were repeated once before harness repair.
No decoder requests were made outside the own 18114 tunnel. Wrapper concurrency
limit is 2; all sampled waiting counters were zero. Full request-start metadata is
retained in decoder-requests.jsonl; no audio or transcript content in that ledger.

Final pre-/new gate, after all source changes: Python 1849 passed / 2 skipped /
37 subtests passed / 21 warnings in 138.86s (python-final.txt); frontend 242/242
across 27 files (frontend-final.txt); typecheck/build pass. Owned service PID 53582
and tunnel PID 53245 terminated; ports 17874/18114 have no listeners. Source/full
assets fixes are committed; fresh-context verification will record a separate result.

## Fresh-context verification (2026-09-18)

Tested b30ea628, no production/test-fixture changes and no new decoder requests.
Retained evidence consistency PASS; product acceptance remains FAIL / INCOMPLETE.
First literal full Python run: 1848 passed, 1 failed, 2 skipped, 37 subtests.
F5: tests/phase2/test_owner_bound_live_meeting.py:2091 uses a 30 ms lease; it expired
before first system frame (sequence 0; 409 at line 474). This fixture and production
lease implementation are unchanged from 8068afce. Unchanged isolated retry: 1 pass;
unchanged full repeat: 1849 passed, 2 skipped, 37 subtests (142.49 s). Timing
sensitivity is the leading explanation, precise scheduling cause unmeasured; no
assertion relaxed or lease widened. Original failure retained in fresh-python.txt.
Both skips are ordinary missing real-corpus exclusions. Frontend 242/242 in 27
files; typecheck/build pass, rebuilt assets identical. Full commands, evidence
references, budget/coverage qualifications and cleanup: ../../../../VERIFY-RESULT.md.
