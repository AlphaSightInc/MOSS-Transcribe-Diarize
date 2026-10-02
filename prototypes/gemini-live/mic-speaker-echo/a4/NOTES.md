# R5B-A4 — frontier snapshot, D15 time ownership ($0)

Current contract: lead amendment D1 below supersedes the initial absolute publication-
freshness gate. Product now implements the measured time-only guarantee; final verification
is complete. A unit is hidden only if the time rule proves it was published at or before
the confirmed point, or the existing text rules cut it exactly as today.

Current prototype command: same worktree Python + `a4/measure_core.py`.
Product matrix: `a4/measure_core.py --product`; full pipeline: `a4/product_pipeline.py`;
retained checks: `a4/verify_retained.py`. Paths relative to this bench's parent.

The original contract/audit below is preserved as historical evidence, not the current gate.

## Initial structural contract (superseded by D1)

- Q1: can the exact frontier snapshot compose with retained arm C/A2/A5 cuts while
  hiding zero units first published after that lane's confirmed point?
- P1: lane isolates evidence; original turn key identifies continuity; lane publication
  clock dates an occurrence; actual lane solid frontier owns old publications; comparable
  units/spans identify and render a prefix; latest eligible snapshot supplies the time cut.
  Each is necessary for isolation, continuity, eligibility, authority, comparison or rendering.
- I1: zero fresh units hidden; old preview omissions may disappear under D15; prefix-only
  cuts; lane isolation; no clock advance from stale other-lane republication; degraded
  replacement cannot leave a time cut ahead of surviving solid; uncertain identity abstains.
  Existing arm C and remembered-cut invalidation stay; max of individually valid cuts.
- U1: unspaced/script variants and rewrites may defeat exact prefix; text alone cannot
  distinguish a fresh chorus from a restatement. Recorded publication end is a lane clock
  only in original one-lane source events. Raw stress and physical-device runs UNMEASURED.
- H1: exact unchanged prefix of the last lane publication at/before confirmed time is
  safely old under D15; combining it with retained text cuts still meets absolute G-fresh.
- X1: any known fresh occurrence hidden rejects implementation. In particular, a retained
  text cut beyond the snapshot may itself violate the absolute gate. Do not relabel this
  as additional-only fresh loss or weaken the user's definition.
- T1: first attack composition through real publish_update with an injected, fully dated
  new turn/chorus and both lanes. Audit original Mandarin/English event histories against
  their recorded product inputs: pure appended units have known first-publication clocks;
  rewritten suffix identity stays unknown. This detects whether G-fresh conflicts with
  G-same on the frozen population before building identity/clock/state plumbing.
  If this falsifier fires, stop candidate work as required; record full state and exact
  conflict. If it survives, extend this bench to lane clocks, degradation/replacement,
  lifecycle, bounded state, rewrites, all requested controls and cost before production.

Gates: A4 G-fresh absolute; G-repeat divergence/long streams; G-same F1 2749 calls
and R5-D; G-degraded c5b 23 rows/0 openings/1 Right and 61-word replacement;
G-cost <=1ms mean added; G-observe content-free per-lane numbers.

One command from root:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a4/audit_initial_gate.py`

Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A4/`.

## Initial verdict — BLOCKED, superseded by lead amendment D1

D15 accepts older grey text disappearing even if solid omitted it; that is no longer a
falsifier. The remaining absolute publication-freshness gate fails independently of that
trade. Existing text alignment can remove newly published occurrences without any time
snapshot. Taking max with a safe snapshot cannot repair an unsafe text cut.

### F1 actual product seam, known clocks (injections, both lanes)

Solid frontier15s; a NEW original turn starts16s and is first published20s. Snapshotcut0;
all units are fresh by A4's explicit definition. Stateless/product/combined-max agree:

| Control | Fresh units hidden per lane | Unique fresh unit absent from solid |
|---|---:|---|
| Five-word repeat | 5 | none |
| Five-word repeat with one insertion | 6 | novelword |
| Six-word chorus | 6 | none |
| Eleven-character repeated sentence | 11 | none |

The Chinese control has11 comparable characters (above the nine-character threshold).
No missing origin, stale lane clock, degradation, remembered cut or rewrite is needed.
Full raw/solid/shown/cut/memory/occurrence-clock state is in controls.json.

