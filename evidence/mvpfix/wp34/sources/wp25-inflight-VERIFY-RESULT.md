# WP25 fresh-context verification — 2026-09-18

Run in progress; final measurements will replace this paragraph before commit.

## Identity and scope

Fresh session began in `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp25-qualify-run`, branch `mvpfix/wp25-qualify-run`, HEAD `1dd59f66e4a9d1a24db44cf53cb961223d59755c`, clean. Candidate `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`; measured harness `ab4744511b415455551761ad116db0801370561d`. `git diff --exit-code ab4744511b41 HEAD -- scripts tools/qualify prototypes` passed. The prescribed Python import resolved to this worktree's `moss_transcribe_diarize/__init__.py`.

Read VERIFY.md, COMMON.md, execution-plan sections 1–2, local AGENTS.md, and required prototype skill. Existing prototype verdict retained: parameter isolation supported by 4/4 dependency witnesses, 2/2 real 60-second mono inputs, HTTP budget control 200/200/429. No new algorithm, production code, benchmark predicate, threshold, or policy.

## Commands and authorization change

Initial user cap 400 superseded VERIFY.md's 2000:

```sh
bash scripts/mvpfix-qualify.sh --budget 400 --compare evidence/mvpfix/wp25/ab4744511b41-20260918T073411045029Z/summary.json --out evidence/mvpfix/wp25/fresh
```

While static pytest was running, user raised the short-run cap to 900. Sent SIGTERM to owned runner PID 29154; its finally block stopped owned pytest and emitted teardown PASS and BUNDLE. No decoder request occurred. Retained interrupted attempt `fresh/1dd59f66e4a9-20260918T084323167672Z`; runner FAIL/remaining gates UNRUNNABLE indicate interruption, not product observations. This was a user-directed budget restart, not a retry to chase a result.

```sh
bash scripts/mvpfix-qualify.sh --budget 900 --compare evidence/mvpfix/wp25/ab4744511b41-20260918T073411045029Z/summary.json --out evidence/mvpfix/wp25/fresh
```

The completed-run target is `fresh/1dd59f66e4a9-20260918T084357230876Z`. Both commands omit `--long`. Console remains ignored in `.wp25runtime/fresh-console.raw` and `.wp25runtime/fresh-400-interrupted-console.raw`.

Deviation: interrupted evidence was retained uncommitted before restart; therefore the second start's `tree_clean` gate truthfully fails on only `?? evidence/mvpfix/wp25/fresh/`. It should have been committed before restart. Do not call the new run clean-start or exact-SHA determinism; do not suppress this delta. Source was unchanged. No further live rerun.

## F3 — capacity timeout adjudication from retained long-run data

The 90-second limit is the campaign's wall-clock limit from immediately before POST Stop through the Stop response and subsequent polling. POST uses `deadline:30`; production continues draining after its 30-second caller wait. The campaign checks elapsed >90 after each observation, then raises `finalization_timeout_90s` and aborts. It does not wait 90 seconds after a terminal decode starts. Poll overhead can exceed 90; exact timeout timestamps were not retained.

| Session | Stop monotonic seconds | Stop→final | Last timed event after Stop | Rolling admitted/completed | Terminal starts |
|---|---:|---|---:|---:|---:|
| 1 | 105022.749654500 | unmeasured; no final by >90 s | 84.063235 s | 30/29 | 0 |
| 2 | 105022.753155833 | unmeasured; no final by >90 s | 89.445280 s | 31/30 | 0 |
| 3 | 105022.759615875 | unmeasured; no final by >90 s | 87.708519 s | 5/4 | 0 |
| 4 | 105022.753058625 | unmeasured; no final by >90 s | 85.880724 s | 22/21 | 0 |

All four retained streams have finalization `not_started`, zero terminal events and zero session-closed events. Canonical/rolling work is serial across sessions via the single canonical pump. Stop waits for both before creating a terminal plan. Thus **zero terminal requests in the observed campaign**, inferred from the event-before-dispatch code contract and absent terminal-start events; request logs do not independently tag terminal/lane. There were 64 decoder starts after the first Stop, 1107 total, peak one in capacity. Those post-Stop calls must not be called terminal calls. Each session still had one unmatched admitted rolling window at its final observation.

Terminal architecture itself is one thread per session, then up to two lane jobs per session, bounded by the owned two-request proxy. It is not a serialized four-sessions-times-two-lanes terminal path. That path was never reached here. The observed failure is drain not finishing before the campaign limit; no exact counterfactual terminal latency or performance cause is established.

Microphone frames were `bytes(fb)` with `silent=True` throughout. Canonical and rolling lane decoders skip zero PCM. The terminal decoder also has a zero-lane skip, but was never reached. This campaign therefore provides four voiced system lanes, not eight voiced lanes. Each session accepted/accounted 9,600,000 timeline samples and acknowledged 2400 lane frames; zero mic content does not remove frame accounting.

Source: `prototypes/capacity-campaign/run.py:331,367–437`; `moss_transcribe_diarize/app/live_service_runtime.py:464,900–996,1471–1490,1533–1605`; `moss_transcribe_diarize/app/live_lane_decode.py:35,204–214,252–255,310–315`. Safe numeric/event-count projection: `evidence/mvpfix/wp25/fresh/capacity-adjudication.json`. Original long capacity FAIL 0/4 remains unchanged. Saved-final WER, final lag, and complete pre-stop real-time factor remain unmeasured.

## F1 — live quality, unchanged bars

WER (word error rate) = substitutions + omissions + additions divided by reference words. System denominator 106; microphone 53. Immediate bar <=0.166655; final and reopened <=0.095074. Lower is better. Mic amplitude gain remains 0.03, not 0.316.

| Run / invocation / case | Immediate system / mic | Final = reopened system / mic |
|---|---|---|
| Long / workspace_row_4 / alternation | 0.150943 / 0.207547 | 0.103774 / 0.094340 |
| Long / workspace_row_4 / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Long / demo_lanes / alternation | 0.150943 / 0.207547 | 0.084906 / 0.094340 |
| Long / demo_lanes / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Fresh / workspace_row_4 / alternation | 0.141509 / 0.207547 | 0.084906 / 0.094340 |
| Fresh / workspace_row_4 / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |
| Fresh / demo_lanes / alternation | 0.150943 / 0.207547 | 0.084906 / 0.094340 |
| Fresh / demo_lanes / overlap | 0.216981 / 0.113208 | 0.122642 / 0.094340 |

Fresh first text 3.330545s <=4s (long 3.328802s); row-4 base-session Stop→terminal 2.050827s. Every lane case reaches final. All attribution, duplication, and unresolved-word counts are zero. Failure remains ordered word accuracy: alternation mic immediate and overlap system immediate/final. Long workspace alternation system final also failed; fresh improves to passing, without changing the aggregate gate. Do not claim numeric determinism or infer decoder causation.
