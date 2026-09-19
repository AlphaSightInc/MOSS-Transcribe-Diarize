# Fresh verification — PANE 3.3

Run literally from `/private/tmp/moss-round3-20260919/runner`. Do not edit production or
tests. Record every command and exact result in
`docs/verify/wp49-wp53/VERIFY-RESULT.md`.

1. `git branch --show-current && git status --short`
   - Expect `round3/runner` and no status output.
2. `prototypes/durable-batch-owner-p2/run.sh`
   - Expect exit 0, verdict `SUPPORTED`, both arms 40 retained + 61 new = 101 unique,
     five violating controls refused before decode/publication, cancellation order preserved.
3. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests`
   - Expect 2,052 passed, 5 skipped, 37 subtests, 0 failed.
4. `npm --prefix frontend test -- --run`
   - Expect 28 files and 288 tests passed, 0 failed.
5. `npm --prefix frontend run typecheck`
   - Expect exit 0.
6. `npm --prefix frontend run build`
   - Expect exit 0.
7. `git diff --exit-code && git status --short`
   - Expect exit 0 and no status output (the prototype result must reproduce byte-for-byte).

Falsify on any nonzero exit, count mismatch, dirty output, prototype `REJECTED`, violating
control reaching decode/publication, replay outside windows 40–100, duplicate/missing segment,
second publication, URL refetch, cancellation-order change, or retained terminal artifacts.
