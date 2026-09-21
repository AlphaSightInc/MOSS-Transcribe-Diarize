# R4-10 feature-row runner

## Contract

**Structural question.** Can one frozen-SHA runner keep feature evidence separate from
its prerequisites, so a missing decoder, key, or private stack cannot become a false
PASS?

**Minimum primitives.** A frozen product-path check; one row receipt; the merged
lane-second request plan; explicit decoder/provider authority; and the existing product
surface command for each feature. Remove any one and the runner either loses custody,
silently spends authority, or cannot distinguish unmeasured from failed behavior.

**Invariants.** Every receipt records command, exit code, denominator, and artifact
paths. Missing prerequisites are `INCOMPLETE`, never `PASS`. The external-summary
population is 2 transcript lengths x 3 trials = 6 non-retrying attempts, below the
cap of 10. Credentials are sourced only inside the real summary subprocess and are
never printed, retained, or committed. `--plan-only` imports the merged
`tools/qualify/run.py:request_plan` arithmetic rather than duplicating it.

**Assumptions / unknowns.** A later operator must supply an isolated stack started
from this exact product tree, a leased/capped decoder endpoint, and the key authority.
This slice does not establish their availability or any summary/decoder quality.

**Falsifier.** The design is false if a product-path change outside this runner or its
evidence is accepted, a missing prerequisite produces `PASS`, the summary row plans
more than ten calls, or case 13 records a provider POST.

**Tool decision.** `--plan-only` answers the request-population question without
dispatch. The existing loopback `summary_fixture.py` is necessary for standalone
browser-stress case 13 because that case needs a completed transcript but must make zero
provider posts. Existing browser/e2e suites are invoked rather than reimplemented.

## One command

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/feature-rows/run.py --plan-only
```

The current no-dispatch control is `--rows disabled-summary`. A real all-row run needs
`--base <private-frozen-stack> --allow-decoder --allow-provider`; it must be supplied
with a separately authorised, capped decoder authority. The runner opens no tunnel and
never starts a shared service.

## D24 minimal provider smoke

**50 s smoke: `EXPECTED — timestamp-absent`.** The verifier's actual 50 s browser/settings/
summary path reached `current` twice through OpenRouter using
`google/gemini-2.5-flash-lite`, with 2 provider POSTs total and 0 decoder requests.
The first invocation's product verifier returned 0 but its local receipt assembly exited
1; its redacted record is retained. The single permitted retry returned 0, was current,
and had 0 detail timestamps. This is an observed empty list, not a malformed timestamp.

Evidence: `evidence/round4/features/provider-smoke-20260921T063618Z/` and
`evidence/round4/features/provider-smoke-20260921T063857Z/`. The official S15 row still
needs the frozen product stack with its real decoder, 50 s and 180 s x `TRIALS=3`, and
the 10-call provider cap. This smoke is only a key/model/product-path check.

## D24 timestamp diagnosis

**Verdict: `EXPECTED`.** The shipped prompt permits `details: []` when a short
introduction/open-question excerpt has no selected chronological support
(`frontend/src/lib/final-summary-prompt.txt:44-46,102-104`). Both browser and server
validators accept an empty list, but reject every supplied malformed or out-of-range
`HH:MM:SS` value (`frontend/src/lib/finalSummary.ts:94-111` and
`moss_transcribe_diarize/app/phase2_summary.py:21-45`). The focused server test passed
12/12, and a local probe confirmed exactly that boundary.

The official condition is deliberately the 180 s Adam case, not the 50 s introduction:
the verifier selects both inputs (`tests/e2e/verify_summaries.py:43-49,125-156`) because
the former 50 s-only row missed the realistic-meeting timestamp defect
(`docs/handoffs/e2e-smoke-for-operator.md:30-38`). Retained V15 evidence for the matching
180 s Adam source has two valid details, `00:00:49` and `00:01:59`, with zero invalid
timestamps: `evidence/round4/features/timestamp-diagnosis-20260921/receipt.json`.
Diagnosis used 0 additional provider calls and 0 decoder requests. S15 remains
`INCOMPLETE` until its frozen-stack, real-decoder, 50/180 s x3 campaign runs under cap 10.
