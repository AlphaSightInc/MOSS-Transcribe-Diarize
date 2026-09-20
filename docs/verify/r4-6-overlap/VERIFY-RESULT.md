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
