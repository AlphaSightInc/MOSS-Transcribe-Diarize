# Goal handoff: attended-quality closure and lower word-to-screen latency

Date: 2026-08-19

## Mandatory first action

Start the session with `/goal` (or the exposed goal-creation equivalent), no token budget:

> Systematically resolve the attended microphone/lane-balance and apparent speaker-splitting issues, then measure and materially improve live word-to-screen latency while preserving transcript quality, diarization, lifecycle safety, and bounded concurrency. Finish with reproducible evidence, corrected design records, focused/full validation, and fresh attended acceptance; do not claim completion from mocks or unreplicated one-corpus results.

Keep that goal active until all required work below is actually complete or a genuine external/user gate is reached.

## Read first; do not duplicate

- Project method rules: `AGENTS.md`.
- Original two-defect brief: `docs/handoffs/handoff-mic-XXXXXX.md`.
- MVP/product goal: `docs/plans/mvp-demo-plan.md`.
- Standing design/evidence record: `docs/design-streaming-diarization.md`.
- Lane prototype: `prototypes/lane-balance/`.
- Current speaker diagnosis: `evidence/phase1/g3-attended/attended-session-8049-speaker-split-diagnosis.json`.

Authoritative product checkout is this repo, not the similarly named `0.AISIGHT_LOOP` control-plane checkout.

## Live starting state

> **Corrected after this brief was written.** The operator asked for a clean worktree, so
> everything this section listed as pending was committed. Do not go looking for uncommitted
> diffs -- there are none, and nothing was lost. Only these facts changed; the rest of this
> brief stands as written.

- Branch/head: `dev` at `bd6add4` (this brief was written against `b47c6d2`).
- Working tree is **clean**. The diagnostic/prototype work is committed, not pending:
  - `978da65` -- lane-balance bed, both preregistrations, the validator, all three evidence
    artifacts, and the design-record entries. Its commit message also carries the review
    findings that reopen Issue 1, so the record does not read as a settled `RETAIN_IDENTITY`.
  - `f87e2fe` -- retires the superseded `docs/handoffs/handoff-XXXXXX.md` (recoverable at `ce9e130`).
  - `bd6add4` -- adds `docs/plans/mvp-demo-plan.md`.
- At last check, HTTPS service `:7861` and read-only vLLM tunnel `127.0.0.1:18000` were live. Recheck; do not assume.
- Live attended service reported source revision `cc8f778a89326ee18a3c362d886bb9abdd63646b`, not current checkout head. Separate code evidence from deployed evidence.

## Peer review status

Claude's last completed review was captured read-only from `MOSS:1.1`. The visible next prompt was “run the recalibrated sweep and tell the monitor,” but no resulting artifact was present at this handoff. Use `$tmux-peer` read-only or inspect new files to learn whether that work later completed; do not duplicate it blindly.

The fleet monitor is `MOSS:2.1`; the original queue already carried the mic defect. Coordinate before renewed implementation so the fleet does not duplicate it. `$tmux-peer` itself is capture-only—never use that skill to send keys.

## Issue 1: microphone buried in mono mix — reopened

The previous `RETAIN_IDENTITY` conclusion is not reliable enough to close the defect:

1. Fixture calibration was wrong for the attended observation. The fixture sources naturally differ by `10.741875 dB`; adding `-15 dB` synthetic attenuation created `25.741875 dB` total disparity. To reproduce the measured attended `15.377 dB`, synthetic microphone attenuation is `-4.635124658 dB`.
2. `proto_lane_balance.py::lcs_matches` uses `difflib.SequenceMatcher.get_matching_blocks()`, not true LCS. On the v2 artifact, identity microphone matches are 12, not 8; peer-RMS shared matches are 33, not 32. The emitted metrics and corresponding design text need correction.
3. Microphone-only Levenshtein/WER against a transcript containing both lanes is not a valid rejection guard; insertions from the other lane dominate it.
4. Naively summing the two per-lane LCS scores is also invalid: identity yields 51 summed matches from only 49 hypothesis tokens, proving double-counting.
5. A small prototype of a non-double-counting edit distance against any order-preserving interleaving of the two lane references gave total-content WER `0.6168` for identity versus `0.3458` for the extreme `+25.742 dB` peer-RMS arm. This reopens gain-only exploration; it does not authorize that arm or a production policy.
6. Same hashed identity audio decoded identically 6/6 in an independent check. Decode nondeterminism was not reproduced. The larger limitation is one corpus/same-model references, not repeated inference count.

Current revised work plan:

1. Seal a v3 contract before another score. Use true LCS only as a per-lane diagnostic. Primary metric must credit each hypothesis token at most once and tolerate lane interleaving (an ORC/shuffle-style edit score is the current candidate). State the exact recurrence and print full state.
2. Recalibrate to `-4.635124658 dB` synthetic attenuation, yielding `15.377 dB` total disparity.
3. Sweep microphone gain from identity through RMS parity and `parity + 6 dB`. Experimental offsets may locate a target; no hand-tuned constant may ship.
4. Report limiter/clipping, total-content errors, per-lane diagnostics, output length/hallucination cost, decode timing, and hashes.
5. Replicate any apparent optimum on distinct-speech evidence. One synthetic 12 s corpus cannot select production policy.
6. If a target survives, prototype a causal live rule: define RMS window, activity/silence gate, adaptation rate, maximum gain, headroom/limiter behavior, echo/bleed behavior, and reset semantics. Whole-clip future RMS is not a live policy.
7. If gain-only fails, test separate-lane decode/merge. It remains untested; measure latency, inference load, attribution/merge coherence, overlap, and identity effects.
8. Only then change production code/manifest, with regression and attended evidence.

