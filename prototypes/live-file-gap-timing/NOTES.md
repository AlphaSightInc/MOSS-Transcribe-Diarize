# H5 — timestamp fidelity as a share of the live-vs-file accuracy gap

**Question.** Live mode's per-span model timestamps come from ~2.5s isolated decodes.
Are they systematically noisier or biased vs file mode's long-window timestamps, and
does that deflate overlap-based metrics (text_speaker_accuracy, DER, coverage) enough to
explain a material share of the live-vs-file TBSA gap?

**Answer: yes — and far more than expected. Timing explains ~91% of the TBSA gap, but
the finding that matters is that this is mostly a scorer defect, not a live-mode defect.**

Baseline (trio mean, fresh paired deployed-stack run `remeasure-20260824T160130`):

| arm  | TBSA  | TSA   | coverage | WER   | DER   | emitted s |
|------|-------|-------|----------|-------|-------|-----------|
| file | .9106 | .9115 | .9199    | .1039 | .1021 | 54.59 |
| live | .8384 | .8400 | .8640    | .1999 | .1764 | 51.23 |

TBSA gap = .0722.

---

## F1 — 67% of the TBSA gap sits in terms that contain no text information

`calculate_tbsa` = 0.40·TSA + 0.35·coverage + 0.25·(1−WER). Reading
`evaluation._text_speaker_weights` and `_text_coverage`: **both** credit a reference
segment by `ref_tokens × (overlap_seconds / ref.duration)`. Neither compares a single
character of hypothesis text. They are pure time-overlap measures, token-weighted.
Only WER (25% of the composite) is text-based.

Gap decomposition:

| term | contribution | share | nature |
|------|--------------|-------|--------|
| 0.40·ΔTSA      | .02860 | 39.6% | pure time-overlap |
| 0.35·Δcoverage | .01957 | 27.1% | pure time-overlap |
| 0.25·ΔWER      | .02400 | 33.3% | only text-based term |
| **total**      | .07217 | | |

## F2 — the reference has no word times and no silence, so the temporal terms reward wall-clock extent

The corpus references are coarse speaker-turn intervals on round boundaries that tile the
full 60s with zero gaps (e.g. `lex_bill_ackman`: 0–29, 29–33, 33–40, 40–42, 42–60;
`lex_javier_milei`: 0–10, 10–60). Word rates inside a segment vary 1.0–3.7 w/s.
Consequence: covering wall-clock time *is* the metric.

Degenerate control — one segment `{start: 0, end: 60, speaker: "S01", text: "xx"}`,
i.e. zero correct words:

| case | coverage | TSA | DER | TBSA | WER |
|------|----------|-----|-----|------|-----|
| lex_bill_ackman  | 1.000 | .9148 | .1000 | .7159 | 1.0 |
| lex_javier_milei | 1.000 | .9040 | .1667 | .7116 | 1.0 |
| lex_keyu_jin     | 1.000 | .6691 | .2500 | .6176 | 1.0 |
| **trio mean**    | **1.000** | **.8293** | **.1722** | **.6817** | 1.0 |

A hypothesis with no correct words scores coverage 1.000, TSA .8293 and **DER .1722 —
better than the real file arm's coverage (.9199) and statistically indistinguishable from
the real live arm's DER (.1764)**. TSA .8293 is only 8pp below file's .9115.

## F3 — D1 as specified cannot measure timestamp noise; live is not worse than file on it

Token-level alignment (Levenshtein over `_tokenize`d tokens, matches only), hypothesis and
reference token times interpolated uniformly inside their segments:

| arm  | median abs | p90 | max | mean signed |
|------|------------|-----|-----|-------------|
| file | 1.302 s | 2.417 s | 3.711 s | +0.912 s |
| live | 1.206 s | 2.586 s | 3.863 s | +0.811 s |

Both arms show ~1.2–1.3 s median error and a shared ~+0.9 s bias — an artifact of
interpolating inside 2–50 s reference turns (per-case: `lex_javier_milei`, whose reference
is two segments of 10 s and 50 s, shows med 2.05–2.32 s in *both* arms;
`lex_keyu_jin`, the finest reference, shows 0.39–0.50 s in both). **Live's error is
slightly lower than file's at the median.** The measurement is dominated by reference
coarseness and is unusable as an absolute number.

## F4 — with file timestamps as pseudo-gold, live's timestamps track file's to ~0.24 s

