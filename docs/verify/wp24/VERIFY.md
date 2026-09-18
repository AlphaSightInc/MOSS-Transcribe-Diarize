# WP24 — literal fresh-context verification

You are the NEW session in MOSS:3.4 after the user-requested `/new`. Do not treat a prior-session repeat as
fresh verification. Assignment: regenerate the owner sign-off pack, compare its checklist, record the result,
commit it locally, then give the <=60-line report in THIS pane. No peer dispatch needed.

## Boundaries

Only modify `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp24-visual-copy-pack`.
No push/merge/rebase/deploy/GitHub; no ports 7861/7862; no operator-reserved fidelity gate.
Own vLLM tunnel only 18124. At most 100 requests per regeneration, cumulative budget 150,
maximum 2 in flight. Generator owns and stops its services.
Use the specified Python with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` and cwd in this worktree.
Do not use subagents. Do not change product behavior to make verification pass.

## What has already passed

Production commit `205dc611`, from integrated `0ce5122d`.
Full Python: 1908 passed, 2 skipped, 37 subtests passed (21 warnings, 152.33s).
Frontend: 250 passed in 28 files; typecheck/build passed. Logs: `evidence/mvpfix/wp24/checks/`.
The requested full-suite gate was run before this VERIFY.md was written.
Read `evidence/mvpfix/wp24/AUDIT.md` for five fixed findings (F1/F2/F3/F5/F6), deferred F4/D3,
fixture limitations, the literal owner checklist, and the distinction between owner acceptance and this pack.

## Execute

1. Confirm branch `mvpfix/wp24-visual-copy-pack`, clean status, and import resolves inside this worktree:

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp24-visual-copy-pack
git status --short
git branch --show-current
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c 'import moss_transcribe_diarize as m; print(m.__file__)'
```

2. Regenerate actual browser/file capture plus all replay/fixture presentations from CURRENT built assets.
This takes about 3–5 minutes. Give brief progress updates while running. All runtime writes remain in `.wp24/`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp24/tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/ui-signoff-pack/run.py --regenerate .wp24/fresh-verification > .wp24/fresh-verification.log 2>&1
```

3. Diff the checklist and check the complete denominator, relevant transcript states, measured accessibility,
keyboard restoration, cumulative budget, and closed listeners:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/ui-signoff-pack/verify.py .wp24/fresh-verification
```

Expected: `passed:true`, checklist byte-equal; **52 states × 3 viewports = 156** PNG/copy pairs;
zero measured contrast failures, unnamed controls, horizontal overflow, checked header/panel intersections;
real active snapshots have both lanes; provisional snapshots have provisional rows; focus restored 3/3;
ports 18124/17884/17885/17886 closed. Nondeterministic transcript words/timestamps/pixels are NOT diffed.
A mismatch, missing state, false provenance, or remaining owned listener falsifies verification.

4. Inspect fresh representative PNGs for desktop active capture and mobile failure (paths in fresh pack).
Do not claim comprehensive visual acceptance or that gradients/opacity were measured as passes.
If successful, copy `.wp24/fresh-verification/verification.json` and `request-count.json` to
`evidence/mvpfix/wp24/fresh-verification.json` and `fresh-request-count.json`.
Write `docs/verify/wp24/VERIFY-RESULT.md`: explicitly fresh session, commands, exact counts, checklist equality, decoder total,
remaining F4/D3 and fixture/native-picker limits. On failure write the exact failure honestly; do not self-retry
provider traffic without diagnosing the cause and accounting for budget.
Before committing, run the full suites requested by the fresh-session assignment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp24/tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests --basetemp=.wp24/test-fresh-session
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Retain logs in `evidence/mvpfix/wp24/checks/`. Commit the result and supporting evidence locally;
check clean status. Verification documents belong only under `docs/verify/wp24/`.

5. Report <=60 lines in this pane: branch + final SHA; prototype verdict; changed files; test counts;
52 states / 156 captures; five fixed, F4 and D3 deferred; decoder count; fresh result; pack link; limitations.
No push/merge/deploy/GitHub, no fidelity gate, no running owned processes. Owner approval remains pending.

Prior memory was used only to preserve fidelity/sentinel boundaries, verified against current briefs/tests.
If citing that lineage, use MEMORY.md:5541-5541 and rollout 01a0ab2e-9a18-7b60-a3c9-0e3c4c23d5e2.
