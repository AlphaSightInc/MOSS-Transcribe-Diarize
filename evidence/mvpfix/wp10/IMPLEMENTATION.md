# WP10 — relocating the all-zero span guard

Branch `mvpfix/wp10-zero-guard-seams`, from `integration/mvp-fix-20260917` @ `79467f08`.
Python: `…-wt-auto-mvp-0911/.venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`,
cwd = this worktree (`moss_transcribe_diarize.__file__` resolves inside it). No decoder,
no tunnel, no shared service, no network.

## Reproduction (before)

```
python -m pytest -q -p no:cacheprovider \
  tests/test_live_pipeline_seams.py tests/phase2/test_draft_lane.py \
  tests/phase2/test_runner_composition.py tests/test_live_rolling_wiring.py \
  tests/test_live_service_replay.py
→ 19 failed, 128 passed, 9 subtests passed
```

Full suite at the same commit: **19 failed, 1764 passed, 2 skipped, 37 subtests passed**
(`test_voiceprint_latency_measurement` already green — WP4 is merged here).

Reverting only WP3's two guards (`live_adapters.py` `if not any(pcm)` and
`live_transcript_convergence.py` `if not any(pcm)`) on the same commit leaves
**4 failed, 183 passed** over those five files plus WP3's two guard files: the three WP3 guard
assertions, and `test_reader_retires_draft_by_audio_boundary[multiple]`. That last one
therefore is **not** a zero-guard regression; see `prototypes/zero-guard-seams/NOTES.md` §2.

## Candidate matrix

See `prototypes/zero-guard-seams/NOTES.md` for the verdict and the per-test reasoning.
Raw logs here: `c{1,2,3}-*-seams.log`, `c{1,2,3}-*-guards.log`, `c{1,2,3}-*-falsify.log`,
plus `c1-dispatch-falsify.json` (machine-readable requirement results).

| candidate | seams (147) | WP3 guards | requirements R1–R8 |
|---|---|---|---|
| 1 — dispatch guard | 146 / 1 pre-existing | 40/40 | 7/7 |
| 2 — mixer `silent` provenance | 146 / 1 pre-existing | 37/40 | 3/7 |
| 3 — guard in the decode seam (WP3 as merged) | 128 / **19** | 40/40 | 7/7 |

## After

```
python -m pytest -q -p no:cacheprovider tests
→ 1792 passed, 2 skipped, 21 warnings, 37 subtests passed   (full-suite-after.log)

npm --prefix frontend test -- --run
→ 26 files, 230 tests passed                                 (frontend-test.log)

npm --prefix frontend run typecheck
→ clean                                                      (frontend-typecheck.log)
```

Delta vs the baseline: −19 failures, +9 tests (`tests/test_live_zero_span_dispatch.py`).
No frontend source changed, so `moss_transcribe_diarize/app/frontend_assets/*` is untouched
and no rebuild was needed.

## Measurements

No new hand-tuned constant was introduced. The one threshold in the change is exact equality
with zero, which is WP3's own measured line (`evidence/mvpfix/wp3/`: energy-based suppression
falsified at 99% explained playback energy on real quiet local speech, so one nonzero
least-significant bit must still decode). `is_digital_silence` counts rather than iterates
because it is asked about a whole meeting's tape on the stop path; `CompleteMixedTape` answers
from a flag set as audio arrives, so the terminal pass performs no second scan.

## Deviations from COMMON.md

* The prototype is the harness the WP10 brief specifies (candidate branches + a requirements
  falsifier) rather than the interactive TUI the `prototype` skill's LOGIC branch describes.
  Both halves print full state after every step and run from one command, and the verdict is
  in `NOTES.md` beside them.
* `/new` fresh-context verification was replaced, per this agent's instructions, by executing
  `VERIFY.md` in a new shell from a clean cwd; result in `VERIFY-RESULT.md`.
* `frontend/node_modules` is the symlink COMMON.md prescribes (needed to run `tests/phase2`,
  which shells out to node).
