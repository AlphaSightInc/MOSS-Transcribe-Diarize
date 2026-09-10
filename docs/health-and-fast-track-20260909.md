# MOSS: health check and frictionless MVP release plan

> Planning update, September 10: the recommendations/execution order below are superseded by [the adversarially reviewed production completion plan](production-plan-20260910.md), incorporating the user's D1–D5 rulings. The health observations below remain dated September 9 evidence.

Checked September 9, 2026, approximately 20:53–20:58 EDT (September 10 UTC).

## Verdict

**The existing infrastructure is alive and usable for development. The project is not yet ready for frictionless end-user testing or a production-ready verdict.** The shortest path is to replace Google/capture-bearer entry with an automatically created browser workspace, provide browser-trusted HTTPS, repair acceptance inputs/collection, and qualify one narrow release. Do not redesign transcription or diarization.

This was a diagnostic/advisory pass. No application source, service configuration, credentials, database, deployment pointer, or running service was changed. Short inference requests were sent to the existing local model. Report artifacts are the only repository additions.

## 1. Current evidence

Initial inference hypotheses were F1 unsuitable fixture, F2 malformed model output, and F3 unavailable inference. Their dispositions are below; none is silently counted as a passing test.

| Code | Area | Measured result | Meaning |
|---|---|---|---|
| F1 | Configured File acceptance fixture | `fixtures/account-file.wav`: 2.1 seconds; repeated response `[humming]`, 5 tokens, zero parsed segments, `EmptyTranscriptionError` | **Blocked success-case fixture.** Replace it with verified human speech for successful File-Meeting acceptance; retain this sample as a separate empty/unparseable-output test. Its acoustic content has not been independently listened to in this pass. |
| F2 | Output-format failure hypothesis | The fixture produced no timestamped transcript; the real-speech control produced 10 parseable segments | No evidence of a general parser/format regression. Existing rejection of unusable output is correct; do not weaken it. |
| F3 | Actual inference and Live providers | 50-second `mono_javier_intro_50s/audio.wav`: 1.450 seconds reported by the production `VllmRunner`, 296 tokens, 10 segments. Fresh Live-provider preflight: available, no failures | **Inference smoke passes.** This one batch request is not an accuracy, live-latency, or four-user capacity benchmark. |
| F4 | Network and endpoints | Headscale `/health` 200/pass; Windows Tailscale running/no health warnings; SSH/Ubuntu reachable. Both product ports respond over `100.64.0.8` and LAN `192.168.68.32`. Loopback `/api/runtime`, model `/health`, `/v1/models`, `/metrics` respond | **Core availability passes.** LAN HTTP reachability was tested with curl; the automated browser's direct LAN navigation failed, so LAN-browser acceptance is not claimed. |
| F5 | HTTPS onboarding | Default curl: self-signed-certificate failure. Fresh Chromium: `ERR_CERT_AUTHORITY_INVALID`. Certificate valid until October 20, 2028, but not trusted in these fresh clients. Its IP SAN lists old LAN `.38`, not current `.32` | **Fresh-client blocker.** Use a trusted DNS-name certificate and one canonical hostname, not IP bookmarks or bypass instructions. |
| F6 | Candidate integrity | Local clean `dev` and installed inert candidate: `e5ff94e879a13ff1cf78cec17fffcb67bc581647`. Candidate checkout/launchers/units validated; dependencies match; 100 installed package records verified; Python 3.12.3, SQLite 3.53.4, Node 24.20.0 | **Ready to build on.** Not the live product. No dependency repair/reinstall needed. |
| F7 | Service recovery | Web PIDs 329307/329393, model PID 169937, unchanged; all active, no automatic restarts. Live/model enabled, user lingering enabled. Batch unit disabled. Windows MOSS task runs at interactive logon and explicitly starts services | Running today; **unattended Windows reboot recovery remains unproved**. Disabled batch alone does not mean it never starts: the logon task starts it. |
| F8 | Actual user entry | Existing Phase-1 UI asks for a capture bearer and disables capture until provided. Phase-2 CLI still requires Google client/secret and OAuth cookie secret | **Neither matches no-entry MVP.** Removing a visible field alone is insufficient; change bootstrap, session policy, launcher, and qualification together. |
| F9 | Acceptance plumbing | Cookie/browser-profile/sentinel inputs and configured log files remain absent. Actual service logs exist in systemd journal. Phase-2 control socket/audio root absent while Phase 2 is inert | Old qualification profile is not runnable end to end. Socket/audio absence is expected before candidate startup, not a live Phase-1 outage. |

