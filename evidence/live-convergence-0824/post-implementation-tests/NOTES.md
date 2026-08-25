# Post-implementation tests (handoff-8YIE4C step 6) — 2026-08-25 ~12:39–13:10 EDT

Run AFTER the campaign completed (`df5e297`, loop run 20260825-042645-70858, complete at
iteration 35) against the deployed service pid 37488 (HEAD `22dc5b8` production code — no
`moss_transcribe_diarize/` change exists between `22dc5b8` and `df5e297`). Conducted by the
monitoring session, not the loop.

## 6a — Regression: the checked-in paired drivers vs the checked-in baseline

Commands (verbatim drivers, no edits):
`prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py` then
`remeasure_5m_case.py`, sequential, one in-flight vLLM request, 16:39–16:49Z.

- **File arms byte-identical to `prototypes/live-file-gap-baseline-20260824/` on 5/5 cases**
  (`cmp` on `file-hypothesis.jsonl`: bill, milei, keyu-1m, jamie(acq), keyu-5m). The hard
  regression check of the handoff: file mode did not move across the campaign's fifteen
  production changes.
- Live arms (now terminal, via iteration 28's finalization wait): **equal to the paired file
  arm on every metric and every case** — bill .1591/.0755, milei .0880/.1518, keyu
  .0647/.0790 (WER/DER; spk_acc .9245/.8482/.9210), 5-min .0506/.0579/.9421. Segment-level
  speaker+text content identical live-vs-file on all three primaries.
- Known wall reproduced: the trio driver exits 1 at `acquired_nfl` (empty reference text,
  record 6) after every scored case is written — same wall as the 2026-08-24 baseline run.
- Artifacts: `regression-trio-results.json`, `regression-5m-results.json`, consoles.

## 6b — Stress: back-to-back live sessions

Three consecutive live replays of `lex_bill_ackman` through one harness
(`--runs 3`, pace 1.0, deployed service):

- 3/3 `status=succeeded`, accepted == accounted == 960000 samples each.
- 3/3 `finalization_status=final`, `finalization_waited=true` (async terminal lifecycle).
- Published surfaces hash-identical across all three runs.
- Complements the campaign's own M2 5-minute soak (G-M2-5 artifacts in `M2-e2-exit/`).
- Artifacts: `stress-run{1,2,3}-summary.json`.

## 6c — Remote client: live replay from m4mbp over real network transport

Campaign code (`df5e297` via git bundle → worktree `/tmp/rlc-wt` on m4mbp, module resolution
verified) driving `https://macstudio.tailnet.aisight.us:7861` (tailscale **direct** path,
15 ms RTT, self-signed TLS + bearer): `lex_javier_milei`, 2 runs, pace 1.0.

- Both runs `succeeded`, exact accounting, `finalization_status=final`.
- Scored on MacStudio with the checked-in driver's own scorer: **WER .0880 / TBSA .8812 /
  DER .1518 / spk_acc .8482 on both runs — identical to the local file arm and local live
  arm.** Real network transport changed nothing about the surface.
- **Transport finding (honest, recorded):** with the client's default `--max-pacing-lag 1.0`
  the first attempt ABORTED at ~30 s (lag 2.82 s): at 10 fps synchronous HTTPS posts, WAN
  per-frame overhead accumulates monotonically (no catch-up), so the default bound is not
  achievable from this client over this path even at 15 ms RTT. Rerun with
  `--max-pacing-lag 10` succeeded. The aborted run also gave the service an unplanned
  mid-meeting client-abort test: it failed the session cleanly with honest accounting
  (accepted 488000 / accounted 466240 at abort). If remote live capture becomes a product
  path, frame batching or connection reuse is the lever — a client concern, not a service one.
- Artifacts: `m4mbp-remote-run{1,2}-summary.json`.

## Verdict

Every step-6 check passes: file mode byte-stable, live == file through the deployed service
from both machines, repeated sessions stable and deterministic, async finalization holds
under stress and over real transport. One client-side pacing default documented for remote
WAN use.
