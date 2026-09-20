# Fresh-context verification result — fix-runner

## Verdict

**FAIL.** Code, retained evidence, backend, frontend, and three required listener
checks passed. The required shared GPU lease check failed: at
`2026-09-20T01:50:52Z`, the lease file said
`HELD by PANE-3.1 since 2026-09-20T01:32:36Z; port 18251; budget 250 requests`,
not `FREE`. This falsifier is not waived. I did not contact the holder, retry the
check, use the lease, open a tunnel, or make a decoder request.

## Fresh-context provenance

- Worktree: `/private/tmp/moss-round3-20260919/fix-fix-runner`
- Branch: `round3/fix-fix-runner`
- Inspected SHA: `a378fe90ef27feac90287e2fafccce36df578e56`
- Initial `git status --short`: empty, including untracked files.
- Imported module: `/private/tmp/moss-round3-20260919/fix-fix-runner/moss_transcribe_diarize/__init__.py`
- Instructions read: repository `AGENTS.md` and this lane's `VERIFY.md`.

## Diff custody

`git diff 738cdfdd..a378fe90 --name-status` showed 22 files: the verification
instructions, retained evidence/audit, four capacity-campaign prototype files,
and `tests/test_capacity_campaign_fix.py`. `git diff --quiet 738cdfdd..HEAD --
moss_transcribe_diarize` returned clean. No production file, protected production
constant, or production protocol changed. Executable changes are confined to the
capacity prototype, its control test, and the offline evidence audit.

## Commands and results

1. Fix controls:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_capacity_campaign_fix.py
   ```

   **PASS:** 3 passed in 0.12 seconds. The healthy attributed interleaving passed;
   missing attribution and a whole-batch hold were refused.

2. Retained mutation/control receipts, parsed as JUnit:

   - `unpatched-controls.xml`: 3 tests, 3 failures, 0 errors, 0 skipped,
     0.119 seconds, at base `738cdfdd`.
   - `patched-controls.xml`: 3 tests, 0 failures, 0 errors, 0 skipped,
     0.120 seconds.

3. Offline audit:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/round3/fix-runner/audit.py
   ```

   **PASS / exit 0:** 2x300 sessions; 342/342 attributed dispatch windows;
   10/10 Live preemptions; 342/400 decoder requests. The command does not emit a
   duration and was not rerun merely to add one.

4. Backend gate:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
   ```

   **PASS:** 2,103 passed, 5 skipped, 21 warnings, and 37 subtests passed in
   189.93 seconds.

5. Frontend gates:

   ```sh
   npm --prefix frontend test -- --run
   npm --prefix frontend run typecheck
   npm --prefix frontend run build
   ```

   - Tests: **PASS**, 310/310 in 28/28 files, 2.94 seconds.
   - Typecheck: **PASS**, exit 0; tool wall time 1.238 seconds.
   - Build: **PASS**, exit 0; Vite reported 34 transformed modules and 110 ms
     build time (tool wall time 0.416 seconds).

## Falsifiers and cleanup

- Source custody: passed. Correct branch/SHA, clean start, import inside this
  clone, no production or protected constant/protocol diff.
- Control sensitivity: passed. The base mutation failed 3/3 and the patch passed
  3/3; unattributed proxy rows and whole-batch holding are rejected.
- Dispatch evidence: passed. Complete attribution 342/342; maximum total/background
  in-flight 2/1; File first-dispatch values 4.313, 0.243, and 0.182 seconds, all at
  or below 12 seconds; all three File/URL owners interleaved; Live priority 10/10;
  no missing timings or priority inversion.
- Campaign accounting: passed. Both 300-second Live sessions accounted
  4,800,000/4,800,000 samples with zero retries and zero wrong-owner failures;
  request receipt is 342 started / 342 finished / 400 authorized.
- Full gates: passed with the exact counts above.
- Listener cleanup: passed at `2026-09-20T01:50:52Z`; listener counts were zero on
  18271, 17990, and 17991.
- GPU lease cleanup: **failed** at the same timestamp. The authoritative file
  `/Users/gao/Documents/Codex/2026-09-19/moss-round3/status/GPU-LEASE.md` said
  `HELD`, not `FREE`.
- Post-build tree before this result: `git diff --exit-code` passed and
  `git status --short` was empty.

## Limits retained

- No GPU/network campaign was run during this verification; retained live evidence
  was audited offline only.
- MG5 remains blocked by host SQLite 3.50.4 versus required 3.53.4.
- MG10 host tape manifest remains 9,600,000 versus 384,000,000 bytes required for
  200 minutes. The campaign used an isolated 460,800,000-byte, 240-minute manifest.
- This result does not authorize push, merge, deploy, GitHub writes, peer contact,
  or any claim stronger than the checks recorded above.
