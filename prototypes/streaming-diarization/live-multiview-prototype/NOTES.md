# Live multi-view transcript prototype — 2026-08-24

## Question

Can five-second seam views, staggered ten-second views, or a terminal 150-second
view correct the quality lost by independent short live MOSS spans? In particular,
can a ten-second witness make a one-second provisional cap useful without making
the one-second text canonical?

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-multiview-prototype/compare_live_multiview.py \
  --output /tmp/moss-live-multiview-results.json
```

The command prints preflight, every arm's complete endpoint accounting, and the
full aggregate result. The JSON retains every span/view plan, raw MOSS transcript,
reconciliation event, case score, request time, and endpoint metric delta.

## Contract

- Three fully referenced real 60-second interviews: Bill Ackman, Javier Milei,
  and Keyu Jin; 180 seconds total.
- Same deployed `OpenMOSS-Team/MOSS-Transcribe-Diarize`, prompt, greedy decode,
  production WebRTC VAD, production span endpoint policy, and production WeSpeaker
  live identity stack.
- One-second and 2.5-second arms decode independently. Rolling10 uses one shared
  set of 10-second windows at five-second stride and is applied to both bases.
  Terminal150 uses one full 60-second request per case.
- Reconciliation never reads reference truth. Truth enters only in the evaluator.
- GPU real-time factor (RTF) uses vLLM's inference-time counter deltas. Every arm
  had exact expected/observed request counts, zero running/waiting requests at its
  boundaries, and negligible queue time.
- Publication/correction times replay real request wall times from each view's
  audio-eligibility point. They exclude capture transport and browser paint, and
  do not model contention between provisional and witness queues.
- References contain coarse turns tiling most of each minute. That can inflate
  timestamp-derived coverage, diarization error rate (DER), and transcript-based
  speaker attribution (TBSA). Word error rate (WER) is the primary evidence that
  words were actually corrected.

## Measured aggregate

| Arm | TBSA | WER | Coverage | DER | First output | Correction/final | GPU meeting-load RTF |
|---|---:|---:|---:|---:|---:|---:|---:|
| Current 2.5 s | .838 | .200 | .864 | .176 | 3.25 s | none | .057 |
| Seam5 on 2.5 s | .846 | .217 | .925 | .231 | same provisional | .20 s after replaced provisional | .057 + .074 = .131 |
| Rolling10 on 2.5 s | .889 | .146 | .905 | .114 | same provisional | 3.69 s after provisional | .057 + .056 = .113 |
| Current 1 s | .638 | .377 | .783 | .457 | 1.19 s | none | .115 |
| Rolling10 on 1 s | .804 | .146 | .905 | .292 | same provisional | 4.65 s after provisional | .115 + .056 = .171 |
| Terminal150 | .911 | .104 | .920 | .102 | meeting end | 1.86 s after meeting | .030 component |

`First output` is mean publication time from meeting start. Mean age of the first
word at publication was 3.04 seconds for current 2.5 s and 1.00 second for current
1 s.

All three rolling10 cases improved WER over both bases:

| Case | Current 2.5 s | Rolling10 | Current 1 s | Rolling10 | Terminal150 |
|---|---:|---:|---:|---:|---:|
| Bill Ackman | .261 | .205 | .330 | .205 | .159 |
| Javier Milei | .144 | .104 | .448 | .104 | .088 |
| Keyu Jin | .194 | .129 | .353 | .129 | .065 |

## Full-state finding during the prototype

The first midpoint stitch duplicated overlap text because MOSS timestamps whole
speaker turns, while adjacent windows can place the same boundary words in turns
with different bounds. It produced impossible speaker-credit values above one and
was rejected before interpretation. The corrected truth-blind stitch distributes a
turn's words over its reported interval, owns/subtracts the same word-time pieces on
both sides, and prevents adjacent seam ownership intervals from overlapping. A full
fresh inference rerun reproduced the corrected scores above.

## Verdict

- **D1 — Current 1 s alone: REJECT.** It cuts first-word age by 2.05 seconds, but
  WER worsens by 17.7 percentage points, DER by 28.1 points, requests rise 80→189,
  and endpoint GPU RTF nearly doubles despite identical submitted audio.
- **D2 — Seam5 at every current seam: REJECT.** It spends 380 seconds of witness
  audio over a 180-second corpus, worsens WER and DER, and its TBSA increase is a
  timestamp/coverage effect rather than better words.
- **D3 — Rolling10 text correction: PASS as the next prototype direction.** It
  reduces WER .200→.146 on the 2.5-second base and .377→.146 on the one-second base.
  Thus the longer witness fully compensates the one-second base's ASR loss in this
  corpus and gives the same corrected words/coverage from either base.
- **D4 — Rolling10 speaker correction on a 1 s base: NOT YET.** DER improves
  .457→.292, but remains far worse than .114 on the 2.5-second base. The same
  rolling words but different DER isolate the remaining problem: rolling speakers
  are reconciled through the short base's weaker identity anchors.
- **D5 — Terminal150: PASS as delayed canonical convergence.** It is the quality
  upper bound and cheapest inference component, but cannot provide live corrections.

## Next measured design

Keep one-second output explicitly provisional. Make rolling10 authoritative for
both text and speaker identity by extracting/reconciling identity evidence from the
long witness itself instead of inheriting one-second labels. Keep terminal150 as the
meeting-end canonical pass. Prototype that speaker-authority change before any
production implementation.
