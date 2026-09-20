# R4-3 command record

Base: `89f833acd4c654dd702664a17ed19783a2999c95`, branch `round4/gap`.
Python import resolved to this clone. Decoder requests: **0 / budget 0**.

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/gap/run.py --output evidence/round4/gap/diagnosis.json
```

Production CPU ONNX: `/Users/gao/.local/share/moss-transcribe-diarize/live/voxceleb_resnet152_LM.onnx`.
Manifest-pinned SHA-256: `5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8`.
Counts: 26 causal spans; 15 final saved spans; 1 terminal-only unresolved span.

## Focused controls

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> -m pytest -q -p no:cacheprovider \
  tests/test_r4_gap_terminal_identity.py
```

Result: `1 passed, 1 xfailed in 0.42s`.

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> -m pytest -q -p no:cacheprovider \
  --runxfail tests/test_r4_gap_terminal_identity.py
```

Result: `1 failed, 1 passed in 0.44s`. Failure is the required R4-3 violating control:
the 0.27-second same-partition return remains `None` while its 2.5-second partner matches.

Focused identity/lane batch first ran 123 tests and produced `120 passed, 1 xfailed,
2 failed`: both failures were the known standalone collection-path issue in
`test_draft_uses_separate_pcm_skips_zero_and_isolates_failure`, which imports bare
`_browser_workspace_fixtures` when Phase-2 is not collected. No R4-3 path failed. The
causal terminal/album population then ran `104 passed, 18 deselected, 1 xfailed`.

Retained S17 source copies and exact source paths are in `retained/PROVENANCE.json`.

## Full-suite gate

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> -m pytest -q -p no:cacheprovider tests
```

Result: `2117 passed, 5 skipped, 1 xfailed, 21 warnings, 37 subtests passed in 196.05s`.

```sh
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Results: `311/311`; TypeScript clean; vite clean. Build changed no tracked asset.
