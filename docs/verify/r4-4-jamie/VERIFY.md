# R4-4 fresh-context verification

Run every command from `/private/tmp/moss-round4-20260920/jamie` with no prior
Python process or imported module state.

```sh
git branch --show-current
git merge-base HEAD 89f833acd4c654dd702664a17ed19783a2999c95
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c "import moss_transcribe_diarize as m; print(m.__file__)"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/jamie/run.py
jq -e '.verdict == "FALSIFIED" and .runtime.decoder_requests == 0 and .denominators.single_180s_source_jamie_sec == 4.221 and .denominators.retained_600s_three_repeat_jamie_sec == 12.663 and .transcript_invariants.word_changes == 0 and .transcript_invariants.timestamp_changes == 0 and ([.policies[] | .merges] | all(. == 0)) and ([.policies[] | .false_births] | all(. == 3))' evidence/round4/jamie/results.json
jq empty prototypes/jamie/snippets.json evidence/round4/jamie/results.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
git diff --check
```

Expected:

- branch `round4/jamie`; merge-base exactly `89f833ac…`;
- import resolves inside this clone;
- fresh CPU prototype prints full state; `jq` succeeds; decoder requests remain 0;
- backend: 2,116 passed, 5 skipped, 2 expected xfailed, 37 subtests, 0 failed;
- frontend: 311/311; TypeScript and Vite clean; diff-check clean;
- `git diff --name-only 89f833ac…` contains no production path.

Falsify the handoff on any count mismatch, production diff, changed threshold, decoder
request, nonzero merge, missing unknown denominator, or if any R4-4 xfail unexpectedly
passes (strict xpass).
