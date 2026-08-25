# M4 precondition P-M4-A — the three-minute comparator, acquired

Campaign iteration 23, 2026-08-25. **No production file was touched. Zero production behaviour
changed.** Two warm-decoder paired passes of `calibration_diarization_3min/samples/lex_adam_frank`
(180 s) against the deployed service, so plan §12.2's five gated cases all have a comparator for
the first time in this campaign.

Artefacts:

| file | what it is |
|---|---|
| `passes/adam3m-A/`, `passes/adam3m-B/` | the two paired passes, in the layout `verify_m2_exit.case_paths` reads (`results.json`, both hypotheses, `live/run-001/{trace.jsonl.gz,summary.json,evaluator.jsonl}`) |
| `passes/runner.txt` | the warm-decoder protocol log: warm-up, pass, warm-up, pass, all exit 0 |
| `m4-baseline.json` | the full M4 comparator table, now with five measured cases |
| `console.txt` | `measure_m4_baseline.py` exit 0 against this bundle — `MISSING COMPARATOR: none` |
| `selftest.txt` | both instruments' self-tests, 0 failures |
| `pytest-full.txt` | the suite, unchanged by this iteration |
| `sha256.txt` | digests of everything above; `shasum -a 256 -c` from the repo root verifies the bundle |

## 1. The headline

`lex_adam_frank` is the **only case in the corpus where the live rolling surface is better than
the paired file arm on text**: rolling WER `.122411` against file `.126177`. Every other case has
the file arm ahead by `.008` to `.045`.

That single fact does three things to M4, and all three are consequences of bounds that were
fixed in `PREREGISTRATION-M4.md` **before** this pass existed:

1. **G-M4-1 is already inside on this case** — `|.126177 - .122411| = .003766` against a `.010`
   tolerance. That is the *third* of ten convergence readings a build that ships nothing passes
   (F1 of the preregistration predicted two, over the four cases that then had a comparator).
2. **G-M4-3 and prediction P1 are now mutually exclusive here.** G-M4-3 binds terminal WER at
   "that pass's own rolling arm", which this pass fixes at `.122411`. P1 predicts terminal equals
   the file arm exactly, i.e. `.126177`. If P1 holds, **G-M4-3 fails on `lex_adam_frank` by
   `.003766`**. Unlike `lex_javier_milei`'s DER, the gate is not arithmetically unsatisfiable —
   any terminal WER in `[.116177, .122411]` satisfies both — so it stays a gate and it stays
   preregistered. It is not moved here, and it must not be moved later.
3. **G-M4-4 fails on this case too under P1.** Its bound is the pass's own rolling v2 arm
   (`content_recall` and `matched_word_speaker_accuracy` both `.951036`), and terminal == file
   gives `.949153` on both — `-.001883`.

## 2. The measured comparator

| axis | file arm | rolling arm | terminal == file costs | gate reading |
|---|---|---|---|---|
| WER | `.126177` | `.122411` | `+.003766` | G-M4-1 **ALREADY INSIDE** (`.003766` ≤ `.010`); G-M4-3 fails by `.003766` |
| DER | `.053222` | `.079889` | `-.026667` (an improvement) | G-M4-2 **must move** (`.026667` > `.020`) |
| speaker accuracy | `.946778` | `.920111` | `+.026667` | reported |
| text coverage | `.952260` | `.928022` | `+.024238` | reported |
| v2 content recall | `.949153` | `.951036` | `-.001883` | G-M4-4 fails by `.001883` |
| v2 matched-word speaker | `.949153` | `.951036` | `-.001883` | G-M4-4 fails by `.001883` |
| v2 DER over speech regions | `.054079` | `.066209` | `-.012130` (an improvement) | reported |

Structure: 8 reference segments, 2 reference speakers (`Adam Frank`, `Lex Fridman`), 180.0 s of
16 kHz mono PCM16, 2 880 000 samples. Terminal plans **2 windows** — `[0, 150)`, `[120, 180)` —
which is the same plan file mode runs, so `terminal == file` is an identity here as it is on the
trio, not an approximation. Complete tape: 5.493 MiB, inside Appendix B Q10's budget.

Live arm, both passes: `succeeded`, 360 frames, 2 880 000 accepted samples,
`accepted == accounted`, decode RTF p95 `.396` / `.339`, 76 spans frozen (71 `hard_cap`,
4 `leading_silence`, 1 `end_silence`), 3 empty, 18 text revisions, 1 label revision, **no S00
segment at all** — the surface publishes only `S01` and `S02`.

