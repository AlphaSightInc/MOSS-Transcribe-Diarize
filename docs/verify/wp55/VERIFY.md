# PANE 3.2 fresh-context verification

Run literally from `/private/tmp/moss-round3-20260919/identity` with no prior context.
Do not edit product code. Record exact outputs/counts in
`docs/verify/wp55/VERIFY-RESULT.md`.

1. Confirm custody and scope:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
git diff --exit-code a7a738cf9f9ff246f64c52c112e0bf597ba58241 -- \
  moss_transcribe_diarize tests frontend
```

Expected: branch `round3/identity`; clean status; no product/test/frontend diff.

2. Re-run WP55a-P. Exit 2 is the expected measured gate failure:

```bash
set +e
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
prototypes/identity/file_policy_compare.py
wp55a_status=$?
set -e
test "$wp55a_status" -eq 2
jq -e '.gate_verdict == "FAIL" and .selected_policy == null and
  (.qualifying_policies | length) == 0 and
  .exact_raw_arms[1].p0_matches_production_resolver == true and
  .exact_raw_arms[1].policies.P3.per_person.TOTAL.wrong ==
    .exact_raw_arms[1].baseline.TOTAL.wrong' \
  prototypes/identity/file-policy-results.json
```

Expected: no qualifying policy; exact 30-minute WAV P3 retains baseline wrong time.

3. Re-run WP55b-P step 1. Exit 2 is the expected stop-and-report:

```bash
set +e
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
prototypes/identity/short_speaker_adjudication.py
wp55b_status=$?
set -e
test "$wp55b_status" -eq 2
jq -e '.gate_verdict == "FAIL" and .clean_snippets_frozen == 0 and
  .scope.decoder_requests == 0 and .next_steps.oracle_matrix == "NOT UNLOCKED"' \
  prototypes/identity/short-speaker-results.json
```

Expected: step 1 fails; IP1/oracle remain unrun; decoder requests 0.

4. Run the full suites:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
-m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: backend 2,037 passed / 5 skipped / 37 subtests / 0 failed; frontend
288/288; typecheck clean; build clean.

5. Confirm no generated drift or live process:

```bash
git status --short
git diff --exit-code
if lsof -nP -iTCP:18312 -sTCP:LISTEN; then exit 1; else true; fi
if ps -axo comm=,args= | awk '$1 == "ssh" && $0 ~ /127\.0\.0\.1:18312:127\.0\.0\.1:8000/ {found=1} END {exit !found}'; then
  exit 1
else
  true
fi
```

Expected: clean worktree; no listener/tunnel on 18312. Any different count, policy
verdict, product delta, decoder use, listener, or tunnel falsifies verification.