Aligning live tokens directly to file tokens (words *both* arms transcribed correctly),
n = 140 tokens/case:

| case | n | median abs | p90 | max | mean signed |
|------|---|-----------|-----|-----|-------------|
| lex_bill_ackman  | 165 | 0.274 s | 0.900 s | 2.308 s | +0.088 s |
| lex_javier_milei | 114 | 0.263 s | 0.705 s | 1.048 s | −0.298 s |
| lex_keyu_jin     | 142 | 0.189 s | 0.581 s | 0.842 s | −0.082 s |
| **trio mean**    | 140 | **0.242 s** | **0.729 s** | **1.399 s** | **−0.097 s** |

Speaker label agreement on those matched tokens: **98.99%**. Live's per-word timing is
mildly early (−0.10 s) and jitters by a quarter second at the median — *not* the
multi-second corruption the TBSA/DER deltas would suggest.

## F5 — the live deficit is emitted *extent*, and the extent loss is 78% intra-span gaps

Span base = `start_sample/16000` is exact; residuals are within-span only. Drift slope of
signed error vs absolute time is +0.055 / +0.058 / −0.039 s/s — inconsistent in sign
across cases, i.e. no absolute offset or accumulating drift.

| case | spans | empty | s lost to empty spans | s lost to intra-span gaps | emitted s |
|------|-------|-------|----------------------|---------------------------|-----------|
| lex_bill_ackman  | 24 | 1 | 2.50 | 7.26 | 50.24 |
| lex_javier_milei | 32 | 4 | 3.37 | 7.28 | 49.35 |
| lex_keyu_jin     | 24 | 0 | 0.00 | 5.89 | 54.11 |
| **trio mean**    | 26.7 | 1.67 | **1.96** | **6.81** | **51.23** |

Of the 8.77 s of the 60 s timeline live never covers, only 1.96 s is genuine content loss
(fully empty spans); 6.81 s is span time inside spans that *did* produce text.

Within-span edge geometry (D3):
- The first segment of a span starts at exactly relative `0.000` in **50–70%** of spans
  (.70 / .50 / .62) — a hard leading-edge snap.
- The trailing edge is *not* clamped: only 7–17% of spans end at the 2.5 s cap; median
  relative end is **2.43–2.44 s**, i.e. ~60 ms short.
- Error binned by within-span position (early / mid / late thirds) shows no monotone
  compression or expansion — the between-third differences are smaller than the
  between-case variation.
- `lex_javier_milei` freezes 32 spans with durations from 0.06 s to 2.5 s (silence
  freezes), vs uniform 2.5 s hard-cap spans for the other two cases.

## F6 — D2 oracle re-timing bound

Rebuild each hypothesis with every segment's times replaced by the reference-derived
times of its matched tokens (segments with no matches keep their own times); clipped to
disjoint so overlap credit cannot double-count.

| arm  | baseline TBSA | oracle-retimed TBSA | Δ |
|------|---------------|---------------------|---|
| file | .9106 | .9432 | +.0326 |
| live | .8384 | .8878 | +.0494 |

Residual gap after both arms get oracle timing: .9432 − .8878 = **.0554**.
Timing's share by this bound = (.0722 − .0554) / .0722 = **.0168 TBSA = 23.3%**.
(Unclipped: file .9432, live .8964, residual .0468 → .0254 = 35.2%.)

Note the file arm gains +.0326 from oracle re-timing *even though its timestamps are the
reference standard* — that gain is the looseness floor of the ref-snap oracle against a
coarse reference, so only the live-minus-file differential is meaningful here.

## F7 — Phase 2: a realizable span-edge correction closes 91% of the gap without touching a word

`vad_span_edge_snap.py` runs webrtcvad (30 ms frames, 200 ms silence bridging, 90 ms
minimum speech) over each committed span's PCM, then re-lays that span's emitted segments
so they tile exactly the span's VAD speech, in order, proportional to their original
emitted durations. Text, speaker labels and token order are untouched — WER is invariant
by construction (asserted in the script).