### F2 frozen recorded conflict with G-same

Match original source events to F1 captured raw row text/end; use the original turn start,
never the clipped row start. Pure appended units inherit their first source publication
end; an earlier rewritten suffix is marked UNKNOWN, not aligned by semantics. Count only
known clocks greater than the same-lane confirmed point. This deliberately measures A4's
literal definition, not actual word audio time or acoustic omissions.

| Stream | Captured calls | Publications hiding known fresh units | Hidden known-fresh unit-publications | Such calls where snapshot adds nothing | Unmapped rows |
|---|---:|---:|---:|---:|---:|
| Mandarin188s | 366 | 199 | 1115 | 199 | 0 |
| English302s | 575 | 410 | 1922 | 410 | 0 |

Occurrences persisting over several calls count several unit-publications, not distinct
spoken units. UNKNOWN rewritten suffixes are excluded. The exact unchanged-prefix time
cut is no greater than the baseline text cut in every one of these609 publications.
G-same therefore requires preserving their output; absolute G-fresh requires changing it.

English call26: solid frontier10s; source turn start0; latest eligible snapshot cut32;
product text cut34. Units the/camera first published10.5/11s remain hidden at13.4s.
Mandarin call65: frontier30s; source turn start25.5s; snapshotcut19/textcut21;
们/的 first published30.5s remain hidden at33.5s.

This also distinguishes two concepts the earlier benches kept separate: *audio already
owned by solid* and *units already published before that point*. Preview latency permits
newly published spelling of older audio; the text rule handles it, but that conflicts with
the newly specified absolute publication-freshness invariant. No actual acoustic-loss
claim is inferred from these recorded counts. The injected new turn supplies known
fresh speech as well as known fresh publication, including a genuinely novel unit.

### Decision and limits

Stop implementation under the brief's explicit G-fresh stop rule. A lead scope change
must permit timing-valid restrictions on existing text cuts and the resulting G-same
output changes while retaining absolute G-fresh. Do not silently weaken the gate to
additional-only fresh loss. Clock/identity production plumbing cannot resolve the measured
max-cut conflict: this first prototype already grants perfect clocks and original keys.

No production code/tests/telemetry changed. Regression fail-before/pass-after and
product-vs-prototype implementation parity do not apply to an unimplemented rejected
composition. G-repeat/G-degraded/G-cost/G-observe and remaining lifecycle attacks are
UNMEASURED for T4. Existing D15 decision is respected; saved transcript unchanged.
No provider calls ($0), audio access, browser, ports/hosts, frontend or deployment.

## Retained PRODUCT verification ($0)

One command: same Python + `prototypes/gemini-live/mic-speaker-echo/a4/verify_retained.py`.
This reruns the required `a3/verify_retained.py` and `a5/product_check.py`, changing only
write destinations to A4 evidence; their original prototype receipts stay read-only.
The first A5 wrapper invocation missed its sibling import path; corrected the wrapper
path and reran. No original assertions, input population or scoring rules changed.

- F1 final-form/arm-C2749/2749; non-CJK575/575 identical to old rule.
- A2 product/prototype frozen output parity2749/2749; original Mandarin366,
  English575 and R5-D64 publication replays identical, same repetition/fresh/flicker metrics.
- c5b baseline/prototype/product: rows27/23/23, paragraph openings19/0/0,
  Right5/1/1; distinct Yeah2/2/2. c2/c4/c5b/c6 stress metrics unchanged.
- A5 product/prototype full-state transition parity5/5: 61 unsupported words visible,
  empty replacement restores81, other-lane/retained-base controls survive, Stop/new
  meeting cuts empty; all recorded text/fresh/re-shown metrics identical.

These checks confirm the retained partial build, not a T4 implementation or passing
absolute G-fresh. The earlier fresh scores use later-solid text proxies and cannot
replace A4's literal first-publication denominator.

## Binding amendment D1 — prototype contract before resumed measurement

The lead corrected the definition: preview latency can publish spelling of older audio
after the confirmed point. G-fresh applies ONLY to additions made by the time rule.
Existing arm C/A2/A5 output stays exactly as today, including its genuine-repeat limit.
G-same: snapshotcut <= textcut gives byte-identical output; otherwise only snapshot-prefix
units disappear. **A unit is hidden only if the time rule proves it was published at or
before the confirmed point, or the existing text rules cut it exactly as today.**
The earlier negative counts retain their publication-clock denominator; they no longer
reject this amended composition. D15's old-grey omissions remain accepted.

