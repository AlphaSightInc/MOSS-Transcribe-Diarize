# Fresh verification — fix publication

Run from `/private/tmp/moss-round3-20260919/fix-publication`. Do not edit product, test, evidence, or status files. Record literal commands, results, exact counts, timings, tested SHA, and PASS/FAIL in `docs/verify/fix-publication/VERIFY-RESULT.md` only.

1. `git branch --show-current && git rev-parse HEAD && git merge-base --is-ancestor 738cdfdde092b8ba9341179fb1d33e1c34cbd24c HEAD && git status --short`
   - Expect branch `round3/fix-publication`, base ancestry success, and a clean tree.
2. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c "import moss_transcribe_diarize as m; print(m.__file__)"`
   - Expect the imported package path inside this clone.
3. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests/phase2/test_export_oracle.py`
   - Expect 84/84 passed. This includes 10/10 five-format live/file healthy controls; JSON must equal API identity and human-readable formats must contain no literal `S00`.
4. `npm --prefix frontend test -- --run src/lib/transcriptExport.test.ts src/lib/speakerMap.test.ts src/components/MeetingHistory.test.tsx`
   - Expect 51/51 passed. This checks canonical JSON fields, all actual History downloads, display mapping, and reserved labels.
5. `/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests`
   - Expect 2,105 passed, 5 skipped, 37 subtests; zero failures/errors.
6. `/usr/bin/time -p npm --prefix frontend test -- --run`
   - Expect 311/311 tests across 28 files.
7. `npm --prefix frontend run typecheck && npm --prefix frontend run build && git diff --check && git status --short`
   - Expect clean typecheck/build/diff and no generated-asset drift.
8. `scripts/check_verify_layout.sh && git diff --unified=0 738cdfdde092b8ba9341179fb1d33e1c34cbd24c..HEAD -- . ':(exclude)moss_transcribe_diarize/app/frontend_assets/**' ':(exclude)docs/verify/**' | rg '^[+-][^+-].*(QUALITY_BOUNDS|ALBUM_MIN_MATCH_SCORE|MARGIN|LIVE_MEETING_LIMIT|min_segment_samples|durable.admission|readiness|poll.*delay|Refresh sentinel|frame protocol)' || true`
   - Expect layout PASS and no changed invariant line. Any wrong custody, dirty generated asset, changed invariant, focused/full-suite/typecheck/build failure, JSON/API mismatch, human-readable sentinel leak, or reserved-label regression is FAIL.

No decoder, GPU, network, tunnel, push, merge, deploy, GitHub write, or peer message is needed or allowed.
