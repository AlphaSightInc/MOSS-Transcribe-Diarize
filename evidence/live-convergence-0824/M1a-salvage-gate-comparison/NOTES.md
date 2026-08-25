# M1a — plan §9.1 salvage-gate comparison (O1 vs O2)

Campaign run `20260825-042645-70858`, iteration 6, 2026-08-25. Preregistration:
`prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M1a.md` (written before
the comparison was run). **Zero MOSS requests were issued**: every decode read here was
already generated and saved.

## Answer in one line

**Choose O1** (salvage only a `hard_cap` span). O1 and O2 recover exactly the same words on the
full 184-span corpus; they disagree on one span, where O2 publishes one extra word that earns
**no** content-recall credit and buys +0.0043 `text_coverage` — the plan §3.4 extent artifact,
not recovered speech. O1 also needs no new state.

## The whole decision surface

10 of the 184 saved spans parse to zero segments; the other 174 parse and are gate-independent
by construction (the gate is consulted only after a parse returns nothing).

| span | freeze reason | speech ratio | dur | raw decode | O1 | O2 |
|---|---|---|---|---|---|---|
| `lex_bill_ackman#2` | hard_cap | 0.904 | 2.50 s | `[S01] The difference between,[S01] you said the stock market.` | **salvaged** | **salvaged** |
| `lex_javier_milei#3` | leading_silence | 0.000 | 1.49 s | refusal boilerplate | refused | refused |
| `lex_javier_milei#5` | leading_silence | 0.063 | 1.58 s | `[0.00][S01]Okay.` | refused (gate) | refused (gate) |
| `lex_javier_milei#13` | leading_silence | 0.000 | 0.06 s | refusal boilerplate | refused | refused |
| `lex_javier_milei#31` | stop_flush | 1.000 | 0.24 s | `[0.00][S01]And.` | **refused (gate)** | **salvaged** |
| `acquired_jamie_dimon#6` | leading_silence | 0.000 | 0.31 s | refusal boilerplate | refused | refused |
| `acquired_jamie_dimon#22` | hard_cap | 0.984 | 2.50 s | `[0.15][S01] Last year, we had you on the video board at Chase.` | **salvaged** | **salvaged** |
| `lex_adam_frank#18/47/62` | leading_silence | 0.000 | 0.87/0.04/0.30 s | refusal boilerplate | refused | refused |

**One disagreement, `lex_javier_milei#31`.** Plan §9.1's shortcut ("prefer O1 if it matches O2 on
the full corpus") therefore does not apply, and the preregistered tie-break decides it.

## Adjudicating the disagreement

Projected through the **deployed** evaluator on a real modified live hypothesis JSONL, and
through **evaluator v2** (M0c) on the same hypothesis:

| arm | WER | text_coverage | TSA | composite | v2 content recall |
|---|---|---|---|---|---|
| file (target) | .1039 | .9199 | .9115 | .9106 | .9506 |
| live baseline | .1999 | .8640 | .8400 | .8384 | .9135 |
| **O1 hard_cap** | **.1885** | .8813 | .8573 | .8542 | **.9267** |
| O2 speech ratio | .1885 | .8828 | .8587 | .8553 | **.9267** |

Per case, WER: bill .2614 → **.2273** (both gates), milei .1440 → .1440 (both), keyu .1942 →
.1942 (both). No case regresses under either gate.

The two gates are identical on every honest text axis. O2's whole margin is
`text_coverage` +0.0043 and `composite` +0.0033 on milei, produced by publishing `And.` over a
0.24 s session-tail fragment. Evaluator v2 shows what that word is worth: content recall is
**unchanged** (.9200 on milei for baseline, O1 and O2 alike), so the word entered no
longest-common-subsequence match. It is WER-neutral only by alignment accident — the reference
continues `…brought inflation down **to** its lowest…`, so `and` converts one deletion into one
substitution and the error count does not move.

By the preregistered rule — same recovery, fewer false words published, tie to the cheaper
option — **O1 wins outright**, and it wins on the metric the campaign trusts rather than on the
one plan §3.4 warns is reachable by widening timestamps.

## Cost of the two gates

- **O1** reads `FrozenSpan.reason`, which already exists at the classification seam. No new state.
- **O2** must re-run WebRTC VAD over the span PCM at decode-completion time, which also requires
  the span PCM to still be retained at that moment. New work on the latency-sensitive path.

## Findings worth carrying forward

