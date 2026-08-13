# Context — Phase 1 ticket #4

Iteration 6. The provider-manifest finalization path is now locally audited and documented with
all required flags; the host-owned manifest still must be finalized with the reviewed post-merge
SHA by an authorized operator.

## Where things stand

- Branch: `afk/t4-*`, cut from `dev` at `a05a7f6`. Worktree 4 of 6 (treehouse pool).
- All 12 wayfinder decision tickets are **closed**. Design is settled; this is execution.
- `frontend/` holds the reference's three build-config files, entry HTML, entrypoint, complete
  stylesheet, font license, logo, and all 11 `woff2` files. All transferred reference files are
  byte-identical. The reference lockfile was stale (`npm ci` rejected missing transitive entries),
  so the target lockfile was regenerated from the verbatim `package.json` and clean-install passes.
- `frontend/src/App.tsx` is an inert three-column shell: no API calls, transcript data, `/live`
  link, capture behavior, or file behavior. Those remain in their assigned tickets.
- `ProjectResources/Frontend/` is a committed production build with stable `/static/app.js`,
  stylesheet, source map, logo, and all fonts. FastAPI serves its `index.html` at `/` and mounts
  the directory at `/static` using a checkout-relative path independent of process cwd.
- The byte-unchanged inline Subtitle Studio is at `/studio`. `/live` remains default-off and is
  still enabled only via `create_app(live_enabled=True, ...)`; the new shell does not link to it.
- `LOCAL_DEPLOYMENT.md` documents `npm ci`, `vite build --watch`, the companion FastAPI process,
  and the prohibition on using/opening the second-origin Vite dev server for capture/API work.
  A measured watch rebuild completed in 25 ms and the running FastAPI service returned the exact
  committed bytes at `/` and `/static/app.js`. Root `.gitignore` excludes the installed
  `frontend/node_modules/` development dependency tree.
- The documented provider-manifest command now supplies all required identity-policy flags. Its
  prior form omitted `--album-admission-seconds` and `--birth-min-seconds` and exited before work.
  The corrected command dry-runs against a host-shaped provisional fixture, stamps a checkout SHA,
  regenerates and admission-checks hashes, and leaves both input and output untouched. Actual host
  finalization remains post-merge operator work: the final SHA does not exist yet and the remote
  host is read-only to this loop.
- Target typecheck and its shell test pass. Both reference component suites pass at the oracle;
  neither is imported because `TranscriptPane` belongs to #7 and `LlmSettingsModal` is out of
  Phase 1. The verbatim target `package.json` therefore remains unchanged.

## Issue #4 acceptance checklist (verbatim scope)

- [x] Reference `vite.config.ts`, `tsconfig.json`, `package.json`, and four bundled `woff2` font
  families lifted verbatim.
- [x] `/` serves the new app; `/static/**` serves the bundle; `/static/app.js` is stable.
- [x] Inline Subtitle Studio moves to `/studio`, byte-unchanged.
- [x] `/live` remains an unadvertised operator diagnostic.
- [x] Fonts are self-hosted; no page makes a CDN request.
- [x] Built bundle is committed; deploy needs no Node toolchain.
- [x] Development uses `vite build --watch` behind FastAPI; no second-origin Vite dev server.
- [x] Typecheck and the reference component tests run in local validation.
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

## Reference shell evidence (iteration 3)

`evidence/phase1/t4/iteration-03-reference-shell.txt` records a clean `npm ci`, byte-identity checks
for the six newly transferred reference files, successful typecheck, one focused shell component
test, and a successful Vite production build. The built HTML points to `/static/app.js`,
`/static/styles.css`, and `/static/logo-mark.svg`; built CSS points to all 11 `/static/fonts/**`
assets. A built-page scan found no network resource reference or local path in the source map.
Vite warns that the verbatim config's `__dirname` will be unsupported by a future native config
loader; the current build passes. This does not prove FastAPI serving, the reference project's full
component test suite, or browser rendering.

## Serving cutover evidence (iteration 4)

`evidence/phase1/t4/iteration-04-serving-cutover.txt` records 39 passing app/portal tests plus 10
passing subtests. FastAPI responses match the committed bytes for `/`, `/static/app.js`, and a
nested font; `/studio` matches the pre-cutover SHA-256
`aaa308fa135e8e29ed1d96e9b9417952959c9c0218f783ddd4b62ff249a6e43d`. The full `/live` portal
suite remains green, and the root shell contains no `/live` link. Combined with iteration 3's
built-resource scan, this proves the served page and CSS use only same-origin assets. It does not
prove browser rendering, attended display capture, deployment, or remote-host state.

## Development-loop evidence (iteration 5)

`evidence/phase1/t4/iteration-05-watch-and-component-tests.txt` records a clean `npm ci`, Vite's
initial watch build and a measured rebuild after a source touch, plus a locally-run FastAPI service
returning the exact generated bytes from `/` and `/static/app.js`. Target typecheck and shell test
pass; the oracle's two component suites pass 9/9. The oracle suites do not test target code, and
their components were intentionally not copied: transcript implementation/rendering is #7 and the
LLM modal is out of Phase 1. This evidence does not cover browser pixels, capture, deployment, or
the remote host.

## Provider-manifest evidence (iteration 6)

`evidence/phase1/t4/iteration-06-provider-manifest-finalization.txt` records the old documented
command failing on two omitted required flags, then the corrected tracked command succeeding under
`--dry-run` with the checkout's 40-character SHA. It records regenerated config/manifest hashes,
runtime descriptor admission, unchanged input SHA-256, absent output, and 26/26 focused tests.
This proves post-merge finalization is mechanically ready without pre-merge host mutation; it does
not finalize or inspect the host-owned manifest, deploy, or mutate the remote.

## Ranked candidates

1. Restore full-suite prerequisites (Swift products plus real benchmark corpus) and rerun baseline
   before merge.
2. After merged-result validation, publish per protocol and hand the reviewed merge SHA plus the
   corrected finalization command to the authorized operator. Do not mutate the read-only host.
