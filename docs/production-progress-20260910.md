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

Standalone probe migration: lifecycle and Live-owner benches now bootstrap browser
workspaces, retain drain/commit/audio/cancellation/interruption assertions, and reject
old handles after a new unrelated browser visit. Normal Stop preserves credentials;
same-browser tabs share authority, while read-only observation remains page-local UI
state. Both probes pass with explicitly reported host SQLite 3.50.4. Operator status
uses workspace IDs and passes. Added browser/bootstrap and revocation-snapshot probes
to the required deterministic command set; no deployed gate removed.

Service log automation: read-only host measurement proved real cursor-bearing records
for all three current service journals. Qualification now reads fixed web/vLLM journal
windows around sentinel/operator/load experiments; no caller-made log files or invented
server external-AI prompt log. Missing baseline, failed reads, malformed/wrong-unit
records and missing source observations fail. Empty tails are accepted only after a
real readable baseline cursor. Ten journal-reader tests plus 88 qualification tests
pass. Only flags/counts enter evidence, not log messages.

W1 source checkpoint: full Python **1129 passed, 2 skipped, 37 subtests passed**
(62.85 s); frontend **121/121**, type-check and build pass. All seven original
standalone deterministic probes pass; the added browser/revocation probes pass as
recorded above. Fidelity probe imports and CLI start without retired Google classes.
These are development/source results, not trusted-TLS deployed qualification.

## C4 — Ticket-24 manual naming integration

Source worktree was left untouched. Seven changed/new files were copied byte-for-byte
(verified with `cmp`) to snapshot branch `integration/ticket24-snapshot-20260910`,
commit `3f8e98f9`, then merged without rebasing. The retired Google test's sole new
schema assertion was ported to the browser-workspace lifecycle test.

The inherited slice adds owner-bound active manual naming, immediate transcript
relabeling, quality-gated 2 s enrollment, replaceable pending intent, private list and
persistence. Matching, bank rename/delete, UI and G8 remain subsequent W2 work.

Adversarial review found three reachable lifecycle regressions. A real-COMMIT probe
reproduced cancelled naming leaving SQLite label Durable while live label stayed S01;
the service-owned task fixed convergence. Tail-eligible pending enrollment measured
one sample when cleared late and zero when closed at accepted Stop. Fixed both, plus
restored synchronous publication fencing before identity cleanup. Lifespan joins
accepted naming. Regression tests cover held COMMIT, next publication, held identity
cleanup versus Stop and newly eligible Stop/abort tail evidence.

Focused naming/Live/lifecycle tests: **80 passed**. Prototype verdict is retained in
`prototypes/phase2-account-lifecycle/MANUAL_IDENTITY_NOTES.md`.

Merge commit: `0b0e0d45` (parents `123a08d8` and preserved snapshot `3f8e98f9`).
Post-merge full regression: **1141 passed, 2 skipped, 37 subtests passed**, 64.94 s.
Frontend remains **121/121**, type-check/build passed; no frontend changes in this
backend slice. Manual naming is not yet wired into the user interface.

## C5 — Manual-naming user interface

- Active capture page speaker chips open a name dialog. No extra login or enrollment
  recording; the saved/pending response explains the private voiceprint outcome.
  Reload/history observers, stopped meetings, previews and unattributed S00 rows
  cannot initiate naming.
- Label-only revisions redraw cached canonical rows without waiting for new speech
  or resetting the speech cursor. Duplicate names stay distinct in Live/history;
  display names feed search/copy/export. Explicit generic-looking names remain literal.
- Saved Live rows retain canonical IDs alongside labels; unattributed rows omit the
  absent ID. Adversarial review caught and corrected null-ID history rejection and
  impossible S00 naming controls. Original transcript text remains intact.
- Four-state prototype absorbed into production poller/tests. Muted headless Chrome
  confirmed modal interaction, exact selected-ID PUT, pending text and observer
  disabling using explicitly synthetic state/mock response, not device capture.
- Full Python before the final unattributed-row correction: **1141 passed, 2 skipped,
  37 subtests passed**, 63.77 s. After that correction: **59 focused Python tests
  pass; 136 frontend tests pass**, type-check/build pass. An initial parallel
  build/test run hit Vite's temporary asset deletion (58 passed, one missing-assets
  failure); rerunning after build completed passed. Build and asset-consuming
  backend tests must run sequentially.

## C6 — Voiceprint recognition and bank operations

Implemented private opaque-ID bank rename/delete and UI; compatible-entry matching
uses original causal evidence, not enrollment centroids. Manual labels win; recognition
never enrolls. Changes propagate only to linked active meetings; stopped history stays
literal. Delete removes samples/links, preserves recorded names, and fences prepared
matches by bank revision. Incompatible entries show a re-enrollment explanation.

Stress: 32 simultaneous renames converge; cancelling a client at a held real COMMIT
still completes accepted work. Reviewer found an uncaught matching-database failure
that killed the publisher and stranded Stop. Reproduced red, fixed the failure boundary,
then verified interruption, a surviving publisher and bounded Stop.

Fresh production encoder/rule bench: causal known **441/470 correct, 29 abstentions,
zero wrong**; unknown **470/470 abstentions**. Terminal album known **14/14 correct**;
unknown **14/14 abstentions**. Two development corpora, not blind or deployed G8 proof.
Command: standing bench `voice-profile-matching/measure_production_rule.py` with the
original checkout's ignored `data` assets; report `/tmp/moss-production-rule-20260910.json`.
Prototype decision: `prototypes/phase2-account-lifecycle/BANK_REVISION_NOTES.md`.

Full Python: **1148 passed, 2 skipped, 37 subtests passed**, 67.48 s.
Frontend: **138 passed**, type-check/build pass. Builds ran before backend tests.
Read-only host refresh: batch, Live and vLLM services active, zero service restarts;
batch root, Live runtime and model health/models/metrics returned 200. Live certificate
verification was explicitly disabled for availability measurement: trusted TLS remains
unqualified. No service changes or playback.

## C7 — Remaining sequence

1. Finish real G8 measurement/evaluation for the integrated W2 source.
   Preserve the separate accepted evidence boundaries: causal matching uses at least
   1 s live evidence; enrollment uses the quality-gated album centroid at 2 s. Do not
   silently substitute the enrollment observation seam for causal match evidence.
2. Reuse the standing voice-profile bench and its accepted rule. The production
   worktree lacks ignored bench assets. Located both 55 MB development corpora and
   the working Python 3.12.12/ONNX Runtime 1.28.0 bench environment in the original
   worktree; reuse those assets without altering the original checkout. No fresh
   run completed as recorded in C6. This is development evidence only.
3. Implement W3 optional browser-direct AI settings/calls and version-bound summary
   persistence; never persist endpoint, model, API key or prompt on the server.
4. Trusted HTTPS and renewal; staged installation, final integrated G8/G9 producers,
   quality/load/overload and restart/rollback evidence.
5. After quiet hours, attended Chrome microphone + shared-audio canary. Only then
   final production deployment approval/admission.

No manual action is required for these completed source checkpoints. DNS credential provisioning and the attended
canary remain later manual prerequisites; never put credentials in chat.
