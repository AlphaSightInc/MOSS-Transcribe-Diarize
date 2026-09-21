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
