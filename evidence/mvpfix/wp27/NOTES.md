# WP27 — early Share during microphone setup

## Structural contract and prototype
- Question: which ordering of microphone setup, Share, failure and Reset loses an actionable explanation or resources?
- Minimum primitives: capture-client identity (which setup owns a completion), lane error (which source failed and why), existing capture phase (which actions are available). A single message cannot represent two independent failures; phase cannot identify an obsolete async completion.
- Invariants: an error remains visible until Reset; both failed lanes are named; Reset clears errors/meters and releases tracks; obsolete setup cannot revive capture. Existing readiness thresholds, nine-key protocol, identity policy, QUALITY_BOUNDS and two-Refresh sentinel unchanged.
- Unknown: physical permissions/device behavior unmeasured; simulated devices exercise real ControlPanel and CaptureClient, not a capture-client mock.
- Falsifier: any reachable completion erases an error, removes Reset, updates retired meters, or leaks acquired tracks after Reset.
- Tool decision: Vitest/jsdom with deferred descriptor and microphone promises makes exact ordering controllable. Failure requires changing/rejecting the state design before production. Full Python/frontend gates detect unrelated regression; fix or explain every unexpected failure.

Hypothesis: independent lane errors retained until Reset, plus existing-client identity checks at async completion, suffice. No thresholds or new capture-client lifecycle machinery needed.

Command (prototype stage): `npm --prefix frontend test -- --run src/components/ControlPanel.earlyShare-prototype.test.tsx`.
The throwaway component copied the production panel and used the real CaptureClient. Logs surface phase, status, Reset, meters, connections, track stops, contexts, handlers and actual chooser calls after each action.

## Measured verdict (before production edits)
Baseline: **9 failed, 1 passed / 10**, 543 ms (see retained log for exact run duration).
Candidate: **10 passed / 10**, 576 ms. Hypothesis supported for measured ordering cases.
- Descriptor pending → early Share → microphone success/failure (2).
- Permission pending → early Share → microphone success/failure (2).
- Reset while descriptor/permission pending → old success (2).
- Microphone attached → Share rejected/cancelled or missing audio (2).
- Microphone failure before Share (1); successful two-lane readiness control (1).
Early Share throws `start microphone before display capture` synchronously: **0 chooser calls**. Therefore actual chooser cancellation/failure while the initial microphone is pending is unreachable through this client. Its reachable equivalent is Share rejected early, then microphone settles. Admitted chooser rejection/cancellation is tested after microphone attachment.

Baseline also reproduced late setup reattaching after Reset. Candidate closes retired setup after await, ignores obsolete callbacks, and stops late display tracks. This is the same reachable Reset path, not broader capture lifecycle redesign.

Prototype absorbed into ControlPanel and permanent early-Share regression tests; throwaway copy removed. User-requested Vitest prototype takes precedence over the generic skill's interactive-TUI/no-tests guidance.

## Regression extension attempts
First focused run: **73 passed, 2 failed / 75**. Two new tests assumed a track-ended event before session creation offers Reset; real CaptureClient only marks that lane failed, leaving panel configuring. Invalid Reset precondition corrected to an actual concurrent chooser rejection (second Share while first pending), which invokes the existing pre-session failure callback. This separately observed pre-existing track-ended recovery gap is outside WP27's early-Share message fix; no capture-client lifecycle change made.

## Final implementation gate
- Full Python: **1917 passed, 2 skipped, 21 warnings, 37 subtests passed**, 164.04 s, exit 0.
- Full frontend (after absorbing prototype cases into WP3 fixtures): **264 passed / 264**, **28 files / 28**, 2.66 s, exit 0.
- Focused capture suite before fixture consolidation: **75 passed / 75**, 1.64 s.
- Typecheck: exit 0. Vite production build: exit 0, 34 modules, 60 ms. Rebuilt app.js and app.js.map retained.
- Python source origin confirmed inside this worktree; no Python source/test changes. Disposable pytest/Torch scratch was inside this worktree and removed after completion.
- Commands: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/evidence/mvpfix/wp27" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests`; `npm --prefix frontend test -- --run`; `npm --prefix frontend run typecheck`; `npm --prefix frontend run build`.
- Scope diff: ControlPanel, its existing real-client failure tests, rebuilt JS/map, design note and WP27 evidence only. No shared service, network decoder, push, merge, deploy, or GitHub operation.
- Fresh-context instructions written only after both full-suite gates passed. Fresh results belong in root VERIFY-RESULT.md.
- Implementation session: `01a0b378-4e04-72c2-808a-98ad350f5fc5`, pane `%27` = MOSS:3.4. Fresh verification must use a different session after the requested `/new`.
