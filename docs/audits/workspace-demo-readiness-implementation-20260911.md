# Workspace demo readiness: D1–D4

Isolated branch `fix/workspace-demo-readiness-20260911`, based on `887e76a0`.
Production is not updated. No host operations. The separate canonical-preview branch
is not included. Identity policy, audio admission, Stop and canonical behavior unchanged.

## Contract

Question: can a first-time viewer tell what is required to start, which meeting is
selected, what happened to each import, and where its result is shown?
Primitives: connection state, current sound level, existing capture readiness,
server meeting state, explicit selection. A connection is not proof of sound;
submission is not completion; background refresh is not user selection.
Invariants: keep both-source Start eligibility and Stop behavior; preserve words and
speaker identities; no invented progress; maintain existing predicate selectors and
header/pane geometry. Unknown: attended operator acceptance and host pixel fidelity.
Falsifiers: microphone-only Start, quiet connected source shown absent, lost batch
items after a rejection, unsolicited navigation, wrong selected mode, or changed
header/pane dimensions. Existing controlled UI/prototype evidence motivates these
small presentation changes; local state tests and built-browser tests check them.

## Changes

**D2 — Capture readiness first.** The UI explicitly states that microphone AND shared
audio are required, and microphone-only capture is unavailable. Each named source
shows not connected, connected/quiet, or connected/receiving sound. The next-step
prompt identifies microphone permission, sharing a tab with audio enabled, speaking,
or playing shared sound. Listening setup is explicitly how the operator listens,
not a source selector. Read-only observers see that capture belongs to another tab.

Connection state comes from successful source attachment, not the sound meter.
Existing Start readiness still requires non-zero readings on both sources; no new
threshold or start mode. Quiet connected shared audio now correctly offers Reshare
and replaces the existing source rather than attempting a second attachment. Stop
code, action and capture-phase attributes are preserved.

**D1 — Selected context.** Topbar uses MOSS as fallback and the selected meeting's
title and actual Live/File-URL mode. New/reset capture clears the old selected title;
reattaching an explicitly selected live meeting preserves its title. Background
history refresh and renaming a different record cannot overwrite current context.
Existing title truncation is retained. A local inline no-wrap/min-width adjustment
on this header's metadata prevents long titles wrapping on mobile. No global CSS.
The transcript-pane implementation, typography, controls and layout are unchanged;
this is the topbar correction described in D1, not an in-pane redesign.

**D3 — Import outcomes.** Existing form retains all predicate-facing fields and
submit button. Its handler moves from inline HTML to the built frontend module.
Each file/URL gets its own outcome and an explicit Open meeting action once accepted.
The module reads real server status until completed/failed/interrupted; it fabricates
no percentage. HTTP rejections show the server reason. Network uncertainty instructs
the user to check history before retrying, rather than falsely claiming rejection.
Later items still submit after an earlier failure. The submit button prevents a
second in-flight batch from the same form. Work on the server continues independently.

**D4 — Selected result.** Explicit history or import Open actions use the same
owner-bound meeting loader, bring the transcript panel into view, and announce the
selected title. Background refresh neither scrolls nor switches the displayed
meeting. The existing guard against opening another meeting during live capture
remains. No new sidebar, summary view or transcript markup.

## Predicate contracts / geometry

Unchanged: `input[name=file]`, `textarea[name=urls]`, exact button text
`Transcribe files and URLs`, capture-phase attributes, Stop action/text/behavior,
scoped `Meeting history` region and its `data-open-meeting` buttons. Import buttons
use their own accessible labels and do not duplicate those data attributes.
No acceptance predicate selector needed updating; no acceptance modules changed.

The old Python test that extracted inline upload JavaScript was replaced by a test
of the actual built bundle. It retains the same four-item sequence, two successes,
one network failure and one HTTP rejection, now also checking per-item explanations.

Built-browser tests compare `.topbar` and `#transcript-panel` width/height against
887e76a0's actual compiled assets at 1280×800 and 390×844, after the same extraction
used by fidelity. Both match, including a very long selected title. Initial mobile
measurement exposed +26 px header wrapping; the scoped adjustment removed it.
These are geometry measurements against the implementation base, NOT a pixel verdict
against host-only reference 6a8d0c1f. Current-DOM locator tests also run unchanged.

## Validation

Frontend: 162 tests passed; TypeScript typecheck and production build passed.
Targeted browser/backend checks: mixed file/URL acceptance, original locator/sentinel
checks and both geometry viewports passed (16 tests after the geometry correction).
The full application Python suite result is recorded below when complete.

Final application validation: `.venv/bin/python -m pytest -q tests` — 1,255 passed,
2 skipped, 37 subtests passed. `git diff --check` clean. Built CSS unchanged;
no global CSS or transcript-pane source changes. Production not merged or pushed.

## D6 — Outer-shell finish

The upload form now uses the existing field-label, field and primary-button styles,
with a locally bounded 680 px form width and 16 px field spacing. The browser-history note uses the existing muted color to give the account name
visual priority without changing font metrics.
No header padding, font size, line height or pane dimensions are changed. All styling
is applied to these outer-shell elements; no global CSS, transcript changes,
selector changes or D5 summary changes. This is cosmetic, not a workflow change.

D6 validation: existing geometry, upload-flow and locator/sentinel tests passed
(16 tests); final combined-suite validation is recorded in the integration audit.
