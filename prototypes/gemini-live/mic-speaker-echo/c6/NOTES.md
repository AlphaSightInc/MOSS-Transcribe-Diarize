# R5B-FIX6 — admission and time-shift judgement share the source run

## Contract

Q1 Structural question: does rejected source evidence hide a time-shifted reply from H2 when admission later removes that source?
P1 Minimum primitives: provider hole locates omissions; admitted source run owns eligibility and whole-run duplicate judgement; original clean-up words own the replacement text; existing H2 comparison owns the bounded decision. None substitutes for another.
I1 Invariants: no duplicate insertion or diagnostic count; genuine omissions survive; per-source eligibility, labels, counters/caches, existing hole-level H2 check and 1 s/12-unit/0.1 s bounds unchanged.
U1 Unknowns: fresh provider/device frequency remains UNMEASURED. The inherited H2 accepted loss for a genuine repeated phrase adjacent to an identical clean-up phrase remains.
F1 Falsifier: any lost genuine restore, recorded gate regression, stray restore, or cost >2 s/120 candidates rejects the change; stop without tuning.
T1 Tools: unchanged reviewer probes establish failure; in-memory method substitution tests placement; copied C5 runner measures the frozen population with production modules; red tests pin source custody at rolling->terminal seam; full backend detects integration regressions.

## Prototype rule

After final surviving per-source weight-15 admission, group admitted words by the existing `local[id(word)]` source-run number. Reuse `_already_beside` on each whole surviving source run against original clean-up words. Remove only complete matching source runs before existing label assignment/insertion/counting. Keep the remaining admitted words in their original order and existing aggregate insertion/label/counter shape. This also checks distinct admitted runs sharing one hole, without pooling their duplicate evidence.

System path: `restore_system_witnessed_words` calls `restore_witnessed_words` once on whole holes; only labels are reassigned afterward, with every filled word retained. There is no separately admitted/inserted source subset; leave it unchanged.

## Reproduction

From worktree root (no provider calls):
`R5B_FIX6_PROTOTYPE=1 PYTHONPATH=/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX6/hook:. PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX6/c5-run.py product`

Throwaway method snapshot and launch hook retained in owned evidence only. Reviewer scripts first ran unchanged (copied file location only): both 1 alone/2 mixed, stray0. Closure copies change only the expected mixed-copy count to1. Prototype both 1 alone/1 mixed, stray0. Full per-word/saved state retained in logs and JSON.

Initial harness indentation mismatch failed installation: failed logs retained as `setup-failed-*`; incomplete C5 run interrupted. Fixed substitution indentation; installation now fails closed. These are harness failures, not gate results.

Verdict before production edits: **PASS**. Both reviewer probes1/1; stray0;19 attacks pass;127 cells x4 surfaces exact against immutable C2; zero saved row/label changes;56 negative conditions/28 samples/908 words restore0;24 isolated controls and4 whole-engine injections pass; local recall206/291/310 of343; system names236/250; H100 lost4/doubles0;120 candidates1.625445s (<2s),720000 mode1 frames/360 restored words; empty candidates0 frames. No genuine restore lost. Full logs/receipts preserved in `prototype-results/` before product replay.


## Product verdict — PASS

| Gate | In-memory prototype | Product |
|---|---:|---:|
| G1 deterministic reviewer: alone/mixed copies; stray |1/1;0|1/1;0|
| G1 public PCM + production detectors/encoder: copies; stray |1/1;0|1/1;0|
| G2 FIX5B attack/closure probes |19 pass|19 pass|
| G2 negative conditions / samples / provider words |56 /28 /908; restored0|56 /28 /908; restored0|
| G2 frozen recorded cells x surfaces |127 x4 exact|127 x4 exact|
| G2 local recall live /Stop /saved, denominator343 |206 /291 /310|206 /291 /310|
| G2 system names, denominator250 |236|236|
| G2 H100 lost names /adjacent duplicates |4 /0|4 /0|
| G2 cost120 candidates, seconds |1.625445|1.554920|
| G2 cost120 mode1 frames /restored words; empty frames |720000 /360;0|720000 /360;0|
| G2 isolated controls /whole-engine injections |24 /4 pass|24 /4 pass|
| G3 terminal states vs prototype, excluding measured wall clock |131 reference|131 exact|
| G3 saved row changes in recorded population /lost genuine restores |0 /0|0 /0|
| G4 full backend |not a prototype gate|2860 passed,9 skipped,2 xfailed,27 warnings,37 subtests;432.15s|

Both reviewer mixed cells changed from2 copies to1 by withholding the entire time-shifted reply run; original clean-up copy retained, stray0. No other recorded cell's saved rows changed. Complete before/after per-word and row state: owned evidence `product-vs-prototype.json`; no lost genuine restore and no tuning/reruns of adverse results. Inherited sweep proxy flags unchanged; no scoring change.

## Red -> green

- `test_shifted_reply_with_rejected_source_is_saved_once`: FAIL on94354db5 (8 saved words vs4) -> PASS product; shift contributes0 restored words.
- `test_genuine_omission_with_rejected_source_is_restored_once`: PASS baseline -> PASS product; omitted reply restores4 words once, rejected neighbour0.
- `test_isolated_shifted_reply_stays_saved_once`: PASS baseline -> PASS product; unchanged H2 case,0 restored words.

The two controls intentionally already pass baseline; no existing test changed. Targeted93 pass. Tests check real rolling source custody -> terminal saved words/rows and restore diagnostics; detectors controlled like the deterministic reviewer probe. Public closure additionally measures actual voice detectors modes1/3, pinned encoder, registry and saved rows with injected words/clocks; gain4 seam with12 clipped samples retained. Fresh provider/device occurrence remains UNMEASURED; inherited H2 adjacent genuine-repetition loss remains. No frontend or provider calls.

Implementation: `gemini_coverage.py:119` exposes the existing H2 rule through one small helper; `gemini_lane_engine.py:688` groups final admitted words by their existing source-run number and withholds matching complete runs before existing insertion/counting. System unchanged: `gemini_coverage.py:295` delegates whole-hole insertion to:208; later labels retain every filled word. Design paragraph: `docs/design-gemini-live.md:183`.

Evidence/reproduction commands and harness-only deviations: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX6/RUN.md`. Prototype rule absorbed into product; baseline method snapshot and monkeypatch retained only as replay evidence. Gates ran once on the final product; full backend completed before final commit. Local commit only; no push/merge/PR.