Q1/P1/I1/H1/X1 now ask whether the time rule's additional cut stays inside the exact
unchanged prefix of the latest known eligible same-lane/original-turn publication.
Unknown turn composition, merges, filtered text or lost publication history abstain.
No fuzzy snapshot matching, unit-count rewrite fallback or altered text-rule cut.

Proposed minimum plumbing: GeminiPreview carries original source rows, each lane's own
publication end and finished original-turn keys. Hybrid attaches these before ordered
projection; lane composition forwards each cached lane's own clock rather than max clock.
Runtime maps a rendered row to a unique identical original text within its original
extent. Different starts/splits/merges/new finals never inherit a guessed key. Existing
successful lane_live_preview socket-open events clear that lane's snapshot state on
reconnect/device-source replacement. Old clock watermark survives reset so stale cached
rows cannot resurrect an old source. Stop clears after tail drain; new meeting is empty.

Confirmed point: max end of CURRENT effective solid rows in that lane, not accepted/base
clock or a rolling update's nominal end without solid. Recompute after base/rolling;
if it retreats, discard snapshots/history now ahead of surviving solid. Degraded advance
owns only its visible row extent; it cannot date a55s publication at21s. Normal replacement
at30s must leave the61 words of the55s preview visible (A5 attack).

Pending history bound:64 publications per active original turn plus one eligible snapshot.
On overflow record the lost-through clock; abstain while a frontier needs discarded
history, resume when a retained eligible publication supplies the true latest snapshot.
64 is a prototype choice, not configuration: measure the largest pending population on
original188s/302s streams and stress a10,000-publication stall. Do not certify if the
bound changes any recorded snapshot. State size scales with active turn text, never
finished meeting history. A final can use existing state for its publication, then clears.

Experiments: original streams and full2749 captures with original identity where known,
A3 omission injections; A2/A5 controls; lane-stale republication, splits/merges/restarts,
rewrite, frontier without publication, empty frontier, degraded replacement, Stop/new
meeting and bounded overflow. Compare ideal unlimited-history snapshot with bounded
candidate, full state receipts, additions/fresh suffix/residue and per-publication cost.
Then RED regressions on unchanged product, lift exact measured candidate, product replay,
numeric-only diagnostics, earlier retained checks and a fresh full suite before commit.

## Resumed prototype verdict — ACCEPT amended time composition (before product edits)

`measure_core.py`:6/6 divergence injections (both lanes), zero extra time-cut fresh
suffix loss; repeated residue0 units/0s. Snapshot sizes129/140/362 for22 omitted words,
11 inserted words and169 inserted Mandarin characters. Controls cover rewrite, new
key/split/merge, lane isolation, final-restatement, reset/replacement same key, frontier
without publication, degraded55s→30s replacement, stale lane clock, Stop-equivalent
clear and10,000-publication overflow. Overflow holds64 pending and abstains if required
history is gone; resumes on retained eligible history. Full state in controls-prototype.json.

Original Mandarin366:23 changed calls,46 additional removed unit-publications;
English575:0 changes. Time additions outside exact oracle snapshot0; G-same mismatch0.
Max pending35/28 gives64-entry margins29/36; no recorded overflow. Added mean0.107/0.124ms,
max0.367/0.409ms. Combined later-solid-proxy residue max4/5 units on non-rewrite
publications; residue present45/41 cumulative publication seconds (not45s of speech).
Rewrite events16/41; maximum residue on rewrite publications4/3. This is recorded
proxy scoring, not raw stress/page/fresh acoustic certification. Snapshot-only rewritten
residue remains the A3 55/111-unit limit; the preserved text rule reduces it. No unit-count
rewrite refinement: rewritten words within an old count could be newly published, so
count alone is no proof. Existing text refinement already gives the small combined residue.

RED on unchanged product:20 regression cases failed,1 retreat preservation control passed;
red-tests.log records names and causes. Seven output improvements fail with assertions;
clock/source identity/lifecycle/counter contracts fail missing fields/keys as appropriate.
No existing expectation changed. Lift exactly this64-entry reducer, exact prefix rule,
visible-solid frontier and conservative origin matching. Integration and metadata tests
must turn green before product parity/retained/full-suite qualification.

