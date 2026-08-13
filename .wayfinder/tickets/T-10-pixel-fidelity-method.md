---
id: T-10
map: map-001-phase1-chrome-client
title: How pixel fidelity is proved
type: prototype
status: open
assignee:
blocked_by: [T-05]
---

## Question

The operator's requirement is the reference design "pixel by pixel exactly". That is only a
requirement if it is checkable. What is the method, and what is the tolerance?

Resolve:

1. **The oracle.** Can the reference actually be run to compare against? It is a Swift/Vapor
   app: `./scripts/run_app.sh` launches the entitled packaged app and opens
   `http://127.0.0.1:8090/`. Confirm it runs on this machine, or fall back to rendering its
   built `ProjectResources/Frontend/` bundle statically. Without a running oracle there is
   nothing to diff against.
2. **The method.** Screenshot diff at fixed viewport(s) with a stubbed transcript fixture?
   Computed-style comparison per component? Both? Name the tool and where the baselines live.
3. **Tolerance and exemptions.** Antialiasing and subpixel text rendering will differ; a
   0-pixel bar is not achievable and demanding it makes the gate useless. Set a real
   threshold. Then list the **legitimately exempt** regions: T-05's dropped controls, the
   changed layout where `HistoryPanel` / `SummaryView` / `LlmSettingsModal` are absent, and
   T-06's brand-new preflight screen.
4. **What fidelity means where reference pixels do not exist.** For the preflight screen and
   the shared-token entry, there is nothing to diff. Define the standard instead — the
   reference's own tokens (its CSS custom properties, type scale, spacing, and the four
   bundled font families) reused verbatim, reviewed by eye.
5. **Where the gate runs.** Local pre-promotion check, or part of the loop's validation
   commands? Note the reference already ships component tests (`vitest`) that transfer with
   the components — those prove behaviour, not pixels, and both matter.
6. **The honest fallback.** If a true pixel gate proves disproportionate, what is the
   defensible substitute — a reviewed side-by-side screenshot set per component, archived as
   evidence? Say so rather than shipping a gate that always passes.

This ticket exists because "pixel-perfect" is the operator's single most emphatic
requirement, and an unfalsifiable version of it would let the build drift while every gate
stayed green.

Ground truth: reference `README.md` §Quick Start / `scripts/run_app.sh`,
`frontend/src/styles/index.css`, `frontend/public/fonts/`; T-05's control-disposition table.
