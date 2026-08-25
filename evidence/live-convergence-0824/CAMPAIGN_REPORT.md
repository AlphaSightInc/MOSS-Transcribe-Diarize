# Campaign report — live-mode convergence (E0–E4)

**Branch `ralph/live-convergence-0824`, 2026-08-24 → 2026-08-25. Every row below is
UNSIGNED: the mechanical gates are scored and the evidence is written; morning review
signs.**

## The answer in three sentences

**On the three fully-referenced one-minute meetings, live mode is no longer converging
toward file mode — it *is* file mode, agreeing to six decimal places on word error rate,
diarization error rate and speaker accuracy.** The five-minute meeting moves the same way:
live word error `.146375 → .050616`, live diarization error `.131533 → .057933`. What a
listener sees *during* the meeting also improved, though less far: the rolling surface
reaches trio word error `.131357` from a `.199870` baseline, and it is that surface — not
the final one — that still carries the one gate no arm in the grid can pass.

Five gates across the ladder are unsigned, needing four rulings — and rulings, not more
code. None of them is a failure of the approach; all five are named, measured, and disposed
below.

## The mental model, in one paragraph

A meeting can be transcribed two ways. **File mode** waits until the audio is complete and
hands the decoder 150-second windows — long context, one pass, no deadline. **Live mode**
must publish while people are still talking, so it hands the decoder ~2.5-second spans as
they close. The same model, the same prompt, the same greedy decoding: the only difference
is *how much of the meeting the decoder can see at once*. That difference is the whole
gap. A word split across a span boundary is a word neither span decodes well (measured:
word error `.483` at boundaries versus `.082` in span interiors, which is file-mode-like).
The campaign closes the gap by giving live mode three progressively longer looks at the
same audio — **without ever adding a second model, changing the prompt, or touching file
mode**:

1. **Salvage** what a span already decoded but the parser threw away (E1).
2. **Re-decode** finished audio in 10-second rolling windows while the meeting runs, and
   let those revise the words already on screen (E2).
3. **Re-decode the whole meeting once** when it ends, through the very same 150/120
   windowed runner file mode uses, and replace the text with that (E4).

Step 3 is why the final numbers are *identical* to file mode rather than merely close: on
a 60-second meeting, "the whole meeting through a 150-second window" is byte-for-byte the
same request file mode makes. The identity is structural, not a tuned coincidence.

## What the numbers are

Two surfaces, and the report never blurs them:

- the **rolling surface** — what the user reads while the meeting is running;
- the **terminal surface** — what is published seconds after the meeting stops, and what
  gets exported.

The tables below are the terminal surface against the pre-campaign baseline. Both are
scored by the deployed evaluator on the same references, and `distance` is the campaign's
mission metric: how far live is from the paired file arm of the same pass.

### Text

| case | live WER before | live WER after | paired file WER | distance |
|---|---|---|---|---|
| lex_bill_ackman | .261364 | .159091 | .159091 | 0.000000 |
| lex_javier_milei | .144000 | .088000 | .088000 | 0.000000 |
| lex_keyu_jin | .194245 | .064748 | .064748 | 0.000000 |
| lex_adam_frank | n/a | .126177 | .126177 | 0.000000 |
| keyu-5m | .146375 | .050616 | .050616 | 0.000000 |
| **trio mean** | .199870 | .103946 | .103946 | 0.000000 |

### Speaker

| case | live DER before | live DER after | file DER | live spk before | live spk after | file spk |
|---|---|---|---|---|---|---|
| lex_bill_ackman | .223500 | .075500 | .075500 | .776500 | .924500 | .924500 |
| lex_javier_milei | .194500 | .151833 | .151833 | .805500 | .848167 | .848167 |
| lex_keyu_jin | .111167 | .079000 | .079000 | .888833 | .921000 | .921000 |
| lex_adam_frank | n/a | .066222 | .053222 | n/a | .933778 | .946778 |
| keyu-5m | .131533 | .057933 | .057933 | .868467 | .942067 | .942067 |
| **trio mean** | .176389 | .102111 | .102111 | .823611 | .897889 | .897889 |

Three things a careful reader should notice:

