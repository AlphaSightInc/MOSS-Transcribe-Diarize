# P-F2F6 evidence receipt

Frozen candidate: `0de56e1a139f833f12cb23224f10e1668be2efd9`

## Measured prototype

- Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/p-f2f6/run.py --out evidence/round4/p-f2f6/prototype-output.json`
- Result: F2 `SUPPORTED`; F6 `SUPPORTED`; every asserted control passed.
- Contained case: raw `S01` 32,000 samples; raw `S02` 4,320 samples. Frozen capture emitted only `S01`; prototype raw stream emitted both and mapped raw index 1 to no normalized partition.
- Normalized `system:S01`: member raw indexes `[0]`; 32,000 samples; floor 8,000; score `speaker-0001=0.909091`; margin `0.909091`; published `speaker-0001`.
- Capture off/on/writer-refusal publication bytes: identical on frozen and prototype seams.
- Decoder requests: 0. Tunnel: none. Network calls: 0.

## Violating controls

- Forced command: `python -m pytest -q -p no:cacheprovider --runxfail tests/test_p_f2f6_violating_controls.py`
- Frozen result: **2 failed / 2** in 0.36 s. F2 failed because frozen capture labels were `[S01]`; F6 failed on `BoundedCausalIdentityPreparer` in `terminal_label_capture.py`.
- Normal command with existing labels2 controls: **3 passed, 2 expected xfailed** in 2.12 s.

## S17 zero-request plan

- Command: `python prototypes/s17-identity-rerun/run.py --plan-only --out evidence/round4/p-f2f6/s17-identity-plan.json`
- Population: 3 sessions; 360 lane-seconds; `ceil(360 × 0.51) = 184` planned requests.
- Capture status on frozen product: `REQUIRED-BEFORE-RUN`.
- Required streams: raw terminal spans; raw-to-normalized mapping; native normalized partitions.
- `--run --budget 184` without an endpoint refused first on missing raw capture, exit 1; no output directory, stack, request, tunnel, or network call.

## Full gates

- Backend: `python -m pytest -q -p no:cacheprovider tests` — **2,167 passed, 5 skipped, 4 expected xfailed, 0 failed, 37 subtests passed** in 205.87 s (wall 207.14 s). Two xfails are the new F2/F6 controls; two pre-existed.
- Frontend: `npm --prefix frontend test -- --run` — **312/312 passed**, 28 files, 3.30 s (wall 4.16 s).
- TypeScript: `npm --prefix frontend run typecheck` — clean, wall 1.44 s.
- Vite: `npm --prefix frontend run build` — clean, wall 0.75 s; no generated product diff.
- `git diff --check` — clean.

## Fresh-context gate

- Independent no-history verifier: **PASS**.
- Backend rerun: **2,167 passed, 5 skipped, 4 expected xfailed, 0 failed,
  37 subtests** in 212.43 s.
- Frontend rerun: **312/312** in 2.93 s; typecheck/build/diff clean.
- Full receipt: `docs/verify/p-f2f6/VERIFY-RESULT.md`.