### Identity refinement (measured before lifting)

Two new adversarial RED assertions exposed ambiguity in the first plumbing: duplicate
original starts with different texts, and ordered projection joining a fully overlapping
final/interim into one row. Candidate now deletes/abstains on duplicate source keys;
hybrid drops origin metadata if projection changed the row count or per-row text.
These are uncertain identities, not new alignment rules. Identity prototype retains
23/0 changed calls,46/0 extra units and zero safety/parity failures; pending35/28 unchanged.
identity-red.log:2 assertion failures before guards. No threshold or text cut changes.

### Covered-final lifecycle refinement

A final whose source clock is already confirmed is ignored by the old hybrid producer.
That would retain snapshot history after a known turn end. final-red.log:2 assertion
failures. Use the already-measured reducer.finish(keys) through a metadata-only preview
(no rows/no lane clocks), forwarded by the lane composer without replacing its cache,
consumed before provisional begin; no public text/version change. Ending/failing a
meeting also clears snapshot text in the existing resource-release path. No new cut rule.

## Product verification (final code)

The reducer/product matrix matches prototype on all6 injections, bounded10,000-publication
stall, lifecycle/key controls and both original streams, excluding wall-clock timings from
exact receipt equality. Actual product hybrid→lane composer→runtime replay also matches
the measured reducer's full state and shown text on1,005 publications:366 Mandarin,
575 English,64 R5-D. Changed calls23/0/0; additional units46/0/0; G-same mismatches0;
all time additions inside the dated exact snapshot prefix. Pending35/28 of64 unchanged.

Full-pipeline cost compares the exact pre-A4 methods from41bc82d9 with product methods
on the same recorded inputs/current primitives, timing source callback through publication.
Baseline/product means: Mandarin0.318/0.655ms, English0.392/1.093ms, R5-D0.213/0.401ms;
added0.337/0.701/0.188ms. The independent semantic verification run is separate from the
cost run so prototype/scoring work is excluded. All <=1ms added; product total is not
claimed <=1ms. pipeline-product-check.json/log and per-publication pipeline receipts.

Targeted tests221 passed after the full change. Initial20 RED cases now pass; original
retreat control passes before/after. Identity2 and covered-final2 RED assertions now pass.
No existing expectation changed. Product source identities/own clocks, final lifecycle,
61-word degraded replacement, numeric accounting and original-rule preservation are
covered. Final retained checks/full backend result recorded below.

Diagnostics contract for lead: `engine_diagnostics.preview[lane]` contains numeric
`lane_publications`, `units_published` (rendered raw units on own-clock advances), cumulative
`text_hidden_units`/additional `time_hidden_units` (every composed publication),
`shown_units_max`, and latest `raw_units_last`, `shown_units_last`,
`text_hidden_last`, `time_hidden_last`, `lane_end_sample`, `confirmed_sample`.
Latest R = shown + text-hidden + time-hidden. Stale lane republications do not advance
its source publication totals; latest/cumulative rendered counts still describe the
composed public update. Metadata-only covered finals change no public text/version.
`preview_snapshot_max_pending` and `preview_snapshot_history_overflows` expose the bound.
`preview_snapshot_errors` counts optional snapshot failures cleared without ending the meeting.
No text, audio, origin text, key or credential is logged in these counters. Existing
operator diagnostics at meeting end include these numeric fields automatically.

The real-run helper must still capture original public-fixture source events/raw text,
per-lane clock/turn-instance/final kind, composed raw and shown rows, same-time lane solid
and later revisions, plus browser versions/DOM/poll times, as A3 specifies. Counts alone
cannot establish occurrence identity or actual speech truth. No provider/browser/host run
is authorized here; those lead stress/physical gates remain UNMEASURED, not a pass.

Receipt correction: the first state serializer retained mutable clock/frontier dictionaries
in earlier trace entries. It now copies those numeric dictionaries at each action; semantic
state/text assertions were already synchronous and valid. Re-generated semantic traces
and core receipts with unchanged inputs/rules; the separate full-pipeline timing receipt
is retained. This changes evidence capture only, not product code or any denominator.

## Final retained/build result

