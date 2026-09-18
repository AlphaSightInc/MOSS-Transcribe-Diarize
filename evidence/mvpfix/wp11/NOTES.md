# WP11 export label decision and prototype verdict

Question: do lane-tagged overlapping documents, two speakers per lane, round-trip
through all five export formats while corrupt controls fail?
Primitives: speaker identity (person reference), speaker label (display), lane
(origin namespace), timed words (content). None substitutes for another.
Invariant: labels resolve independently of lane; JSON preserves optional source_lane;
word order, timestamps, overlaps and legacy labels stay unchanged.
Assumption: WP2's label decoration was a UI-consistency choice, not a user requirement.
WP2 NOTES says prefix matches option A; its design doc says lane is not person identity.
Unknown: external subtitle-player display; actual microphone fidelity.
Falsifier: valid output mismatch, dropped JSON lane, accepted wrong label/words/time.
Tools: Node strip-types calls the actual serializer; independent Python oracle checks
represented fields. Public WP2 corpus attacks overlap and independent lane identities.

Prototype command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <brief-python> evidence/mvpfix/wp11/prototype.py`.
Baseline: overlap 0/5 accepted, legacy 5/5; corrupt labels rejected 5/5 for each.
Candidate: overlap 5/5 accepted, legacy 5/5; corrupt labels rejected 5/5 for each.
Population: 9 tagged segments / 4 IDs (2 per lane); 5 legacy segments / 2 IDs.
Full inputs, serialized outputs and oracle checks: prototype.log.
Verdict: SUPPORTED. Remove lane decoration from speaker labels in every format.
Keep optional JSON source_lane and UI lane badges. The prototype is deleted after
absorbing its corpus round-trip into oracle regression tests; retained log is evidence.
Prototype deviation: scripted action sequence instead of interactive TUI, as this
brief requests a deterministic serializer/oracle fixture experiment.

Verification plan: oracle tests detect export field drift; deliberate corruptions
must fail or the oracle needs repair. Browser cases 8,11,10,12 detect upload failure,
rename/export mismatch, two-lane saved-export mismatch, and 400px history breakage.
Full Python/frontend suites detect integration regressions outside focused coverage;
fix failures or record their independent cause. Typecheck/build detect invalid TS
and stale shipped frontend bytes; repair before committing.

## Integrated discoveries and bounded repair
Case 10 exposed a production projection omission: `_transcript_document` copies
words/IDs/times but omits source_lane. Snapshot lane data therefore disappears from
saved meetings. Projection prototype (projection-prototype.log): 2/2 input lanes,
0/2 saved lanes; copying the optional field produces 2/2 without changing labels.
Verdict: preserve the existing optional field at the durable publication boundary.
No new schema, algorithm, threshold or identity policy. Add exact projection tests
and repeat the actual Stop/reopen/export path to falsify this repair.
Case 8 exposed the upload follower ignoring existing API failure_reason. History
already displays it; show the same reason in the upload row. This composes the
existing meeting outcome with the existing status UI; no new error taxonomy/policy.
First campaign: case 8 3/5 variants pass (4 valid files complete; 2 rejected rows lack
specific reason), case 11 passes with rename exports 5/5, case 10 fails because lane
set is empty, case 12 passes: 60 rows, 2 Refresh buttons, scroll width 400 at 400px.
10 decoder calls in this attempt. No microphone/echo fidelity claim.

## Full-suite inherited failures: independently reproduced
Initial full suite: 19 failed, 1807 passed, 2 skipped, 37 subtests passed, 138.47s.
An unchanged b31683a6 source snapshot was extracted with git archive into ignored
`runs/wp11/base/` inside this worktree (no other worktree touched). Running the five
failing modules from INSIDE that snapshot reproduces the identical 19 failed node
IDs: 128 passed, 19 failed, 9 subtests passed, 6.83s; base-failures.log.
These are retained integration failures, not a green whole-repo gate. File-by-file:
- tests/phase2/test_draft_lane.py: 1 failure. Synthetic replacement updates legacy
  committed text while retaining explicit empty effective_transcript. Reader honors
  WP2's explicit authoritative surface; assertion expects two legacy rows instead.
- tests/phase2/test_runner_composition.py: 1 failure. Transport-call test supplies
  all-zero tape; WP3's all-zero guard correctly sends zero requests, test expects one.
- tests/test_live_pipeline_seams.py: 15 failures. Decoder transport/salvage/token-cap
  tests use zero PCM; guard prevents their intended transport path, so response and
  timing assertions cannot observe the supplied runner result.
- tests/test_live_rolling_wiring.py: 1 failure. Salvage test uses zero PCM and expects
  recovered words; the existing zero guard preempts decoding.
- tests/test_live_service_replay.py: 1 failure. Terminal success fixture writes zero
  PCM; existing terminal all-zero refusal yields failed rather than expected final.
No assertion, lifecycle check, silence guard, decoder policy or threshold is changed
to hide these failures. Their owner must adjudicate fixture inputs against the
accepted zero-speech policy and explicit effective-transcript authority.

Other failed attempts: time-corruption JSON initially replaced `0.0` text, but Node
serializes zero as `0`; 46 passed/2 failed. Mutation now edits the parsed start field;
48/48 pass. Frontend initial 229 passed/3 failed were WP2 decoration expectations in
laneConsumers.test.ts; changed under the explicitly revised label contract, then
232/232. Projection red: 49 passed/1 failed; upload red: 2 passed/1 failed.
Projection repair exposed a pre-existing SimpleNamespace mock missing source_lane;
added None to those two legacy fake segments, preserving its exact expectations.
First SSH attempt refused because an explicitly empty known-hosts source had no key;
used existing known-hosts read-only with UpdateHostKeys=no. No host files changed.

Second campaign: case 8 5/5 variants pass; case 11 renamed exports 5/5 pass and
voiceprint persists; case 12 passes. Case 10 sees both saved lanes but times out on
its fifth (VTT) export. Retained events show 10 successful downloads in 0.864s, then
no eleventh download event. Bench redundantly downloaded rename JSON twice; removed
that duplicate, reusing the already-downloaded JSON for its oracle check. Browser
burst limiting is the hypothesis; no product timeout/limit or security switch changed.
This attempt consumed 18 calls (28 cumulative). Third campaign will falsify whether
removing redundant browser work is sufficient; failures remain retained.

Final integrated campaign: 4/4 cases pass. Case 8: 5/5 variants (four successful
uploads, two visibly explained rejections). Case 11: 5/5 renamed exports, two renamed
turns, one enrolled voiceprint after reload. Case 10: live 5/5 + file 5/5 exports;
live has both lane values, four turns; file has one turn. Audio retries 2/2 decode,
54,693 and 72,837 bytes exactly; intentionally cancelled after 1,500 bytes each.
Case 12: 60/60 history rows, 2 visible Refresh controls in Voiceprints, 400/400px.
Case durations: 15.785 / 15.751 / 1.759 / 0.193 seconds for 8 / 11 / 10 / 12.
Third campaign uses 14 calls; 42/60 cumulative, at most two requests in flight.
Removing duplicate download sufficed; burst-limit causality remains a hypothesis.

Final full Python before VERIFY: 1809 passed, identical 19 inherited failures,
2 skipped, 37 subtests passed, 137.76s. Frontend: 233/233 across 26 files, 2.45s.
Typecheck passes; native production build passes (77ms). No policy values changed.
Scope deviation discovered after full runs: existing tests explicitly create short
Unix sockets/directories in /tmp despite TMPDIR; these are self-cleaned. Future
verification redirects those fixture paths with a local pytest plugin; assertions
and production lifecycle checks remain unchanged. Geometry tests rewrite WP2
screenshots inside this worktree; restore only those generated bytes after testing.

Fixture-isolation tooling attempts (not product regressions): first hook requested
monkeypatch before pytest initialized fixtures (160 passed, 3 setup errors before
interrupt); second attempt retained that hook error (959 passed, 2 inherited failed,
43 setup errors before interrupt). Replaced hook with normal autouse fixture, scoped
Path redirection only to tests using /tmp. Initial confined subset: 172 passed,
3 admin socket-length failures. Return relative temporary directory paths for those
three tests, as the existing WP2 test runner does; no lifecycle assertions changed.
Full unmodified-invocation result remains python-full-final.log; interrupted logs
python-full-confined*.log are explicitly NOT final suite results.
Final confined fixture validation: 175/175 across six affected fixture modules plus
export oracle, 11.75s; confined-fixtures-final.log. No extra decoder calls. All owned
servers, tunnels, browser/media processes stopped; no listeners on 17871/18111.

Fresh-context instructions: root VERIFY.md. Official CLI /new semantics checked at
https://learn.chatgpt.com/docs/developer-commands?surface=cli ; same-pane reset will
hand only VERIFY.md's path to the next session. Fresh result must distinguish WP11
acceptance from the inherited failing full-suite gate.
