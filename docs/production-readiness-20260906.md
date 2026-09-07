# Production readiness — 2026-09-06

## Decision

Keep Phase 1 serving; stage a fresh Wave-1 candidate. Do not repeat a cutover
until real qualification inputs are ready. No gate is waived.

## Verified findings

- **F1 — packaging:** the staged `6c10b30f` runtime's dependency projection differs
  from its manifest: `webrtcvad-wheels==2.0.14` was added manually. The locked
  acceptance and speaker-identity extras now include that deployed dependency.
  Acceptance also owns `uv==0.9.13`; cutover puts the release's `bin` first on PATH
  and runs the documented `npm --prefix frontend ci` in its fresh qualification clone.
- **F2 — startup:** systemd `active` preceded HTTP readiness during restore.
  The adapter now waits for both real Phase-1 runtime views before returning from
  startup, while creation remains blocked. Candidate startup also requires an
  HTTPS response with the exact candidate SHA. Dead/malformed/wrong-release
  responses fail. The bounded startup decision and measured falsifiers are in
  `prototypes/phase2-cutover/NOTES.md`; it is not a latency qualification.
- **F3 — evidence:** the remote `restored-20260902T035345Z` verdict is false,
  with **0/12 deterministic commands executed** and no executed external campaigns.
  Successful restoration is not successful qualification. Account cookies,
  sentinels, and Google browser profiles are absent. Collector-configured log files
  are also absent; deployed operator events currently go to systemd's journal.

## Already settled

Google OAuth client/secret are provisioned. The September 1 operator ruling permits
the existing self-signed HTTPS certificate after client trust installation; NS1 is
not an MVP blocker. See the ruling linked in `phase2-afk-charter.md` §4.1.

## Remaining release work

- **A1 — genuine bootstrap:** use the two allowed Google accounts and one denied
  account to prepare real browser sessions. The qualification runner currently
  reads cookie files; it does not mint/export them. Resolve that bootstrap step
  inside the rollback-protected candidate window, not with fabricated sessions or
  by writing the product database. Produce distinct sentinel inputs.
- **A2 — evidence sources:** bind log collection to actual systemd output, including
  the operator event stream. Do not create empty stand-in logs to satisfy the profile.
- **A3 — acceptance:** run all twelve same-SHA deterministic commands and deployed/
  pre-admission campaigns; then attended Chrome microphone/tab/screen G7. Report
  exact measured denominators. Only a passing candidate can reach pre-admission.

Local verification for F1/F2: **1,080 Python tests and 37 subtests passed**, including
**252 Phase-2 tests**. Frontend: **121 tests**, typecheck, and production build passed.
`uv lock --check` and `git diff --check` passed. This is implementation evidence,
not a production-ready verdict. The separate dirty ticket-24 worktree is preserved.

## Linux component run

The first exact-runtime run on `2568966c` executed all twelve component commands;
**8 passed / 4 failed**. This exposed further unattended blockers:

- **F4 — frontend tooling:** the host's Node 18 cannot load the locked tools.
  Staging now installs pinned Node 24.20.0 alongside the application and links its
  `node`/`npm` into the release, without replacing the system Node.
- **F5 — executable tests and scripts:** a test invoked `uv run`, attempting to
  resync the sealed runtime. It now invokes the installed interpreter directly.
  Separately, moved venvs broke generated console scripts. The measured installer
  repair rewrites interpreter prefixes and installer-owned RECORD rows before
  sealing; direct command execution and full RECORD verification both pass.
- **F6 — stale test assumptions:** Linux FFprobe includes MP3 encoder padding in
  container duration. The test now verifies reported container metadata against
  the artifact and independently decodes exactly 16,000 source samples. The old
  revocation probe now performs the required durable interruption before revoking
  authority. Both corrected checks passed on Linux; production audio and
  revocation semantics were not changed.
- **F7 — failure/Stop race:** the subsequent Linux run passed 11/12 commands but
  caught a genuine race: normal Stop could publish `completed` while a failure
  fence waited for Stop. The existing publication gate now closes before that
  wait; the accepted raw Stop remains allowed to finish. A deterministic probe
  measures newly admitted terminal publications **1 before / 0 after**. All
  **56 Live owner-binding tests pass on both platforms** after the fix.