- **`lex_javier_milei` gets worse on the speaker axes while getting better on text.** Its
  file arm is genuinely the weaker one for speakers (`.151833` DER against a live baseline
  of `.194500` — better, but by less than the other cases). Converging to file mode buys
  that case `.056` of word error and pays `.034500` of DER back. This was ruled before any
  terminal number existed (**D-M4-2**) and the deal is published in full rather than hidden
  inside the trio mean.
- **`lex_adam_frank` is the only case where live is not identical to file** — `.013000` of
  DER, `.013000` of speaker accuracy, and `0.000000` of word error. It is a three-minute
  meeting, so its terminal pass spans two windows and has a *seam*; the campaign's
  seam-resolution rule merges the overlap, and the residual is an artifact of the deployed
  DER metric, explained under "What we learned that outlives the campaign".
- **`lex_adam_frank` has no "before" column** because it was acquired mid-campaign as the
  three-minute comparator (`M4-three-minute/`); it never had a pre-campaign baseline.

### The ladder — where each rung got the trio

| rung | WER | coverage | DER | speaker accuracy |
|---|---|---|---|---|
| baseline live (2026-08-24) | .199870 | .864015 | .176389 | .823611 |
| M1 bounded salvage | .192294 | — | .162667 | — |
| M2 rolling convergence | .131357 | — | .111278 | .888722 |
| M4 terminal convergence | .103946 | .919865 | .102111 | .897889 |
| paired file arm | .103946 | .919865 | .102111 | .897889 |

Read this table as the campaign's real shape: **salvage was worth `.0076` of word error,
rolling re-decode was worth `.0609`, and the terminal pass was worth the remaining `.0274`
— and it is the one that closed the distance to the file arm to zero.** The dashes are axes that rung did not report as a
trio mean; every cell present is read from the bundle that measured it, not recomputed here.

## The ledger

| milestone | evidence | gates | failing |
|---|---|---|---|
| M0 | `evidence/live-convergence-0824/M0d-paired-reacquisition/` | 4 of 5 | G2_live_transcript_reproducible |
| M1 | `evidence/live-convergence-0824/M1-e1-exit/` | 5 of 6 | G_M1_1_trio_live_wer_bound |
| M2 | `evidence/live-convergence-0824/M2-e2-exit/` | 7 of 8 | G_M2_4_correction_p95 |
| M3 | `evidence/live-convergence-0824/M3-disposition/` | 14 of 14 | none |
| M4 | `evidence/live-convergence-0824/M4-e4-exit-2/` | 12 of 14 | G-M4-3, G-M4-4 |

Thirty-two evidence bundles sit under `evidence/live-convergence-0824/`; the five above are
the scored milestone exits, and the rest are the steps that built them.

## M0 — measurement integrity

**Before you can close a gap you have to be sure the gap is real.** E0 fixed the
instrument, and it found three defects that were quietly corrupting every reading:

- **The replay client silently dropped three fields** when it reconstructed a session from
  JSON — including `revised_transcript` and `label_revision_version`, i.e. the very
  revisions the campaign was about to start making. Fixed, with a round-trip test that
  fails on any *new* defaulted field, so the defect class cannot recur silently
  (`M0a-replay-roundtrip/`).
- **Three different decode endings were reported as one.** "No tokens", "empty text" and
  "text the parser could not read" all surfaced as `decoder_returned_no_transcript`. Typed
  now: seven saved real decodes that the baseline lost report
  `decoder_returned_unparseable_transcript` with their true token counts (13–24)
  (`M0b-decode-disposition/`). This is what made M1 possible — you cannot salvage what you
  cannot name.
- **The deployed scorer pays for timestamps, not words.** A hypothesis that is one
  60-second segment whose only word is `xx` earns text coverage `1.0000` and TBSA `.6817`
  from it. Evaluator v2 scores the same thing `.0000` on content recall
  (`M0c-evaluator-v2/`). v2 is a measurement instrument only — it is deliberately NOT in
  production — and every milestone reports its axes beside the deployed ones.

**The one unsigned gate.** G2 asked that two fresh live runs of the same audio produce
hash-identical transcripts. Four of four sixty-second cases pass; the five-minute case does
not. The cause is measured and external: the deployed decoder is not bit-reproducible at
that length. The PRD forbids changing the model, prompt or decoding to make a gate pass, so
this needs an owner ruling, not a fix.

