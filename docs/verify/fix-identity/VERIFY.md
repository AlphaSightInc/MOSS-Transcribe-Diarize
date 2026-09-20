# FIX-3.2 fresh-context verification

Run literally from `/private/tmp/moss-round3-20260919/fix-identity` with no
prior context. Do not open a tunnel, acquire the GPU lease, make decoder calls,
edit product code, or change the diagnosis. Record exact results in
`docs/verify/fix-identity/VERIFY-RESULT.md`.

The work outcome is intentionally **BLOCKED** by the 80-request budget. A
verification **PASS** means the partial receipt, stop boundary, clean candidate,
and local suites are reproducible; it does not classify (a), (b), or (c).

1. Confirm custody and scope:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --exit-code 738cdfdde092b8ba9341179fb1d33e1c34cbd24c -- \
  moss_transcribe_diarize tests frontend docs/known-limitations-20260918.md
```

Expected: `round3/fix-identity`; clean status; no product, test, frontend, or L1
change.

2. Validate the retained live receipt and explicit non-conclusion:

```bash
jq -e '.revision == "738cdfdde092b8ba9341179fb1d33e1c34cbd24c" and
  .hop == "direct_tunnel_127.0.0.1_18261" and
  .remote_requests == 59 and .request_budget == 80 and
  .cases.alternation.pre_terminal.system.errors == 16 and
  .cases.alternation.pre_terminal.microphone.errors == 11 and
  .cases.overlap.pre_terminal.system.errors == 24 and
  .cases.overlap.pre_terminal.microphone.errors == 6 and
  .verdict == "BLOCKED_INCOMPLETE_MATRIX"' \
  evidence/round3/fix-identity/integrated-direct-summary.json
rg -n 'No \(a\)/\(b\)/\(c\) classification|unchanged because' \
  evidence/round3/fix-identity/NOTES.md
```

Expected: predicate true; notes refuse classification and L1 modification.

3. Run lane controls and full suites:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
-m pytest -q -p no:cacheprovider tests/phase2/test_demo_lane_measurement.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
-m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: lane controls 10/10; backend 2,100 passed / 5 skipped / 37 subtests /
0 failed; frontend 310/310; typecheck/build clean.

4. Confirm the stopped resource boundary:

```bash
test "$(sed -n '1p' /Users/gao/Documents/Codex/2026-09-19/moss-round3/status/GPU-LEASE.md)" = FREE
if lsof -nP -iTCP:17861 -sTCP:LISTEN; then exit 1; else true; fi
if lsof -nP -iTCP:18261 -sTCP:LISTEN; then exit 1; else true; fi
if ps -axo comm=,args= | awk '$1 == "ssh" && $0 ~ /127\.0\.0\.1:18261:127\.0\.0\.1:8000/ {found=1} END {exit !found}'; then
  exit 1
else
  true
fi
git status --short
git diff --exit-code
```

Expected: lease `FREE`; no owned listener/tunnel; clean tracked worktree. Any
different count, receipt, scope delta, live resource, or classification falsifies
verification.