| arm | TBSA | ΔTBSA | TSA | coverage | WER | DER | emitted s |
|-----|------|-------|-----|----------|-----|-----|-----------|
| file_baseline     | .9106 | +.0722 | .9115 | .9199 | .1039 | .1021 | 54.59 |
| live_baseline     | .8384 |  .0000 | .8400 | .8640 | .1999 | .1764 | 51.23 |
| live_vadsnap a=0  | .9071 | +.0687 | .9273 | .9605 | .1999 | .0852 | 57.42 |
| live_vadsnap a=1  | .9071 | +.0687 | .9273 | .9605 | .1999 | .0852 | 57.42 |
| live_vadsnap a=2  | .9042 | +.0658 | .9235 | .9564 | .1999 | .0892 | 57.13 |
| live_vadsnap a=3  | .8966 | +.0582 | .9133 | .9465 | .1999 | .1011 | 56.44 |
| live_spanfill     | .9150 | +.0766 | .9378 | .9711 | .1999 | .0752 | 58.04 |
| degenerate 0–60   | .6817 | −.1567 | .8293 | 1.0000 | 1.0000 | .1722 | 60.00 |

At aggressiveness 2, pure re-timing takes live from .8384 to **.9042 — 91.2% of the
.0722 gap — and puts live *above* file on TSA (.9235 vs .9115), coverage (.9564 vs .9199)
and DER (.0892 vs .1021) while still transcribing at nearly twice the word error rate
(.1999 vs .1039).** `live_spanfill` (tile the whole span, ignore silence) reaches .9150,
i.e. **106% of the gap** — it overtakes file's TBSA outright.

VAD speech in the 60 s corpus: 55.9–58.7 s (ackman), 48.6–53.9 s (milei), 57.2–59.2 s
(keyu) depending on aggressiveness — versus 60.0 s the reference labels as speech.

---

## Verdict (D4)

- **Timing's share of the .0722 TBSA gap: 23.3% (1.68 pp) by the reference-snap oracle
  upper bound of D2; 91.2% (6.58 pp) by the realizable VAD span-edge correction; 106% by
  naive span-fill.** The realizable correction beats the "upper bound" because the D2
  oracle can only re-time segments that have matched tokens, while span-based correction
  needs no reference at all.
- **The honest reading is not "fix live's timestamps".** 67% of the TBSA gap and 100% of
  the DER gap live in metrics that a single 60-second segment containing the text `"xx"`
  scores at coverage 1.000 / TSA .8293 / DER .1722. Padding hypothesis extent is worth
  more to TBSA than transcribing correctly. Live's real handicap under these scorers is
  that it emits 51.2 s of the timeline where file emits 54.6 s.
- **Live's timestamps are not materially noisier than file's**: 0.242 s median and 0.729 s
  p90 deviation from file's on words both arms got right, 98.99% speaker agreement, no
  drift, no within-span compression, span base exact.
- **The residual, genuine content gap is the WER term: .0960 absolute WER
  (.1999 vs .1039), contributing .0240 of TBSA (33.3%).** That is the only part of the gap
  that survives any re-timing, and the only part worth chasing as an accuracy problem. Of
  the extent loss, 1.96 s/case is true content loss (empty spans) — that shows up in WER
  too — and 6.81 s/case is span time inside spans that did produce text.

### Recommendation

1. Do **not** ship a timestamp correction to chase TBSA. It would buy 6.6 pp of a metric
   that a garbage hypothesis already scores .68 on, and would make live look better than
   file while transcribing worse. That is metric gaming, not an accuracy improvement.
2. **Fix the scorer or the corpus first.** Either give the references word-level times and
   real silence gaps, or reweight TBSA away from the two pure-extent terms. Until then,
   TSA / coverage / DER comparisons between arms with different emitted extents are not
   interpretable, and the H1–H4 hypotheses should be re-read with that in mind.
3. The one substantive live-mode defect this surfaced is the **empty-span rate**
   (1.67 spans/case, 1.96 s, worst on `lex_javier_milei` at 4 spans / 3.37 s) and the
   `lex_javier_milei` span-freeze pathology (32 spans, durations down to 0.06 s). Both are
   content problems and both show up in WER.

## Repro

```bash
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize
.venv/bin/python prototypes/live-file-gap-timing/vad_span_edge_snap.py
```

Phase-1 analysis scripts (D1/D1b/D2/D3) live in the session scratchpad at
`/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/bd3632af-da27-408f-8e03-ecd56a586e8d/scratchpad/`
as `h5_timing.py` / `h5_timing2.py`, writing `h5-timing-report.json` /
`h5-timing-report2.json`. They read only the paired baseline artifacts in
`remeasure-20260824T160130/` plus the corpus references — no decodes, no GPU, no service
calls.

**Status: prototype answered its question. `vad_span_edge_snap.py` is throwaway — delete
it once the scorer decision in recommendation 2 is made.**
