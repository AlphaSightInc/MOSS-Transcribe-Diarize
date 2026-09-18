# WP13 — fresh-context verification

Execute after `/new` in the assigned pane, without importing prior conversation.
Work only in `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp13-tls-hygiene`.
Branch must be `mvpfix/wp13-tls-hygiene`. No push/merge/deploy/GitHub writes.
Host and DNS strictly read-only. Never execute renewal `--apply`, legacy issuance,
installer, reload, restart, staging, GPU/decoder or attended-browser automation.

## Claim under test

Prepared TLS renewal defaults to effect-free offline dry-run, handles both actual TLS
units, refuses unsupported reload before issuance, verifies ordinary trust/hostname
and >=21-day expiry, and recovers partially applied renewal. Screenshot writes are
temporary; root VERIFY files rejected; raw chunk log ignored and reproducible.
Operator docs distinguish overlap expectation from attended proof and retain authority.

Read `ops/tls/NOTES.md`, `evidence/mvpfix/wp13/NOTES.md`, and
`docs/handoffs/tls-renewal-runbook.md`. Tests/evidence, not those conclusions, decide.
Full suite has **19 inherited failures** proven at pristine base d8ee6f41; this is
**not** a green suite or the permitted voiceprint exception. Record it as FAIL.

## Execute literally

1. Establish worktree and import provenance. Any mismatch falsifies the run; correct
   execution context before testing, never collect the other editable-install tree.

```sh
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp13-tls-hygiene
git branch --show-current
git rev-parse HEAD
git status --short
mkdir -p .wp13runtime/tmp .wp13runtime/raw evidence/mvpfix/wp13/fresh
export TMPDIR="$PWD/.wp13runtime/tmp"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
wp13_python=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
"$wp13_python" -c 'import moss_transcribe_diarize as m; print(m.__file__)'
```

Expected clean starting tree and import inside this worktree. Existing frontend
node_modules symlink must point to the shared dev dependency directory; no npm install.

2. Focused gate detects broken tool logic, dry-run effects, wrong target service,
   unsafe secret logging, hostname bypass, threshold off-by-one, failed TLS rotation,
   root verification collisions, and screenshot routing. Any failure blocks WP13.

```sh
"$wp13_python" -m pytest -q -p no:cacheprovider tests/phase2/test_tls_preparation.py tests/phase2/test_tls_renewal.py tests/phase2/test_lane_consumer_geometry.py > .wp13runtime/raw/fresh-focused.txt 2>&1
printf '%s\n' "$?" > .wp13runtime/raw/fresh-focused.exit
```

Expected **27 passed**, exit 0. Inspect last line and retained stderr warnings.

3. Required full suites detect out-of-scope regressions. Run both, even though the
   inherited Python failures are expected. Retain actual exit codes.

```sh
"$wp13_python" -m pytest -q -p no:cacheprovider tests > .wp13runtime/raw/fresh-python.txt 2>&1
printf '%s\n' "$?" > .wp13runtime/raw/fresh-python.exit
npm --prefix frontend test -- --run > .wp13runtime/raw/fresh-frontend.txt 2>&1
printf '%s\n' "$?" > .wp13runtime/raw/fresh-frontend.exit
```

Expected Python **1809 passed, 19 failed, 2 skipped, 37 subtests passed**, exit 1.
Expected frontend **239 passed, 27 files passed**, exit 0. Compare the exact Python
failure node set to `test-summary.json` → `base-qualified.txt` → `failed_nodes`.
Any new failure requires investigation; same set means inherited, never PASS.

```sh
"$wp13_python" - <<'PY'
import json
from pathlib import Path
expected = set(json.loads(Path('evidence/mvpfix/wp13/test-summary.json').read_text())['base-qualified.txt']['failed_nodes'])
actual = {s.removeprefix('FAILED ') for s in Path('.wp13runtime/raw/fresh-python.txt').read_text().splitlines() if s.startswith('FAILED ')}
assert actual == expected and len(actual) == 19, (actual - expected, expected - actual)
print('Exact same 19 inherited failure IDs; full-suite status remains FAIL')
PY
```

4. Read-only TLS and offline renewal. Any dry-run effect falsifies scope; no trust
   override is permitted. Live state can change independently: record actual output
   and explain a changed certificate instead of modifying it.

```sh
"$wp13_python" ops/tls/renew.py --dry-run > evidence/mvpfix/wp13/fresh/dry-run.json
"$wp13_python" ops/tls/verify.py ga0-alienware-rtx4070ti.tailnet.aisight.us 7861 > evidence/mvpfix/wp13/fresh/live-7861.json
printf '%s\n' "$?" > .wp13runtime/raw/fresh-live-7861.exit
"$wp13_python" ops/tls/verify.py ga0-alienware-rtx4070ti.tailnet.aisight.us 7862 > evidence/mvpfix/wp13/fresh/live-7862.json
printf '%s\n' "$?" > .wp13runtime/raw/fresh-live-7862.exit
```

Expected dry-run effects 0. Earlier observations: 7861 self-signed, exit 1, leaf
expires 2028-10-20 03:04:57 UTC; 7862 trusted, exit 0, leaf expires 2026-12-09
21:32:04 UTC. Do not label an expected trust failure as trusted service readiness.

5. Hygiene: no screenshot/evidence rewrite, no root verification files, raw log
   ignored. Regenerate the relocated log OFFLINE and compare the full numeric rows
   with the base's retained source (direct comparison, no new hashes).

```sh
bash scripts/check_verify_layout.sh
git diff --exit-code -- evidence/mvpfix/wp2
git check-ignore evidence/mvpfix/wp3/raw/chunks.json
"$wp13_python" prototypes/streaming-diarization/capture-guards/chunks.py > .wp13runtime/raw/fresh-chunks.txt
"$wp13_python" - <<'PY'
import json, subprocess
from pathlib import Path
old = json.loads(subprocess.check_output(['git','show','d8ee6f4109f277a22bfbca298da9ebdf85b218c8:evidence/mvpfix/wp3/chunks.json']))
new = json.loads(Path('evidence/mvpfix/wp3/raw/chunks.json').read_text())
assert old == new and len(new) == 17640
print('17640/17640 numeric rows equal; 0 decoder calls')
PY
git diff --check
```

6. Read the two updated operator documents (`e2e-smoke-for-operator.md`,
   `demo-script.md`) and confirm cross-lane overlap is expected, the never-overlap
   workaround is obsolete for the per-lane build, and attended proof is not claimed.
   Confirm TLS runbook has explicit unexecuted actions, 7861 unit/reload blocker,
   rollback, Chrome trust steps, and pending I10-D05 authority.

7. Write `docs/verify/wp13/VERIFY-RESULT.md`: fresh pass/fail by gate, exact counts,
   timings, actual TLS results and exit codes, failure-set comparison, tested SHA,
   limitations/deviations. Put compact fresh summaries in `evidence/mvpfix/wp13/fresh/`;
   raw test logs stay ignored. Preserve negative results. Do not edit other WPs.
   Commit these verification artifacts locally; confirm clean tree and final SHA.
   Stop any process you started. No root VERIFY copies.

8. Final report IN THIS PANE ONLY, <=60 lines: branch + final SHA; prototype verdict;
   changed files; exact counts; measurements; full-suite FAIL with 19 base-reproduced
   failures; live 7861 trust/reload blocker and what owner authority is needed;
   deviations (work-package docs under docs/verify/wp13 per WP13-specific layout).
   No message to Fable's pane is required. Do not claim issuance/renewal/Chrome proof.
