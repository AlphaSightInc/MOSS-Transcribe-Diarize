# H3 "empty-span decodes" — verdict

**Throwaway prototype.** Question, gates and policy list were fixed in `PREREGISTRATION.md`
before any policy was measured. Nothing here is production code; fold the verdict in and
delete the directory.

Measured 2026-08-24 against the fresh baseline
`…/scratchpad/remeasure-20260824T160130/`, branch `dev` @ d910a06, vLLM
`OpenMOSS-Team/MOSS-Transcribe-Diarize` on the shared RTX 4070 Ti, greedy, request
concurrency 1. **All wall-clock numbers are contended** (three sibling agents share the GPU);
accuracy numbers are not affected — decoding is deterministic greedy.

## Answer in one line

H3 is real but **misnamed**: the decoder is not returning empty. It returns the words and
omits the closing `[end]` timestamp, so `parse_transcript` yields zero segments and the live
path throws a correct transcript away. The cheapest fix is **not a retry** — it is repairing
the timestamps of the decode already in hand (**P1v**, 0 extra requests, 0 extra decode
seconds), which recovers 8 of 10 recoverable trio words and closes **33.6 %** of the trio
coverage gap, **11.8 %** of the WER gap and **23.4 %** of the composite gap.

## Findings

**F1 — 5 empty spans of 80, not 79.** The trio committed 80 spans (bill 24, javier 32, keyu
24); 5 committed `transcript=""`. The "79" in the brief counts `span_frozen` *events*: the
final span of a session is frozen by stop-flush after the last traced freeze event, so
javier's span 31 has a `canonical_processed` event and a committed entry but no
`span_frozen`. `common.load_spans` therefore reads the terminal snapshot, not the freeze
events.

**F2 — the decoder answered; the parser discarded it.** Bypassing
`VllmRunner._validate_transcription_response` shows what each "empty" span actually returned:

| span | window | raw decode | gen. tokens | parsed segs |
|---|---|---|---|---|
| bill 02 | 5.00–7.50 | `[S01] The difference between,[S01] you said the stock market.` | 19 | 0 |
| javier 03 | 5.28–6.77 | `[0.00][S01]I'm sorry, I can't assist with that request.` | 23 | 0 |
| javier 05 | 7.94–9.52 | `[0.00][S01]Okay.` | 13 | 0 |
| javier 13 | 23.73–23.79 | `[0.00][S01]I'm sorry, I can't assist with that request.` | 23 | 0 |
| javier 31 | 59.76–60.00 | `[0.00][S01]And.` | 13 | 0 |
| jamie 22 | 51.51–54.01 | `[0.15][S01] Last year, we had you on the video board at Chase.` | 24 | 0 |

Every one is missing the **closing** timestamp; bill 02 is also missing the opening one.
`TranscriptStreamParser.close_into` only emits from state `_AFTER_END`, i.e. only after an
end timestamp, so all six parse to zero segments.

**F3 — the discard seam, and a mislabelled trace.** `vllm_runner._validate_transcription_response`
raises `EmptyTranscriptionError` on `not parse_transcript(text)`; `RunnerBoundedWavInference.
transcribe_pcm` catches it and returns `transcript=""`; `live_coordinator` then records
`empty_reason="decoder_returned_no_transcript"`. The coordinator *does* distinguish
`decoder_returned_unparseable_transcript` — but it can never see it, because the runner has
already converted the words into an empty string. **The trace says the decoder said nothing
when it in fact said the right words.**

**F4 — only 2 of the 5 trio "empty" spans lost speech.** Three are the source audio's own
digital-silence gaps (javier's intro cut, verified: exact-zero PCM runs at 5.09–6.86 s and
8.09–9.53 s), where the decoder hallucinated a refusal string. The parse discard is
*protecting* the transcript there.

| span | dur | RMS | webrtcvad(mode 1) | ref words lost |
|---|---|---|---|---|
| bill 02 | 2.50 s | −21.1 dBFS | 0.904 | **10** ("the difference between / you said the stock market in the") |
| javier 03 | 1.49 s | −∞ (all zero) | 0.000 | 0 |
| javier 05 | 1.58 s | −102.8 dBFS | 0.063 | 0 |
| javier 13 | 0.06 s | −∞ (all zero) | 0.000 | 0 |
| javier 31 | 0.24 s | −22.5 dBFS | 1.000 | 0 (session-tail fragment, "and") |

Trio totals: 5 spans, 5.87 s of audio, 13.5 evaluator-weighted reference tokens, **10 real
lost words**, all of them in one span. Neighbour spans that decode fine sit at RMS −20 dBFS
and VAD ≈ 0.94, so **energy and VAD do not distinguish the failing span from its neighbours**
— bill 02 is ordinary loud continuous speech.

