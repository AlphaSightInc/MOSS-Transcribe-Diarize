# Preregistration — M1a, plan §9.1 salvage-gate comparison (O1 vs O2)

Written **before** the comparison and the projection were run (2026-08-25, campaign run
20260825-042645-70858, iteration 6). Throwaway prototype; the verdict is ported into
`classify_live_transcript` by plan §9.3, then this directory's finding folds into the design doc.

## Question

Plan §9.1: a live span whose decode parses to zero segments carries words the system throws
away. Two gates were proposed for deciding when the repaired decode may be published:

- **O1** — `freeze_reason == hard_cap` + safe grammar completion + non-refusal text.
- **O2** — safe grammar completion + WebRTC VAD speech ratio `>= 0.5` recomputed over the span
  PCM + non-refusal text.

**Which gate publishes recovered speech without publishing hallucinations, and does O1 match O2
on the full corpus?**

## Corpus (fixed now, no new decodes)

184 spans, all decodes already saved; **zero MOSS requests are issued by this comparison**.

| tier | case | spans | text source |
|---|---|---|---|
| trio | `lex_bill_ackman` | 24 | committed transcript; the 1 discard from `out/d3.json` |
| trio | `lex_javier_milei` | 32 | committed transcript; the 4 discards from `out/d3.json` |
| trio | `lex_keyu_jin` | 24 | committed transcript (no discards) |
| secondary | `acquired_jamie_dimon` | 27 | committed transcript; the 2 discards from `out/d3.json` |
| 3-min | `lex_adam_frank` | 77 | `out/p1-lex_adam_frank.json` raw decodes (validation bypassed) |

Span bounds and freeze reasons come from `prototypes/live-file-gap-baseline-20260824/trio-60s/`
(verified span-for-span identical to the `live-file-gap-emptyspan` prototype's `out/d1.json`
corpus) and from the 3-minute span simulator whose fidelity gate G2 already passed.

Plus **constructed two-speaker hard-cap spans**, required by plan §9.2, which the saved corpus
does not contain: a same-speaker two-chunk text, a two-speaker text with an interior timestamp,
and a two-speaker text with no interior timestamp.

Speech ratio is recomputed with the production `WebRtcSpeechProvider`
(`app/live_provider_bundle.py`) under the deployed configuration (`webrtcvad` mode 1,
`frame_samples` 160), not with the prototype's own VAD call.

## Completion rule under test (common to O1 and O2)

The gates differ only in *when* to publish; both need one rule for *what* the repaired
transcript is. Preregistered rule, from `live_span_bounds`'s own governing precedent (a
timestamp outside the span is clamped in, never refused) extended to a timestamp that is
**absent**:

1. Tokenize the raw text into timestamp / speaker / text runs. If it is not the span grammar
   `([start])?[Sxx]text([end])?` repeated, refuse — `unparseable_not_salvageable`.
2. Merge consecutive chunks that carry the **same speaker label and no timestamp between them**.
   No boundary is invented; the words and the label are unchanged.
3. Supply an absent **outer** bound from the span's own bounds: a missing first start becomes
   `0.0`, a missing final end becomes `sample_count / 16000`.
4. **Refuse if an interior boundary between two different speaker labels is absent.** The words
   are real but the extent is not knowable, and a guessed boundary would hand
   `live_identity` an interval containing another speaker's audio (plan D5; PRD: speaker
   embeddings never receive mixed-window audio).
5. Require `parse -> render -> parse` to be a fixed point through the production
   `span_segments` / `render_segments`; refuse otherwise.

This rule is stricter than the earlier `live-file-gap-emptyspan` prototype's P1v, which
interpolated absent interior boundaries by character count. Whether the strictness costs
recovery on this corpus is one of the reported numbers.

## Gates (pass/fail, decided now)

- **G1 corpus fidelity** — all 184 spans load with bounds, freeze reason, speech ratio and text;
  the recomputed production speech ratio reproduces the earlier prototype's per-span ratio to
  within 0.01 on every span, or the difference is explained.
- **G2 no refusal boilerplate published** — under the chosen gate, no span whose text is the
  observed refusal hallucination is published.
- **G3 no new words on digital silence** — no span with an all-zero or near-zero PCM window is
  published.
- **G4 fixed point** — every salvaged transcript satisfies `parse -> render -> parse`.
- **G5 witness-owned intervals** — the intervals a salvage emits are exactly the intervals a
  downstream identity preparer would receive; no invented cross-speaker interval is emitted.
- **G6 zero extra MOSS requests** — the policy issues none, and this comparison issues none.
- **G7 no case-level WER regression** — projected through the real deployed evaluator on a real
  modified hypothesis JSONL, per-case live WER must not rise for any trio case.

## Decision rule (fixed now)

1. If O1 and O2 accept and refuse exactly the same spans on the full corpus, choose **O1**
   (plan §9.1: no new state, targets the observed failure shape).
2. If they disagree, each disagreeing span is adjudicated on the gates above in order:
   an option that fails G2, G3, G5 or G7 loses outright. If both survive, the winner is the one
   with the higher (oracle words recovered − false words published); a tie goes to **O1**, the
   cheaper option, per the earlier prototype's stopping rule.
3. The chosen gate's projected trio numbers are reported whether or not they beat the published
   P1v projection (composite .8553 / WER .1885). No threshold moves to make a result pass.

## Cost accounting

Extra decode requests: 0 by construction for every option (the words are already generated).
Extra state: O1 reads `FrozenSpan.reason`, which already exists. O2 needs the span PCM re-run
through a VAD instance at classification time — new work on the decode-completion path, and the
PCM must still be retained at that moment.
