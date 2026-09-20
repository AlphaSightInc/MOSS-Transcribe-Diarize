# VERIFY RESULT — CURRENT RERUN: PASS

- Source custody: `/private/tmp/moss-round4-20260920/overlap/moss_transcribe_diarize/__init__.py`.
- Attribution: 83 rows; raw words 105.
- Demo system: 13 rows; class `a=3`, class `d=10`.
- Ladder `overlap@1` system: 35 rows; class `a=2`, class `d=33`.
- Ladder `overlap@0.316` system: 35 rows; class `a=2`, class `d=33`.
- Publication/prefix checks: 2 true, 0 false; raw/demo publication inequalities 0; ladder-prefix inequalities 0.
- Tests: 10 passed, 2 xfailed, 0 xpassed, 0 other failures.
- Decoder requests: 1/40; peak in flight 1; retries 0.
- Proposal status: `proposal_only_never_applied`.
- Attribution classes: `b=0`, `c=0`.
- Product files modified: 0.
- Falsifiers hit: 0 (none).

## lead-issued fresh context

- Step 1 PASS — source custody resolved inside this clone.
- Step 2 PASS — 83 rows; raw words 105; demo `a=3,d=10`; both ladder rows `a=2,d=33`; stream inequalities 0.
- Step 3 PASS — 10 passed, 2 xfailed, 0 xpassed, 0 other failures.
- Step 4 PASS — requests 1/40; peak in flight 1; retries 0; proposal only; classes `b=0,c=0`; product/evidence diffs 0.
- Overall PASS — falsifiers hit 0; no GPU, tunnel, network, or product change.

## Lead-issued fresh context — 2026-09-20

- Step 1 — **PASS**: source custody resolved to `/private/tmp/moss-round4-20260920/overlap/moss_transcribe_diarize/__init__.py`.
- Step 2 — **PASS**: 83 attribution rows; demo system `a=3,d=10`; `overlap@1` system `a=2,d=33`; `overlap@0.316` system `a=2,d=33`; raw words 105. Raw/demo publication equality true; ladder-prefix equality true.
- Step 3 — **PASS**: 10 passed, 2 xfailed; 0 unexpected passes; 0 other failures.
- Step 4 — **PASS**: decoder requests 1/40; peak in flight 1; retries 0; proposal status `proposal_only_never_applied`; class (b) 0; class (c) 0; tracked product-file modifications 0.

**Overall: PASS.**

Falsifiers hit: 0.

## Follow-on alternation/microphone — 2026-09-20

- Step 5 — **PASS**: 19 final edit rows; alternation system `a=2,d=7`; alternation microphone `a=5`; overlap microphone `a=5`; final `b=0,c=0`. Pre-terminal counts preserved as 16/106 and 11/53; all 27 classes `UNMEASURED` because historical word streams were not retained.
- Step 5 correction replay — **PASS**: alternation system 5/102 (1S/1D/3I); alternation microphone 5/53; overlap microphone 5/53.
- Step 6 — **PASS**: 13 passed, 3 xfailed, 0 xpassed, 0 other failures.
- Step 7 backend — **FAIL**: 1 failed, 2,118 passed, 5 skipped, 3 xfailed, 37 subtests passed. Sole failure: `test_verify_layout_current_tree` rejects the lead-mandated root `VERIFY.md` and `VERIFY-RESULT.md`; no product test failed.
- Step 7 frontend — **PASS**: 311/311 passed; typecheck passed; build passed (34 modules).
- Operational — **PASS**: follow-on GPU 0/10, cumulative 1/40; peak 0; retries 0; lease `FREE`; port 18314 clear; product files modified 0; remote calls 0.
- Falsifiers: nonmatching local replay (15/106, 13/53) rejected instead of replacing retained pre-terminal evidence. No final-layer falsifier hit.

**Overall: FAIL only on mandated-root verification-layout conflict; diagnosis and all product/frontend controls pass.**

## Post-relocation fix — 2026-09-20

- Verification documents relocated to `docs/verify/r4-6-overlap/`; all earlier result sections retained above.
- Attribution lead line names both `UNMEASURED` pre-terminal alternation arms and the exact retained stage streams required to measure them.
- Full backend — **PASS**: 2,119 passed, 5 skipped, 3 xfailed, 37 subtests passed, 0 failed in 174.09 s.

**Overall: PASS.**