## M1 — bounded salvage

Some spans hit their 2.5-second hard cap mid-word; the decoder answers, the parser rejects
the answer for a missing closing timestamp, and correct words are thrown away. `M1` ships
`classify_live_transcript` (`app/live_span_bounds.py`): a table-driven classifier that
recovers such text **only** when the span was hard-capped, the grammar is safe, and the
text is not refusal boilerplate. Zero extra decode requests — it reads an answer that was
already paid for.

Measured: trio live word error `.199870 → .192294`, no per-case regression, file mode
byte-identical, and the identity path receives only intervals the salvager actually
emitted.

**The one unsigned gate.** G-M1-1 wanted `<= .190` and got `.192294` — a miss of `.0023`.
Attribution (in the bundle) traces it to one decode flip on `lex_bill_ackman` that entered
the instrument *before* M1 was written; re-running until it disappears would be tuning the
instrument to the answer, which the preregistration forbids.

## M2 — rolling convergence

The rung that did most of the work. While the meeting runs, finished audio is re-decoded in
**10-second windows on a 10-second stride** and the resulting words revise what is already
on screen. The geometry was chosen by a preregistered grid over four window/stride
combinations × three stitching policies (`M2-rolling-grid/`). `10/10` won under the
preregistered rule — *the cheapest arm that passes every gate*: it adds exactly `1.000×`
decode audio and needs no stitcher at all, because non-overlapping windows have nothing to
stitch. The best-quality arm, `15/10:lexical`, reached trio word error `.1075` for `1.5×`
the decode audio; it is recorded as the measured upgrade path (**D-M2-1**), not taken.

What shipped: `RollingTranscriptConverger` and the word-revision authority in
`app/live_transcript_convergence.py`, refinement scheduling in `app/live_arbiter.py`, the
snapshot fields and events of the plan's §7.3/§7.4, the portal rendering the revised
surface, and — last, in one reviewed change — the export switch. The decision record is
**ADR-0005**, whose D1–D7 are the plan's decisions *verbatim*, mechanically checked by
`verify_adr_text_finalization.py`.

Measured: trio rolling word error `.131357` (bound `.150`), content recall `.943916`
(bound `.940`), five-minute rolling word error `.082079` (bound `.0985`), exact sample
accounting, file mode byte-identical, combined real-time factor well under 1 with bounded
queues.

**The one unsigned gate.** G-M2-4 wanted a provisional word to be corrected within `6.0`
seconds at the 95th percentile and measured `8.756675`. This is arithmetic, not slowness:
a word spoken just after a window closes cannot be revised until the next window closes and
decodes, so with central ownership the oldest owned word is `(L+S)/2` old and a 6-second
p95 needs `L + S <= 12`. The four grid geometries have floors of `6.46` s (10/5), `8.51` s
(10/10), `11.64` s (15/10) and `12.81` s (15/7.5) — **not one of them can pass, and cost
and latency rank them in opposite orders.** Adding a fifth geometry after seeing the number
is what the preregistration forbids. **Ruling needed — one of two: (O1) accept `~8.8` s as
the price of the cheapest arm that passes every other gate, or (O2) keep the 6-second
target and re-run the grid in a follow-up campaign over geometries with `L + S <= 12`
(e.g. 8/4), pricing the extra decode audio a shorter stride costs.**

## M3 — witness-owned speaker authority

E3 asked whether taking speaker embeddings strictly from witness-owned speaker intervals
improves the speaker surface. It was built as an offline arm (S1), measured against
fourteen preregistered gates, and **it ties on every gated axis** — same trio DER
(`.111278`), same speaker accuracy (`.888722`), same five-minute DER (`.0886`).

**Nothing shipped, and that is the finding.** The decision (**D-M3-2 = O3**) rests on three
measured things: the arm changes no gated number; it makes two wrong relabels the current
path does not make; and the plan's own §12.3 terminal pass falsifies the premise that E3's
ownership model is what E4 builds on — the terminal pass re-resolves identities from the
complete tape and never consults it. All fourteen gates pass, so the row is clean; the
milestone's honest summary is "measured, neutral, declined".