**F5 — what does distinguish it: a hard-cap window cut mid-word at both edges.** Both
real-speech discards (bill 02, jamie 22) are `hard_cap` freezes, i.e. 2.5 s of unbroken
speech with no endpoint at either edge. Widening the window fixes the *format*, not the
words: `+0.10 s` on each side of bill 02 already yields a fully-formed
`[0.45][S01] The difference between, you said the stock market.[2.73]`. Shifting the window
without widening it (−0.25 s) also fixes it; shifting it forward does not. jamie 22 needs
`+0.50 s` before the closing timestamp appears. The model's omission is a **boundary
artefact**, and it is unstable in exactly the way retries exploit.

**F6 — the 3-minute tier discards at 3.9 %, but loses no speech.** The offline span simulator
(gate G2: reproduces all 80 baseline span boundaries exactly) partitions `lex_adam_frank`
into 77 spans; decoding all 77 gives 3 discards (3.9 %), all on exact-zero audio, all the
same refusal hallucination, oracle words lost = 0. Across everything decoded here — 184 spans
over 7 minutes of audio (trio 80 + jamie 27 + adam 77) — there are **10 discards, of which 2
lose real speech**.

## Per-policy recovery (all 10 discarded spans; trio subset in brackets)

`recovered` = oracle words matched, `false` = emitted words not in the oracle. Oracle = the
file arm's own decode restricted to the window. Extra cost is per policy over all 10 spans.

| policy | recovered | false | +requests | +audio s | wall s (contended) |
|---|---|---|---|---|---|
| P0 baseline (ships today) | 0 [0] | 0 [0] | 0 | 0.00 | 0.00 |
| **P1v salvage + VAD ≥ 0.5** | **17 [8]** | **3 [1]** | **0** | **0.00** | **0.00** |
| P1r salvage + VAD + refusal filter | 17 [8] | 3 [1] | 0 | 0.00 | 0.00 |
| P1 salvage, ungated | 17 [8] | 52 [18] | 0 | 0.00 | 0.00 |
| B1a retry, 1.0 s lead | 16 [7] | 5 [3] | 10 | 19.89 | 1.38 |
| B1b retry, 2.5 s lead | 17 [8] | 2 [0] | 10 | 34.89 | 1.69 |
| B2 alternate prompt | 0 [0] | 0 [0] | 10 | 9.89 | 0.67 |
| B3 merge-forward (5 s window) | 16 [8] | 0 [0] | 9 | 30.82 | 1.63 |
| B4 pad ±0.25 s | 7 [7] | 1 [1] | 10 | 14.64 | 1.02 |

Notes:
- **B2 is a no-op by construction and a regression in practice.** `VllmRunner._build_fields`
  does `prompt.strip() or DEFAULT_PROMPT`, so a literally empty prompt is byte-identical to
  the baseline request. Substituting an English instruction prompt instead made *every* span
  return nothing parseable — 0 recovered, 10 wasted requests.
