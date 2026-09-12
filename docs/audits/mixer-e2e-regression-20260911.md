# Mixer repair browser regression — 2026-09-11

**Combined requested run: 9/10 PASS. Row 14 changed from the previous 14/14 run, but its failure reproduces on the pre-mixer commit. Row 14 alone passes all three meetings on the repaired candidate. No product changes.**

## F1 — custody and scope

Fresh isolated stack, `https://127.0.0.1:17863`, product head `3d1e2b8a`, configured MacStudio/RTX4090 relay and `--live-draft-lane-seconds 1.0`. Separate state/control paths under `/tmp/moss-mixer-regression-20260911`; existing decoder tunnel `127.0.0.1:18000`. No operator 17861 database or host operations. The later `f8e66aeb` adds only optional-browser regression tests and evidence.

Real Chromium, corpus `evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s`, actual microphone fixture and tab audio. File rows 2/3, summary row 9 and recognition row 10 were not run. Two temporary runner adaptations allow the requested subset: row 7 uses the completed live recording and compares MP3 duration to accepted PCM samples / 16000 (same 5 percent duration tolerance); row 8 starts its own capture instead of requiring row 10. These are preserved as patches; product and committed harness remain unchanged. Row 7 therefore qualifies live audio export, not file-mode export.

## F2 — requested row results

| Row | Check | Result | Evidence / observation |
|---|---|---|---|
| 1 | Fresh workspace | PASS | Signed in, boot ready |
| 4 | Mic + tab capture | PASS | First text 2.318 s; Stop to completed 2.071 s |
| 5 | Rename and enrollment acknowledgement | PASS | Both names update rows/history; final name in export |
| 6 | Transcript exports | PASS | Five formats, nonempty; SRT/VTT valid ordered cues |
| 7 | Audio download | PASS | Decodable MP3; 18.000 s matches 18.000 s accepted PCM |
| 8 | Owner interruption | PASS | Interrupted history item, playable 11.904 s partial MP3 |
| 11 | History selection | PASS | Correct title and Live mode |
| 12 | Phone width | PASS | 400 px viewport and 400 px content width |
| 13 | Network recovery | PASS | 3 s and 20 s outages survive; both completed/final; frame sequences continuous |
| 14 | Consecutive same-tab meetings | FAIL in combined run | First cycle blocked before admission: disabled Listening setup; passes independently with three completed/final meetings |

Results, screenshots, downloaded exports/audio and network traces: [combined — removed; inventory](content-boundary-files-20260912.json), [independent row 14](../../evidence/mixer-e2e-regression-20260911/row14-alone/results.json). Browser cookies are excluded from committed evidence.

## F3 — failure attribution

The combined run fails at `setup_live`, `tests/e2e/verify_workspace.py:175–178`: it checks whether Reset capture exists once, then selects Listening setup. Row 13 waits for the server meeting to complete (`:518`) but does not wait for the capture UI's terminal phase. If the UI still shows stopping, Reset is absent. The subsequent select remains disabled even after terminal arrives because Reset was never clicked. The 12-second locator timeout is retained.

A fresh detached **pre-mixer `cf0dc398`** stack on isolated port 17864 reproduces the identical 13→14 failure. Its instrumented setup records `phase=stopping`, `reset_count=0`, then still `stopping` after the skipped reset. Thus this is not introduced by mixer repair `905eadbb` or its differential-evidence commit `3d1e2b8a`. The conditional reset originates in `2b5eb340d`; row 13's server-only finalization wait originates in `ad059be5e`. This identifies the existing code interaction, not a claim that every execution of either commit fails.

The unchanged ControlPanel intentionally disables Listening setup during stopping/terminal (`frontend/src/components/ControlPanel.tsx:340`) and only exposes Reset in terminal/error (`:397`). Row 14 itself waits for UI terminal after each of its own stops (`verify_workspace.py:571`), which explains why the independent three-cycle test succeeds.

Baseline evidence: [results](../../evidence/mixer-e2e-regression-20260911/baseline-transition/results.json), [phase/reset trace](../../evidence/mixer-e2e-regression-20260911/baseline-transition/network.jsonl). Minimal runner proposal: when setup enters during stopping, wait for the existing terminal phase before checking Reset. Preserve all capture/decoder assertions; do not reload, force-enable controls or change product behavior.


## F4 — measured runner-only intervention

On the repaired candidate, a temporary runner adds only a conditional wait for `[data-capture-phase=terminal]` when setup sees `stopping`, using the same 30-second terminal deadline already used inside row 14. Then it executes the normal Reset click. **Rows 13 and 14 both PASS**: both outages survive and all three consecutive meetings complete/finalize, remain in history, and export the correct current transcript. Trace shows terminal/Reset present → idle on every cycle. [Results](../../evidence/mixer-e2e-regression-20260911/settled-transition/results.json), [temporary patch — removed; inventory](content-boundary-files-20260912.json).

No new mixer regression demonstrated. Preserve the original combined 9/10 result; do not relabel it 10/10. The independent row-14 PASS and 13→14 intervention PASS qualify the underlying behavior and isolate the existing harness handoff gap. The nine other requested rows retained PASS versus the previous 14/14 run. No product code or committed harness changes were made. Test instance state and full local logs remain under `/tmp/moss-mixer-regression-20260911`; only owned stack processes were stopped after measurement.
