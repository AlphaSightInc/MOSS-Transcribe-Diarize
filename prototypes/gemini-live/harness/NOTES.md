# P6.2 quality harness prototype

## Structural question

Can a local, GPU-free live stack be measured on the exact H1 six-case, two-pass, three-surface population using H1's replay and scorer, while measuring UI-visible latency at actual audio pace?

## Minimum primitives

- **Frozen case**: audio, reference, manifest claim. Removing the identity check permits a different denominator.
- **HTTP replay**: one system frame and one silent microphone frame at each timestamp, through the published live API. Removing it changes the path being tested.
- **Surface snapshot**: immediate before Stop, drained before Stop, and final after Stop. They have different authority and must remain separate.
- **Production score and projection**: H1 scorer and macro aggregation. A second metric implementation cannot establish equivalence.
- **Timed observation**: wall-clock sample of the public snapshot at 250 ms cadence. Replay traces alone do not prove when text was visible.

## Invariants

- The default arm uses `accept6`, 2 passes, forward then reverse, at 1.0x, with zero digital microphone audio.
- Each scored row comes from the corresponding public surface. Raw and D45b ruled settled DER are retained separately.
- One-second bucket latency uses the first observed text or labelled non-provisional row that overlaps the bucket. Never convert accelerated replay to a latency claim.
- Stub output proves API, transport, capture, and scoring plumbing only; it is not a quality comparison.
- All recordings stay local unless a separately authorized Gemini run explicitly sends public audio. This pane makes no Gemini calls.
- Gemini `WindowResult.timing_anomalies` from common fix `bc567bb2` has denominator 0 in this pane. Counts and per-call rates are UNMEASURED here.

## Assumptions and unknowns

- The future Gemini runtime will keep the same HTTP descriptor, frame, snapshot, event, Stop, and finalization shapes. Unknown until pane 6.3 lands.
- A stub may fail H1's rolling-window coverage predicate even while replay and scoring work. Report the failure rather than fabricate equivalent coverage.
- Speech activity and UI visibility differ; bucket latency denominator is all one-second audio buckets, with uncovered buckets counted explicitly.

## Hypothesis and falsifier

Hypothesis: the retained H1 functions can consume a local loopback-stack replay and emit the same `content-free-metrics.json` schema, with 12 complete case passes. Falsifier: a missing surface, scorer disagreement on a retained hypothesis, or any forced reimplementation of H1's metric arithmetic.

## Tool decisions

- Inspect the H1 collector and receipts to identify exact code and denominator; any mismatch changes the comparison contract.
- Run a one-case retained interval re-score to test metric identity; disagreement blocks quality claims.
- Run the loopback stub and local HTTPS stack to test the actual API path; service failure blocks the receipt.
- Run the full 12-session replay only after the one-case plumbing probe; failure is reported with trace and no Gemini quality claim.

Commands from the worktree:

```bash
# Terminal 1; loopback plumbing:
scripts/gemini-live/run-local-stack.sh --port 18500 --stub
# Terminal 1 for Gemini, after pane 6.3 lands its composition-root selector:
scripts/gemini-live/run-local-stack.sh --port 18500 -- --live-engine gemini
# Terminal 2; choose a new scratch output path for each run.
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/harness/run_quality.py \
  --base-url https://127.0.0.1:18500 --out "$TMPDIR/p62-quality-$(date +%s)" \
  --status /Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-6.2-STATUS.md
```

The launcher passes arguments after `--` through to `phase2_web_cli`. Pane 6.3's runtime brief names `--live-engine gemini`; that option is not in the current CLI yet. The Gemini command above becomes runnable when it lands. Local frontend assets already exist at `moss_transcribe_diarize/app/frontend_assets/`; the launcher checks the required files. If absent, run `npm --prefix frontend run build` in a tree whose owner permits that write.

## Verdict

**PASS for local plumbing, UNMEASURED for Gemini quality.** The loopback MOSS stub completed 12/12 HTTPS replay sessions at 1.0x on the frozen `accept6` corpus, 1,239.987 audio seconds. H1's production projection emitted the same top-level JSON keys, case/pass population, manifest identity, and duration as the retained H1 receipt. All 122 planned full windows were covered: 116 rolling, 6 terminal, 0 uncovered. Immediate, settled, and final surfaces appeared in every run. No service or scorer discrepancy falsified the plumbing hypothesis.