### Endpoint coverage

- Tailnet product: `http://ga0-alienware-rtx4070ti.tailnet.aisight.us:7860/` returned 200; `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/` returned 200 only after certificate verification was bypassed for diagnostic content inspection.
- LAN product: `http://192.168.68.32:7860/` returned 200. Live HTTPS returned 200 using the canonical hostname resolved explicitly to `.32`, with diagnostic certificate bypass.
- Both runtime views report creation open, zero entrants/jobs/queued jobs/live sessions before and after checks.
- Live `/static/app.js`, `/static/styles.css`, `/api/runtime`: 200 in browser; no browser page errors observed after diagnostic bypass.
- Model `http://127.0.0.1:8000`: health/models/metrics and actual audio transcription exercised. Direct LAN/tailnet port 8000 connections refused, consistent with its loopback listener.
- GPU: RTX 4070 Ti SUPER, 13,909/16,376 MiB used; sampled utilization 83%. Request queue was empty. RAM: 3.4 GiB available, 1.8 GiB swap occupied; short samples showed no ongoing swap-in/out. Available WSL disk: 794 GiB; Windows D: 732 GiB. Capacity/headroom under concurrent meetings remains unmeasured today.
- No systemd failed units or error-priority entries for the three MOSS services since September 7. This does not prove absence of application errors logged at other levels.
- Live checkout remains clean detached `29c32f9aace5eb5dffd0062d38127c45ecaf8ef1` (Phase 1). Do not confuse the local/staged SHA with what users currently run.

Not exercised: new product Meeting creation, upload/URL lifecycle, real microphone/tab/screen capture, browser reconnect/restart, full concurrency/quality campaigns, backup restore, Windows reboot, external-network exclusion. Those are release gates, not inferred from healthy HTTP. No Phase-3 LLM service was qualified.

### Historical tests, freshly located but not rerun

Remote `/mnt/d/Coding/moss-stage-e5ff94e8/component-summary.json` still records **12/12 component commands successful**. September 6 Python evidence: 1,079 passed, 2 external-corpus skips, 37 subtests; frontend: 121 tests plus typecheck/build. These are historical component results for the unchanged candidate, not today's full acceptance. The two skipped corpus checks must be supplied/reconciled where relevant to the release; never report zero skips from this run.

The separate ticket-24 worktree remains dirty and was not changed. Its manual naming/voiceprint work is not part of the staged candidate.

## 2. Smallest sufficient design

**Structural question:** how can a returning browser recover its own meeting history without asking its user to authenticate or type an identifier?

**Primitives:** (1) network admission decides who can reach the app; (2) an opaque browser credential remembers one browser profile; (3) a workspace owns its meetings; (4) each meeting owns transcript/audio. Removing admission exposes the app beyond scope; removing the credential loses continuity; removing workspace ownership mixes histories; removing durable meetings loses results after capture ends.

**Invariants:** no login/passcode/bearer entry; stable history after browser/server restart; no cross-workspace reads or mutations; no automatic restart of recording after interruption; Stop remains truthful about transcript/audio durability. Network membership is not a human identity.

**Assumptions/unknowns:** cooperating users on trusted LAN/tailnet; separate-browser histories are acceptable as the default recommendation. Cross-device shared history is not implied. Browser eviction/clearing, private browsing, and a new browser profile create a new identity. LAN-only DNS setup, unattended boot, automatic certificate renewal, and current quality/capacity are unqualified.

**Falsifier:** a clean-profile prototype requires typing, loses history after an ordinary restart, gives browser B browser A's results, silently restarts capture, or succeeds only by disabling certificate checks.

**Tool decision:** use the real app/store and two persistent browser profiles to test bootstrap/persistence; network/TLS probes select certificate delivery; existing speech/concurrency benches test inference and capacity. Do not build a new identity framework or invent thresholds.

### D1 — Automatic browser workspace: recommended

