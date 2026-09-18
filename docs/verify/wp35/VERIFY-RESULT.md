# WP35 VERIFY-RESULT — executed 2026-09-18

**Verdict: PASS**, with one honest caveat about how the verification was run (below).

Executed with `bash --noprofile --norc`, started from `/`, then `cd` into
`…-wt-wp35-stop-drain`. Branch `mvpfix/wp35-stop-drain`, SHA inspected
`b372e48d4ff2849ba9a9ce87752eea8a132521ac` (this file and step 5's correction are the only
commits after it). Python
`…-wt-auto-mvp-0911/.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`.
No GPU, no network, no tunnel, no stack, no push.

**Caveat on independence.** The contract asks for a fresh `/new` session; this agent has no
pane, so the substitute agreed in its brief was a new `bash --noprofile --norc` shell from
`/`. That gives a clean shell environment, not a clean *context* — the same agent wrote
VERIFY.md and ran it. Treat every number below as reproducible-by-command, not as
independently re-derived. VERIFY.md is written so a genuinely fresh reader can repeat it.

| Step | Command | Expected | Actual | Verdict |
|---|---|---|---|---|
| 1 | branch / HEAD / status / import source | clean tree, import inside this worktree | `mvpfix/wp35-stop-drain`, `b372e48d`, status empty, `…-wt-wp35-stop-drain/moss_transcribe_diarize/__init__.py` | PASS |
| 2 | `git diff integration/mvp-fix-20260917 HEAD -- moss_transcribe_diarize` | exactly 2 files | `app/live_service_runtime.py` +44, `concurrency_evidence.py` +11; 55 insertions, 0 deletions | PASS |
| 2 | forbidden-value grep | no output | grep exit 1 (no match) | PASS |
| 3 | full `pytest -q -p no:cacheprovider tests` | 1974 passed / 5 skipped / 37 subtests | **1974 passed, 5 skipped, 37 subtests passed**, 168.46 s, 0 failed | PASS |
| 4 | `npm --prefix frontend test -- --run` | 28 files / 271 tests | **28 files, 271 tests**, all passing | PASS |
| 4 | typecheck / build / status | exit 0, tree clean | `typecheck_exit=0`, `build_exit=0`, status empty (no asset moved) | PASS |
| 5 | red: revert `live_service_runtime.py` to the integration branch | 3 failed / 4 passed | **3 failed, 4 passed** — the three named tests | PASS |
| 5 | green: restore and re-run | 7 passed | **7 passed**, status empty after restore | PASS |
| 6 | stub evidence | see VERIFY.md | table below | PASS |
| 7 | `rescore.py` on the real run | see VERIFY.md | table below | PASS |
| 8 | `decoder.jsonl` | 1098 lines, `2 549` | **1098**, `2 549` | PASS |
| 9 | 18135 / 17835 listeners | none | both `lsof` exit 1 (empty) | PASS |

## Step 6 — stub bench, read back from the retained files

| Arm | all final | max Stop→outcome (s) | decoder requests after the first Stop | per session |
|---|---|---:|---|---|
| 1×600 before | true | 4.314 | canonical 1, rolling 1, terminal 1 | final, 1 rolling after Stop, terminal started, 9,600,000 accepted = accounted, 956 → 960 words |
| 1×600 after | true | **3.710** | canonical 1, terminal 1 | final, **0** rolling after Stop, terminal started, same accounting and words |
| 4×600 before | **false** | 600.035 (the cap) | canonical 4, **rolling 143** | 4/4 `not_started`, `stop_error` `LiveServiceStopPending`, 35 rolling admitted after Stop each, terminal started **false** 4/4, 9,600,000 accepted = accounted, 956 → 960 words |
| 4×600 after | **true** | **8.544** | canonical 4, terminal 4 | final 4/4 at 5.544 / 8.537 / 8.544 / 5.518 s, **0** rolling admitted after Stop, terminal started 4/4, 9,600,000 accepted = accounted, 952–956 → 960 words |

Falsifiers checked and not triggered: no after-arm session admitted a rolling window after
Stop; every after-arm session is `final`; no after-arm session ends with fewer words than its
before-arm counterpart (960 in every arm).

## Step 7 — real 4×300, re-scored offline

`decoder_calls` 549, `maximum_own_inflight` 2, `foreign_load_detected` false,
`clean_rescored` **true**, `clean_as_run` false (pre-repair scoring, `excluded_failures` names
`inference_evidence:rolling completion has a non-healthy terminal outcome`), pre-Stop RTF
**0.08040159975667241**.

| Session | outcome | Stop→final (s) | accepted = accounted = 4,800,000 | frames | rolling admitted after Stop | rolling completions after Stop | terminal started |
|---|---|---:|---|---:|---:|---|---|
| 1 | final | 32.443 | true | 1200 | 0 | `not_awaited` | true |
| 2 | final | 18.325 | true | 1200 | 0 | `not_awaited` | true |
| 3 | final | 35.355 | true | 1200 | 0 | `not_awaited` | true |
| 4 | final | 29.247 | true | 1200 | 0 | `not_awaited` | true |

## Deviations and limits recorded during this verification

1. **VERIFY.md step 5 was wrong on its first draft and was corrected before this result was
   written.** It said `git stash push <file>`; the fix is committed, so that stash was a
   no-op and the "red" run reported 7 passed — a false green dressed as a red. Step 5 now
   reverts the file to `integration/mvp-fix-20260917` instead, which produced the expected
   3 failed / 4 passed. No other step changed.
2. **No real 4×600.** 1,060 decoder requests > the 800 budget; 549 were spent on 4×300. The
   90 s campaign bar at 600 s on the real decoder is therefore **not** verified here.
3. The stub bench uses a deterministic voiceprint stand-in and prices a 600 s terminal lane
   at 3.0 s, so its Stop→final numbers are lower bounds on the real ones.
4. Real-run per-session WER is not comparable to `QUALITY_BOUNDS` (each session loops a
   50–180 s clip to fill 300 s; session 4's reference is partial and its `wer` is null).
5. Other agents' processes were running throughout (WP30 on 17890/18130). They were left
   alone; the campaign ran with `--allow-contention` and still observed no foreign load.