Historical v1/v2 artifacts must remain traceable. Mark them superseded/invalid for policy selection; do not silently overwrite their sealed inputs/results.

## Issue 2: apparent speaker over-splitting — no production change

The no-change verdict stands:

- `S04/S05` are source-confirmed Lex Fridman question versus James Holland answer: genuinely different people.
- Raw centroid cosine is `0.004914265821`.
- `S01/S02` raw cosine is `-0.074201670028`; production clamps it to `0.0` by contract. The current artifact's `production_cosine_similarity: 0.0` is accurate production output, but annotate that it is floor-saturated and record raw cosine separately.
- Retained transcript gives useful context: S01 has Cookiebot tagline copy; S02 has conversational ad copy. This supports two roles but cannot prove two humans because audio was not retained.
- Keep `production_change: NONE` and `threshold_change: NONE`. Reopen only with the exact ad/audio plus human identity truth.

Correct the evidence/design wording after the mic v3 work so item 2 is not conflated with mixer quality.

## New issue: 3–5 s word-to-screen delay

User reports hearing a word, then waiting roughly 3–5 s before it appears. Treat this as a real product-latency defect even though the streaming transcript is simulated/chunked.

Known seams—not yet a root-cause verdict:

- Deployed manifest: 16 kHz, `frame_samples=8000` (0.5 s ingress), `hard_cap_samples=40000` (2.5 s span), `min_silence_samples=8000` (0.5 s).
- Normal live canonical decodes in retained concurrency evidence are commonly about `0.1–0.3 s` for 2.5 s spans; the serial queue can add wait under load.
- React poller uses 250 ms while active: `frontend/src/api/mossPoller.ts`.
- Legacy served portal uses 500 ms: `moss_transcribe_diarize/app/live_portal.py`. Determine which UI/bundle the operator actually saw; never optimize an inactive reader.
- macOS already has `mtd-capture latency` and `CaptureLatencyProbe.swift`. It measures capture-to-committed p50/p95 plus an analytic portal render bound, but its committed-end measurement can hide the first word's wait inside a 2.5 s span.
- `canonical_processed` events already expose span duration, decode elapsed/RTF, token cap/capped status, and committed samples.

Diagnosis/prototype order:

1. Reproduce on the exact attended path. Run the existing latency report and preserve raw output; require at least its declared 20 committed advances.
2. Add diagnostic-only stage timestamps/ages where missing. On one capture clock report, at minimum:
   - first/last captured sample age when the span freezes
   - queue wait
   - decode time
   - commit-to-fetch
   - fetch-to-React-render
   - first-word/start-of-span age at actual render
   - last-word/end-of-span age at actual render
   Report p50/p95/max and sample counts. Do not call server/browser clocks comparable without a proved mapping.
3. Attribute the 3–5 s budget before changing knobs. Likely candidates are 2.5 s hard-cap accumulation, 0.5 s silence closure, serial queueing, decode, and reader cadence.
4. If span accumulation dominates, extend the standing prototype with a preregistered cap/silence sweep (candidate caps such as 0.75/1.0/1.5/2.0/2.5 s are experiments, not policy). Measure user-visible latency, WER/content recall, empty/unparseable rate, speaker/identity stability, request rate, queue depth, and capped-decode rate.
5. If decode/queue dominates, measure tunnel transit separately and preserve single-worker fairness/backpressure semantics. Do not disguise overload by dropping work or weakening 409/429 contracts.
6. If reader cadence dominates, fix only the actually served frontend and rebuild/verify the committed served bundle.
7. Choose the smallest measured change. Regenerate manifest hashes through `live_manifest_finalizer`; manifest values are not code constants.
8. Validate no regression in mic recovery, diarization, stop/drain, reconnect, two-user fairness, or transcript correctness.
9. Finish with a fresh M4 MacBook attended run. Compare before/after first-word and last-word p50/p95 plus the user's perceived delay. Ask the user for a final acceptance threshold only after the measured baseline/breakdown is available; do not invent one now.

## Verification discipline

- Use real GPU-host inference only through the read-only tunnel. This Mac must not load the model.
- Keep prototypes measured, one-command, and recorded in `NOTES.md`; absorb or delete throwaway code after verdict.
- Separate static tests, real-vLLM prototype evidence, deployed browser evidence, and attended acceptance.
- Preserve the two declared historical full-suite baseline failures from the original brief unless current live inspection proves the baseline changed.
- Before claiming done: inspect diff, run focused tests, full Python/frontend suites proportional to changes, rebuild frontend bundle if touched, validate generated manifest hashes, and prove the served/deployed revision.

## Suggested skills

- `$diagnose`: latency reproduction/attribution and any newly observed failure.
- `$prototype`: v3 scoring/gain sweep and latency-cap/silence experiments before production changes.
- `$tmux-peer`: read-only review of Claude/monitor state.
- `$tdd`: only once a measured production change is selected.

Do not begin by tuning thresholds. Begin with `/goal`, protect the dirty tree, reconcile any completed Claude sweep, then execute the measured plan above.