On first visit, the server automatically creates a workspace and issues an opaque, cryptographically random persistent cookie. Subsequent requests resolve that cookie to the same workspace. Keep the existing owner-bound meeting/store interfaces and durability machinery; replace the Google-specific admission seam rather than pretending a generated identifier is a Google user.

Reuse the existing cookie attributes: `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Domain`; refresh its existing 400-day lifetime at bootstrap, not on every frame. This is invisible to the user. Browser cookie lifetime is not a guarantee against user deletion or browser storage policy. [MDN cookie guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)

Call it a **browser workspace**, not a physical-device ID. Chrome and Safari on the same laptop are different workspaces. Two people sharing one browser profile share its workspace. LAN-to-tailnet switching preserves history when the same hostname/profile is used. Clearing site data loses the access credential, not automatically the server's stored recordings. Explain this once in Help, not with an onboarding wizard.

Do not use MAC address, IP address, browser fingerprinting, or microphone `deviceId` as ownership. Do not add accounts, email verification, passcodes, an identity-provider adapter framework, or cross-device linking to the first release. If later needed, explicit workspace transfer can be a separate feature; it is not a reason to retain mandatory Google today.

The cookie is an access credential even though there is no login ceremony. Keep it out of URLs, JavaScript-readable storage, operator logs, and screenshots. Retain simple same-origin mutation checks and owner checks. Operator control stays host-local. This is proportionate to the existing MVP, not a new security program.

### D2 — Trusted HTTPS on the existing network: recommended

Your actual control server is `https://headscale.aisight.us`, MagicDNS suffix `tailnet.aisight.us`; advertised certificate domains are absent and Serve has no configuration. Hosted Tailscale's automatic `.ts.net` certificate workflow is therefore **not a verified drop-in option** for this deployment. Do not migrate the network to solve one certificate.

Use a publicly trusted certificate for the existing product DNS name, obtained and automatically renewed using DNS-01. Public DNS proves domain control; the application can remain private. Current authoritative nameservers are NS1, consistent with the repo's previously selected NS1/lego path. DNS-01 does not require exposing the app to the internet. DNS API permissions/renewal are not verified here. [Let's Encrypt DNS-01](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge)

Keep one bookmarked hostname on LAN and tailnet. For clients without Tailscale, internal DNS must resolve that name to the host's reserved LAN address. Avoid a new proxy/port/domain merely for cosmetics; the existing HTTPS listener can use a trusted certificate. If direct-server renewal needs a reload, perform it in a zero-active-meeting window and prove it. Introduce a reverse proxy only if it removes a measured operational obstacle.

Fallback for immediate testing on managed machines: the existing documented OS/browser trust installation. It is still a per-client prerequisite and is not the zero-setup end-user finish line. Never ship instructions to bypass warnings.

### D3 — Ship the core before the remaining roadmap

First release: Live capture, File/URL ingress already in Wave 1, durable per-browser history, transcript export, playable audio, recovery, and operator interruption. Freeze UI redesign and diarization changes. Preserve the accepted four-session/quality bars; if capacity is to be reduced for an earlier pilot, make that an explicit scope decision, not an undocumented gate waiver.

Then ship voiceprint/manual naming (Wave 2), then optional final summaries (Wave 3), in the existing order. These are still part of the full roadmap; deferring them from the first internal release does not mean the whole project is finished. A voiceprint identifies a speaker within a workspace, never the browser's owner.

## 3. Ordered developer handoff

The following are future implementation instructions, not changes performed by this health check.

### A1 — Record the new admission contract and isolate the work

1. Branch from clean `e5ff94e8` in a new worktree. Preserve ticket-24 work unchanged; do not merge it into the core release yet.
2. Record the user's explicit LAN/tailnet, no-login requirement. Update the Google-only portions of `docs/phase2-afk-charter.md`, `CONTEXT.md`, and ADR-0007 coherently during implementation; mark the old policy superseded, not silently ignored.
3. Define browser workspace, browser credential, and meeting owner. Preserve resource ownership and operator interruption; replace person/email admission rules. State explicitly that cross-device history is deferred.
4. Retain a documented list of release gates. Remove only tests whose requirement truly disappeared (Google login/allowlist); replace them with real bootstrap, persistence, invalid-cookie, and workspace-isolation tests.

