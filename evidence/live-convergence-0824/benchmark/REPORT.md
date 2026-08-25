# Benchmark: MOSS live mode vs LiveTranscribe and ProjectClerk (handoff-8YIE4C step 7)

2026-08-25, post-campaign (`df5e297`). One scoring instrument for every number: this repo's
deployed scorer (`calculate_tbsa` / `calculate_diarization` / `score_live_speaker_accuracy`)
plus evaluator v2 (campaign M0c), identical references, identical audio bytes per case.
Producer: `prototypes/streaming-diarization/live-convergence/score_external_benchmark.py`
(re-runs offline from `raw/`); results: `results.json`.

## Systems and modes (read this before the table)

| System | What ran | Mode | Where |
|---|---|---|---|
| **MOSS-Transcribe-Diarize** (this repo, campaign build `22dc5b8`) | deployed `web_cli` live replay → terminal finalization | **LIVE** (paced 1.0×, terminal == file by campaign result) | MacStudio + 4070 Ti vLLM |
| **LiveTranscribe** (m4mbp `6a8d0c1`) | `DiarizationDump --transcribe --post-cluster`, production `CalibrationProfile.current.json`, whisper-large-v3 (WhisperKit), debug binary | **FILE** (its own file-mode bench proxy) | m4mbp (M4 MBP, CPU/ANE) |
| **ProjectClerk** (m4mbp `4345b66`) | `pcbench` release binary (pipeline-faithful ImportManager steps 1–5 replica, 2026-07-15 lineage), whisper-large-v3 + FluidAudio VBx | **FILE** | m4mbp (M4 MBP, CPU/ANE) |

The comparison is deliberately asymmetric in MOSS's favor being harder: **MOSS's column is
its live mode** (streamed at real-time pace, published incrementally, then terminally
finalized); the other systems are scored on their **offline batch file modes**. Neither peer
system has a headless live mode to run (ProjectClerk's live path is app-only; LiveTranscribe's
live capture needs attended AV). After this campaign, MOSS live == MOSS file exactly, so this
is also a comparison of everyone's best file-quality surface.

## Accuracy (this repo's evaluator; WER ↓ / DER ↓ / speaker-accuracy ↑ / v2 recall ↑)

| Case | MOSS live(terminal) | LiveTranscribe file | ProjectClerk file |
|---|---|---|---|
| lex_bill_ackman 1 min | **.1591** / **.0755** / .9245 / .932 | .1193 / .2140 / .7860 / .943 | .1193 / .2540 / .7460 / .943 |
| lex_javier_milei 1 min | .0880 / **.1518** / .8482 / .920 | .1200 / .1632 / .8368 / .898 | **.0640** / .1822 / .8178 / .942 |
| lex_keyu_jin 1 min | **.0647** / **.0790** / .9210 / .986 | .1007 / .1642 / .8358 / .942 | **.0647** / .1583 / .8417 / .978 |
| lex_adam_frank 3 min | .1262 / .0662 / .9338 / .949 | .1808 / **.0562** / .9438 / .924 | **.1281**¹ / .1668 / .8332 / .953 |
| lex_keyu_jin 5 min | **.0506** / **.0579** / .9421 / .973 | .0793 / .0991 / .9009 / .952 | .0547 / .1204 / .8796 / .966 |
| **mean** | **.0977** / **.0861** / .9139 | .1200 / .1394 / .8607 | .0862 / .1764 / .8237 |

¹ PC's adam-3m WER .1281 and LT's .1808 reproduce the 2026-07-15 PC-vs-LT benchmark's own
.128/.181 to 3 dp — independent cross-validation that this pipeline (conversion + scorer)
is faithful to how those systems were scored before.

**Reading.** Speaker attribution: MOSS wins DER on 4/5 cases and by .05–.09 absolute on
mean — the two whisper-based systems trail badly on 1-minute two-speaker clips (.16–.25 vs
MOSS .08–.15). Text: ProjectClerk (whisper-large-v3 + hallucination guards) edges the mean
WER (.0862 vs .0977), entirely from `lex_bill_ackman`, where whisper transcribes the clip
better than the MOSS model does in ANY mode (MOSS file == .1591 there — a model ceiling,
not a live-mode defect). MOSS wins or ties WER on both keyu cases outright and is the only
system whose speaker-attribution quality does not collapse as clips shorten.

## Latency (definitions differ — read the notes; not one clock)

| Quantity | MOSS live (measured this campaign) | LiveTranscribe | ProjectClerk |
|---|---|---|---|
| Provisional first words | 2.5 s span cap + queue/decode ~0.6 s p50 (base path publication, M2 exit) | ≈1.16 s provisional (handoff-attributed to its docs; not re-verified this session) | streaming exists (LocalAgreement-2) — no headless measurement available |
| Correction/refinement age | rolling correction p95 **8.757 s** (G-M2-4, structural floor 8.51 s at 10/10; unsigned row, D-M2-3 pending) | ≈4.9 s canonical (same attribution) | n/a headless |
| Terminal/final surface | stop → `final` in ~2.06 s on 60 s meetings (stress runs, 4 polls); cold terminal readiness 2.182 s, RTF .036 (M4 exit) | stop-time refinement stages exist, unmeasured here | file import only |
| File-mode wall (this bench) | (not re-timed; decodes on 4070 Ti) | 10–24 s per case on m4mbp (debug binary) | 4–18 s per case on m4mbp (release; ~12 s model load in first runs) |

Wall-clocks run on different hardware (MOSS: remote 4070 Ti vLLM; peers: m4mbp CPU/ANE) and
different build types — they are provenance, not a speed race.

## Honest incomparabilities

- Mode asymmetry as stated above; it favors the peers, and MOSS still leads DER.
- Different ASR models is the point (product-vs-product), not a controlled ASR study; the
  2026-07-15 doc holds the controlled same-weights LT-vs-PC comparison.
- LT ran its debug binary (accuracy unaffected; wall-clock inflated).
- LT's latency analogues are cited from the handoff, which attributes them to LT's docs;
  this session did not locate the primary measurement and marks them accordingly.
- PC's `pcbench` is the surviving 2026-07-15 pipeline replica
  (`~/Desktop/AI_Projects/0.AISIGHT_LOOP/bench-filemode-pc-lt-0715/pcbench`, not in PC's
  repo); PC has evolved since (`4345b66`), so treat PC rows as "PC as of the replica's
  pipeline with current models/assets on disk".
- LT post-cluster relabels: applied by utteranceID row-alignment; 0 label changes resulted
  on every case (`convert.relabels_changed=0` in results.json) — post-clustering agreed
  with streaming labels on this corpus.

## Provenance

- MOSS numbers: `evidence/live-convergence-0824/M4-e4-exit-2/gates.json` `quality.cases`
  (runs A==B to 6 dp), fresh deployed batch 15:29–15:55Z; independently reproduced by the
  step-6 regression (`../post-implementation-tests/`).
- LT/PC raw outputs: `raw/` (transcripts + relabels / hyp + timing per case), produced
  13:0x EDT on m4mbp, sequential, one system at a time; walls in `results.json`.
- Corpus: the five fully-referenced golden cases (trio 1-min, adam-frank 3-min, keyu 5-min),
  shipped byte-identical from this repo to m4mbp (`/tmp/rlc-bench/<case>/audio.wav`).