The decomposition it produced is more valuable than the arm: **63 % of the remaining
speaker confusion is segments that straddle a reference turn** — a segment-*extent*
question owned by the text geometry, not by identity — and 27 % is sub-0.5-second
microfragments below the evidence floor.

## M4 — terminal convergence

When the meeting stops, the session's complete mixed audio is decoded once more through the
**same `WindowedRunner` object file mode uses**, with the same resolved inference options,
and the result replaces the text and re-resolves the speaker identities. This is why the
final table's distance column is zeros: it is one object with one configuration, not two
configurations that must agree.

What shipped, in order: an in-memory `CompleteMixedTape` bounded by a declared byte capacity
(`app/live_tape.py`, **ADR-0003 D8**); `TerminalTranscriptFinalizer` and
`terminal_speaker_mapping` (`app/live_transcript_convergence.py`, **ADR-0005 D8**); an
asynchronous `finalization_status` lifecycle so the stop request returns immediately
(`app/live_service_runtime.py`); the deployment wiring; a replay client that outlives the
stop response so every driver measures the terminal surface; and finally a **seam
resolution** for meetings long enough to span two terminal windows (**ADR-0005 D9**).

The costs, all measured on the deployed service:

| what it costs | measured |
|---|---|
| combined real-time factor during capture (base + rolling) | max `.172669`, bound `1.0` |
| terminal decode, after capture stops | real-time factor mean `.032575`, max `.037027` |
| stop → published final surface | cold `2.574621` s; warm p50 `2.586969` s, max `10.802953` s (five-minute case) |
| retained audio | peak `9 600 000` bytes = `9.155` MiB, released after the terminal evidence is written; zero tapes survive a session |
| queues | rolling depth ≤ 1, zero admission refusals, zero stale completions, zero failed windows |
| extra decode requests | one terminal pass per session (1–3 windows), one in-flight request throughout |

**The two unsigned gates.** G-M4-3 and G-M4-4 are gates *the campaign added to itself*:
terminal must be no worse than the rolling surface it replaces. On four of five cases it is
much better. On `lex_adam_frank` the rolling surface is `.122411` and the faithful terminal
surface is `.126177` — the paired file arm's own number. **The two gates fail because
converging to file mode is, on that one case, a small step backwards from rolling.** The
trade was ruled before the numbers existed (see the ID note below) and the batch reproduced
all five predicted values to six decimal places. The alternative was worse: before the seam
resolution shipped, that meeting could not publish a terminal surface *at all*.

**An identifier collision to fix at review.** The seam-trade ruling is labelled `D-M4-3` in
`M4-seam-overlap/NOTES.md`, `M4-seam-ship/NOTES.md` and `M4-e4-exit-2/NOTES.md`, but
`D-M4-3` was already taken on iteration 22 by the preregistered decision "asynchronous
finalization with snapshot polling" (`PREREGISTRATION-M4.md` §4). Two different decisions,
one identifier. This report calls the seam trade **D-M4-4**; the bundles' digests were left
untouched rather than rewritten, so a reader who sees `D-M4-3` beside `lex_adam_frank` is
reading D-M4-4.

## M5 — evidence and record

This report, the plan's §18 row annotations, and the dated verdict entry in
`docs/design-streaming-diarization.md` §7. Every number above is re-derived from the
checked-in evidence by `verify_campaign_report.py` (see Reproduction); no table here is
hand-transcribed.

## Gates the campaign added beyond the PRD

The PRD names the gates a milestone must pass. The campaign added more — every one of them
*stricter*, never a substitute for a PRD bound, and every one fixed in a preregistration
before its numbers existed. They are marked `[C]` in the preregistration tables and listed
here so a reviewer can tell the two sets apart:

- **M3**: G-M3-0 (every embedding input is a subset of one witness-owned interval —
  structural, verified from the arm's own per-embedding log); G-M3-5 (evaluator-v2
  matched-word speaker accuracy *gated* rather than merely reported, since a reported number
  nobody may fail is not evidence); G-M3-11 (correction latency must not get worse).
