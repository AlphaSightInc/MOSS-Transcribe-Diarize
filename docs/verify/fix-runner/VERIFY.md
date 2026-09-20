# Fresh-context verification — fix-runner

Execute literally in a fresh context. Work only in
`/private/tmp/moss-round3-20260919/fix-fix-runner` on branch
`round3/fix-fix-runner`. Do not open a GPU tunnel, make decoder requests, rerun the
live campaign, edit product/tests, use another tree, push, merge, deploy, write GitHub,
or message another pane. Use the Python below with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`.

1. Read `AGENTS.md`, then record branch, SHA, `git status --short`, and the imported
   module path. Initial tracked and untracked status must be clean; import must resolve
   inside this clone.
2. Inspect the diff from `738cdfdd`. Production under `moss_transcribe_diarize/` must
   be unchanged. The only executable changes may be the capacity prototype and its
   tests/evidence. Confirm no protected constant or protocol edit.
3. Run the fix controls:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_capacity_campaign_fix.py
   ```

   Expect 3/3. These cover the healthy attributed interleaving and violations for
   missing attribution and whole-batch hold. The retained unpatched JUnit must show
   3/3 failures at `738cdfdd`; patched JUnit must show 3/3 passes.
4. Run the offline evidence audit (no GPU/network):

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/round3/fix-runner/audit.py
   ```

   Expect PASS, 2x300, 342/342 attributed windows, 10/10 Live preemptions, and
   342/400 requests. Any assertion failure falsifies the result.
5. Run full gates:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
   npm --prefix frontend test -- --run
   npm --prefix frontend run typecheck
   npm --prefix frontend run build
   ```

   Expect backend 2,103 passed / 5 skipped / 37 subtests; frontend 310/310 in
   28 files; typecheck/build exit 0. Record any failure; do not waive it.
6. Confirm `lsof` has no listener on 18271, 17990, or 17991; GPU lease is not held
   by PANE-3.3 (another pane may legitimately acquire it after PANE-3.3 released it);
   `git diff --exit-code` and `git status --short` are empty after build.
7. Write `docs/verify/fix-runner/VERIFY-RESULT.md` with fresh-context provenance,
   inspected SHA, commands, exact counts/timings, all falsifiers, cleanup, and limits.
   Commit only that result locally. Final status must be clean. No further `/new`.

Known prerequisites to retain, not change: MG5 host SQLite 3.50.4 versus required
3.53.4; MG10 host tape manifest 9,600,000 versus 384,000,000 bytes for 200 minutes.
The campaign used an isolated 460,800,000-byte (240-minute) manifest.
