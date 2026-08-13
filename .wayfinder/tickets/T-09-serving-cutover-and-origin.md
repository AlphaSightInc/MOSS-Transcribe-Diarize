---
id: T-09
map: map-001-phase1-chrome-client
title: Serving cutover — new app at /, Studio at /studio, one origin
type: grilling
status: closed
assignee: operator+claude
blocked_by: []
---

## Question

C7 and C8 fix the routing and the toolchain. Specify the serving and build cutover, including
the same-origin constraint that browser capture makes non-negotiable.

Resolve:

1. **Route moves.** `/` becomes the new app; today's 1686-line inline `INDEX_HTML`
   ("MOSS Subtitle Studio", Chinese labels, import → processing → subtitle workbench) moves to
   `/studio` unchanged. What serves the Vite bundle — a static mount, or explicit routes? The
   reference's own server contract is a useful precedent: `GET /` serves `index.html`,
   `GET /static/**` serves the bundle, and `/static/app.js` is a *stable* entrypoint.
2. **What happens to `/live`.** The existing server-rendered read-only portal is genuinely
   useful (it is the only thing that works with no build step) and is covered by a full
   mutation battery. Keep it, retire it, or keep it as an operator diagnostic?
3. **Build integration.** C8 lifts the reference's `vite.config.ts` / `tsconfig.json` /
   `package.json` / bundled fonts verbatim into the target's empty `frontend/`. Where does the
   built bundle land in the repo, is it committed or built at deploy, and what does CI/local
   validation run (`npm run typecheck`, `vitest`)? Reuse A-010's server-side static-serving
   pattern only — see `git diff main..acl/IDEA-006--A-010`.
4. **Fonts must be self-hosted.** The reference bundles Inter, Source Serif 4, IBM Plex Mono
   and Fraunces as local `woff2` in `public/fonts/`. Any CDN dependency would break both the
   zero-install promise and pixel fidelity on a network-restricted host. Confirm they carry over.
5. **Same-origin, with the port.** Capture UI and API **must** share one HTTPS origin: that is
   what makes the one-time TLS interstitial click-through work at all, and it avoids CORS while
   giving one origin a single microphone-permission identity. For this deployment the origin
   must include **`:7861`** — omitting it silently targets unconfigured port 443 (a real probe
   error made during the research). State this in the spec so no one repeats it.
6. **Dev loop.** Vite dev server on a different port breaks the same-origin rule and thus
   breaks capture. What is the supported local development story — proxy, or build-and-serve only?
7. **A-010 disposition.** Per C8 it closes as superseded. Record that ruling where the AFK
   loop's Reviewer role will see it (`REVIEW_DECISIONS`), and confirm nothing else depends on it.
8. **Deploy trap, already burned once.** `source_revision` comes from the **provider
   manifest**, so it must be re-finalized per host — a frontend cutover that changes the
   served revision must not silently invalidate the deployed manifest hash.

Ground truth: `moss_transcribe_diarize/app/server.py` (`index`, `favicon`, `INDEX_HTML` at
line ~497); `moss_transcribe_diarize/app/live_portal.py`; reference `README.md` §packaging
contract; `git diff main..acl/IDEA-006--A-010`; target `LOCAL_DEPLOYMENT.md`.

## Resolution

**Deferred to implementer judgement by the operator (2026-08-13); ruled as follows.**

1. **Routes.** `/` serves the new app. Today's inline `INDEX_HTML` Subtitle Studio moves to
   `/studio`, byte-unchanged. `/static/**` serves the Vite bundle, mirroring the reference's
   packaging contract, with `/static/app.js` kept as the stable browser entrypoint.
2. **`/live` is KEPT, as an operator diagnostic.** It is the only surface that works with no
   build step, it carries a full mutation battery, and it is the fallback when the bundle is
   broken. Retiring a certified surface to save a route is a bad trade. It is not advertised in
   the product UI.
3. **Built bundle is committed to the repo**, following the reference's precedent
   (`ProjectResources/Frontend/`). Rationale: the inference host is a Windows box running from a
   checkout under systemd; requiring a Node toolchain on the deploy path adds a new failure mode
   to the GPU host for no gain. Building at deploy is rejected on that basis.
4. **Dev loop: `vite build --watch` plus FastAPI serving the bundle. No Vite dev server.**
   This is forced, not stylistic — a dev server on another port/scheme breaks the same-origin
   rule, which breaks *both* the secure context that `navigator.mediaDevices` requires and the
   one-time TLS interstitial click-through. Watch mode keeps the loop tight while preserving one
   origin. A Vite dev server may be used **only** for pure-presentation work against mocked
   data, never for anything touching capture or the live API.
5. **Origin must always carry `:7861`.** State it in the ADR; omitting it silently targets
   unconfigured port 443, a mistake already made once during the research.
6. **Fonts stay self-hosted** (Inter, Source Serif 4, IBM Plex Mono, Fraunces as local `woff2`).
   A CDN would break both the zero-install promise and pixel fidelity on a restricted host.
7. **A-010 closes as superseded**; record in the control plane's `REVIEW_DECISIONS`.
8. **Deploy trap:** `source_revision` comes from the provider manifest and must be re-finalized
   per host. A frontend cutover that changes the served revision must not silently invalidate
   the deployed manifest hash.