## 3. What "two fresh passes" says here, and why `runs_agree` is `False`

| axis | pass A | pass B | spread |
|---|---|---|---|
| WER | `.122411` | `.122411` | `0.000000` |
| DER | `.079889` | `.080222` | `.000333` |
| speaker accuracy | `.920111` | `.919778` | `.000333` |
| text coverage | `.928022` | `.927683` | `.000339` |

The two live **transcripts are word-identical** (546 words, same SHA-256 over the concatenated
text) and both file arms are **byte-identical to each other**. What differs is segment extent, and
only extent — the same signature the trio showed at iteration 8 and the five-minute case showed at
M0d. `runs_agree` is `False` because that flag compares every scored axis exactly; the honest
reading is "text reproducible, extents spread by `3.3e-4`", which is two orders of magnitude below
the `.020` DER tolerance G-M4-2 applies. `_targets` reads pass A, the convention every other case
in this table already uses.

There is no pre-campaign baseline for this case (it was never run), so
`file_arm_stable_since_precampaign` reports `no-precampaign-baseline` rather than `True`. The
available stability evidence is the two identical file arms in this bundle plus the shared
provenance line: same `live_source_revision cc8f778a…`, same `combined_config_hash 431efb3f…`,
same greedy decoding, as every campaign pass since the M2 exit.

## 4. What did not move

The four cases that already had a comparator are **byte-identical** to
`M4-preregistration/m4-baseline.json`, and so is the trio mean. Folding a fifth case into the
instrument changed nothing about the four it already scored — checked by comparing the two JSON
tables case by case, not by eye.

## 5. The instrument, and why it is the checked-in driver's shape

P-M4-A requires the acquiring driver to be *"the checked-in paired driver's shape, not a new
instrument"*. `remeasure_one_case.py` is `remeasure_5m_case.py` with the case lifted out of the
module constants, and `--selftest` **checks** that rather than claiming it:

- the replay keywords (`pace 1.0`, `max_pacing_lag 3.0`, `runs 1`) and the base URL are parsed out
  of `remeasure_5m_case.py`'s own source with `ast` and compared;
- the scoring path is re-run over the checked-in `M2-e2-exit/passes/keyu5m-A` hypotheses and must
  reproduce that pass's own recorded WER / DER / speaker accuracy / coverage to `1e-12` — it
  reproduces them at `0.000e+00`;
- the five relative paths it writes must equal the five `verify_m2_exit.case_paths` reads;
- audio the live transport would have to resample is refused, not converted.

`measure_m4_baseline.py` now reads whether the three-minute case has a comparator **off the disk**
(`--three-minute-root`, default this bundle), finds the pass directory by its run suffix rather
than by a hard-coded label, and refuses two candidates for the same run instead of picking one.
Its self-test covers both directions: an empty root leaves the case `MISSING`, two runs on disk
make it gateable whatever the label is.

## 6. Reproduction

```bash
# the comparator table, from this bundle (no GPU, no service, zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py \
  --output /tmp/m4-baseline.json

# both instruments' self-tests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/remeasure_one_case.py --selftest
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py --selftest

# re-acquire the pass itself (needs the running service; ~7 min; 2 x 180 s of real MOSS traffic)
prototypes/streaming-diarization/live-convergence/run_paired_case.sh /tmp/m4-3min-<stamp> \
  adam3m lex_adam_frank \
  prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples/lex_adam_frank
```

## 7. For the M4 exit (candidate 8d), stated before the terminal build exists

The disposition of the two gate misses this comparator predicts is an **owner decision at the M4
exit**, on the pattern of D-M4-2 — not a bound change, and not a reason to re-run. Both are
recorded now, with their arithmetic, so that resolving them later cannot look like gate-shopping:

- **G-M4-3 on `lex_adam_frank`**: terminal == file costs `.003766` WER on the one case where the
  rolling surface is the better text. The PRD's mission is convergence toward the paired file arm;
  the campaign's own strengthening says do not regress a case. They disagree here by less than
  four thousandths, and the extent-free reading agrees with the deployed one (v2 WER moves the
  same `+.003766`).
- **G-M4-4 on `lex_adam_frank`**: `-.001883` on both v2 content axes, same cause.

Everything else this case contributes is a gain: DER `-.026667`, speaker accuracy `+.026667`,
coverage `+.024238`, v2 speech-region DER `-.012130`.
