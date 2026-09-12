# A2 — identity birth-floor evidence, 2026-09-11

**Finding: raising the birth floor removes both false identities and genuine brief speakers. Fewer output identities is not sufficient evidence of better diarization.** No policy recommendation is being applied; the operator retains the decision. Production code and policy values are unchanged.

## F1 — what the experiment establishes

- **F1:** On identical short observations containing Lex plus a genuine 1 s Bill Ackman contribution, floor 1 s produces one false split but misses no person. Floors 1.5/2 s remove that split by leaving **both people entirely unnamed** (40 s).
- **F2:** With an initial 2 s Lex seed, all floors identify Lex without splitting. A brief 1 s Bill contribution is detected only at floor 1 s. A 1.5 s Bill contribution is detected at floors 1/1.5 s, but missed at 2 s. A global higher floor therefore costs a reachable real person even when the main speaker is already stable.
- **F3:** If Bill later returns for 2 s, floors 1.5/2 recover his earlier 1 s contribution at the 60 s sweep: **50.6 audio-seconds of correction delay**. Without that return, the person remains missed through the final sweep. This is not extra transcription delay; it is speaker-label delay.
- **F4:** The nine-clip admission/cold-start regression remains separate. Current default-floor mean/minimum is **93.97% / 84.70%**. At floor 2 s, `acquired_jamie_dimon` drops from **87.41% to 49.44%**, reproducing ADR-0002’s 49.4% cold-start failure.
- **F5:** Floor 1.5 s improves the nine-clip mean to **95.30%**, yet still loses the real 1 s speaker in the controlled cases. The average and rare-person recall answer different questions; neither replaces the other.

## Method and boundaries

**Structural question:** can a longer birth requirement distinguish unreliable fragments from a genuine brief speaker? The same amount of short evidence can represent either, so duration alone cannot guarantee that distinction.

**Minimum primitives:** source speech with known person; a bounded observation and its embedding; birth/match decisions; later label revisions. Source identity is independent of output-ID count.

**Invariants:** floors 1.0/1.5/2.0 receive identical PCM-derived embeddings and observation order within each case. Album admission stays 2.0 s; matching floor 0.5 s; score 0.35; margin 0.10; span cap 2.5 s; sweep cadence 60 audio-seconds plus final sweep. Only the bench constructor’s birth argument varies. No channel-specific rules, QUALITY_BOUNDS, identity policy, host service, vLLM or database changes.

**Falsifier:** fewer splits accompanied by a genuine person receiving no distinct identity disproves the claim that suppressing births alone improves quality. F1/F2 reach that falsifier.

**Tool decision:** the existing `tests/live_identity_accuracy.py` production replay avoids a substitute matcher. A trace-only optional argument records state after commit/sweep. Local `WeSpeakerResNet152LmAdapter` freshly embedded every unit once; all floor arms replay those exact vectors. Every arm is also replayed without the observer and its entire `ReplayResult` must be identical. No ASR/remote inference is called. Marker transcripts supply known within-span speakers; zero PCM inside the cached replay is not an acoustic input to the model. The actual embedding input is the source WAV.

**Source custody:** nine clips are the unchanged adopted manifest (`tests/fixtures/live_identity_real_corpus.json`), six one-minute and three three-minute clips. Existing audio/reference pin checks passed. Local asset SHA-256 is the existing pinned `5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8`. Lex uses the existing `mono_javier_intro_50s/audio.wav`; the peer’s committed VAD inventory selects the same 39 fully voiced 1 s units. Bill uses the existing golden `lex_bill_ackman` source: brief interval begins at 1 s; returning interval is 10–12 s. Both lie inside the reference’s Bill 0–29 s turn. No generated voice or downloaded corpus.

Controlled PCM concatenates these real intervals with 0.6 s silence between observations. Seeded variants replace Lex [1,2) and [2,3) with contiguous [1,3); these are different scenarios, never a claimed floor-only improvement. Bill is inserted after five observations; his optional return is observation index 20. Full source intervals, meeting times, vectors and label histories are retained. The synthetic conversation timing isolates identity; it is not a natural-conversation or AirPods capture.

**Unknowns/limits:** this bench does not diagnose microphone/Bluetooth causality, decoder diarization errors, overlap, real UI publication or wall-clock latency. The established replay derives observations from reference turns (overlaps clipped in reference order), and tests the L1 retained-embedding sweep, not terminal ASR/VAD resegmentation or the full live coordinator. It preserves the historical helper’s reconciliation/final-sweep semantics. Do not generalize its correction times to a measured end-to-end session.

## Metric definitions