The public-snapshot probe collected 1,240 one-second buckets: stub text appeared in 942; non-provisional speaker-labelled rows appeared in 90. Unobserved buckets remain in the denominators. Stub speech is meaningless; these values prove observation mechanics only. A 50 s optional PUBLIC E1 synthetic microphone arm succeeded separately (100 frames, 800,000 accepted/accounted samples, 5/5 windows covered); it is not H1-comparable.

Retained H1 Bill Ackman pass-1 intervals were re-scored through production `_quality_speaker_intervals`, with exact agreement on every raw/ruled D45b diagnostic (raw DER 0.140000, ruled 0.121167). Lexical re-scoring remains impossible from speaker-only retained intervals.

Two committed worktree reference JSONL files (Bill Ackman and Keyu Jin) fail their own frozen manifest hashes. Their manifest-matching Git blobs at `966d250b^` are restored into scratch by `run_quality.py`; the production input verifier then passes. The checkout corpus is never edited.

Receipts: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/{content-free-metrics.json,stub-run.json,latency-summary.json,scorer-equivalence.json,mic-arm.json,moss-baseline.json}`. Gemini calls 0, spend $0, timing-anomaly rate UNMEASURED. No listeners remain on ports 18500/18501.

## H1 offline segment scoring extension

**Structural question.** Can the three H1 quality surfaces be scored from offline segment lists without changing the production metric definitions or speaker label semantics?

**Minimum primitives.** A frozen H1 case supplies the reference, audio, duration, and category. A surface is a list of timed text and opaque speaker IDs. A common speaker album maps those IDs to H1's published `S01` labels; `None` and `S00` map to unattributed `S00`. The existing H1 exporter, surface scorer, D45b settled diagnostic, and macro mean are the only metric operations.

**Invariants.** All three surfaces use one speaker album. Their segment times go through H1's sample based exporter. Only settled DER carries the H1 raw and D45b ruled pair. Macro values are the eight `QUALITY_BOUNDS` names, with each case weighted once. Reference audio and JSONL must match the H1 manifest; the two stale committed JSONLs are recovered in scratch.

**Assumptions and unknowns.** Input `text` is the hypothesis actually shown on each surface; empty text has the production exporter's usual omission semantics. Arbitrary speaker strings are stable within one case. Offline segments do not prove live window coverage, latency, or finalization. The retained H1 settled intervals contain no words, so they can check DER and reference speech DER only; lexical equivalence is unmeasured from that receipt.

**Hypothesis and falsifier.** Reconstructing a minimal snapshot and calling H1's unchanged exporter/scorers reproduces all four Bill Ackman pass-1 settled DER values from retained intervals. Any mismatch or need for new metric arithmetic falsifies the wrapper.

**Tool decision.** A one-case scratch probe tests whether opaque IDs survive H1 export and D45b scoring. The final equivalence call tests the public wrapper; a mismatch blocks handoff. No provider, host, or local service is required.

**Probe verdict.** PASS. The scratch snapshot/export/scorer path reproduced retained Bill Ackman pass-1 settled raw DER `0.140000`, ruled DER `0.121167`, raw reference-speech DER `0.124172`, and ruled reference-speech DER `0.105337` over 21 intervals. Full probe state: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/h1-offline-probe.json`. Its placeholder text cannot prove the word metrics.

**Offline call.** From another pane, add `prototypes/gemini-live/harness` to `sys.path`, then `from h1_offline import score_case, macro`. Call `score_case("interview_bill_ackman_60s", immediate=rows_a, settled=rows_b, final=rows_c)` with each row `{start: seconds, end: seconds, speaker: arbitrary_string_or_None, text: str}`; `"S00"` also means unattributed. Pass a list of returned cases to `macro(results)`. Each case result has exactly H1's per-case keys and each surface has H1's metric keys. `pass`, `session_id`, `windows`, `window_coverage`, and `surface_observations` are `None` because offline hypotheses do not observe live execution. `der_raw` and `reference_speech_der_raw` occur only on settled, as in H1. Macros are the eight `QUALITY_BOUNDS` keys, with one equal weight per result. Frozen `accept6` cases recover two stale reference files in temporary scratch. Other timed JSONL case IDs follow `common/corpus.py` (`benchmark:...`, `calibration:...`, `benchmark_5m:...`, `benchmark_30m:...`, `rtfl90`). The `category` field labels sparse acquired long-form references `sparse diagnostic`; keep them out of qualification macros.

