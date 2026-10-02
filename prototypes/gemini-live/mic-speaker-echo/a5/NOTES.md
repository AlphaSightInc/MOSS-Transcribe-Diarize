# R5B-FIX5A — remembered cuts lose removed solid support ($0)

Registered before measurement; throwaway candidate, retained as a replay bench.

## Structural contract

- Q1: can a cut remain justified after rolling removes the solid text that proved it?
- P1: lane isolates authorities; existing comparable prefix identifies the removed text;
  existing observed end bounds continuity; visible base rows identify replaceable support;
  successful rolling update is the replacement event. No new state or thresholds needed.
- I1: never hide newly unsupported speech; prefix-only output; lane isolation; preserve
  A2 normal-turn divergence and suffix-only degraded commits; no additional recorded
  flicker; empty preview, Stop and a new meeting have empty remembered state.
- U1: text membership does not establish actual speech timing. Replacing base rows can
  remove proof even when the rolling clock advances. Raw stress previews and physical
  device behavior remain UNMEASURED; frozen post-trim captures are not raw provider input.
- H1: forget a remembered cut after successful rolling if that lane loses a visible
  base row starting before the remembered end. Rolling rows are retained, so a normal
  rolling append does not discard its earlier proof. The next preview uses today's
  stateless alignment, then can remember the resulting proven prefix again.
- X1: any of the 61 unsupported words remains hidden; an A2 recorded output worsens;
  a normal-turn proven prefix flickers; the other lane loses its cut; Stop retains state.
- T1: actual runtime callbacks replay the confirmed attack and lifecycle/ownership
  controls; A3's unchanged retained checker exercises all recorded F1/A2 cells and c5b.
  Red regressions prove production lacks the repair. Full backend tests detect integration
  breakage. No provider, browser, host, port, audio access or new measurement scaffold.

## Exact candidate

After an applied rolling update, compare the pre/post effective solid rows. A visible
base row has authority `provisional`. Forget only cuts in a removed base row's lane with
observed end greater than that removed row's start. Use actual surface removal rather
than duplicating lane-frontier rules: an empty `revision_lanes` can retain existing
lane frontiers. This also handles a straddling row removed by start-owned projection.
Do not infer textual coverage from time or advance a cut from time.
Clear remembered state when Stop has actually closed the session, after tail drain.

One command from worktree root:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a5/measure.py`

Evidence: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-FIX5A/`.
Verdict: **ACCEPT**, measured before production edits.

## Prototype receipts

- M1 replacement: baseline hides 61 unsupported words; candidate hides 0, restoring
  all 61 plus the 21-word fresh suffix. Empty answer: baseline hides 81, candidate 0.
  Both lanes pass; full cuts/solid/preview state in `transitions.json`.
- M2 retention: 11 existing A2/ownership controls pass in both runtimes, including
  >5-minute normal turn, divergence, chorus, rewrite, empty preview and other-lane
  replacement. Unscoped rolling with existing lane frontiers retains the base proof
  and its cut. Stateless output is not a fresh-loss oracle when that full base survives.
- M3 lifecycle: candidate clears cut state on Stop (baseline retains it); new meeting
  state empty in both. Stop follows tail drain so the existing commit repair can finish.
- M4 frozen matrix: 2,749/2,749 exact A2/F1 parity; all unchanged vs stateless on that
  recorded population, 575/575 non-CJK calls unchanged. Original streams: 366 Mandarin,
  575 English, 64 R5-D calls, exact output parity; no additional fresh loss or flicker.
- M5 c5b: pre-A2/A2/candidate rows 27/23/23; paragraph openings 19/0/0;
  `right` 5/1/1; distinct `Yeah.` 2/2/2. c2/c4/c5b/c6 re-trim text and fresh/re-shown
  metrics unchanged; bounded-tail scorer unchanged. Raw stress repair remains unmeasured.

The first frozen harness run bound a copied method's trim globals too early and made
the pre-A2 baseline report 23 rather than 27 rows. Fixed only the prototype's module
lookup; reran all cells. Accepted receipt reproduces 27/23/23, not that invalid run.

Five new regression cases failed with assertion failures on unchanged production:
`test_rolling_replacement_forgets_cut_backed_by_removed_solid` (both lanes × empty/
20-word replacement) and `test_stop_clears_remembered_preview_cut`. Other-lane retention
control passes before the change. No existing expectation changed.

## Product verification

Current-tree one-command bench (absorbs the transition audit and unchanged A3 checker):
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a5/product_check.py`

The original `measure.py` command is the pre-implementation experiment at ac67b852;
its baseline expects the confirmed 61-word loss. Product checking uses the fixed
runtime directly, comparing every transition to the saved pre-implementation candidate.

- A5 product/prototype full-state parity: 5/5 transitions, including empty replacement,
  both lanes, retained-base control, Stop and new meeting. Unsupported words hidden 0/0.
- Exact review probe copied with only its two fixed-output assertions changed: fails
  unchanged product, passes fixed product, showing the missing 61 words plus fresh suffix.
- Product tests: 121 preview/runtime tests pass; five new failing assertions now pass;
  other-lane retention control passes before/after. Existing tests unchanged.
- F1/A2 product: 2,749/2,749 exact output parity, 575/575 non-CJK unchanged;
  Mandarin/English/R5-D 366/575/64 original-stream calls identical. All recorded text,
  fresh, repetition and re-shown-prefix metrics equal the prototype, including c2/c4/c5b/c6.
  Product vs prototype c5b: rows 23/23; paragraph openings 0/0; right 1/1; Yeah 2/2.
- Timing is retained separately from text gates: comparing repeated wall-clock timing
  samples as exact values initially failed the added receipt comparison. Only the three
  `us_mean`/`us_p99`/`us_max` fields were excluded from equality; all text metrics still
  require exact equality. Neither the unchanged A3 checker nor the frozen F1/A2 rules changed.

Full backend: **2833 passed, 9 skipped, 2 xfailed, 37 subtests passed**, 27 warnings,
401.97s, exit 0. Command: `MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1
../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python -m pytest -q -p no:cacheprovider tests`.

Retained trim timing prototype/product: captured weighted 0.178/0.184ms; c2
0.184/0.190ms; c4 0.152/0.153ms; c5b 1.455/1.472ms; c6 0.740/0.746ms.
These time only trim, not added rolling replacement work; no speedup claimed.

Provider calls/spend: 0/$0. No frontend or neighbouring
engine changes. T4 still rejected. Existing raw-stress repetition/c5b >1ms and physical
device qualification limits remain; this repair adds no fresh-provider claim.
