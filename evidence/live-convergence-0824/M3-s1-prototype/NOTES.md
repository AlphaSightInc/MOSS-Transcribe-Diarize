# M3 (plan E3) step 2 — the S1 arm, measured before any production code exists

Campaign iteration 20, 2026-08-25. Preregistered in
`prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M3.md` (iteration 19):
arms, 14 gates, seven predictions, selection and disposition rules, all fixed before this
measurement. Nothing below moved a bound, added an arm, or touched a threshold.

**Verdict in one line: S1 is measured-neutral. On all four cases, both passes, every gated
quality axis is identical to S0 at six decimal places — Δ DER `0.000000`.**

## What was run

```bash
# the arm (trio: zero MOSS requests, decodes reused from the §10.2 grid cache)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin,keyu-5m --runs A,B \
  --decode-cache evidence/live-convergence-0824/M3-s1-prototype/witness-decodes.json \
  --output /tmp/m3-s1-all.json

# the derived quantities react
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py --selftest
bash prototypes/streaming-diarization/live-convergence/mutate_speaker_authority.sh /tmp/m3-mut-out
```

`witness-decodes.json` carries the 63 ten-second window decodes the arm reads (the trio's 18
came from the §10.2 grid cache at zero cost; the five-minute case's 30 were decoded once
through the production runner, one in-flight request). With it checked in, the whole
measurement re-runs with **no GPU and no service** — only the pinned WeSpeaker ONNX, which is
already in the repo, and ~2.5 minutes of CPU.

## Results (mean of two passes; the two passes agree exactly on every case)

| case | arm | DER | miss | confusion | speaker_accuracy | v2 matched-word | WER | S00 s | collapsed |
|---|---|---|---|---|---|---|---|---|---|
| lex_bill_ackman | S0 | `.127333` | `.090167` | `.037167` | `.872667` | `.920455` | `.204545` | 0.73 | 1 |
| lex_bill_ackman | **S1** | `.127333` | `.090167` | `.037167` | `.872667` | `.920455` | `.204545` | **0.33** | 1 |
| lex_javier_milei | S0 | `.117333` | `.117333` | `.000000` | `.882667` | `.920000` | `.096000` | 0.00 | 0 |
| lex_javier_milei | **S1** | `.117333` | `.117333` | `.000000` | `.882667` | `.920000` | `.096000` | 0.00 | 0 |
| lex_keyu_jin | S0 | `.089167` | `.077000` | `.012167` | `.910833` | `.985612` | `.093525` | 0.00 | 0 |
| lex_keyu_jin | **S1** | `.089167` | `.077000` | `.012167` | `.910833` | `.985612` | `.093525` | 0.00 | 0 |
| keyu-5m | S0 | `.088600` | `.082700` | `.005900` | `.911400` | `.954856` | `.082079` | 0.56 | 0 |
| keyu-5m | **S1** | `.088600` | `.082700` | `.005900` | `.911400` | `.954856` | `.082079` | 0.56 | 0 |

Trio mean, both arms: DER `.111278`, speaker_accuracy `.888722`, matched-word `.942022`.

The only difference S1 produces anywhere on the bench is **two segment labels on
`lex_bill_ackman`**, and 0.40 s of `S00` becoming named.

## Why it ties — the finding that matters

The surface's remaining confusion is **not a voice-identity error**. Decomposed post-hoc
(the arm itself never reads a reference), each confused second falls into one of three classes:

| class | what it is | can a speaker authority fix it? | trio + 5m seconds |
|---|---|---|---|
| `segment_straddles_turn` | the published segment contains audio from two reference speakers, so whichever single label it carries is partly wrong | **no** — it is a segment-extent defect | **2.96 s** (63 %) |
| `unattributed` | published as `S00`; nobody claimed it | yes, by naming it correctly | 1.29 s (27 %) |
| `misattributed` | one speaker's audio published as another | yes, outright | **0.48 s** (10 %) |

Per case: bill `1.02 / 0.73 / 0.48`, milei `0 / 0 / 0`, keyu `0.73 / 0 / 0`, 5m `1.21 / 0.56 / 0`.

So the `.016445` of trio DER that iteration 19's confusion-free floor called E3's ceiling is
**not** all reachable by a label change. Only the last two classes are, and on this bench they
are 1.21 s of bill's 2.23 s and 0.56 s of the five-minute case's 1.77 s — a label-only ceiling
of `.00672` trio mean DER, of which S1 realises **zero**.

The two labels S1 does change are both sub-quarter-second microfragments at
`39.84–40.00` ("Right?") and `49.75–49.99` ("You know."), which the projection had published
as `S00`. The reference says both are Bill; S1 names them Lex. DER does not move (an `S00`
second already counted as confusion), `S00` seconds fall 0.73 → 0.33, and bill's
`misattributed` seconds rise 0.48 → 0.88. **The one visible effect of S1 on this bench is
trading an honest abstention for a confident error.** These are exactly plan §11.4's
microfragments, which §11.4 already scopes as a separate candidate.

## The mechanism is correct; there is simply nothing for it to win

* **118 witness-owned evidence units embedded, zero D5 violations** (G-M3-0). Every embedding
  input is a subset of one witness-owned local speaker interval — verified from the arm's own
  per-embedding log, not asserted.
* **Zero whole-window abstentions, zero ambiguity refusals**, and every local speaker maps
  one-to-one or is left to the projection (G-M3-9 holds by construction: the matcher is the
  production `assign_speakers`). Four locals across the five-minute case's 30 windows found no
  album match and were correctly left alone.
