# Fresh-context verification result — fix-runner

## Verdict

**PASS.** The source-custody checks, sensitive controls, retained-evidence audit,
full backend/frontend gates, and PANE-3.3-owned cleanup checks all passed. The shared
GPU lease was held by PANE-3.1, which is **PASS with a note** under the verification
contract; I did not wait for or contact that pane.

## Fresh-context provenance

- Worktree: `/private/tmp/moss-round3-20260919/fix-fix-runner`
- Branch: `round3/fix-fix-runner`
- Inspected SHA: `70b7f8b2bbb1e6d81c73fc869d7bc9c3c551b258`
- Initial `git status --short`: empty, including untracked files.
- Imported module:
  `/private/tmp/moss-round3-20260919/fix-fix-runner/moss_transcribe_diarize/__init__.py`
- Instructions read: repository `AGENTS.md` and `docs/verify/fix-runner/VERIFY.md`.

## Diff custody

`git diff 738cdfdd..70b7f8b2 --name-status` showed 23 files: verification
instructions/prior receipt, retained evidence and its offline audit, four
capacity-campaign prototype files, and `tests/test_capacity_campaign_fix.py`.
`git diff --exit-code 738cdfdd..HEAD -- moss_transcribe_diarize/` was empty.
No production file, protected production constant, or production protocol changed.
Executable changes are confined to the capacity prototype, its control test, and
the retained-evidence audit.

## Commands and exact results

1. Fix controls:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_capacity_campaign_fix.py
   ```

   **PASS:** 3 passed in 0.12 seconds. The healthy attributed interleaving passed;
   missing attribution and whole-batch holding were refused.

2. Retained JUnit controls:

   - `unpatched-controls.xml` at base `738cdfdd`: 3 tests, 3 failures, 0 errors,
     0 skipped, 0.119 seconds.
   - `patched-controls.xml`: 3 tests, 0 failures, 0 errors, 0 skipped,
     0.120 seconds.

3. Offline evidence audit:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/round3/fix-runner/audit.py
   ```

   **PASS / exit 0:** 2x300 sessions; 342/342 attributed dispatch windows;
   10/10 Live preemptions; 342/400 decoder requests. The audit emitted no duration.
   Maximum in-flight work was 2 total and 1 background. File first-dispatch times
   were 4.312907291, 0.243309708, and 0.181881166 seconds; all three owners fairly
   interleaved. Terminal-to-terminal wait was 22.604181332 seconds. The paired Stop
   gap was 0.000058083 seconds and File submission followed the final Stop by
   0.028504417 seconds.

4. Backend gate:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
   ```

   **PASS:** 2,103 passed, 5 skipped, 21 warnings, and 37 subtests passed in
   188.94 seconds.

5. Frontend gates:

   ```sh
   npm --prefix frontend test -- --run
   npm --prefix frontend run typecheck
   npm --prefix frontend run build
   ```

   - Tests: **PASS**, 310/310 in 28/28 files, 2.96 seconds.
   - Typecheck: **PASS**, exit 0; command wall time 1.231 seconds.
   - Build: **PASS**, exit 0; Vite transformed 34 modules and built in 106 ms
     (command wall time 0.389 seconds).

## Falsifiers and cleanup

- Source custody passed: correct checkout, branch, SHA, clean start, and local import.
- Diff custody passed: no production, protected-constant, or protocol edit.
- Control sensitivity passed: the base failed 3/3 while the patch passed 3/3;
  unattributed rows and whole-batch holding are rejected.
- Dispatch audit passed: complete attribution, bounded concurrency, all observed Live
  priority opportunities, timely first dispatch, fair File/URL interleaving, complete
  session accounting, no retries, no wrong-owner failures, and matched request receipt.
- Full gates passed with the exact counts above; no failure was waived.
- At `2026-09-20T01:58:58Z`, PANE-3.3-owned resource counts were: 0 listeners on
  decoder port 18271, 0 listeners across stack/proxy ports 17990–17999, 0 processes
  whose command referenced this clone, and 0 PANE-3.3 entries in `GPU-LEASE.md`.
- Shared-lease note: `GPU-LEASE.md` said `HELD by PANE-3.1 since
  2026-09-20T01:32:36Z; port 18251; budget 250 requests`. Per the contract, this is
  PASS-with-note, not a PANE-3.3 cleanup failure.
- After build and before writing this result, `git diff --exit-code` passed and
  `git status --short` was empty.

## Limits retained

- No GPU tunnel, decoder request, network campaign, or live campaign rerun occurred.
  Only retained evidence was audited offline.
- MG5 remains blocked by host SQLite 3.50.4 versus required 3.53.4.
- MG10 host tape manifest remains 9,600,000 versus 384,000,000 bytes required for
  200 minutes. The campaign used an isolated 460,800,000-byte, 240-minute manifest.
- This result does not authorize push, merge, deploy, GitHub writes, peer contact, or
  any claim stronger than the checks recorded here.
