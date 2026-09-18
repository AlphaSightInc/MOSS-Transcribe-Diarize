# WP25 fresh-context verification — execute literally after /new

## Scope and prerequisites
First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp25-qualify-run`.
Only modify this worktree. Branch `mvpfix/wp25-qualify-run`; production candidate is
`625dbaa97b55fb5be66e06db9bfe4d8c985fd935`. Implementation/harness commit `ab4744511b41`.
No push, merge, deployment, GitHub, shared services, ports7861/7862, policy changes,
benchmark-case edits, or decoder tuning. This is the explicitly authorized fresh run,
not another long run. Own tunnel18125; <=2 own in flight; budget2000 for this rerun.
Stop all owned processes. Keep audio, raw logs, cookies and keys in ignored scratch.
Use Python `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`
with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`. Frontend node_modules already symlinked;
never npm install or use Vite's default config loader.

## 1. Establish identity
Run `git status --short --branch` and `git rev-parse HEAD`.
Run `git diff --exit-code ab4744511b41 HEAD -- scripts tools/qualify prototypes`.
Expected: clean tree; scripts/tools/prototypes unchanged since measured harness.
Evidence/docs commits may make HEAD differ; report both SHAs. Run the mandated Python
import check and require its __file__ inside this worktree.
A code difference, dirty starting tree or wrong import falsifies repeatability: investigate
and report, do not silently claim same-code status comparison.

## 2. Run the entire short bundle once
From this worktree execute exactly:

```sh
bash scripts/mvpfix-qualify.sh --budget 2000 --compare evidence/mvpfix/wp25/ab4744511b41-20260918T073411045029Z/summary.json --out evidence/mvpfix/wp25/fresh
```

Capture console only under `.wp25runtime/fresh-console.raw` if redirecting it.
Do NOT add --long. This includes full Python/frontend suites, asset parity/typecheck,
workspace, demo lanes, lifecycle, reshare, all3 identity cases, all6 ladder points,
all16 browser cases, six-minute file and five typed failures. The two long-only gates
must be explicitly SKIP. No sibling-load pause. Do not rerun to chase nondeterminism.
Exit1 is expected for existing failed qualification; it does not mean the command
failed to execute. Wait until BUNDLE and teardown appear. If the runner itself fails,
record the reason and observed/missing denominators. Keep failed attempts.

## 3. Compare and adjudicate observations
Read fresh summary.json, long summary.json, and `evidence/mvpfix/wp25/LONG-DETAILS.md`.
Expected static: Python1910 passed/2 skipped/1912 collected plus37 subtests;
frontend249/249;helpers9/9;assets17/17;typecheck/layoutPASS.
Expected dynamic statuses: workspaceFAIL (row4FAIL, row9SKIP, other12 rowsPASS),
demo_lanesFAIL, lifecyclePASS7/7, resharePASS6/6, identityPASS3/3, ladderPASS6/6,
browser_stress_allFAIL (13PASS/1FAIL/2UNRUNNABLE), file_6minPASS1/1,
file_failuresPASS5/5. Compare observations, never force these expectations.
`determinism.deltas` must list any unexpected gate-status changes. The runner separately
lists intentionally omitted file_30min/capacity_4x600. SHA equality will be false if only
committed evidence/docs differ; do not describe it as exact-SHA determinism.
Ladder reference:37/37 system+32/32 mic at all4 overlap points; alone controls37/37+0/32
and0/37+32/32. All6 finalized. Unique vocabulary is not transcript accuracy.
For every FAIL report exact existing bar and measured values. Row4/demo immediate WER
bar0.166655;final/reopened0.095074. Actual unchanged mic gain0.03, not0.316. Summary
skip requires configured relay models; a key alone did not configure the long run.
Browser cases3/15 unavailable if native visibility remains false; case9's old keyword
predicate rejected two truthful UI reasons. Keep case logic unchanged.
Long capacity failed4/4 with finalization_timeout_90s despite all9600000 samples
accepted/accounted per session; preserve this long result when the short run skips it.
The supplement capacity-failure-details.json retains safe machine codes omitted by the
broad string sanitizer. If any new fresh failure detail is missing from projection,
read private raw data and retain only exact safe numeric/boolean/machine-code operands.

## 4. Verify teardown and retained evidence
Check no listeners remain on18125,19125,17825,17826,17827,17828,17829; an owned leak
must be stopped and reported. This check detects cleanup failure; never stop unrelated
listeners. Record fresh calls, peak, budget rejections, duration, contention counts.
Retain only safe projections, no audio/transcripts/cookies/secrets/screenshots/raw logs.

## 5. Record, commit, report in this pane
Write `docs/verify/wp25/VERIFY-RESULT.md`: fresh-session identity, commands, exact counts,
expected vs actual gate statuses, qualification verdict and verification verdict
separately, unexpected changes, limits and any deviations. Retain a <=60-line final
report at `evidence/mvpfix/wp25/FINAL-REPORT.md` and print that report in this pane.
Include full gate table with long+fresh statuses/denominators/durations (35 gates),
branch/final SHA, prototype verdict, files changed, exact failed bars, reasons for
SKIP/UNRUNNABLE, request/contention counts, ladder comparison and lead command.
For the lead: `bash scripts/mvpfix-qualify.sh --long --budget 2000` from this worktree.
Run `bash scripts/check_verify_layout.sh` and `git diff --check` before committing
only fresh evidence and verification/report docs. No code change is expected.
Commit locally, then report final SHA and clean status. Final report may use “final SHA:
see pane report” in its committed copy to avoid a self-referential SHA. Do not end with
an offer to continue: the fresh rerun, commit and <=60-line pane report complete WP25.
