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

## Scorecard latency handoff correction

**Structural question.** Can the latency probe hand the scorecard its run population and observed one-second bucket counts without changing how latency is measured?

**Minimum primitives.** Each saved case-pass latency row is one run. Its `words.buckets`, `words.observed`, and `labelled_rows.observed` are the only counts the scorecard needs. The ordered `runs` list preserves per-case p50/p90; the totals count buckets across those rows. Removing a run loses a case-pass; pooling its p50 values would invent a statistic.

**Invariants.** `runs` is a list with one row per saved `latency.json`; `total_audio_buckets`, `word_observed_buckets`, and `label_observed_buckets` sum those same rows. Existing per-run quantiles remain unchanged. The scorecard still marks pooled p50 unmeasured.

**Assumptions and unknowns.** The scorecard currently reads `len(runs)` and the three totals. A future pooled-percentile gate would need raw one-second delay samples, which these receipts do not retain.

**Falsifier and tool decision.** If the retained 12-pass receipt gives any population other than 12 runs and 1,240 buckets, or if the scorecard still rejects the corrected JSON, the handoff is unresolved. An inline throwaway read of the production saved rows showed 12 runs, 1,240 total buckets, 964 word-observed, 964 label-observed, with word/label bucket denominators equal in all 12. Change only the serializer; then consume its output through pane 6.4's scorecard. No provider call is needed.

**Measured verdict.** The corrected serializer produced `latency-scorecard.json` for the retained 12-pass run. Pane 6.4's unmodified scorecard consumed it and recorded 12 runs, 1,240 audio buckets, 964 word-observed and 964 label-observed buckets. The quality decision remained FAIL; its latency eligibility text still correctly says pooled p50 is unavailable.

## Fixed-runtime E1 visual command

Lead explicitly assigned `evidence/P64/p62-gemini-e1-*/` to this pane for the visual run. Both PUBLIC fixture WAVs are 16 kHz mono PCM16, 302.0 s. Run these after pane 6.3 reports D-1/D-2/D-3 fixed and the paid-run cap is known. Terminal 1 runs the fixed `$RT` code on pane 6.2's port; terminal 2 runs pane 6.4's unchanged DOM harness against it:

```bash
RT=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-runtime
scripts/gemini-live/run-local-stack.sh --tree "$RT" --port 18500 -- --live-engine gemini

# Separate terminal, cwd=this worktree:
FIXTURE=/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture
E1_OUT=/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/p62-gemini-e1-$(date -u +%Y%m%dT%H%M%SZ)
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/e2e/run.py --stack-url https://127.0.0.1:18500 \
  --system "$FIXTURE/system.wav" --mic "$FIXTURE/E1-microphone.wav" --out "$E1_OUT"
```

The external-stack mode's `summary.source_revision` is this harness worktree SHA; report the actual `$RT` SHA beside it. The harness records the filmstrip, pre-Stop and final snapshots, and visual metrics in the assigned P64 directory. It does not calculate provider spend in external-stack mode, so count those calls and cost from the runtime diagnostics snapshot.

## Preview visibility correction before fixed rerun

**Structural question.** Does the 250 ms observer count text the frontend can render when the runtime publishes a canonical preview?

**Minimum primitives.** `session.provisional` is the current canonical preview; `draft` is shown only while active, with no provisional, and starting at the committed frontier. Both carry MOSS-formatted timed text relative to their `start_sample`. The production transcript parser yields the relative segment bounds; the frontend adds the start offset. A visibility observation is an overlap between those absolute bounds and a one-second audio bucket.

**Invariants.** Provisional and draft rows count as words but never committed speaker labels. A draft hidden by a provisional cannot count. No span-wide surrogate interval is inferred from text presence. The effective transcript remains the source of committed words and labels.

**Assumptions and unknowns.** The browser's `parseMossTranscript` and Python's production `parse_transcript` accept the same emitted grammar. If a future preview uses another grammar, these buckets stay unobserved until that surface is measured separately. The old run's aggregate latency cannot be retroactively corrected because its 250 ms snapshots were not retained.

**Falsifier and tool decision.** A public snapshot with a word-bearing provisional that produces no earlier word observation, or a hidden draft that produces one, falsifies the probe. An inline throwaway snapshot probe will print all observed bucket delays for both cases before the full paid rerun. This is necessary because the first-run word/label bucket equality can reflect an observer omission rather than actual UI latency.

**Probe verdict.** PASS on the emitted transcript grammar: two provisional words at absolute 10.2–10.8 s and 11.2–11.8 s observed buckets 10 and 11 at a 12 s snapshot, with delays 1.0 and 0.0 s; the simultaneous hidden draft at 20 s observed no bucket; no speaker label was attributed to the preview. After removing provisional, a visible draft at the committed frontier observed bucket 0. The old 964/1,240 word-latency total is superseded as a UI preview measurement; the fixed real run will provide a fresh value.