Both requested A3/A5 checkers pass on the final product. F1/A2 exact2749/2749,
non-CJK575/575; Mandarin/English/R5-D366/575/64 text parity without origin metadata.
c5b baseline/prototype/product27/23/23 rows,19/0/0 openings,5/1/1 Right,2/2/2 Yeah.
A5 product/prototype5/5 transitions;61 unsupported words (81 with empty replacement)
visible; Stop/new meeting empty. Stress re-trim metrics unchanged. These retained checks
preserve old text behavior; added time behavior is measured separately above.
Every actual pipeline change listed in output-differences.json: Mandarin23, English0,
R5-D0. Captured Korean/other cells add no time cut and remain identical in2749 parity.
Core controls/injections/per-publication full states match product/prototype exactly;
only three elapsed-time fields are excluded from numeric summary equality.

Full backend: **2874 passed,9 skipped,2 xfailed,37 subtests passed**,27 warnings,
416.41s. Command from worktree root:
`MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python -m pytest -q -p no:cacheprovider tests`.
Evidence full-suite.log. Targeted221 passed. No existing expectation changed.
The four text functions are byte-identical to41bc82d9, including arm C and A2 memory.
Provider0/$0; no frontend/assets, private audio, ports, hosts, push/merge/PR.

### Added tests: before / after (25 cases)

| Test | Before | After |
|---|---|---|
| `test_time_snapshot_removes_solid_omission_but_keeps_fresh_suffix[system]` | failed on base41bc82d9 | passes |
| `test_time_snapshot_removes_solid_omission_but_keeps_fresh_suffix[microphone]` | failed on base41bc82d9 | passes |
| `test_time_snapshot_removes_preview_insertion_but_keeps_fresh_suffix` | failed on base41bc82d9 | passes |
| `test_time_snapshot_removes_long_unspaced_insertion` | failed on base41bc82d9 | passes |
| `test_time_snapshot_prefix_shrinks_on_rewrite` | failed on base41bc82d9 | passes |
| `test_time_snapshot_uses_last_eligible_publication_not_first` | failed on base41bc82d9 | passes |
| `test_frontier_without_new_publication_uses_existing_snapshot` | failed on base41bc82d9 | passes |
| `test_source_restart_same_turn_key_discards_snapshot` | failed on base41bc82d9 | passes |
| `test_new_split_merged_or_restated_turn_never_borrows_snapshot[16]` | failed on base41bc82d9 | passes |
| `test_new_split_merged_or_restated_turn_never_borrows_snapshot[5]` | failed on base41bc82d9 | passes |
| `test_new_split_merged_or_restated_turn_never_borrows_snapshot[20]` | failed on base41bc82d9 | passes |
| `test_snapshot_lane_isolation` | failed on base41bc82d9 | passes |
| `test_stale_lane_clock_cannot_date_new_units` | failed on base41bc82d9 | passes |
| `test_final_clears_snapshot_after_rendering` | failed on base41bc82d9 | passes |
| `test_nominal_rolling_frontier_without_solid_does_not_own_preview` | failed on base41bc82d9 | passes |
| `test_degraded_replacement_keeps_61_words_and_fresh_suffix` | failed on base41bc82d9 | passes |
| `test_stop_new_meeting_clear_snapshot_history` | failed on base41bc82d9 | passes |
| `test_preview_diagnostics_numbers_show_only_additional_time_cut` | failed on base41bc82d9 | passes |
| `test_preview_carries_each_lane_clock_and_original_turn_before_clipping` | failed on base41bc82d9 | passes |
| `test_stream_preview_preserves_original_turn_before_projection_and_final_key` | failed on base41bc82d9 | passes |
| `test_ambiguous_original_turn_key_abstains` | failed before identity refinement | passes |
| `test_merged_preview_abstains_from_original_turn_identity` | failed before identity refinement | passes |
| `test_already_confirmed_final_clears_history_without_republishing` | failed before covered-final transport | passes |
| `test_already_confirmed_final_reports_end_without_text_publication` | failed before covered-final transport | passes |
| `test_retreating_solid_frontier_discards_snapshot_ahead_of_it` | preservation control passes on base | passes |

## Lead L1: two-hour publication cost (registered before measuring)

