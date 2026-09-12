# Read-only Playwright driver copy — 2026-09-12

**Fixed:** add owner-write permission to the temporary `package/lib/coreBundle.js` before replacing its forced-focus override. Preserve all other mode bits. The installed source package is neither patched nor chmodded. No product polling/capture behavior, browser flags, deadlines or gate criteria changed.

Round 12 failed before browser launch because `shutil.copytree` preserves source permissions. The new test makes source files mode 0444 and directories 0555, invokes the real setup helper, and reproduces `PermissionError`, errno 13, before the fix. After the fix it verifies the copied override, unchanged read-only source, restored driver resolver and deleted temporary tree. This also checks cleanup through read-only copied directories.

The no-copy alternative was already measured in the [round-11 diagnosis](round11-browser-fixes-20260912.md): changing focus emulation through a separate CDP session left the page visible. Retain the proven isolated-driver mechanism; normalize only the one file it edits.

Validation: `pytest tests/phase2/test_round11_browser_fixes.py -q` — **3 passed**, including the genuine headless hidden-state/post-hidden-request test and the new read-only-source case. The pre-fix read-only case failed with the same errno as the host.

Fresh isolated current-head stack (`aff84fdb` plus this helper patch), port 17863, relay configured, draft lane 1.0 s, separate state/control paths. E2E `--rows 1,4,11` — **3/3 requested rows PASS** (the live row also runs its naming subcheck). First text **2.332 s**, Stop-to-completed **2.060 s**; history selection correct. Only metadata retained; private downloads/media are handled by the current content-boundary-safe harness. [Validation](../../evidence/readonly-browser-driver-20260912/validation.json), [E2E results](../../evidence/readonly-browser-driver-20260912/e2e-results.json).

No host operations or operator 17861 database access. The owned local instance was stopped after measurement. These local checks do not retrospectively pass the failed round-12 host gate.
