# R4-10 qualification bundle runtime

## Verdict

**Runtime: RUNNABLE. Bundle today: BLOCKED.** The disposable CPython 3.12.12
interpreter at `/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python`
uses SQLite 3.53.4 and starts the unmodified candidate at `71f23c0c`. The default
qualification bundle cannot complete without an authorized decoder endpoint: its
`stack()` requires upstream `/metrics` before it starts the candidate and otherwise
opens its own SSH tunnel. No such endpoint was used here.

This is runtime/preflight evidence only: zero decoder requests, no GPU, tunnel, or
external provider. It is not transcript, browser-case, capacity, or quality evidence.

## Structural contract

- **Question.** Which parts of `tools/qualify/run.py` require a real candidate stack,
  and can the exact SQLite runtime host that stack without weakening the pin?
- **Minimum primitives.** The exact interpreter/SQLite linkage; one production stack
  launched without the local-stack pin override; the consumed 30-minute manifest;
  root plus bootstrapped descriptor; and the mode-0600 operator socket. Removing one
  leaves the runtime version, startup, configured capacity, service surface, or
  host control unknown.
- **Invariant.** The runtime Python is the process that launches `run.py`, so its
  module `sqlite3.sqlite_version` is `3.53.4`. The source checkout is selected by
  `PYTHONPATH=.`, and no phase2 pin, module, or manifest is changed. The direct probe
  sends no frame/file/URL request and points VLLM at dead `127.0.0.1:9`.
- **Assumptions / unknowns.** An owned R4-10 decoder later exposes both `/metrics`
  and `/version` on loopback. The actual 2,238-request population, transcript scores,
  browser predicates, capacity, and file outcomes are unmeasured until that bounded
  run. Existing Chrome launch proves browser availability, not case correctness.
- **Falsifier.** Stop if the exact interpreter reports any SQLite version other than
  3.53.4; root or bootstrapped descriptor is not 200; the socket is absent/non-0600;
  the copied manifest fails admission; a required port is occupied; Chrome cannot
  launch; or the future owned upstream lacks metrics/version.
- **Tool decision.** `Phase2Store.open(':memory:')` is the smallest exact pin seam.
  The direct CLI stack, not `run_local_stack.py`, proves no local pin override is
  needed. The latter always assigns `phase2.REQUIRED_SQLITE_RUNTIME` and is therefore
  unsuitable for this question, even though it assigns the same value under 3.53.4.

## 1. Gate map

`run.py` does **not** need a stack for every gate. Pure offline gates are
`tree_clean`, `python_import`, `asset_parity`, `pytest`, `frontend`,
`bundle_helpers`, `typecheck`, and `verify_layout`. Default non-long execution also
records `file_30min` as `SKIP` and `capacity_2x1800` as `REQUIRED-NOT-RUN`.

After `stack()` is ready, the stack-dependent gates are `workspace` (and rows 1–14),
`demo_lanes`, `lifecycle`, `reshare`, `identity_stress`, `level_ladder`,
`browser_stress_all`, `file_6min`, `file_3min_formats`, `file_failures`, and
`capacity_2x300`. `--long` additionally runs `file_30min` and `capacity_2x1800`.
Browser, file, and capacity benches start auxiliary local services, but all still
need the owned decoder proxy at `19125`; browser also starts its own candidate stack
at `17826`.

## 2. Runtime-host result

**RUNNABLE preflight.** Host Python reproduces the exact refusal:
`3.50.4 != 3.53.4`. The disposable Python opens `Phase2Store` unchanged and imports
this checkout. With the actual source manifest, and separately with the bundle's
admitted 30-minute copy, the direct Account process returned root 200 and a
bootstrapped descriptor 200. Its operator socket was `0600` and `status --json`
reported `readiness=ready`.

There is no dedicated `/health` route in `phase2.py`; root 200 is the HTTP liveness
surface, while `/api/live/descriptor` requires workspace bootstrap. The full bundle
remains **BLOCKED today** only by the deliberately absent decoder metrics/provider,
not by SQLite, assets, browser executable, port, socket, or manifest admission.

## 3. Exact R4-10 activation and launch

From this checkout, after an owned loopback decoder has been authorized and started:

```sh
cd /private/tmp/moss-round4-20260920/bundle-runtime
R4_RUNTIME=/private/tmp/moss-round4-20260920/runtime-prefix/venv
export PATH="$R4_RUNTIME/bin:$PATH"
export PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 MOSS_TEST_REAL_SQLITE=1
unset MOSS_LLM_UPSTREAMS GEMINI_API_KEY GOOGLE_API_KEY OPENAI_API_KEY MOSS_LLM_UPSTREAM_API_KEY
npm ci --prefix frontend
R4_DECODER_PORT=<owned-loopback-port-with-metrics-and-version>
"$R4_RUNTIME/bin/python" tools/qualify/run.py --budget 2238 \
  --decoder-upstream-port "$R4_DECODER_PORT" \
  --ladder /Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/moss-mvp-review/evidence/independent-review/probes/ir_lane_ladder.py \
  --out evidence/round4/bundle-runtime/qualification
```

`--decoder-upstream-port` is mandatory for this run: omitting it makes `run.py`
attempt its own SSH tunnel. `2238` is the current non-long planner minimum:
`ceil((3457 lane_seconds * 0.51 + 11 file windows + 16 browser cases) * 1.25)`.
The runtime's `_sqlite3` has an embedded scoped-library rpath; do not set a global
SQLite or `DYLD_LIBRARY_PATH` override.

## 4. Other host prerequisites

- **Ports: RUNNABLE at observation.** `18125`, `19125`, and `17825`–`17829` were free.
- **Tape/storage: RUNNABLE at observation.** The bundle's copied manifest admits
  57,600,000 B (1,800 s) per tape; the state filesystem had 251,971,907,584 B free.
- **Frontend: RUNNABLE.** Current clone source passed 312/312 frontend tests,
  typecheck, and production build. A fresh clone needs `npm ci --prefix frontend`
  before the bundle's asset parity/frontend gates.
- **Browser: RUNNABLE preflight.** Playwright's bundled Chromium is absent, but the
  bench selects `/Applications/Google Chrome.app/.../Google Chrome`; headed launch
  and close passed. This does not run any decoder-backed browser predicate.
- **Operator socket: RUNNABLE.** The stack creates its state-local socket, avoiding
  the shared default path and its ownership conflict.
