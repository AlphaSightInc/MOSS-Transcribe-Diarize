# R4-4 evidence receipt

- Source revision: `89f833acd4c654dd702664a17ed19783a2999c95`.
- Branch: `round4/jamie`.
- Interpreter: protected worktree venv required by COMMON; import resolved in clone.
- CPU model SHA-256: `5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8`.
- Reference SHA-256: `72a6173d92323d5c7ff5e6ba084063970966d4bd4e146c23e24d57949ad1a01b`.
- Scorer: `r4-jamie-policy-scorer-v1`.
- Decoder requests: **0**. GPU/tunnel/playback: **none**.

Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/jamie/run.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
bash scripts/check_verify_layout.sh
git diff --check
```

Exact final gates: backend 2,116 passed / 5 skipped / 2 expected xfailed /
37 subtests / 0 failed (198.39 s); frontend 311/311 (3.03 s); TypeScript and
Vite clean; layout and diff checks clean. See `results.json` for full policy state.