**Done when:** code/spec/test expectations agree on no-login semantics and ownership. No fake Google email/subject workaround.

### A2 — Prototype automatic identity before production edits

1. Extend the existing Phase-2 lifecycle bench with the smallest real-store/bootstrap experiment, in disposable state. One command; print workspace relationships and verdicts, never raw credentials.
2. Profile A opens the app: no form, one workspace. Create a small test meeting through the real interface.
3. Refresh, close/reopen the persistent browser profile, and restart the prototype server: A sees the same meeting.
4. Profile B opens the app: distinct workspace; A's meeting/audio cannot be read or changed by B.
5. Check two tabs, including simultaneous first bootstrap, so initialization does not scatter ordinary tab activity into different histories. Resolve the observed case with the smallest measured design.
6. Test deleted/invalid/blocked cookies: never silently attach another workspace or repeatedly create meetings. A missing credential on an in-flight mutation must fail visibly; automatic bootstrap happens before work is admitted.
7. Record measured verdict in `NOTES.md`; absorb useful cases into tests. Stop here if persistent-browser continuity does not work.

**Done when:** those behaviors are measured through the real store and browser, not asserted from a UUID generator.

### A3 — Implement the proven bootstrap seam

1. Replace Google admission in `moss_transcribe_diarize/app/phase2.py` with the measured browser-workspace bootstrap. Reuse opaque session generation, cookie policy, workspace handles, and composite meeting ownership.
2. Ensure bootstrap completes before the UI starts parallel history/live/file requests. Exclude credential/bootstrap responses from caches.
3. Remove required Google configuration from `phase2_web_cli.py`, `ops/account-web-launcher.sh`, and the staged profile. Remove Google/capture-bearer entry UI; do not retain an unused auth-mode feature flag.
4. Adapt lifecycle policy deliberately: ordinary close ends/reconciles capture as already designed; it does not forget history. An explicit reset, if shipped, must first settle active work and warn that this browser will lose workspace access. Do not expose reset as a prominent startup action.
5. Audit schema use before changing it. Phase 2 is not active here, but do not assume all candidate databases elsewhere are disposable. For an empty new deployment, create the new schema directly; if a real existing workspace exists, preserve it and specify a bounded conversion rather than deleting it or silently changing schema-v1 meaning.
6. Keep Google secrets untouched on disk unless separately asked to remove them; they simply stop being launch dependencies.

**Done when:** installed candidate starts without Google secrets and a fresh profile reaches usable controls without typing.

### A4 — Remove certificate setup from the normal user journey

1. Keep the current canonical hostname initially; reserve the current server LAN address or use its managed DNS mapping.
2. Verify authority to issue its DNS certificate and access to the NS1 DNS-01 credential. Provision only the certificate-related DNS changes; do not open public app ports.
3. Issue a trusted certificate and configure renewal. Check renewal against a staging CA first, then the trusted chain on a fresh browser without exceptions.
4. Configure LAN-only name resolution to the same hostname. Test one LAN-only browser and one tailnet browser; this pass did not qualify both.
5. Verify actual firewall/router paths match LAN/tailnet-only scope. Existing MOSS web rules allow any source on the Windows Private profile; the model has a broad stale rule but is currently loopback-only. Narrow/remove only MOSS-specific rules as appropriate, preserving intended access. Router/WAN exclusion is not proved by this host check.
6. Prove certificate reload/renewal does not interrupt active meetings; otherwise schedule it during idle.

**Done when:** clean browsers open the same URL with no warning, certificate import, host-file edit, or app credential.

### A5 — Make acceptance self-starting