- **B4 is unreliable**: +0.25 s recovers bill 02 but not jamie 22 (which needs +0.50 s).
- **B3 recovers cleanly but costs the most audio** and cannot run on a session-tail span.
- **P1 ungated is dangerous**: it commits 6 refusal hallucinations ("I'm sorry, I can't
  assist with that request") onto digitally silent audio — 52 false words over 10 spans.
  The VAD gate removes all of them; a refusal-string filter is redundant on this corpus
  (P1r ≡ P1v) but is worth keeping as defence in depth.

## Projected trio movement if deployed (real evaluator, real modified hypothesis JSONL)

Trio = macro mean over the three `lex_*` cases; gate G1 confirmed the recomputation
reproduces `results.json` to 1e-6 on both arms.

| arm / policy | composite | TSA | coverage | WER | coverage gap closed | WER gap closed |
|---|---|---|---|---|---|---|
| file (target) | 0.9106 | 0.9115 | 0.9199 | 0.1039 | — | — |
| live (baseline) | 0.8384 | 0.8400 | 0.8640 | 0.1999 | — | — |
| **P1v salvage + VAD** | **0.8553** | 0.8587 | **0.8828** | **0.1885** | **33.6 %** | **11.8 %** |
| P1 salvage ungated | 0.8497 | 0.8641 | 0.8930 | 0.2338 | 51.8 % | **−35.4 %** |
| B1a lead 1.0 s | 0.8565 | 0.8605 | 0.8845 | 0.1893 | 36.7 % | 11.0 % |
| B1b lead 2.5 s | 0.8541 | 0.8571 | 0.8812 | 0.1885 | 30.7 % | 11.8 % |
| B3 merge-forward | 0.8524 | 0.8548 | 0.8789 | 0.1885 | 26.6 % | 11.8 % |
| B4 pad ±0.25 s | 0.8534 | 0.8562 | 0.8803 | 0.1885 | 29.1 % | 11.8 % |
| B2 alternate prompt | 0.8384 | 0.8400 | 0.8640 | 0.1999 | 0.0 % | 0.0 % |

Per case under P1v — the whole trio movement is one span in one case:

| case | coverage | WER | composite |
|---|---|---|---|
| lex_bill_ackman | 0.8424 → **0.8943** | 0.2614 → **0.2273** | 0.8001 → **0.8475** |
| lex_javier_milei | 0.8464 → 0.8507 | 0.1440 → 0.1440 | 0.8416 → 0.8449 |
| lex_keyu_jin | 0.9032 → 0.9032 | 0.1942 → 0.1942 | 0.8736 → 0.8736 |

Secondary case (not in the trio average, one 2.5 s discard):
`acquired_jamie_dimon` composite 0.6580 → **0.6995** (file arm 0.7165, so 71 % of that
case's composite gap), coverage 0.8772 → 0.9291, WER 0.9661 → 0.8729.

**Ceiling check (D4).** A perfect recovery of only the speech-bearing empty windows is worth
+0.0188 coverage / 33.6 % of the gap; P1v reaches it. Covering *every* empty window, silence
included, is worth 51.8 % of the coverage gap — but that is the metric paying for time
coverage rather than for words (`_text_coverage` never reads hypothesis text), and buying it
means committing hallucinated words. **H3 is not the main story of the live-vs-file gap: two
thirds of the coverage gap and ~88 % of the WER gap are elsewhere.**

## Verdict and recommendation

**Adopt P1v: repair the discarded decode instead of retrying it.**

- Recovers as much as the best retry policy (17 / 19 oracle words overall, 8 / 10 on the
  trio) at **zero extra decode requests and zero extra decode seconds** — the words are
  already paid for; today they are deleted after generation.
- Retry policies buy nothing extra on accuracy and cost 10 extra serial decodes / 34.9 extra
  audio-seconds (B1b) on a queue whose latency tail is already the thing that matters. Reject
  B1/B2/B3/B4.
- **Guard is mandatory, not optional**: gate salvage on the span's webrtcvad speech ratio
  (≥ 0.5 over the span, using the observations the endpoint policy already computes — no new
  dependency), plus a refusal-string filter. Ungated salvage makes trio WER *worse*
  (0.1999 → 0.2338).

Where the change goes (three seams, one decision):
1. `moss_transcribe_diarize/app/vllm_runner.py::_validate_transcription_response` — the
   `not parse_transcript(text)` branch is what deletes the words. It must stop collapsing
   "unparseable" into "empty", or the live path can never see the difference.
2. `moss_transcribe_diarize/app/live_span_bounds.py::span_segments` — the natural home for
   the repair. Its docstring already establishes the governing rule for this exact class of
   decoder sloppiness ("a timestamp outside the span is **clamped into** the span, never
   refused"); a missing closing timestamp is the same problem one step further along, and
   should be **supplied from the span's own bounds, never refused**.
3. `moss_transcribe_diarize/app/live_coordinator.py::_empty_transcript_reason` — already has
   the right vocabulary (`decoder_returned_unparseable_transcript`); it is unreachable today.
   Once (1) stops swallowing the text, the trace stops lying about what the decoder said.

Regression seam that exists today: `span_segments` is a pure function over `(transcript,
sample_count)`, so the six raw decodes in F2 are directly usable as a table-driven regression
test — no live session required. `prototypes/live-file-gap-emptyspan/out/d3.json` holds them.
Verified now: `span_segments` returns `()` for all seven raw texts, and a salvaged transcript
re-renders to itself through the production `render_segments` (`render → span_segments →
render` is a fixed point), so `live_session.revise_labels` would still accept it for a later
relabelling.

Residual risk not measured here: salvaged segments carry synthesised timestamps, so the
identity/diarization path (`live_identity`, WeSpeaker embedding windows) would receive a
speaker-attributable segment where it previously received nothing. TSA rose under P1v
(0.8400 → 0.8587), so the effect is positive on this corpus, but the interaction was not
tested on a span where two speakers share the window.

## Artifacts

- `PREREGISTRATION.md` — question, policies, gates, oracle, cost accounting (written first).
- `out/d1.json` — every span of all 4 cases with RMS / VAD / freeze reason; empty spans
  annotated with lost words.
- `out/d2.json` — deterministic re-decodes (2×) + 3 verbatim controls.
- `out/d3.json` — raw decodes with validation bypassed + the 9-variant bounds sweep.
- `out/d4.json` — gate G1 + recovery ceilings.
- `out/p1-lex_adam_frank.json` — all 77 simulated 3-minute-tier spans, decoded.
- `out/p2.json` — per-span per-policy recovery, false additions, costs.
- `out/p3.json`, `out/hyp/<policy>/<case>-live-hypothesis.jsonl` — projected metrics and the
  modified hypotheses they were scored from.
- `spans/*.wav` — the exact PCM cut for every discarded span and every sweep variant.

Repro: `bash prototypes/live-file-gap-emptyspan/run_all.sh` (~4 min contended, concurrency 1).