**Wrapper verdict.** PASS on reachable equivalence. The public wrapper reproduced the four retained Bill settled DER values, all H1 per-case and per-surface metric key sets, and all eight H1 macro values when applied to the 12 retained results. Replacing the three unattributed Bill intervals' `None` speakers with `"S00"` left every surface metric identical. Word-metric equivalence on retained intervals remains unmeasured because those intervals omit text. Gemini calls 0, spend $0, timing-anomaly rate UNMEASURED.

**Extended corpus question.** Panes 5.3 and 6.1 also score gold9 and 5-minute hypotheses. Their references and WAVs use the same production H1 scorer inputs; case ID to directory plus audio duration are the additional primitives. The invariant is unchanged metric arithmetic, with corpus tier recorded in `category`. Sparse acquired 5-minute and acquired 30-minute references cannot qualify DER/WER. Falsifier: H1's scorer rejects a complete long-form reference. One-segment probes on gold9 Bill, 5-minute Bill, and 30-minute Bill scored all 14 settled H1 fields at their 60/300/1800 s durations. The 5-minute probe used 12 reference rows and gave DER `0.98`, WER `0.978355` for the intentionally partial one-segment hypothesis. These prove scorer compatibility only. The wrapper exposes all timed JSONL cases, with sparse long-form cases marked diagnostic in `category`; qualification follows the lead's reference-completeness ruling.

## Real Gemini first-run contract

**Structural question.** Can pane 6.3's real placeholder engine complete paced accept6 replay through Account HTTPS while retaining three H1 quality surfaces, public visibility latency, and per-session provider accounting?

**Minimum primitives.** The separate runtime worktree owns the engine. This pane's launcher selects its import root without copying code. A frozen accept6 case and paced replay create the three snapshots. H1's production scorer owns the quality numbers; the existing 250 ms latency probe owns visibility. Public `engine_diagnostics` owns calls, errors, timing anomalies, audio sent, and USD cost. A separate six-case pass is a partial population; two opposite-order passes make the H1 comparison population.

**Invariants.** The stack import path must resolve inside the runtime worktree. Each case is 1.0x with silent microphone. Pass 1 follows manifest order; pass 2 reverses it. Save per-case partial receipts before the next case, so failure does not erase completed observations. No one-pass macro is called H1-equivalent. Keep cumulative observed spend below the $5 run cap; record failed-call spend as unknown when the counter cannot be read. All produced reports omit words and credentials.

**Assumptions and unknowns.** The runtime integration is still being edited by pane 6.3. Its final revision, first-run failures, and exact provider cost are unknown until launch. MOSS-specific rolling event classification may not recognize Gemini's terminal event; a coverage disagreement is a measurement failure to report, not a quality verdict.

**Falsifier.** Wrong import root, incomplete/failing surface, unscorable H1 case, absent diagnostics, or an unrecoverable provider error prevents an end-to-end comparison. A clean six-case pass supports only first-pass numbers; the second opposite-order pass is needed for the 12-session H1 population.

**Tool decisions.** Inspect pane 6.3 status and current runtime shape before launch; a missing working adapter changes the action to a timed readiness wait. Probe the public diagnostics shape offline before coding extraction; mismatch changes the capture. Run one paced case first if runtime changed since pane 6.3's probe; failure stops the campaign. Then run both six-case passes and the existing latency summarizer. Use H1's production projection only after all 12 cases exist.

The real snapshot contains `engine_diagnostics` at its root, but the generic Account replay snapshot decoder discards that extra field. `run_quality.py` therefore reads one raw authenticated HTTP snapshot after each replay, before closing its adapter. It writes `engine-diagnostics.json` incrementally with per-case calls/errors/retries/anomalies/cost and distinct named labels at the immediate pre-Stop surface. A missing counter remains `UNMEASURED`.

