# Fresh verification — pane 3.4

Run from `/private/tmp/moss-round3-20260919/publication`. Do not edit product or test files. Record literal commands, results, counts, timings, final SHA, and PASS/FAIL in `docs/verify/wp50-wp51/VERIFY-RESULT.md`.

1. `git branch --show-current && git rev-parse HEAD && git merge-base --is-ancestor a7a738cf9f9ff246f64c52c112e0bf597ba58241 HEAD && git status --short`
   - Expect branch `round3/publication`, base ancestry success, clean tree.
2. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c "import moss_transcribe_diarize as m; print(m.__file__)"`
   - Expect import inside this clone.
3. `/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests`
   - Expect 2,055 passed, 5 skipped, 37 subtests; zero failures/errors.
4. `/usr/bin/time -p npm --prefix frontend test -- --run`
   - Expect 310/310 tests across 28 files.
5. `npm --prefix frontend run typecheck && npm --prefix frontend run build && git diff --check && git status --short`
   - Expect clean typecheck/build/diff and no generated-asset drift.
6. `git diff --unified=0 a7a738cf9f9ff246f64c52c112e0bf597ba58241..HEAD -- . ':(exclude)moss_transcribe_diarize/app/frontend_assets/**' ':(exclude)docs/verify/**' | rg '^[+-][^+-].*(QUALITY_BOUNDS|ALBUM_MIN_MATCH_SCORE|MARGIN|LIVE_MEETING_LIMIT|min_segment_samples|durable.admission|readiness|poll.*delay|Refresh sentinel|frame protocol)' || true`
   - Expect no output. Any changed invariant line, wrong custody, dirty generated asset, or test/type/build failure is FAIL.

No decoder, GPU, network, tunnel, push, merge, deploy, or GitHub write is needed or allowed.