Structural question: can numeric preview diagnostics stay cheap as saved text grows?
Minimum primitives: bounded current-preview units for removal accounting; existing
visible-solid attribute scans for the lane confirmed point. Saved-text unit totals
are unnecessary for either primitive, so remove `solid_units_last` entirely; no cache.
Invariants: cuts/text unchanged; diagnostics retain their numeric accounting identity;
no new per-publication traversal of saved text. Existing attribute scans remain.
Unknown: two-hour cost was unmeasured by the earlier 3–5 minute stream gate. Lead measured
31.9ms diagnostics on 1440 solid rows; that disproves length-independent unit counting.
Falsifier: any retained `solid_units_last` key, or mean added runtime work >1ms on the
fixed two-hour population below, rejects the fix.
Tool decision: red/green key regression catches API residue; a production-primitive
bench isolates newly added work (including visible-solid scans) from unchanged text
trim. Targeted/full backend tests detect unintended runtime behavior changes.

Frozen cost population: 1440 five-second solid rows, alternating system/microphone
(720 each), ending at 7200s, 30 words/row. Two current preview rows, 24 words each.
Ten warm-ups, 200 measured publications with advancing own-lane clocks; production
snapshot advance/publication/cuts, time-cut composition, finish and diagnostics under
a lock. Preview history stays bounded at 64. No text-trim/prototype scorer in timing.
The benchmark only adapts its diagnostics argument list to measure the reviewed
signature before removal and the new signature afterward; no product compatibility
layer. Same population/command/gate before and after; receipts retained even on failure.

One command (from worktree root):
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a4/cost_long_meeting.py --receipt <own-evidence-json>`.

L1 verdict: PASS after removal; reviewed product FAIL before. Same fixed two-hour
population: added mean97.641681 → 0.635399ms/publication (gate<=1ms); diagnostics
97.346739 → 0.347799ms. Post-fix added p950.768583ms, max pending64. This gate measures
all newly added runtime preview primitives, including existing solid attribute scans;
it excludes unchanged text trim/session publication and source-side work. The earlier
source-to-publication stream measurements remain separate receipts. No claim of
length-independent total runtime: the existing attribute scans remain O(rows).

`test_preview_diagnostics_omit_whole_solid_unit_count[system|microphone]`: both FAIL
before and PASS after. Latest diagnostics contain no `solid_units_last`. The production
helper no longer receives solid rows; no replacement cache or saved-text count exists.
All other counters and preview cuts unchanged. Targeted snapshot/duplication/lane/hybrid/
runtime tests223 passed in6.43s. RED/GREEN logs and cost JSON under own evidence:
`l1-key-before.log`, `l1-cost-before.log`, `l1/cost-before.json`,
`l1-cost-after.log`, `l1/cost-after.json`, `l1-targeted.log`.
Full backend:2876 passed,9 skipped,2 xfailed,37 subtests passed,27 warnings
in427.63s. Command: `MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1
../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python -m pytest -q -p no:cacheprovider tests`.
Receipt: `l1-full-backend.log`. No provider calls ($0); no other product change.

## FIX7 contract (before probes/prototype/product edits)

Structural question: when bounded publication history drops a newer rewrite, can an
older snapshot still prove the current prefix? Can this optional proof fail without
ending the meeting? Minimum primitives: retained eligible publication, discarded-clock
watermark, and already-computed text-rule output. The watermark must be compared with
the snapshot clock, not only the confirmed point: newer discarded history invalidates
an older witness when no retained eligible publication replaces it. Retained eligible
history resumes the cut. Keep64 entries, no threshold change or frontier cache.

Invariants: use only the latest retained eligible same-turn/same-lane witness; abstain
if dropped history can supersede it. Text rules unchanged. An exception in optional
snapshot preview steps falls back to text-rule rows, clears snapshot state, increments
numeric preview_snapshot_errors once, and keeps the meeting live. Base/rolling advance
failures also clear/count/continue. No wrapper/flag. Unknown: spontaneous normal-input
faults are unmeasured; fault injection qualifies recovery only. Falsifiers: obsolete
cut in65-publication gap, changed64 control, no resumption on retained eligible history,
fatal injected snapshot fault, or regression/cost gate failure.

Tool decision: unchanged reviewer probes reproduce current behavior; RED tests pin the
65/64 and retained-resumption controls and failure recovery. Extend the throwaway reducer
before product edits, print full relevant state around loss/confirmation/resumption.
Use the existing pipeline/retained/cost benches to detect semantic/cost regressions;
full backend suite detects changes outside those recorded preview populations.

Prototype verdict before product edits: PASS. Command:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a4/fix7_probe.py`.
65/64 gap cuts0/0; retained eligible resumption7/7 units; repeated advancement preserves
both7-unit cuts. Fault prototype shows all7 text-rule units, clears all snapshot state,
error count1. Full seed/history/gap/resumed state and fault state: `fix7/prototype.log`.
The reducer now compares lost_through to the snapshot's publication clock; retained
eligible history wins first. This conservatively abstains if the watermark is newer
than the old witness, including uncertain gaps before the watermark. A later witness
newer than discarded history remains valid on repeated advances.

