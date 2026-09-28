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