- **False splits:** assign each output identity to the true person with greatest assigned speech duration; count extra identities owned by each person. Ties use the lowest truth ID. Report initial committed labels (“live”) and labels after final sweep separately.
- **Missed people:** true people owning no output identity. This counts people, not turns. Wrong-person assigned duration is separately reported so merging two real people cannot silently count as successful detection.
- **Unnamed speech:** duration of all reference speech lacking a label, including sub-0.5 s units that the historical eligible-only accuracy denominator omits. “Live” means each unit’s original committed label, not the transcript viewed at the end.
- **Correction delay:** audio time from an observation’s end until its last transition into a correct settled identity (owned by that person in final output), provided it stays correct thereafter. IDs absorbed before final output do not count as settled. Initially stable correct assignments are excluded; unresolved units are censored, never assigned zero delay. All label-revision delays are retained separately, including duplicate-ID repairs. “—” means no completed correction, not instant correction.
- **Historical accuracy:** unchanged helper’s duration-weighted optimal one-to-one identity/person mapping over embedding-eligible speech. It penalizes splits differently from the explicit metrics above; it does not count all unnamed speech.

## Controlled cases: every floor, separate outcomes

Pairs below are **live → final**. “Wrong” is misassigned duration; all controlled cases have zero. Correction is completed count / p50 / max seconds; unresolved is a unit count.

| Case | Floor s | False splits | Missed people | Unnamed s | Wrong s | Correction count / p50 / max | Unresolved units |
|---|---:|---:|---:|---:|---:|---:|---:|
| lex_short_only | 1.0 | 1 → 1 | 0 → 0 | 6.00 → 6.00 | 0.00 → 0.00 | 0 / — / — | 6 |
| lex_short_only | 1.5 | 0 → 0 | 1 → 1 | 39.00 → 39.00 | 0.00 → 0.00 | 0 / — / — | 39 |
| lex_short_only | 2.0 | 0 → 0 | 1 → 1 | 39.00 → 39.00 | 0.00 → 0.00 | 0 / — / — | 39 |
| lex_seeded | 1.0 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| lex_seeded | 1.5 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| lex_seeded | 2.0 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| unseeded_brief_1s | 1.0 | 1 → 1 | 0 → 0 | 6.00 → 6.00 | 0.00 → 0.00 | 0 / — / — | 6 |
| unseeded_brief_1s | 1.5 | 0 → 0 | 2 → 2 | 40.00 → 40.00 | 0.00 → 0.00 | 0 / — / — | 40 |
| unseeded_brief_1s | 2.0 | 0 → 0 | 2 → 2 | 40.00 → 40.00 | 0.00 → 0.00 | 0 / — / — | 40 |
| unseeded_brief_1p5s | 1.0 | 1 → 1 | 0 → 0 | 6.00 → 6.00 | 0.00 → 0.00 | 0 / — / — | 6 |
| unseeded_brief_1p5s | 1.5 | 0 → 0 | 1 → 1 | 39.00 → 39.00 | 0.00 → 0.00 | 0 / — / — | 39 |
| unseeded_brief_1p5s | 2.0 | 0 → 0 | 2 → 2 | 40.50 → 40.50 | 0.00 → 0.00 | 0 / — / — | 40 |
| brief_1s | 1.0 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| brief_1s | 1.5 | 0 → 0 | 1 → 1 | 1.00 → 1.00 | 0.00 → 0.00 | 0 / — / — | 1 |
| brief_1s | 2.0 | 0 → 0 | 1 → 1 | 1.00 → 1.00 | 0.00 → 0.00 | 0 / — / — | 1 |
| brief_1p5s | 1.0 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| brief_1p5s | 1.5 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| brief_1p5s | 2.0 | 0 → 0 | 1 → 1 | 1.50 → 1.50 | 0.00 → 0.00 | 0 / — / — | 1 |
| brief_1s_return | 1.0 | 0 → 0 | 0 → 0 | 0.00 → 0.00 | 0.00 → 0.00 | 0 / — / — | 0 |
| brief_1s_return | 1.5 | 0 → 0 | 0 → 0 | 1.00 → 0.00 | 0.00 → 0.00 | 1 / 50.60 / 50.60 | 0 |
| brief_1s_return | 2.0 | 0 → 0 | 0 → 0 | 1.00 → 0.00 | 0.00 → 0.00 | 1 / 50.60 / 50.60 | 0 |

`lex_short_only`: 39 s, one person. `lex_seeded`: 39 s, one person, initial 2 s seed. `unseeded_brief_*`: two people, Lex only 1 s units. `brief_*`: two people, seeded Lex. `brief_1s_return`: Bill speaks 1 s then returns for 2 s; total speech 42 s.

## Nine-clip regression retained

Each cell is **live / final eligible-speech accuracy (%)**. All three arms use the same freshly embedded observations.

