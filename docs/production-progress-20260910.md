# Production completion progress — 2026-09-10

Implementation branch: `production/browser-workspaces-20260910`.
No deployment or production admission. Quiet hours: no playback, volume changes,
microphone/screen capture, or permission prompts.

## C1 — Browser-workspace foundation

- Schema 2 replaces Google email/allowlist ownership with an opaque workspace ID and
  a separate server-issued browser credential. Old schemas are refused unchanged.
- Explicit same-origin bootstrap; secure HttpOnly persistent cookie; cross-tab Web
  Lock before workspace UI admission. Missing/invalid credentials do not silently
  create a workspace during meeting mutations. No sign-in, logout, or Reset UI.
- Operator list/revoke uses workspace IDs, retains settlement before revocation,
  and does not disclose meeting content or credentials.
- Launcher/CLI/cutover prerequisites no longer require Google/OAuth secrets.
- History, files/URLs, Live ownership, audio, interruption, persistence and packaging
  tests use the browser-workspace model. Tests specific to retired Google/allowlist/
  logout policy were replaced, not treated as product requirements.

Measured commands:

```sh
.venv/bin/python -m pytest -q tests/phase2 --tb=short
# 233 passed, 13 warnings, 46.25 s; host SQLite semantic tests
PYTHONPATH=. .venv/bin/python prototypes/phase2-account-lifecycle/browser_workspace_probe.py
# 11/11; production HTTP/store/JavaScript, persistent muted headless Chrome
.venv/bin/python -m pytest -q tests --tb=short
# 1059 passed, 2 skipped, 37 subtests passed; 81.09 s
npm --prefix frontend test
# 121 passed, 17 files; Vitest 4.1.10 before advisory update
npm --prefix frontend run typecheck
npm --prefix frontend run build
# Both passed; emitted assets unchanged
```

Read-only adversarial review of bootstrap/store/HTTP/JavaScript: no must-fix finding.
This is not a full release verdict. Existing deployed qualification still contains
Google-era producers/probes and must be replaced before qualification can run.

Dependency audit found one development-tool advisory reported through two packages
(Vitest and its mocker, pinned 4.1.10). Upstream fixes it in 4.1.11:
https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9
The audit does not establish an exposed production attack path. Updated Vitest and
its matched packages to 4.1.11. Post-update: 121 frontend tests pass; type-check and
build pass; `npm audit --json` reports zero vulnerabilities. Built assets unchanged.

## C2 — Browser identity and irreversible revocation collectors

- Replaced deployed Google admission measurement with two fresh persistent browser
  profiles, overlapping first tabs, real nonempty file history, browser restart,
  foreign-owner refusal, cookie privacy and trusted-TLS observations.
- Revocation uses normal operator revoke, rejects old credentials and late writes,
  and proves exact saved prefix plus decodable partial audio through the narrowly
  approved read-only disposable-state seam. No reallow/recovery path.
- Removed orphan Google callback helper and Authlib/itsdangerous dependencies;
  installed dependency projection still binds the complete runtime.
- Gate falsifiers reject each missing browser invariant and mismatched candidate
  restore inventory: 64 qualification tests pass.
- Browser bench: 13/13 production bootstrap assertions (including refused cookies
  and unsupported Web Locks), plus 12 actual collector semantic assertions.
  TLS/inference are explicitly stubbed only in the collector's local probe.
- Revocation bench: seven measured checks pass, including live WAL reads, read-only
  enforcement and corrupt-audio rejection. Neither bench is deployed qualification.
- Adversarial review found three false-pass paths. Corrected: accepted File must
  complete with nonempty speech after cookie loss; revoking B must preserve A's exact
  saved meeting; first-tab overlap must be observed in the browser's actual lock
  queue. Failed/interrupted/empty File, global revoke, changed peer and removed-lock
  mutations are rejected. The removed-lock test runs the actual collector.
- Full Python before these final reviewer corrections: 1085 passed, 2 skipped,
  37 subtests passed (60.07 s). Focused qualification rerun covers the corrections.

Automatic attempt-owned credentials/log collection and migration of the remaining
Google-era lifecycle probes are still required before W1 qualification can run.

## C3 — Automatic attempt setup

- Cutover creates an attempt-private qualification profile using six real HTTP
  bootstraps (three independent workspaces per evidence layer). Peer tabs share the
  same cookie. Four distinct title sentinels and all cookies are mode 0600.
- No copied tokens, Google login, pre-signed-in profiles, synthetic database authority
  or OAuth secret prerequisites. Wrong candidate/origin/TLS and attempt reuse fail.
- G1 revokes a disposable third workspace through the existing operator control,
  not the removed logout endpoint. The eventual attended canary creates its own
  fresh browser profile; capture has not been run during quiet hours.
- Setup, cutover and qualification tests: 102 passed before the canary cleanup.
  The existing setup prototype was absorbed onto production helper functions.
- Remaining operational qualification work: collect actual service journals instead
  of requiring hand-made log files; migrate retired Google-era standalone probes.

## C4 — Remaining sequence

1. Complete W1 deployed browser/lifecycle qualification producers and replace
   superseded prototype invocations; run full Python/frontend gates.
2. Integrate W2 manual names/voiceprints from the preserved ticket-24 work, merge-only.
3. Implement W3 optional browser-direct AI settings/calls and version-bound summary
   persistence; never persist endpoint, model, API key or prompt on the server.
4. Trusted HTTPS and renewal; staged installation, final integrated G8/G9 producers,
   quality/load/overload and restart/rollback evidence.
5. After quiet hours, attended Chrome microphone + shared-audio canary. Only then
   final production deployment approval/admission.

No user action is needed during C1. DNS credential provisioning and the attended
canary remain later manual prerequisites; never put credentials in chat.
