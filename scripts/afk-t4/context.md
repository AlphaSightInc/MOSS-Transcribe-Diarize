# Context — Phase 1 ticket #4

Iteration 11. The ticket branch contains current `dev`, and the complete focused ticket set passes
on that merged result. The branch is published at `private/afk/t4-frontend-shell`; issue #4 has a
criterion-by-criterion evidence comment with explicit non-coverage and both unrelated full-suite
exceptions. The issue remains open. Authorized host manifest finalization is the only unchecked
ticket criterion and remains outside this loop's read-only host authority. The loop posted the
exact fail-closed operator command and requested raw host evidence at issue comment
`#issuecomment-5277087183`. No evidence appeared by iteration 11. The charter's three-consecutive-
iteration blocker threshold is now reached, and the loop escalated to the supervisor/operator at
`#issuecomment-5277116813`; no further loop-authorized implementation work remains.

## Where things stand

- Branch: `afk/t4-*`, cut from `dev` at `a05a7f6`. Worktree 4 of 6 (treehouse pool).
- Published branch: `https://github.com/aiSight-us/MOSS-Transcribe-Diarize/tree/afk/t4-frontend-shell`.
- Current `dev` (`8fec841`) is an ancestor of the validated ticket result (`e8c8c4f`); the required
  merge was therefore a no-op. Iteration 8 ran all ticket-focused gates while holding the shared
  merge lock.
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
  finalization remains authorized-operator work; the remote host is read-only to this loop.
- The published branch resolves to `9a1d70e54153e380e9802fbb446bbcd3f5e44ed8`. The exact operator
  arguments dry-run successfully at that revision and the focused finalizer suite passes 26/26.
  Issue comment `#issuecomment-5277087183` hands the operator the non-dry-run command guarded by an
  exact-HEAD check and asks for raw stdout plus the finalized SHA/source revision. The loop did not
  access or mutate the host.
- Iteration 11 found no operator evidence after that handoff. It reached the charter's three-
  consecutive-iteration blocker threshold, posted the required supervisor escalation as
  `#issuecomment-5277116813`, and read it back under the guarded `yugao-aisight` actor. Raw evidence
  is `evidence/phase1/t4/iteration-11-blocker-escalation.txt`.
- Both Swift products build, and the hash-pinned 92-unit archived Alphabet cache is provisioned
  from the local L2 Stage-0 corpus. The full Python collection runs without setup errors: 980
  passed, 2 skipped, 2 failed, and 475 subtests passed. One failure is the expected L15 product
  drift refusal because ticket #4 changes `server.py` after its pinned source commit. The other is
  the same out-of-scope macOS lifecycle tracer failure seen in iteration 1; a focused retry also
  failed because `NSRunningApplication(processIdentifier:)` returned nil for the socket peer PID.
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

## Full-suite baseline (iteration 7)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
# 980 passed, 2 skipped, 2 failed, 475 subtests in 130.98 s. Zero setup errors.
# Expected L15 drift refusal: its frozen baseline rejects every product-tree change after
# 9089b332, including ticket #4's server route cutover. Persistent out-of-scope failure:
# test_built_macos_app_finishes_launch_and_honors_application_terminate cannot resolve the socket
# peer PID through NSRunningApplication; a focused rerun also failed. Do not weaken either gate.

bash -n scripts/afk-t4/ralph-afk.sh
# PASS. Syntax only; it does not execute the loop.
```

The prescribed `.venv/bin/pytest` path does not exist in this treehouse worktree. The repo's
verified pyenv Python 3.12.10 has pytest 9.0.2 and the needed Python dependencies. Both Swift
products were built separately. The ignored `data/real` link uses the L2 Stage-0 corpus with the
required archived cache SHA-256 `fd13bacb...`; the canonical checkout's newer `327f3328...` cache
has 55 units and is not a valid substitute for the 92-unit legacy-ingest contract.

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

## Full-suite prerequisite evidence (iteration 7)

`evidence/phase1/t4/iteration-07-full-suite-prerequisites.txt` records both separate Swift product
builds, the correct archived-corpus hash, the restored 92-unit focused test, and the final full
suite result. `iteration-07-full-pytest.xml` is the raw JUnit report for all 1,459 reported test
and subtest nodes: 980 passed plus 475 passing subtests, 2 skipped, 2 failed, zero errors. The run
does not make the full suite green; it distinguishes its two remaining non-ticket failures from
the setup errors that blocked iteration 1. The required out-of-scope disclosure is issue comment
`#issuecomment-5276956691`; it does not claim completion or change issue state.

## Merged-result evidence (iteration 8)

`evidence/phase1/t4/iteration-08-merged-validation.txt` records lock acquisition, the required
no-op merge, and proof that `dev` is an ancestor of the tested ticket result. Clean frontend install,
typecheck, target test, deterministic build, reference byte checks, and oracle tests all pass. The
combined serving/live/manifest suite passes 130 tests plus 361 subtests, and a host-shaped manifest
dry-run stamps the tested 40-character SHA without changing its input or creating output. This does
not finalize the host manifest or add browser/deployment/attended-capture evidence.

## Ranked candidates

1. **BLOCKED on authorized operator input:** await raw host finalization evidence requested in
   issue comment `#issuecomment-5277087183` and escalated after the three-iteration threshold in
   `#issuecomment-5277116813`. Do not repeat the dry-run, mutate the read-only host, close the issue,
   or substitute local fixture evidence for the host-owned manifest.

No safe loop-authorized implementation candidate remains. The charter's stop threshold has been
reached and the required supervisor comment has been posted. Resume only if authorized raw host
evidence appears; otherwise record the unchanged external-input blocker without redoing work.
