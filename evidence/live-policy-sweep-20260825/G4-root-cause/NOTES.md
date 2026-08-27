# G4 addendum — the Jamie eviction is root-caused (monitoring session, 2026-08-25 ~17:00 EDT)

Codex's sweep left G4 as "fix/measure the production `pcm_evicted` path." This addendum
closes the diagnosis with two probes. It changes how the sweep's headline table should be
read, and it names a small fix with existing precedent. No production code was changed.

## The mechanism, three levels down (all reproduced, N=3 sessions + 1 offline probe)

1. **The model emits overlapping different-speaker extents inside one window.** A fresh
   greedy decode of Jamie window 4 exactly ([640000,800000)) yields
   `[0.00–0.98] S01 "Incredible."` then `[0.81–9.97] S02 "So the question…"` — a
   2720-sample (0.17 s) overlap, deterministic (probe-output.txt; matches both sweep passes
   refusing at identical seq).
2. **Rolling proposals are never normalized.** `LiveSession._text_revision_refusal`
   (`live_session.py:827`) rejects the whole proposal `segments_out_of_order`. Iteration 31
   shipped exactly the needed normalizer for the TERMINAL path
   (`resolve_terminal_overlaps`); rolling never got it. Applied offline to this proposal it
   displaces 0.17 s per the measured rule, merges 0, drops 0, **loses 0 of 24 words**, and
   the result is admissible.
3. **One refusal forfeits the meeting.** Only an *applied* revision advances the frontier
   (`live_coordinator.py:863`); a refused window stalls planning, PCM overflows the
   2×window ring, `PCM_EVICTED` fires, and the converger stops for the rest of the meeting
   (rolling authority ended at ~40 s of 180 s). Terminal finalization still rescues at stop.

**Not contention:** quiet-GPU rerun (this dir: `quiet-gpu-jamie-trace.jsonl`) reproduces the
identical sequence with canonical decode RTF p95 **0.359**; both sweep passes had p95
.35–.40. G2's separate RTF spikes are unrelated to G4.

## What this does to the sweep's headline table

The 10/10 column ran through the deployed service; the 15/10 columns are quiet-GPU shadows
that (a) never faced the refusal predicate and (b) covered audio the deployed 10/10 lost to
eviction. Per-case pre-Stop-settled WER, pass A:

| case | deployed 10/10 | shadow 15/10 lex | gap | 10/10 rolling state |
|---|---:|---:|---:|---|
| mono_javier_50s | .1593 | .0973 | +.062 | full clip (RTF-flagged session) |
| bill_ackman_60s | .2045 | .1705 | +.034 | full clip |
| keyu_jin_60s | .1151 | .0863 | +.029 | full clip |
| adam_frank_180s | .1337 | .1375 | **−.004** | full clip — 10/10 wins |
| jamie_180s | .1185 | .0714 | +.047 | **evicted @~40 s** |
| rtfl_90s | .1359 | .0874 | +.049 | full clip |

The macro .1445→.1084 gap is therefore part geometry, part bug: jamie's row compares a
crippled 10/10 to an uncrippled shadow, and deployed 15/10 would hit the *same* refusal
class on the same audio without the fix. The honest arm comparison exists only post-fix.

## Fix shape (small; both halves have shipped precedent + tests to mirror)

- **F-A**: normalize rolling proposals with the terminal resolver (or a rolling twin of it)
  before `apply_text_revision` — removes the known refusal class at zero word cost.
- **F-B**: on a contract-violation refusal, advance the frontier past the refused window
  (accounted, evented) instead of stalling to eviction — caps any future refusal's cost at
  one window, not the meeting.

After F-A/F-B, remeasure deployed 10/10 on this 6-clip corpus before any arm decision:
jamie (and any dense clip) improves for free, shrinking the true 15/10 delta.

## Files

`probe_jamie_w4.py` + `probe-output.txt` (window-4 decode, disorder, resolver
admissibility); `quiet-gpu-jamie-trace.jsonl` + `quiet-gpu-jamie-summary.json` (fresh
deployed session, third reproduction). Sweep originals under `../moss/pass-{A,B}/discussion_jamie_dimon_180s/`.
