# Handoff — live-mode convergence campaign: amend, review, launch, steer, test, benchmark

Written 2026-08-25 ~00:50 EDT (session of 2026-08-24). Read this top-to-bottom before acting.
The owner's grand plan below is binding — follow it exactly and in order.

## The grand plan (owner's words, binding)

1. Thoroughly update the ralph loop afk.
2. Then use `/codex:adversarial-review` to review and finalize the ralph loop afk.
3. Git commit and ensure worktree clean.
4. Launch the ralph loop afk in terminal in tmux pane 2.1 (currently in the folder
   `~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`).
5. Post launch, monitor the ralph loop afk and steer it as necessary.
6. Post implementation, conduct thorough testing — stress tests and regression tests using
   real audio files (≤ 5-minute clips), live-mode AND file-mode, from both `gao@macstudio`
   (this computer) and from `ga0@m4mbp`.
7. Post implementation, benchmark accuracy and latency on real audio against two projects on
   `ga0@m4mbp`: `~/Desktop/AI_Projects/LiveTranscribe` and
   `~/Desktop/AI_Projects/Github_Projects/ProjectClerk`.

## Where everything already lives (do not re-derive; do not duplicate)

- **The spec**: `docs/plans/live-mode-convergence-implementation-20260824.md` — 1,400+ lines,
  cross-reviewed to convergence (session `xr-20260824-201035`, 4 rounds, archived under
  `.aisight/xreview/`). **Appendix B = owner decisions and OVERRIDES the body** (≤5-min
  corpora, 2.5 s cap parameterized / 1 s deleted, ADR + tape retention pre-accepted, all
  phases conditionally pre-authorized, local-service restart grants). **Appendix A** = runbook
  (stack endpoints, bearer token, code map, corpora, bench commands).
- **The campaign**: `scripts/ralph-live-convergence/` — `prd.md` (milestone ladder M0–M5 =
  plan E0–E4 + evidence), `context.md` (living state), `progress.txt` (journal),
  `preflight.sh`, engine `ralph-afk.sh` (template: `~/Desktop/AI_Projects/AAgent/0.templates/ralph-loop-afk`).
  Branch: `ralph/live-convergence-0824`. Telemetry per run under
  `scripts/ralph-live-convergence/telemetry/`.
- **Baseline + root-cause evidence**: `prototypes/live-file-gap-baseline-20260824/` (paired
  trio + 5-min metrics, drivers, traces) and `prototypes/live-file-gap-{context,emptyspan,identity,timing}/NOTES.md`.
  Campaign evidence accumulates under `evidence/live-convergence-0824/`.
- **Session memory**: `~/.claude/projects/...MOSS-Transcribe-Diarize/memory/live-file-gap-investigation.md`
  (root causes, stale-clone warning, campaign pointers).
- Peer codex session lives in tmux `MOSS:1.2` (plan author; cross-review partner).

## State at handoff (verify before touching anything)

- Campaign ran 1 full iteration (run `20260825-030106-23237`, opus agents): **M0a CLOSED** —
  replay reconstructors fixed (3 dropped fields, incl. `live_protocol` the analysis missed),
  tripwire test added, evidence in `evidence/live-convergence-0824/M0a-replay-roundtrip/`.
- **The loop is STOPPED — confirmed clean** (2026-08-25 ~00:55 EDT): engine exited 0
  "stopped before iteration 3", lock released, journal marker written, worktree clean.
  Iteration 2 completed and committed **M0b** (typed decode disposition reaches the trace —
  commits `1842782` + checkpoint `bac8e7c`; log:
  `scripts/ralph-live-convergence/telemetry/run-20260825-030106-23237/iter-002.log`).
  So **M0a and M0b are CLOSED**; the ladder resumes at M0c (evaluator v2), and the loop's own
  journal notes: restart `web_cli` onto the campaign branch before M0d (not before M0c).
- Remove `.stop` only right before relaunching (step 4).

## Step 1 — the amendment set (audited gaps; this list exists ONLY here)

These six changes make the setup fully faithful to the plan. Amend `prd.md` and the plan's
Appendix B; gates may be amended now because only M0a is closed and none of the affected
milestones has started. Record the amendment in `progress.txt` as an owner-directed,
pre-M1 setup change (append-only; do not rewrite history).