- **M4**: G-M4-0 (the retained tape is a faithful record of what the session accepted);
  G-M4-3 and G-M4-4 (terminal no worse than the rolling surface it replaces — the two
  unsigned ones); G-M4-9 (terminal replaces the surface exactly once, second proposal
  refused); G-M4-10 (complete-tape retention and release); G-M4-11 (terminal work never
  enters the capture clock); G-M4-13 (no terminal event carries transcript text).
- **M1 and M2**: nothing added. Their preregistrations carry no `[C]` rows — every exit gate
  is a PRD bound.
- **M0**: two extra gates, `G4_service_runs_campaign_code` and `G5_single_provenance`, are
  preconditions rather than quality bounds (a gate scored against the wrong build is void).
  M0 predates the `[C]`/`[PRD]` marking convention, so this pair is named here by hand and
  is the one classification the verifier does not check mechanically.

## What we learned that outlives the campaign

1. **Seam severance was the gap, and length was not.** The live-vs-file gap at 300 seconds
   was the same size as at 60 seconds. What mattered was how much context each decode saw,
   which is why every rung of the ladder is "look at more audio at once" and none is "tune a
   threshold".
2. **The deployed diarization metric pays a bonus for publishing the same audio twice.**
   `evaluation.calculate_diarization` sums the overlap of every (reference, hypothesis) pair,
   so reference seconds claimed by two hypothesis segments are credited twice and real
   `miss` disappears. On `lex_adam_frank` the file arm's `.053222` becomes `.066222` once
   the duplication is resolved — all of it `miss`, exactly `2.34 / 180` seconds. Evaluator
   v2 unions hypothesis intervals first and does not move. **This is the plan's §3.4 extent
   artifact in a new shape (duplication, not padding), and it means `lex_adam_frank`'s
   `.013000` residual is a metric correction, not a quality regression.**
3. **Where the remaining speaker error actually is**: 63 % straddled reference turns
   (owned by text geometry), 27 % sub-0.5-second microfragments. The next campaign should
   start from that decomposition rather than from the confusion total.
4. **Ordering can decide who spoke.** `terminal_speaker_mapping` weighs local speakers
   against canonical ones by shared samples summed over segments, one-to-one. A stretch of
   audio decoded twice therefore votes twice — and a constructed case shows an inflated
   weight swapping *both* speakers' names. Resolving overlaps before naming is not
   bookkeeping.
5. **A prototype arm and a production rule are two rules until someone runs them on the
   same input.** `measure_seam_overlap.py --verify-production` makes that a command
   (identical on 24 inputs) rather than a claim.

## What is not closed

- **The four unsigned rulings** (G2, G-M1-1, G-M2-4, G-M4-3/G-M4-4), each with its
  disposition recorded in its bundle.
- **The attended browser end-to-end test**, deferred to morning review by design. Its
  in-loop substitute is a headless portal render/serialization test driven by real server
  payloads.
- **Portal render time under load**, the one §10.6 soak quantity not read off the
  five-minute passes.
- **Anything above five minutes**, two-session stress, and the 30/60-minute matrix — all
  explicitly out of scope for this campaign.
- **`descriptor.source_revision` is a manifest declaration, not a build stamp.** The
  deployed service reports iteration 27's revision while running iteration 31's code. No
  driver reads the field; the batch's provenance is its restart and `ps` records. Worth
  fixing, worth not fixing *during* a measurement campaign.

## Reproduction

```bash
# the report's own numbers, re-derived from the checked-in evidence
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_campaign_report.py
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_campaign_report.py --selftest

# the milestone exits, each against its own checked-in batch
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_m1_exit.py --fresh-root <batch>
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_m2_exit.py --fresh-root <batch>
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_m3_disposition.py
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_m4_exit.py --fresh-root <batch>

# the shipped rules against the numbers that selected them
.venv/bin/python prototypes/streaming-diarization/live-convergence/measure_seam_overlap.py --verify-production
.venv/bin/python prototypes/streaming-diarization/live-convergence/verify_adr_text_finalization.py

# the suite
.venv/bin/python -m pytest tests/ -q      # 1157 passed, 2 skipped, 411 subtests
```

Every gate script also takes `--selftest`, which mutates a converged fixture and requires
each gate to react to the defect it names.