Unchanged reviewer sources ran first; only receipt writes/temp directories redirected
to own evidence.65 probe reproduces5-unit wrong cut;64 control0; injected cuts fault
status failed/no later preview. Text functions byte-identical; zero-cut2749/2749,
non-CJK575. Reviewer's 10000-publication bounded-state/scan probe retained separately.
No reviewer receipt was overwritten. Production implementation follows this verdict.

FIX7 product/gates before full backend: PASS. Reviewer probes after the fix preserve
the exact input path, change only obsolete wrong-output assertions to the binding
acceptance assertions, and redirect writes to own evidence.65 and64 both show all7
units, time/text cut0. Injected cuts fault: active, terminal failureNone, full text-rule
output, later preview published, preview_snapshot_errors1. Four text functions remain
byte-identical to41bc82d9; zero-time-cut2749 calls unchanged, non-CJK575 unchanged.
FIX7 prototype/product full state identical on65/64 gap, retained resumption and fault.

Final new tests:9 RED on pre-FIX7 production methods → GREEN;64 control passes before
and after. Includes5 preview failure sites and2 post-commit advance sites. Initial new
fixtures were corrected to freeze rolling audio before revising it and to assert public
status `active` (the product's name for a live meeting); initial receipts retained.
Final fixture assertions were rechecked against exact597be447 `advance`/`publish_update`
methods in memory, with no working-file changes:9 FAIL/1 control PASS. Current targeted
suite233 PASS in5.65s. No existing test expectations changed.

G2 production hybrid→lanes→runtime replay1005 publications matches measured reducer:
Mandarin366,23 changed/46 extra unit-publications; English575 and R5-D64 unchanged.
Outside-snapshot time additions0; G-same mismatches0; snapshot-state parity exact.
Added mean source-to-publication0.198299/0.236483/0.169594ms (same baseline/denominators).
G3 requested A3/A5 retained checkers pass on the final product; F1/A2 frozen2749 outputs
and575 non-CJK preserved; c5b27→23 rows,19→0 openings,5→1 Right; A5 transitions5/5 and
61-word degraded replacement retained. G4 same two-hour1440-row/both-lane cost check:
added mean0.598714ms/publication, p950.715167ms; diagnostics0.329964ms, max pending64;
<=1ms PASS. The cost definition/unchanged fixture remains as registered under L1.

Receipts: own `fix7/` evidence: unchanged reviewer-before and accepted reviewer-after
logs/compatibility JSON, prototype.log/product-probe.log, tests-red-final-original-methods.log,
targeted-final.log, pipeline/pipeline-product-check.json plus1005 full-state receipts,
retained.log and retained/{a3-retained,a5-retained,product-transitions.json},
cost-two-hour.json/log. No provider calls ($0), no new threshold/flag/cache; source/lane
metadata and the existing solid scans unchanged. Fault injection proves containment,
not absence of spontaneous faults or fresh-provider/browser qualification.

Final G2 receipt-to-receipt check against preserved pre-FIX7 pipeline traces:
366/575/64 (1005 total) exact raw/text-only/shown/cuts/clock/snapshot-state matches;
0 mismatches. Diagnostics excluded from this equality because this fix adds the error
counter and L1 removed the whole-solid counter. Receipt: fix7/pre-fix7-parity.json.
G5 full backend2886 passed,9 skipped,2 xfailed,37 subtests passed,27 warnings in400.73s.
Command from worktree root: `MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1
../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python -m pytest -q -p no:cacheprovider tests`.
Receipt: fix7/full-backend.log. FIX7 complete; all five gates PASS; no blocker/deviation.
