# Live-vs-file accuracy gap: context starvation (H1) and seam loss (H2)

Throwaway bench. Two questions, one corpus (the primary lex trio, 3 x 60 s), one vLLM
endpoint, concurrency 1.

- **Diagnosis** — `diag_boundary_vs_interior.py` -> `diagnosis.json`. Where in the audio do
  live errors live?
- **Arms** — `proto_context_arms.py` -> `results.json`. Does restoring decode context close
  the gap, and at what cost? Preregistered in `preregistration-context-arms-v1.json`
  (written before any arm was built).

Repro:

```sh
BASE=/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/bd3632af-da27-408f-8e03-ecd56a586e8d/scratchpad/remeasure-20260824T160130
.venv/bin/python prototypes/live-file-gap-context/diag_boundary_vs_interior.py \
  --baseline $BASE --output prototypes/live-file-gap-context/diagnosis.json
.venv/bin/python prototypes/live-file-gap-context/proto_context_arms.py \
  --baseline $BASE --output prototypes/live-file-gap-context/results.json
```

Both are deterministic (greedy) and the second caches every decode, so a re-run costs no GPU.

## Verdict

**It is seam loss, not context starvation.** Live words more than 0.5 s from a span seam are
transcribed about as well as file mode transcribes them (WER 0.082 vs 0.072). Within 0.5 s of
a seam, live is 0.373 against file's 0.088. The 32% of the timeline that sits inside a
+/-0.4 s seam band carries 58-72% of the word-error gap and 90% of the coverage gap, and
reference bigrams that straddle a seam survive at 48.5% against 89.4% for bigrams inside a
span. H1's contribution is about one WER point; H2's is the rest.

**The lever that works is a rolling re-decode with few, wide reconciliation regions (A2).**
10 s windows on a 5 s stride, each window's central 5 s replacing the provisional words there,
passes every preregistered gate: WER 0.1289 (gate <= 0.1519), TBSA 0.8820 (>= 0.8745),
coverage 0.8926 (>= 0.8920), DER 0.1294 (<= 0.1393), and every case improves rather than
regresses. It closes 74% of the WER gap to file mode and recovers 94% of the missing content
words. **It does not meet the cost target**: +1.83 added decode-audio-seconds per audio-second
against an uncontended target of < 1.

**The cost lives in the reconciliation joins, not in the window length.** A1 at 10 s uses a
longer window than A2 but one per seam -- 157 decodes and 77 narrow cells -- and lands at WER
0.1674 for +4.28x. A1 at 5 s is *worse than doing nothing* (0.2298 vs 0.1999) because a 5 s
window leaves only 1.25 s of context on each side of the 2.5 s cell it is replacing, so it
re-cuts the same words at its own edges. Fewer, wider trust regions beat more context.

**In-line context (A4/A5) did not reproduce the sibling project's win here.** Prefix audio
alone (A4) is the only arm inside the cost budget (+0.77) and does improve the text-only
metrics slightly (WER 0.1999 -> 0.1928, content recall 0.9135 -> 0.9154, malformed decodes
5 -> 3), but it fails the extent-sensitive gates. Prompt conditioning (A5) actively harms:
WER 0.2435 and malformed decodes 5 -> 11.

## Arm table (primary-trio means)

| arm | what | WER | content recall | TBSA | coverage | DER | mean seg s | added audio-s / audio-s | gates |
|---|---|---|---|---|---|---|---|---|---|
| baseline live | deployed | .1999 | .9135 | .8384 | .8640 | .1764 | 1.84 | - | - |
| **a0** | production replica | **.1999** | **.9135** | **.8384** | **.8640** | **.1764** | 1.84 | 0.00 | validates bench |
| a4 | prefix audio 1.8 s, text-anchored trim | .1928 | .9154 | .8026 | .8084 | .2289 | 1.26 | 0.77 | fail |
| a4_ts | same, literal timestamp-cutoff trim | .1773 | .8749 | .7837 | .7781 | .2598 | 1.68 | 0.77 | fail |
| a5 | a4 + committed-transcript tail in prompt | .2435 | .8531 | .7531 | .7593 | .2862 | 1.45 | 0.77 | fail |
| a1_5s | seam re-ASR, 5 s window | .2298 | .9238 | .8631 | .9041 | .1266 | 1.84 | 2.14 | fail |
| a1_10s | seam re-ASR, 10 s window | .1674 | .9243 | .8685 | .8908 | .1388 | 1.57 | 4.28 | fail |
| **a2** | rolling 10 s / stride 5 s | **.1289** | **.9485** | **.8820** | **.8926** | **.1294** | 2.51 | 1.83 | **PASS** |
| a3 | whole-file decode (upper bound) | .1039 | .9506 | .9106 | .9199 | .1021 | 3.77 | 1.00 | pass (= file mode) |

Two validations, both exact: **a0 reproduces the deployed live arm to 0.0000 on TBSA and WER
per case**, and **a3 reproduces the deployed file arm exactly on all three cases**. The bench
is measuring the same thing production measures.