1. Replace success-case `account-file.wav` with verified real speech from the existing corpus; validate successful parsed output before launching the larger campaign. Preserve `[humming]` as a separate expected failure case, not a passing success case.
2. Update `phase2_acceptance*.py`, `scripts/phase2-acceptance/profile.example.json`, and browser canaries to create their own disposable browser workspaces via the public bootstrap route. Do not pre-populate SQLite or fabricate cookies.
3. Use profile A/B for isolation, two tabs of A for shared-history behavior, and a separate profile for invalidation. Adapt old multi-Google-device expectations to the new browser-scoped product; do not copy tokens to pretend cross-device identity exists.
4. Generate private sentinel inputs inside the attempt. Collect real server/model/operator events from systemd journal with a bounded attempt time window. Do not create empty fake log files to satisfy path checks. Treat absent LLM traffic as not applicable before Wave 3, not as an invented log file.
5. Give developers one command that runs preflight and automated qualification, with explicit failure reasons. Keep the existing acceptance entry point where practical:

   ```sh
   python scripts/phase2-acceptance/run.py --wave 1 --output evidence/phase2/wave-1/UNIQUE-UTC-CANDIDATE
   ```

   Run it only from the fresh qualification checkout with the exact installed candidate interpreter, pinned Node on PATH, correct SQLite library, and updated profile. The current runner/profile is not ready for the new workflow.

**Done when:** no human login, cookie export, bearer copying, sentinel-file preparation, or log-path repair is needed to start automated acceptance.

### A6 — Give testers one obvious workflow

1. Open bookmark; workspace is ready. Show service availability without asking for model URLs, API keys, or device names.
2. Offer **Try sample**, **Upload file**, and **Start live**. Try sample should use ordinary ingestion with a known speech clip, not a special fake-success path; it requires no microphone permission.
3. Start live requests microphone only when needed. Shared/tab audio selection is a separate explicit user gesture. Show actual lane activity; do not label permission granted as sound received.
4. Preserve the accepted listening-setup/echo behavior; remember harmless preferences so returning users do not reconfigure them. Avoid adding unsupported platform-specific capture promises.
5. Stop becomes complete only after saved results are ready. Refresh/reopen shows history and export/audio actions. Network loss produces a clear reconnect/interrupted state without duplicate meetings or false completion.

Browser permission cannot be eliminated: microphone access requires a secure context and user permission; screen-sharing permission cannot be permanently reused and needs a user gesture. Make those prompts the only normal friction. [Microphone API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia) · [Screen-sharing API](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia)

**Done when:** a nondeveloper can finish the sample path without instructions and the real capture path with only browser/OS permission choices.

### A7 — Qualify one exact candidate

1. Run focused bootstrap/lifecycle tests while implementing; then one complete backend/frontend regression on the frozen candidate. Use `npm --prefix frontend ci`, tests, typecheck, and build in the fresh qualification checkout.
2. Stage a new immutable release using the existing staging workflow. Do not modify sealed `e5ff94e8` in place or install ad hoc dependencies into it.
3. Run real File, URL, Live, owner isolation, restart/reconnect, export, audio replay, operator interruption, and failed-inference/storage cases on that candidate. Validate actual supported URL acquisition; internet/provider failures must be reported rather than masked with a local fixture.
4. Run the existing **four concurrent Live meetings for 600 seconds** across at least two browser workspaces. Retain p95 transcript lag ≤10 seconds per session, no dropped canonical commits/terminal failures, and existing fairness/memory/queue bars. The 50-second smoke result does not qualify this.
5. Run the existing six-case, two-pass quality corpus (12 sessions), keeping the accepted accuracy/diarization thresholds in charter G4. Supply/reconcile the two previously skipped external-corpus checks. Do not retune thresholds to obtain green results.
6. Preserve failed evidence. After a code fix, build a new candidate and run the complete relevant wave once; do not combine mixed-SHA results into a release verdict.

**Done when:** exact collected/passed/failed/skipped counts and real workflow results justify the intended supported capacity and behavior.

### A8 — Prove restart, storage, and rollback once

1. Correct service enablement for the final one-web-service topology. Do not perpetuate the old two-port Phase-1 deployment in parallel after successful cutover.
2. Make MOSS start with Windows/WSL unattended, not only after interactive login. Existing user lingering is useful but does not itself boot a stopped WSL distribution. Test the complete chain in a scheduled maintenance window; do not reboot other host workloads casually.
3. Capture a consistent SQLite-plus-audio backup, not a live database file copy that ignores WAL. Restore to a disposable target and open history/play audio.
4. Write the minimal operator commands for status, restart, interruption, backup, restore, certificate renewal, and release rollback. Use the existing journal and control socket rather than introducing a monitoring stack.
5. Keep a modest scheduled health check: app readiness, model readiness, free disk, and certificate expiry; one actionable failure notification. A heavy inference/corpus campaign is not a minute-by-minute health probe.

