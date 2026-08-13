# Context — Phase 1 ticket #4

Iteration 2. Reference build configuration and four complete font families transferred verbatim.

## Where things stand

- Branch: `afk/t4-*`, cut from `dev` at `a05a7f6`. Worktree 4 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- `frontend/` now holds the reference's three build-config files and all 11 `woff2` files across
  Inter, Source Serif 4, IBM Plex Mono, and Fraunces. `/` still serves the inline Subtitle Studio.
- Live routes are default-off and enabled via `create_app(live_enabled=True, ...)`.

## Issue #4 acceptance checklist (verbatim scope)

- [x] Reference `vite.config.ts`, `tsconfig.json`, `package.json`, and four bundled `woff2` font
  families lifted verbatim.
- [ ] `/` serves the new app; `/static/**` serves the bundle; `/static/app.js` is stable.
- [ ] Inline Subtitle Studio moves to `/studio`, byte-unchanged.
- [ ] `/live` remains an unadvertised operator diagnostic.
- [ ] Fonts are self-hosted; no page makes a CDN request.
- [ ] Built bundle is committed; deploy needs no Node toolchain.
- [ ] Development uses `vite build --watch` behind FastAPI; no second-origin Vite dev server.
- [ ] Typecheck and transferred reference component tests run in local validation.
- [ ] Provider-manifest `source_revision` is re-finalized for the host.

Scope boundary: shell and serving only. Transcript rendering belongs to #7.

## Read these first (do not re-derive)

| Path | Why |
|---|---|
| `docs/phase1-afk-charter.md` | **Binding.** Authority, limits, capture spec §4, fidelity method §5, gates §6, attended checklist §7 |
| `.wayfinder/map-001-phase1-chrome-client.md` | Premises C1–C11 and the decision index |
| `.wayfinder/tickets/` | The 12 closed decision tickets with full rationale |
| `docs/research-chrome-capture-mvp-2026-08-03.md` | Gate 1 measured verdict. Frame geometry, worklet clock anchoring, activation ordering, error taxonomy — all settled |
| `AGENTS.md` | Measure-before-implement is mandatory |
| `CONTEXT.md` | Domain glossary. Use its vocabulary |

## Known traps, already paid for once

- `scripts/ralph-afk/` holds a **stale 285 KB `context.md` and an old PRD** from the earlier
  native-helper effort. **It is not yours. Ignore it.** Your loop lives in `scripts/afk-t4/`.
- Frame geometry is deploy-manifest data, never a code constant.
- 429 on the v2 lane path is non-terminal; on the legacy mono path it is terminal. Only ever send
  v2 lane frames.
- `setInterval` in a backgrounded tab collapses to ~1/min. Worklet port messages do not.
- `source_revision` comes from the provider manifest and must be re-finalized per host.

## Validation baseline (iteration 1)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q \
  tests/test_live_api.py tests/test_live_auth.py tests/test_live_mixer.py -p no:cacheprovider
# PASS: 65 passed, 351 subtests in 7.33 s. Covers current live HTTP/auth/mixer contracts;
# does not cover the frontend, static routes, browser behavior, or real capture.

PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
# ENVIRONMENT-BLOCKED: 964 passed, 4 skipped, 4 failed, 11 errors, 383 subtests in 124.97 s.
# Missing prerequisites: built Swift products and the real benchmark harness_cache.npz archive.
# Two macOS UDS tracer failures also occurred after the missing-product setup errors; re-evaluate
# only after building both Swift products. This command covers the whole collected Python suite.

bash -n scripts/afk-t4/ralph-afk.sh
# PASS. Syntax only; it does not execute the loop.
```

The prescribed `.venv/bin/pytest` path does not exist in this treehouse worktree. The repo's
verified pyenv Python 3.12.10 has pytest 9.0.2 and the needed Python dependencies, so use
`python3 -m pytest` here. Do not count the full suite green until its documented local artifacts
exist and the command passes.

## Reference transfer evidence (iteration 2)

`cmp -s` passed for all 14 transferred files, and source/target SHA-256 values match line-for-line
in `evidence/phase1/t4/iteration-02-reference-transfer.txt`. This proves byte identity only; it
does not prove that the frontend builds or that pages load the fonts without CDN requests.

## Ranked candidates

1. Lift the smallest reference shell/component set needed to build, without transcript rendering.
2. Add FastAPI serving cutover with route regression tests for `/`, `/studio`, `/static/**`, and
   retained `/live`.
3. Restore full-suite prerequisites (Swift products plus real benchmark corpus) and rerun baseline
   before merge.