## Things a reader must not misread

- **TBSA's speaker and coverage terms and DER are time-extent quantities**, not text
  comparisons: the references are gapless turn intervals and `evaluation.py` credits
  `ref_tokens * overlap_seconds / ref.duration`. An arm that emits wider segments raises them
  without transcribing better. WER and `content_recall` are the honest, label-free numbers and
  the verdict is ranked on those; `mean_segment_seconds` is reported beside every arm so
  extent inflation is visible. A2's win survives this test -- it improves WER and content
  recall, not only the extent-sensitive terms. A4's *failure* is partly this artifact in
  reverse: trimming the prefix shortens emitted extents (1.26 s vs 1.84 s) and drags coverage
  and DER down further than its text quality warrants.
- **The identity stage is frozen.** Every arm's segments are relabelled from one shared
  speaker timeline built from the baseline live snapshot, so no arm can be credited or
  penalised for changing diarization. That is what makes a0 reproduce the baseline exactly.
  `text_coverage` and `wer` do not depend on labels; `text_speaker_accuracy` and the DER
  confusion term are held fixed.
- **Prefix audio must never reach the identity embedder.** A sibling controlled experiment
  collapsed two speakers into one when it did. This bench does not recompute embeddings, so
  A4/A5 neither exercise nor clear that risk.
- **Every wall-clock and RTF number is contended** -- three sibling agents shared the GPU.
  Contended per-request p50: a0 0.148 s per 2.5 s span, a4 0.178 s per 4.3 s span, a3 1.87 s
  per 60 s file. These bound nothing.
- **A1/A2 reconciliation is word-level.** The first implementation replaced whole segments
  whose midpoint fell in the region; a 10 s window emits multi-second segments, so that both
  duplicated words (WER 0.73 with content recall *rising* to 0.93) and dropped them in narrow
  cells. Words are split out of each segment with char-proportional times and each region
  takes only the words spoken in it, from exactly one decode.

## Secondary findings worth keeping

- **The 5 "empty" live spans are parser discards, not silence** (confirms H3, and adds the
  raw text). The bench decodes through the production validator unchanged, so it discards
  them identically. bill span 2 `[5.0, 7.5]` returned
  `'[S01] The difference between,[S01] you said the stock market.'` -- the right words with no
  timestamps at all. javier spans 5 and 31 returned `[0.00][S01]Okay.` and `[0.00][S01]And.`,
  opening timestamp present, closing timestamp missing. javier spans 3 and 13 (1.49 s and
  0.06 s) returned the refusal boilerplate `I'm sorry, I can't assist with that request.`;
  the bench filters refusals out of every arm before scoring, which is a no-op for a0 because
  the validator already discards them.
- **Malformed span syntax is a hard-cap artifact.** 5 of 80 2.5 s spans (6.25%) came back
  malformed; **0 of the 110 long windows** (5 s, 10 s, 60 s) did. Prefix audio halves it
  (5 -> 3). Prompt conditioning doubles it (5 -> 11).
- **A5's failure mode is prompt echo.** Injecting the committed tail as `前文：...` makes the
  model drop the markup (`'speculative interests, you know, supply and demand...'` with no
  tags at all), emit speaker tags without timestamps
  (`'[S01] A bit like buying,[S01] trading crypto,[S01] right?'`), or parrot the injected
  context instead of transcribing the audio -- bill spans 19 and 20 both returned
  `"[S01] There's intrinsic value.[S01] But the."`, which is the previous span's text. The
  minimal `前文：` prefix variant *is* what was measured; it is already the gentle form.
- **javier's span-freeze pathology reproduces** because the bench replays the recorded grid:
  32 committed spans, 11 shorter than the 2.5 s cap and 7 of those at or under 1.0 s (down to
  0.06 s). Two of its four empty spans are refusals on exactly those ultra-short spans, so the
  pathology directly manufactures them.
- **There is no measurable span-length dose-response in the deployed corpus** because the
  policy is bimodal: 69 of 80 spans are exactly 2.5 s and all 11 shorter ones are <= 1.58 s
  silence fragments carrying 4 reference words between them. The dose-response that does exist
  is over *context around the decoded region*, and the arms measure it: 0 s -> .1999,
  1.25 s (a1_5s) -> .2298, 2.5 s (a2) -> .1289, 3.75 s (a1_10s) -> .1674, whole file -> .1039.
  It is not monotone in context, which is the point: joins cost more than context buys.

## Recommended next step

A2's shape is right and its price is not. The obvious follow-up, untested here: keep the
rolling re-decode but widen the stride (10 s window / 10 s stride, or 15 s / 10 s) to cut the
added decode load toward 1.0 while keeping the number of joins low. The evidence says the
joins, not the window seconds, are what damages the transcript, so a wider stride should cost
less *and* score no worse. Nothing in this bench tested it.

Do not pursue A5. Do not pursue seam-targeted (per-seam) re-ASR -- A1 is dominated by A2 on
both axes at every window length measured.