**Done when:** an ordinary process restart and the planned cold-boot/restore exercise recover without losing saved results or silently resuming capture.

### A9 — Run the attended canary and cut over

1. At zero active meetings, use the existing rollback-protected cutover procedure with the newly qualified candidate. Preserve the Phase-1 snapshot/archive and model process according to the current cutover contract.
2. Run automated deployed/pre-admission checks on the exact release. Verify the visible/served candidate identity.
3. Use one short, guided human session: clean-page trust; sample upload; microphone speech; tab/shared audio with audible input; Stop; export; audio replay; refresh/reopen; second-browser isolation. Repeat the platform-specific capture check on every platform you actually promise to support.
4. Do not ask the tester for Google login, bearer tokens, or terminal commands. Human involvement is only for actual permissions, audio routing, and usability judgment.
5. Admit users only after the canary passes. Otherwise execute the tested rollback. Confirm legacy plaintext/shared-bearer paths are absent in the final topology.

**Done when:** unattended checks plus real capture demonstrate the shipped product, not just the staged package. This is the internal-production-ready point for the core MVP, not public-SaaS readiness.

### A10 — Finish the remaining roadmap without blocking the useful core

1. Rebase/review ticket-24 manual naming/voiceprints onto the shipped browser-workspace model. Preserve its existing dirty work; verify schema semantics and ownership before merging.
2. Run the existing voiceprint bench/G8; ship Wave 2 independently. Do not redesign the settled album/tape/retrospective-sweep identity architecture.
3. Implement/finish optional final summaries in Wave 3 with G9. A missing LLM setting must not block recording/transcription; do not ask every MVP user for an API key on entry.
4. Close each wave only with its own deployed evidence. Full-project completion means all retained roadmap commitments, not merely the first internal release.

## 4. Practical sequencing and user effort

Suggested engineering timeboxes, **not measured estimates or promises**: first implementation day A1–A3 and A5; infrastructure preparation A4 alongside that work; next block A6–A7; final block A8–A9. The critical path is automatic identity → self-starting acceptance → exact-candidate qualification → attended release. Certificate authority and actual capture/capacity failures can extend it. Avoid another several-day planning cycle before the small identity prototype.

Operator input needed only for infrastructure authority if not already provisioned (DNS certificate automation; a safe host maintenance window). The application user should need only a URL and browser permission choices. A one-time 10–15-minute guided canary is a scheduling target, not a claim that all platform capture checks fit in that time.

Do not restart stable inference, upgrade working pinned dependencies, add Kubernetes/Redis/a new identity provider, require hardware IDs, or merge all waves into one release. None is necessary to resolve the measured blockers.

## 5. Evidence pointers and repeatable checks

Current code: `moss_transcribe_diarize/app/phase2.py`, `phase2_web_cli.py`, `phase2_lifecycle.py`; `moss_transcribe_diarize/installed_candidate.py`; `moss_transcribe_diarize/phase2_acceptance.py`; `ops/account-web-launcher.sh`; `ops/install-services.sh`; `docs/phase2-afk-charter.md`.

Host checks (inside Ubuntu as `devcontainers`):

```sh
systemctl --user show moss-web.service moss-live-web.service moss-vllm.service \
  -p Id -p ActiveState -p UnitFileState -p MainPID -p NRestarts
curl --fail --silent --show-error http://127.0.0.1:7860/api/runtime
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/v1/models
df -h /home/devcontainers /mnt/d
```

Fresh-client trust check (currently fails, and should pass after A4):

```sh
curl --fail --silent --show-error \
  https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/api/runtime
```

Installed release verification in this pass used `validated_candidate_artifacts`, `installed_candidate_identity`, `installed_dependency_projection`, and `installed_project_record_identity` under the release's `python -I`, with the pinned SQLite library. It confirmed the existing manifest, not a newly invented integrity mechanism.

Browser screenshot in the companion HTML shows the real Phase-1 UI after a **diagnostic-only certificate bypass**. It is evidence of the capture-bearer prompt, not evidence of browser trust or successful capture.

![Actual Phase-1 UI: capture bearer required. Certificate bypass used only for diagnostic inspection.](../.lavish/moss-health-app-20260909.png)
