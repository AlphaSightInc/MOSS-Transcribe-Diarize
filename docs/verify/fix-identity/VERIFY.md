# FIX-3.2 fresh-context verification

Run literally from `/private/tmp/moss-round3-20260919/fix-identity` in a new
context. Do not open a tunnel, acquire the GPU lease, make decoder calls, edit
product code, or change the diagnosis. Record exact results in
`docs/verify/fix-identity/VERIFY-RESULT.md`.

The claimed outcome is **(c), unchanged known limitation L1**: fresh detached
`a7a738cf` and integrated `738cdfdd` produced identical direct-tunnel/no-proxy
lane numerators. A PASS certifies retained evidence and local suites only.

1. Confirm custody and pre-result cleanliness:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --exit-code 738cdfdde092b8ba9341179fb1d33e1c34cbd24c -- \
  moss_transcribe_diarize tests frontend
git diff --exit-code 738cdfdde092b8ba9341179fb1d33e1c34cbd24c -- \
  docs/known-limitations-20260918.md >/dev/null; test $? -eq 1
```

Expected: branch `round3/fix-identity`; clean status; no product, test, or
frontend change; the L1 document differs from base.

2. Validate both receipts and the comparison:

```bash
jq -e '.revision == "738cdfdde092b8ba9341179fb1d33e1c34cbd24c" and
  .hop == "direct_tunnel_127.0.0.1_18261" and .remote_requests == 59 and
  .request_budget == 150 and .cases.alternation.pre_terminal.system.errors == 16 and
  .cases.alternation.pre_terminal.microphone.errors == 11 and
  .cases.overlap.pre_terminal.system.errors == 24 and
  .cases.overlap.pre_terminal.microphone.errors == 6 and
  .verdict == "KNOWN_LIMITATION_L1"' \
  evidence/round3/fix-identity/integrated-direct-summary.json
jq -e '.revision == "a7a738cf9f9ff246f64c52c112e0bf597ba58241" and
  .checkout == "fresh_detached_clone" and
  .hop == "direct_tunnel_127.0.0.1_18261_no_proxy" and .remote_requests == 59 and
  .cases.alternation.pre_terminal.system.errors == 16 and
  .cases.alternation.pre_terminal.microphone.errors == 11 and
  .cases.overlap.pre_terminal.system.errors == 24 and
  .cases.overlap.pre_terminal.microphone.errors == 6 and
  .verdict == "KNOWN_LIMITATION_L1"' \
  evidence/round3/fix-identity/base-direct-summary.json
jq -e '.classification == "c" and .exact_numerators_identical == true and
  .remote_requests.total == 118 and .remote_requests.budget == 150 and
  .product_change == false and .threshold_change == false and
  .bisection_required == false' evidence/round3/fix-identity/comparison-summary.json
rg -n 'direct tunnel, no proxy.*a7a738cf.*738cdfdd|unchanged L1' \
  docs/known-limitations-20260918.md evidence/round3/fix-identity/NOTES.md
```

Expected: three true predicates; L1/notes name both revisions, exact direct
scope, and classification (c).

3. Run healthy/rejecting lane controls and full suites:

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

4. Confirm this pane stopped all owned resources and retained scope:

```bash
! rg -q '^HELD by PANE-3\.2 ' \
  /Users/gao/Documents/Codex/2026-09-19/moss-round3/status/GPU-LEASE.md
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

Expected: lease not held by PANE-3.2 (another pane may legitimately hold it),
no owned listener/tunnel, clean worktree. Any different count, receipt, scope
delta, owned resource, or classification falsifies verification.
