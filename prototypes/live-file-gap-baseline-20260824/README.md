# Live-vs-file paired accuracy baseline — 2026-08-24

Fresh paired measurement of live-mode vs file-mode accuracy on the deployed MacStudio
dev stack (`https://127.0.0.1:7861`, code @ `d910a06`, live provider manifest @
`cc8f778`) → SSH tunnel `127.0.0.1:18000` → 4070 Ti WSL vLLM
(`OpenMOSS-Team/MOSS-Transcribe-Diarize`, greedy, max_new_tokens 12000, file windowing
150/120). Both arms hit the same deployed backend; strictly sequential, arm order
alternated per case.

- `trio-60s/` — the three fully-referenced 1-minute cases (lex_bill_ackman,
  lex_javier_milei, lex_keyu_jin) plus partial secondary attempts. `results.json` has
  per-case TBSA/WER/coverage/TSA/DER/speaker-accuracy for both arms;
  `<case>/live/run-001/trace.jsonl` is the full `live_service_replay` trace (the
  `terminal` event carries the final snapshot with committed spans);
  `<case>/{file,live}-hypothesis.jsonl` are the scored segments.
- `keyu-5m/` — one paired 5-minute case (benchmark_5m/lex_keyu_jin): the gap does NOT
  grow with duration (TBSA −7.1pp at 300 s vs −7.2pp at 60 s).
  **Its `live/run-001/trace.jsonl` is span-truncated and must not be used for span-level
  analysis.** The replay client of 2026-08-24 read the service event stream once after the
  session ended, so the service's 1000-event retention bound had already evicted the first
  113 events: the trace starts at frame 60 / span 13 and holds 114 of 127 spans. The scores
  above are unaffected — they come from the `terminal` snapshot, which is complete. The
  client was fixed on 2026-08-25 (drains once per frame); a complete trace for this case is
  `evidence/live-convergence-0824/M0e-trace-completeness/run-5m/trace.jsonl.gz`, and any
  fresh run of `remeasure_5m_case.py` now writes one.
- `remeasure_live_vs_file.py`, `remeasure_5m_case.py` — the drivers (paths inside
  point at the session scratchpad; pass a fresh out-dir to rerun).

Headline (trio means): FILE TBSA .9106 / WER .1039 / coverage .9199 / DER .1021 vs
LIVE TBSA .8384 / WER .1999 / coverage .8640 / DER .1764. File arms byte-match the
peer (codex) run of the same day; live arms replicate within noise. 69/79 frozen
spans hit the 2.5 s hard cap; 5 committed spans empty (later shown to be parser
discards, see `../live-file-gap-emptyspan/NOTES.md`).

Downstream diagnosis/prototypes that consume this baseline:
`../live-file-gap-context/`, `../live-file-gap-emptyspan/`,
`../live-file-gap-identity/`, `../live-file-gap-timing/`.