1. **Plan Appendix B: add the G4 rescope** (most important — prevents a false PRD-vs-plan
   conflict STOP at M3). Deleting the 1 s preview orphaned G4's comparator ("corrected 1 s
   within 2 points of corrected 2.5 s"). Record the replacement officially: M3 speaker gates
   are trio mean DER ≤ .1393 with no per-case regression vs baseline live (bill .2235 /
   milei .1945 / keyu .1112), trio mean speaker_accuracy ≥ .8437, 5-min-case DER ≤ .0947,
   derivation: half-gap recovery + the measured identity ceiling
   (`prototypes/live-file-gap-identity/NOTES.md`).
2. **prd.md M1 additions**: parse → render → parse fixed point on every salvaged span; the
   §9.1 O1-vs-O2 gating comparison (hard-cap+grammar vs recomputed-VAD-ratio; prefer O1 if it
   matches O2 on the full corpus); "speaker identity preparation receives only intervals the
   salvager actually emitted."
3. **prd.md M2 additions**: the §10.5 step-7 export switch (exports stay on current commits
   until terminal/effective export tests pass, then switch once in the same reviewed change);
   the 5-minute soak (Appendix B's rescope of the 30-minute soak); name the headless portal
   render/serialization test as the in-loop substitute for the attended browser E2E (which is
   a morning item).
4. **prd.md M3 addition**: §11.2's "added WeSpeaker cost stays within the real-time budget"
   (combined base + rolling + WeSpeaker RTF < 1 under the rescoped single-session G7).
5. **prd.md M4 additions**: terminal speaker quality — terminal DER within .02 absolute of
   the paired file arm per case (mirrors G8's spirit; §12.3 step 5 resolves terminal
   identities but M4 only gated WER) — and §12.2's cold/warm model-readiness reporting.
6. **progress.txt**: append the amendment entry (what changed, why, "owner-directed pre-M1").

Also propagate 1–5 into `context.md` only where its Candidates/Non-candidates would otherwise
contradict the amended PRD (context.md is the loop's living file — light touch).

## Step 2 — adversarial review

The owner named `/codex:adversarial-review`. If that exact skill is not in your skill list,
do NOT silently substitute: the proven equivalents in this repo are `/aisight-xreview --start
--mode plan --target "scripts/ralph-live-convergence/prd.md scripts/ralph-live-convergence/context.md"`
(codex peer, converged in 4 rounds on the plan earlier tonight) or the codex plugin's review
entry point — state which you used and why. Review scope: the campaign setup files against
the plan + Appendix B (fidelity) and against the ralph template's anti-drift rules (craft).

## Step 3 — commit

One amendment commit (setup files + plan Appendix B + any review edits), message explaining
the amendment; then `git status` must be clean. Stay on `ralph/live-convergence-0824`; never push.

## Step 4 — launch in tmux pane 2.1

Pane `MOSS:2.1` is a zsh in the repo root. Launch visibly there (fresh 40-iteration budget;
the engine's run lock prevents double-launch; remove `.stop` first):

```bash
tmux send-keys -t MOSS:2.1 "cd ~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize && rm -f scripts/ralph-live-convergence/.stop && RALPH_MODEL=opus RALPH_PREFLIGHT_CMD='bash scripts/ralph-live-convergence/preflight.sh' RALPH_PREFLIGHT_REQUIRED=0 ./scripts/ralph-live-convergence/ralph-afk.sh 40" Enter
```

## Step 5 — monitor and steer

- Watch `progress.txt` (journal), `context.md` (current state), and
  `telemetry/run-*/iter-*.log` (full agent logs). `tmux capture-pane -t MOSS:2.1 -p | tail`
  shows the engine banner between iterations.
- Steering levers, in order of preference: edit `context.md` Candidates/Non-candidates
  BETWEEN iterations (the next fresh agent reads it); append guidance to `progress.txt`;
  `.stop` for a clean pause. NEVER edit `prd.md` gates for a milestone already in progress;
  never edit mid-iteration (checkpoint commits sweep the whole tree).
- Red flags that warrant a pause: gate-tuning language in the journal, audio > 5 min, edits
  outside the campaign branch, touching the 4070 Ti host, TBSA-only claims of improvement
  (the extent-artifact trap — WER + content recall are the honest text metrics; see plan §3.4).
- Expect M0–M1 to close quickly; M2 (rolling convergence) is the long pole; a stall of 3
  commit-less iterations stops the loop by design — read the last telemetry log before
  relaunching.

## Step 6 — post-implementation testing (≤5-min real audio, live + file, two clients)

- Corpora (golden, fully referenced): 1-min trio, `calibration_diarization_3min/samples/lex_adam_frank`,
  `benchmark_5m/lex_keyu_jin` (all under `prototypes/streaming-diarization/data/real/`).
  `acquired_*` 1-min refs are partial — diagnostic only.
- From **macstudio**: the checked-in paired drivers
  (`prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py` and
  `remeasure_5m_case.py`) are the regression harness — diff against the checked-in baseline
  (file arms byte-identical pre/post campaign is a hard regression check). Stress: repeated
  back-to-back live replays + the M2 5-minute soak artifacts.
- From **m4mbp** (`ssh ga0@m4mbp`, BatchMode works): client-side tests hit the MacStudio
  service at `https://macstudio.tailnet.aisight.us:7861` (self-signed TLS; bearer token —
  Appendix A). Precedent for a real attended live run from m4mbp:
  `scripts/ralph-afk/live-cert.sh` (real-corpus mode, `afplay` playback, needs the mtd-capture
  app + TCC) with reducer `scripts/ralph-afk/live-canary-clauses.py`. A lighter remote test:
  run `live_service_replay` ON m4mbp against the MacStudio URL (adds real network transport).
- Score everything with the repo evaluators (`evaluation.py`, `live_speaker_accuracy.py`,
  plus evaluator v2 once M0c lands). Report WER/recall as primary, TBSA/DER beside.

## Step 7 — benchmark vs LiveTranscribe and ProjectClerk (both on m4mbp)

- **Access**: read-only SSH `ga0@m4mbp`. WARNING: the LOCAL MacStudio clone of LiveTranscribe
  (`/Users/gao/Desktop/AI_Projects/LiveTranscribe`) is STALE (newest ref 2026-06-17) — the
  authoritative repo is on m4mbp (`HEAD 6a8d0c1`, 2026-08-11). Never cite the stale clone.
- **LiveTranscribe** (Whisper-based live transcription, same golden-corpus lineage): its live
  pipeline, refined-live overlay (RLO), and OSF five-phase machinery are real on m4mbp
  (`Sources/Session/Live/RefinedLive*`, ADR-0029,
  `docs/evidence/overlap-stability-perturbation-0806/REPORT.md`). It computes TBSA/spk-acc
  itself; align scoring by running BOTH systems' outputs through THIS repo's evaluator on the
  same ≤5-min corpora. Latency comparison: use the plan's G5/G6 clock definitions (first-word
  age; correction age) — LiveTranscribe has measured analogues (provisional ≈1.16 s,
  canonical ≈4.9 s, per its docs).
- **ProjectClerk** (`~/Desktop/AI_Projects/Github_Projects/ProjectClerk` on m4mbp): UNKNOWN to
  this session — explore it first over SSH (read its README/AGENTS/docs; find how it
  transcribes, whether it has live mode, how to run one file through it), then design the
  minimal fair comparison (same audio, same reference, this repo's evaluator; document any
  incomparability honestly rather than forcing numbers).
- Deliverable: a benchmark report (accuracy table per case per system per mode + latency
  table + provenance) under `evidence/live-convergence-0824/benchmark/`, plus a published
  artifact if substantial.

## Hard rails (unchanged, from Appendix B)

4070 Ti host read-only (vLLM endpoint only); no pushes; campaign branch only; ≤5-min audio;
one in-flight vLLM request per harness; quiet GPU for certification numbers; embeddings never
from context audio; file mode byte-identical after every change.

## Suggested skills for the next session

`/tmux-peer` (read codex pane MOSS:1.2), `/aisight-xreview` (step 2 fallback / later reviews),
`/diagnose` + `/prototype` (any gate failure or benchmark anomaly), `/codex:rescue` (second
opinion), memory recall is automatic (`live-file-gap-investigation` has the pointers).
