# Fix I2 verification

Run from `/private/tmp/moss-round4-20260920/fix-i2` with no decoder, provider,
network, or tunnel process.

```sh
test "$(git branch --show-current)" = round4/fix-i2
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
plan_out=$(mktemp /tmp/fix-i2-s17-plan.XXXXXX.json)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  prototypes/s17-identity-rerun/run.py --plan-only --out "$plan_out"
/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python -c \
  'import json,sys; p=json.load(open(sys.argv[1])); assert p["planned_requests"] == 184' \
  "$plan_out"
git diff --stat 85aec978 -- moss_transcribe_diarize
git diff --name-only 85aec978 -- \
  moss_transcribe_diarize/app/windowed_transcription.py \
  moss_transcribe_diarize/app/phase2_file.py \
  moss_transcribe_diarize/app/phase2.py
git grep -nE 'sk-or-v1-[A-Za-z0-9]{16,}|OPENROUTER_API_KEY=[A-Za-z0-9]'
git diff --check 85aec978
```

Expected: backend at least 2,201 passed, 0 failed, 5 skipped, 2 xfailed;
frontend 312/312; typecheck/build clean; S17 plans 184 requests without making
one; product diff names only the three I2-owned modules; prohibited-file and
secret searches print nothing; diff check is clean. Falsified by any capture
row lacking Meeting owner, run owner, schema version, or raw-derived source lane,
or by changed proposal bytes with capture off, on, or writer refusal.