| Clip | Floor 1 s | Floor 1.5 s | Floor 2 s |
|---|---:|---:|---:|
| acquired_jamie_dimon | 81.89 / 87.41 | 72.25 / 87.41 | 43.92 / 49.44 |
| acquired_nfl | 75.05 / 84.70 | 94.12 / 96.68 | 94.12 / 96.68 |
| acquired_rolex | 100.00 / 100.00 | 100.00 / 100.00 | 93.44 / 100.00 |
| lex_bill_ackman | 95.00 / 95.00 | 93.33 / 95.00 | 93.33 / 95.00 |
| lex_javier_milei | 87.50 / 87.50 | 87.50 / 87.50 | 87.50 / 87.50 |
| lex_keyu_jin | 95.83 / 95.83 | 95.83 / 95.83 | 95.83 / 95.83 |
| acquired_jamie_dimon_3min | 99.51 / 99.51 | 99.51 / 99.51 | 99.51 / 99.51 |
| lex_adam_frank | 96.11 / 96.11 | 96.11 / 96.11 | 95.28 / 96.11 |
| lex_shapiro_destiny | 98.03 / 99.67 | 98.03 / 99.67 | 98.03 / 99.67 |

| Floor s | Final mean / minimum % | False splits live → final | Missed people live → final | Unnamed s live → final | Wrong s live → final | Completed corrections / p50 / max s | Unresolved units |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | 93.97 / 84.70 | 6 → 5 | 0 → 0 | 18.24 → 12.56 | 8.00 → 5.50 | 5 / 32.98 / 55.00 | 25 |
| 1.5 | 95.30 / 87.41 | 2 → 2 | 0 → 0 | 18.86 → 14.66 | 8.00 → 5.50 | 5 / 37.98 / 55.00 | 27 |
| 2.0 | 91.08 / 49.44 | 2 → 2 | 1 → 1 | 27.17 → 19.33 | 8.00 → 5.50 | 7 / 37.98 / 55.00 | 31 |

Nine clips contain 807.800 s of reference speech and 360 observation units. People are counted per clip, not deduplicated across recordings. Per-clip separate metrics, individual correction delays, ownership counts and full state are in `results.json`.

ADR-0002 records **93.50% mean / 82.14% minimum**, all 3-minute clips ≥96.11%, zero residual corrections. This run gives **93.97% / 84.70%**, all 3-minute clips ≥96.11%, zero residual corrections in every arm. Thus the existing regression bar is preserved; the aggregate is **not an exact reproduction** of the old measurement. The cause of that small historical numeric difference was not isolated; neither the old recording nor the old claim is rewritten. The specific 2 s cold-start failure does reproduce: **49.4437%** on `acquired_jamie_dimon`.

## Decision boundary

**D1 — future operator choice:** floor 1 s preserves the tested 1 s person but permits a false split on fragmented Lex. Floor 1.5 s improves this nine-clip average but excludes the 1 s person. Floor 2 s additionally excludes the 1.5 s person and reproduces the severe natural cold-start failure. No tested global floor dominates across these separate outcomes. A channel-specific higher floor would inherit the same short-person loss whenever that channel carries a brief second person; this experiment supplies no channel-specific justification.

**D2 — already settled by operator:** the draft lane stays ON for the demo candidate. Four-session stress differences were within noise, every session finalized, KV-cache peaked around 5.4–5.5%, and backoff skipped 96–100% of draft ticks. Eight-session degradation remained nonterminal. That decision is recorded here, not retested or changed by this identity experiment.

## Reproduction, retained evidence and validation

Measured production source: `323f122203cc5912ed539b9c753bc5c5c498cd63` in isolated `MOSS-Transcribe-Diarize-wt-llm-relay-0911`; replay observer and bench are the accompanying evidence-only change.

```sh
.venv/bin/python prototypes/streaming-diarization/identity-floor-a2/run.py \
  --data-root ~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data \
  --intro-wav ~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav
```

Add `--reuse` for the retained vectors (missing caches are freshly embedded locally). The existing local corpus and ONNX remain required; the command never downloads them. Generated concatenated WAVs are ignored and reconstructable; `.npz` observations and JSON state are retained in the bench.

- Bench: `prototypes/streaming-diarization/identity-floor-a2/run.py`, `NOTES.md`, `results/results.json`, sixteen `.npz` observation caches.
- Production seam preserved: `tests/live_identity_accuracy.py`; every one of **48 arms** matches the observer-free replay exactly, and every fixture passes production interval-selection checks.
- Metric examples validate known split/missed-person/unnamed counts, duplicate repair timing, and unresolved censoring before each run.
- Existing tests: `MOSS_REAL_CORPUS_ROOT=<main checkout>/prototypes/streaming-diarization/data/real .venv/bin/python -m pytest -q tests/test_live_identity_real_corpus.py tests/test_live_identity_accuracy.py` — **30 passed**, including all nine source pins; no environmental skip.
- Scope: no production file changed; only the bench, this audit, and the test-helper observer. No host operations, remote model calls, service restarts or database mutation.