* **The mapping is label-invariant and it re-anchors correctly across windows.** MOSS's local
  `Sxx` names are arbitrary per window: on `lex_bill_ackman` window 3 the arm maps
  `S01→speaker-0002, S02→speaker-0001`, the reverse of its neighbours, and on `lex_keyu_jin`
  window 3 likewise. Swapping every local label in the input changes nothing (probe I1).
* Where both had an answer, **they agreed**. Of the trio's 50 surface segments: 2 relabelled,
  3 with no witness answer (the projection kept them), and 45 where the witness's answer was
  the projection's answer.

## Cost

| resource | trio | keyu-5m |
|---|---|---|
| witness embeddings (what S1 adds) | 23 units, 23.51 s | 36 units, 41.12 s |
| **marginal WeSpeaker RTF** | **`.130594`** | **`.137078`** |
| album embeddings (the base path's existing work) | 70 units, 23.38 s | 119 units, 41.84 s |
| seconds per witness embed | 1.022 | 1.142 |
| MOSS requests | **0** | 30 (cached; one in-flight) |

Combined single-session RTF would land near `.27–.29` against the M2 exit's `.133–.157` —
inside G-M3-10's `< 1`, so **P6 holds**.

**P7 is at risk.** A witness embed costs ~1.0–1.1 s and a two-speaker window needs two, so a
resolver on the witness path adds ~1.0–2.3 s before its revision can publish. G-M3-11 bounds
correction-after-provisional p95 at the M2 exit's own `8.756675 s`, which is already unsigned;
a serial resolver would very likely breach it. Running the resolver *after* the text revision
is applied — publishing the speaker answer as a separate label revision through the existing
`revise_labels` seam — would keep the text clock untouched. That is an implementation choice
for the production change, not a new arm.

## Predictions, scored

| id | prediction | outcome |
|---|---|---|
| P1 | trio mean DER in `[.094833, .111278]` | **held, at the upper endpoint exactly** (`.111278`) |
| P2 | any gain concentrated in `lex_bill_ackman` | vacuous — no gain anywhere |
| P3 | `lex_javier_milei` cannot improve | **held** (`.117333`, unchanged) |
| P4 | five-minute case moves `< .003` DER | **held** (`.000000`) |
| P5 | bill's `S00` seconds decrease | **held** (0.73 → 0.33) — but for a reason P5 did not anticipate: not less fragmentation, a wrong name on the fragments |
| P6 | combined RTF `< .30`, queue depth `<= 1` | **held** on RTF (`.27–.29`); queue depth is a deployed-pass measurement |
| P7 | G-M3-11 unaffected | **at risk** — see Cost |

## Probes (`mutations.txt`)

| probe | expected | observed |
|---|---|---|
| I1 local labels swapped | **no change** (label invariance) | no change |
| M1 all witness segments collapsed onto one local | S1 must move | S1 DER `.127333 → .135833`, 3 relabels, 1 abstention |
| M2 every committed span published as `S00` | album enrols nobody | 6 abstentions, 0 relabels, S1 falls back to S0 exactly |
| M3 one exported hypothesis row corrupted | the S0 control fails | `export_reproduces_pass=False`, exit 1 |
| M4 1 s of context prepended to every owned interval | D5 must object | 14 violations, exit 1 — and the contaminated vectors changed the mapping, which is D5's premise, measured |

Control re-run before and after: identical.

## Bench controls

* The production export (`hypothesis_from_live_snapshot`) reproduces each pass's own
  `live-hypothesis.jsonl` exactly, on all 8 case-runs.
* The locally-scored S0 arm reproduces the deployed `results.json` DER, speaker accuracy and
  WER to `1e-6`, on all 8 case-runs. S0 is therefore the served surface, not a reconstruction
  of it.
* Fidelity of the replayed witness: the cached decode reproduces the surface the service
  published on **32 of the trio's 36 window-runs**. The two distinct exceptions recur in both
  passes: one word on `lex_bill_ackman` window 1 (`"you're"` vs `"you know,"`) and a
  same-speaker segmentation split on `lex_keyu_jin` window 3. Neither touches a speaker
  boundary. The five-minute case matched **60 of 60**.

## Files

| file | what it is |
|---|---|
| `s1-all.json` | all four cases, both passes, fully cached (the headline table) |
| `s1-trio-timed.json` | the trio with a cold embedding cache — the source of the trio's encoder timings |
| `s1-5m-timed.json` | the five-minute case with a cold embedding cache — its timings |
| `witness-decodes.json` | the 63 window decodes the arm reads; makes the bundle GPU-free |
| `console.txt`, `selftest.txt`, `mutations.txt`, `sha256.txt` | the run, the self-checks, the probes, the hashes |

## Disposition

No production code was written this iteration, and none of the 14 preregistered gates is
scored here: they are scored on deployed passes (preregistration §4). What this bench decides
is whether spending a production change and a deployed pass on S1 is warranted. It says the
arm cannot move any gated quality axis on this corpus, that its only observable effect is on
0.40 s of microfragments where it is wrong, and that it costs `.13` RTF and ~1–2 s of witness
latency. That is the evidence the ship/do-not-ship decision (D-M3-2) is taken against, and it
is recorded in `scripts/ralph-live-convergence/progress.txt` and `context.md`.