The D6 passage sidecar contract supplied by the lead is `<out>/h1-timed-segments.json`: root `schema="h1-timed-segments.v1"`, frozen corpus manifest SHA-256, and `cases` rows with `case_id`, `pass`, raw timed `reference` segments, and `surfaces.{pre_stop_immediate,pre_stop_settled,post_stop_final}` rows. Every row has original `{start,end,speaker,text}` segment bounds in absolute audio seconds. No token timestamps are inferred. The file is updated after each case; `pass-X/<case>/timed-segments.json` preserves each case-pass separately. A six-case file is partial; pane 6.4's scorecard requires the merged 12-case file. The raw reference and public transcript text appear only in this authorized sidecar, not the quality summary.

**Two-pass merge probe.** The compact `moss-baseline.json` lacks H1 window fields and cannot be fed to the full projection. Splitting the retained full H1 receipt into six pass-1 and six pass-2 rows, then calling production `_quality_projection`, reproduced all ten published macro values exactly. A merge must require the exact six case IDs in each pass and the same manifest SHA-256; otherwise it must fail before writing a 12-session comparison.

Lead corpus ruling: `benchmark:acquired_jamie_dimon` has only 12.3/60 s timed reference and is diagnostic only. Gold9 qualification uses the other eight clips; NFL 52.9/60 and Rolex 51.1/60 are near-complete, with small untimed gaps that can inflate miss. The lex 5-minute trio and lex Bill 30-minute reference are complete. `rtfl90` covers 60.9/90 s and is partial diagnostic. Accept6 remains the primary comparison.

**First-run verdict (real Gemini placeholder).** The runtime package import resolved in pane 6.3's separate worktree. One 50 s smoke, then six forward and six reverse accept6 cases completed through the real Account HTTPS path and H1's three surface scorer, with 12 provider manifests and 1,239.987 scored audio seconds. A daemon restart interrupted an extra Bill reverse attempt after 232,000 samples; runtime recorded `aborted/helper_lease_expired`, two preview calls, and $0.001004. Four earlier reverse cases persisted; Bill and mono were rerun alone and stitched in original reverse order. This extra attempt is excluded from the 12 successful case-pass quality population and included in spend.

The 12 successful sessions produced settled D45b DER `0.464568` (MOSS `0.144626`), final DER `0.271687` (MOSS `0.110022`), and final WER `0.117671` (MOSS `0.095074`). Pane 6.4's sidecar passage gate found 208/1,216 settled reference seconds without a word-bearing segment within ±3 s, concentrated in every case's final 17–18 s; final had 0/1,216 missing. These fail D6 quality bars. The public snapshot latency probe observed words and named labels in 964/1,240 one-second buckets; per-case p50/p90 values are in `FIRSTRUN.md`. It retains per-case quantiles only, so a pooled p50/p90 is unmeasured. E1 labels at Stop and the 60-minute cost bar remain unmeasured.

Provider diagnostics for the 12 successful sessions: 380 Gemini calls, 8 clamped words (`8/380 = 0.021053` per call), 0 dropped (`0/380`), 0 errors/retries, $0.444760. The smoke cost $0.013032; all observed pane spend including the interrupted attempt is $0.458796, within the $5 cap. The runtime engine is the phase-2 placeholder, with batch-tail words and L=60/S=10/hold-back=10 policy. It is not a qualification run. Main receipts: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/gemini-placeholder-h1-12/{FIRSTRUN.md,first-run-summary.json,content-free-metrics.json,h1-timed-segments.json,engine-diagnostics.json}` and `gemini-placeholder-scorecard/scorecard.json`. The stack was stopped and port 18500 has no listener.

To reproduce the two-pass collection from a ready runtime stack, run `run_quality.py --passes 1` for pass 1, then `run_quality.py --passes 1 --pass-number 2` for reverse pass 2, each with a new `--out`. `merge_quality_passes.py --pass1 <dir> --pass2 <dir> --out <new-dir>` requires exact six-case populations and one frozen manifest, then calls production `_quality_projection`. `latency_probe.py --run-dir <combined-dir>` reports the per-case timing summaries. Pane 6.4's scorecard accepts the combined quality directory and its exact `h1-timed-segments.json` sidecar. Its optional `--latency` currently rejects `latency_probe.py`'s `runs: int` JSON (`TypeError` expecting a list); the scorecard was run without that optional flag, and the per-case latency values are in this pane's report. The scorecard evaluated the sidecar for a passage FAIL but also emitted an inconsistent “EXCLUDED” eligibility line; pane 6.4/lead were informed in status.