- **F1 — the gate is load-bearing, not decoration.** Removing it (salvaging every zero-parse
  span) moves milei WER .1440 → .1520 while content recall stays .9267: the extra publications
  are false words. Trio coverage rises to .8878 and WER worsens to .1912. See `mutations.txt`.
- **F2 — the freeze reason is not a proxy for the speech ratio; it is a different predicate.**
  Over all 184 spans: `hard_cap` 163 spans, speech ratio .416–1.000, **1 below the O2 floor**;
  `leading_silence` 12 spans, .000–1.000, 11 below; `end_silence` 6 spans, .409–.917, 2 below;
  `stop_flush` 3 spans, .938–1.000, 0 below. The two gates agree on the salvage decision here
  because the zero-parse spans happen to sit where the predicates coincide, not because one
  implies the other.
- **F3 — the refusal-boilerplate filter has zero marginal load under both gates.** Every span
  whose text is the observed hallucination (`i'm sorry, i can't assist with that request.`) is
  a `leading_silence` freeze with speech ratio 0.000, so the gate alone already refuses all of
  them: with the filter disabled, the set of published spans is unchanged under O1 and under O2.
  That is expected under O1 by construction — a `hard_cap` span is 2.5 s of unbroken speech
  (`live_span_bounds` docstring), which is not the condition that provokes the hallucination —
  and 0 of 163 hard_cap spans produced one. **Recommendation for the §9.3 production change:
  ship the gate, not a phrase list.** A locale-specific string table inside general logic is
  the shape `AGENTS.md` rules out, and here it guards nothing the gate does not already guard.
  If review wants it kept as defence in depth, keep it the way this prototype does — the corpus
  read from measurement data, never literals in the module.
- **F4 — the completion rule needs no interpolation.** The earlier `live-file-gap-emptyspan`
  prototype's P1v filled absent interior boundaries by character count. This rule instead merges
  adjacent same-speaker chunks (lossless) and refuses when two *different* speaker labels have no
  timestamp between them. It reproduces P1v's published projection to four decimals
  (composite .8553 / coverage .8828 / TSA .8587 / WER .1885 under O2 = P1v) — so the strictness
  costs nothing on this corpus and removes the invented cross-speaker interval that plan D5 and
  the PRD forbid feeding to the identity path.
- **F5 — a partially parseable span silently drops its trailing turn.** Constructing
  `[0.10][S01] I think so[1.20][1.25][S02] and I agree` shows the production parser emitting the
  first turn and dropping the second, with no empty-span signal anywhere. **Not observed** in the
  77 raw decodes available (`lex_adam_frank`), and invisible in the trio/jamie corpus because
  those texts are post-parse renders. Recorded, not chased: constructible is not reachable.

## Gates (all pass; `comparison.json` → `gates`)

| gate | result |
|---|---|
| G1 corpus fidelity | 184 spans loaded; the production `WebRtcSpeechProvider` (mode 1, 160-sample frames) reproduces the earlier prototype's per-span speech ratio on **every** span (0 deltas > 0.01) |
| G2 no refusal boilerplate published | 0 under both gates; marginal load of the filter itself: 0 |
| G3 no new words on digital silence | 0 under both gates |
| G4 parse → render → parse fixed point | holds on every salvaged span (see `mutations.txt` M4 for its honest weight) |
| G5 witness-owned intervals | 5 constructed spans: same-speaker two-chunk → 1 merged interval; two-speaker with an emitted interior timestamp → 2 disjoint intervals; two-speaker/three-speaker without one → refused. No cross-speaker overlap emitted |
| G6 zero extra MOSS requests | 0 |
| G7 no case-level WER regression | none under O1 (nor under O2) |

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_salvage_gates.py \
  --output evidence/live-convergence-0824/M1a-salvage-gate-comparison/comparison.json
```

Artifacts: `comparison.json` (every span, both gates, both projections), `console.txt`,
`mutations.txt`.

## What §9.3 should ship

`classify_live_transcript` in `moss_transcribe_diarize/app/live_span_bounds.py` with the O1 gate
and the completion rule prototyped in `salvage_gates.py`; table-driven tests from the 10
zero-parse decodes plus the 5 constructed spans above; the adapter seam reading `exc.text`
(iteration 2 left the raw text stopping there deliberately) and routing it here. Expected paired
rerun: trio live WER **.1885** (PRD gate ≤ .190), no per-case regression, file mode byte-identical.