For the fixed H1 rerun, collect `run_quality.py --passes 1 --out <new-pass1>` and then `--passes 1 --pass-number 2 --out <new-pass2>` against the same stack. Merge with `merge_quality_passes.py --pass1 <new-pass1> --pass2 <new-pass2> --out <new-combined>`, write `latency_probe.py --run-dir <new-combined>` output to `<new-combined>/latency-summary.json`, then run `report/scorecard.py --gemini-quality <new-combined> --passages <new-combined>/h1-timed-segments.json --latency <new-combined>/latency-summary.json --gemini-e1 <E1_OUT>/summary.json --out-dir <new-scorecard>`. Require exact six-plus-six case population and fixed runtime commit receipt before the comparison table.

## Stop drain diagnostic seam

**Structural question.** Did Stop publish the accepted tail before terminal finalization, even when H1's settled surface still has its pre-Stop lag?

**Minimum primitives.** H1's existing `pre_stop_settled` snapshot defines the comparable live surface. Its capture service also records `stop_return`, the public snapshot returned after the runtime's Stop drain. The reference and `stop_return` timed rows permit the same ±3 s passage check as a separate D-2 diagnostic. These are distinct clocks and neither can stand in for the other.

**Invariants.** Keep H1's three surfaces and scorecard sidecar unchanged. Save `stop_return` rows with the session's finalization status; if it is already final, the row cannot establish a pre-terminal drain. Report Stop passage coverage separately from pre-Stop settled DER/missing seconds.

**Assumptions and unknowns.** The runtime's Stop return is after its drain and before terminal completion on the reachable Gemini path; this must be checked in the fixed run. Exact tail coverage is unmeasured until then.

**Falsifier and tool decision.** A missing `stop_return` capture, terminal-already-final status, or missing reference seconds in its rows prevents the D-2 claim. Source inspection found H1's `SurfaceCaptureService.stop()` always captures `stop_return` from the published service `stop()` result. Persist that already captured snapshot's rows; score with pane 6.4's existing passage predicate after the run. No new scorer or paid probe is needed.

**Stub probe verdict.** A 50 s 1.0× Javier loopback replay wrote the new receipt with one reference and one Stop-return row. Its Stop-return status was already `final`, so it validates serialization only and cannot prove a pre-terminal drain. The fixed Gemini run must report its Stop-return status and coverage. Stub service stopped with no port 18500 listener; Gemini spend $0.

## Fixed-runtime measured verdict

The scorecard-compatible latency schema and provisional-preview observer completed 12/12 paced H1 case-passes on the `ea224972` server process: 1,238/1,240 word and 1,124/1,240 committed-label buckets observed. Pane 6.4's unchanged scorecard consumed the latency file and timed-segment sidecar. The D-4 pre-Stop settled surface reached the accepted frontier in every case; missing reference seconds fell from 208/1,216 to 0/1,216, but settled DER was 0.175830, above the strict 0.145 bar. Final DER was 0.109542, narrowly within 0.110. The separate E1 visual run, as directed on earlier `034baf1e`, showed 11 speaker labels at Stop versus a limit of five. Thus D6 is FAIL, with E1 not on the H1 runtime revision. All 12 supplemental Stop-return captures were already final and cannot isolate a distinct pre-terminal Stop drain. The accept6 RTF90 reference covers only 60.894/89.994 s; omitting it gives a diagnostic 0.106686 settled DER, not the official H1 verdict. Full tables and custody: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/gemini-fixed-ea224972-h1-12-0702/FIXEDRUN.md`. Known follow-up spend $0.598896 plus an interrupted, unmeasured pre-D4 attempt; cap $8. No listener retained.

## Single-revision ad72bacc rerun contract

**Structural question.** Do the C1+C3 registry, birth rule, growing scheduler, and lane routing improve the complete H1 speaker surfaces and the rendered E1/M2 meetings when measured on one runtime revision?

**Minimum primitives.** The frozen accept6 case, two opposite-order passes, and three H1 surfaces preserve the comparator. The 250 ms public snapshot observer measures word and committed-label visibility. Pane 6.4's browser harness measures rendered E1 and M2 rows. Runtime `engine_diagnostics.lanes` owns system and microphone calls, anomalies, audio seconds, skipped ticks, and cost; top-level counters own the meeting total. A server process started from clean `ad72bacc` binds all these observations to one revision.

**Invariants.** H1 sends case audio on system and digital silence on microphone; E1 and M2 send only the three named PUBLIC WAVs. All sessions run at 1.0×. The 12 H1 manifests must share one descriptor identity. Lane counter sums must reconcile with the top-level calls and cost; a silent H1 mic should have zero provider calls. Keep H1, E1, and M2 revision equal. Never treat sparse RTF90 reference sensitivity as a new official population.

**Assumptions and unknowns.** M2's true speaker count and qualification bar are not declared here; report observed visual measures without inventing a pass/fail threshold. P64's scorecard accepts one E1 receipt; M2 is a separate visual diagnostic. The runtime may be edited after startup by another pane; confirm the process does not restart and all descriptor identities agree.

**Falsifier and tool decision.** A wrong import path or revision, incomplete case-pass population, lane totals that fail to reconcile, a missing visual final surface, or spend reaching $8 blocks a single-revision result. Verify the runtime HEAD and fresh listener before launching; one H1 case exercises lane-counter shape, then finish both passes. Run the unchanged E1/M2 browser harness because service snapshots alone cannot prove rendered speaker labels. Use the unchanged scorecard for the exact H1 population and E1 gate; report M2 alongside it.
