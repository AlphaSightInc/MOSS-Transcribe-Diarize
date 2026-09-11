# Finish-line handoff — September 10

**Implementation is complete; production qualification is not.** All three waves are
on `production/browser-workspaces-20260910` in the isolated production worktree.
Do not advertise or admit this candidate until the remaining measured gates pass.
The original and ticket-24 worktrees remain preserved. September 6 Google-login and
self-signed-trust recommendations are superseded by the approved September 10 plan.

## F1 — What a user will experience

Open `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861` from the internal network.
No password, passcode, login, or device-name entry. MOSS gives that browser profile a
private workspace automatically. Use a normal persistent browser profile: reopening
it keeps history; another browser/profile gets separate history. Clearing site cookies
or using private browsing loses automatic access. This identifies a browser workspace,
not a physical machine. No fingerprinting, linking, or recovery workflow is included.

Record/upload → review transcript → name speakers if wanted → save/export/reopen.
Naming can enroll an eligible voice sample into this workspace's private bank; future
meetings may recognize it. Different people can have identical display names without
their profiles being combined. Bank deletion preserves existing recorded labels.

AI is optional. Leaving Browser AI settings blank never blocks transcription. A user
who wants summaries enters their own HTTPS provider URL/model/key there. Those settings
stay in that browser's storage; requests go directly from browser to provider. Only a
validated summary and meeting/version/lifecycle metadata are saved by MOSS. The provider
receives the current finalized transcript, not audio or other meetings. Browser storage
is not a hardware-backed secret vault; use a private browser profile and a restricted
provider key. Configure once per profile, not once per meeting.

The selected external provider must allow browser cross-origin requests (CORS) from
the canonical MOSS origin, including Authorization/Content-Type. Incompatible providers
fail explicitly; there is no server proxy or silent fallback. The controlled-provider
probe does not qualify every user's provider. See the [Fetch standard](https://fetch.spec.whatwg.org/).

## F2 — Current health and evidence boundaries

Latest read-only host refresh: legacy batch, Live and model units active; respective
PIDs 329307, 329393, 169937, each `NRestarts=0`. Batch root, Live runtime, model health,
models and metrics all returned 200. Live's check bypassed certificate verification
**only to establish availability**. Current Live still uses its old untrusted certificate;
none of this qualifies the new candidate or LAN-only client name resolution.

Development stress includes concurrent mutations/admissions, held real commits,
cancellation and late results, ownership isolation, duplicate speaker labels, missing
gate evidence, real browser→separate HTTPS provider transport, and real TLS rotation.
Fresh development-corpus voice matching: causal 441 correct / 29 abstained / 0 wrong
out of 470; all 470 unknown probes abstained. Truth-aligned terminal probes 14/14 correct,
14/14 unknown abstentions. This is not held-out/end-to-end deployed quality evidence.

The broader `pytest -q` discovery also enters archived research: three failures remain
there (a deliberately pinned historical source contract, two missing ignored legacy
archive inputs). They were not weakened or removed. Product release regression is the
existing fixed `pytest -q tests/` command, with exact denominators in the progress report.

## M1 — Your only infrastructure input, now

Do **not** paste any key into chat, a command argument, Git, or an acceptance report.

1. `aisight.us` is served by Netlify DNS (its `dns[1-4].p06.nsone.net` nameservers are
   Netlify's NS1-backed infrastructure, not a direct NS1 account). Create a Netlify
   personal access token for DNS-01 in the account that manages the zone. Do not change A records, delegate the
   domain, expose a public app port, or change Headscale. The challenge name is
   `_acme-challenge.ga0-alienware-rtx4070ti.tailnet.aisight.us`.
2. Open the Ubuntu WSL terminal on the existing Windows host, as `devcontainers`.
   Run the following; `nano` is your local editor, not the agent chat:

   ```sh
   umask 077
   mkdir -p /home/devcontainers/.config/moss-transcribe-diarize
   nano /home/devcontainers/.config/moss-transcribe-diarize/netlify-token
   ```

   Paste only the new key into the file; save and exit. Then:

   ```sh
   chmod 600 /home/devcontainers/.config/moss-transcribe-diarize/netlify-token
   nano /home/devcontainers/.config/moss-transcribe-diarize/certificate.env
   ```

   Put one line there, replacing the example with your certificate contact address:

   ```text
   MOSS_ACME_EMAIL=you@example.com
   ```

   Save, then:

   ```sh
   chmod 600 /home/devcontainers/.config/moss-transcribe-diarize/certificate.env
   ```

3. Tell the agent **“certificate files ready”**. Do not send their contents. The agent
   will validate permissions without displaying either value and perform the rest.

The already installed ACME tool is lego 5.3.1. It supports `NETLIFY_TOKEN_FILE`, so the key
need not appear in shell arguments. [Official Netlify instructions](https://go-acme.github.io/lego/dns/netlify/).
Publicly trusted issuance publishes certificate/hostname metadata; it does not expose
the private MOSS port or meeting content.

## A1 — Agent: issue and validate HTTPS

From the exact candidate checkout on WSL:

```sh
bash ops/manage-certificate.sh --check
bash ops/manage-certificate.sh --staging
bash ops/manage-certificate.sh --issue
```

Staging and production ACME state are separate. Staging certificates must never be
installed as trusted production certificates. These commands do not restart/change any
web service. Do not force repeated production issuance to test renewal.

Set the staged candidate's existing `MOSS_TLS_CERTFILE` and `MOSS_TLS_KEYFILE` to:

```text
/home/devcontainers/.local/share/moss-transcribe-diarize/acme/production/certificates/ga0-alienware-rtx4070ti.tailnet.aisight.us.crt
/home/devcontainers/.local/share/moss-transcribe-diarize/acme/production/certificates/ga0-alienware-rtx4070ti.tailnet.aisight.us.key
```

Keep private keys mode 0600. Validate a fresh Chrome profile with no certificate
exception, canonical-hostname tailnet resolution, and a genuinely LAN-only supported
client. If the LAN-only client cannot resolve/reach that hostname, report that exact
network prerequisite; do not claim tailnet success establishes LAN success.

## A2 — Agent: qualify one final candidate, not a mixture of commits

1. Record clean branch/SHA/tree/lock and wheel identity. Stage inertly with
   `ops/stage-account-candidate.sh`; no activation pointer or GPU-runtime changes.
2. Bind the real six-case quality corpus, accepted voiceprint model/two development
   corpora, Chrome, reference UI, trusted certificate/key, real service journal and
   operator socket in the acceptance profile. The example profile now includes G8/G9
   paths. Setup creates disposable browser workspaces/cookies/sentinels automatically;
   no user login, copied token or direct database seeding.
3. Run a rollback-protected internal rehearsal using the candidate's
   `mtd-phase2-cutover run --profile <private-profile> --attempt <new-exclusive-path>
   --terminal restored`. It requires Wave 3 and restores Phase 1 afterward. Preserve
   every failed attempt; fix/rebuild/requalify if the candidate changes.
4. Require core gates plus G8 and G9 individually in deterministic, deployed and
   pre-admission layers. Missing/malformed/false rows cannot become a green aggregate.
   Include real File/URL/Live, history/audio/export, ownership/revocation, interruption,
   process restart/recovery and rollback. Keep SQLite 3.53.4 and pinned Linux tooling.
5. Run four Live sessions for 600 seconds, retaining all existing capacity bars
   including per-session 95th-percentile lag ≤10 seconds. Run the mandatory eight-session
   overload/backpressure probe and six-case/two-pass quality campaign unchanged.
6. G8: recompute fresh production embeddings/rule observations, then actual Live
   enrollment, future recognition, no automatic enrollment, duplicate-label isolation,
   rename/delete, stopped-history preservation and foreign-owner rejection.
7. G9: actual two-browser direct requests to a separate trusted HTTPS test provider;
   four byte-identical deliveries at real 60/120/240-second retry intervals; invalid-output
   failure without repair; queued/running/retry cancellation and late-result rejection;
   saved results/manual title, real events, no settings sent to MOSS, no history-triggered
   inference. Hold two provider requests across another full four-session/600-second
   speech load and apply the same speech capacity bars. No paid AI provider needed.

These long deployed runs have **not** passed yet. The two G9 layers alone each contain
at least seven minutes of retry waiting plus ten minutes of load; the total campaign
takes longer. Test duration is not replaced by accelerated unit-test clocks.

## M2 — Your attended check, only when the agent says ready

Do not perform this while you want silence. The agent has not changed volume or asked
for microphone/screen permissions. When ready, reserve one short guided Chrome/macOS
session; the agent supplies the exact candidate URL and runs the canary recorder.

1. Open the trusted URL in a normal Chrome profile. Confirm no certificate warning and
   no application login. Upload the supplied speech sample; inspect transcript/export.
2. Start Live. Allow microphone capture when Chrome asks. Speak a short sentence.
3. Share the selected meeting/audio tab with its audio checkbox enabled. Confirm the
   microphone and shared-audio meters both respond and text appears.
4. Stop. Confirm finalized text/audio, reopen history, and check playback/export at
   **your chosen volume**. The agent must not raise it.
5. Repeat the required entire-screen System Audio route with its real OS permission
   choice. A tab-only pass does not establish entire-screen audio.
6. Open a second Chrome profile: first profile's meetings must not appear. Return to
   the first: its history must remain. Optionally test your own browser-configured AI
   provider; this is separate from mandatory transcription onboarding.

Permission dialogs and actual sound routing cannot be certified with file simulation.
No Apple/Safari/Windows capture parity is claimed by this Chrome/macOS canary.

## A3 — Agent: first launch and operation

Only after the full same-candidate evidence and actual attended canary pass, run the
reviewed pre-admission cutover. Verify the served candidate identity and fresh-browser
access, then announce the single HTTPS endpoint. Preserve the old deployment archive.

Enable renewal only on the qualified release:

```sh
bash ops/install-certificate-renewal.sh
systemctl --user list-timers moss-certificate-renew.timer
journalctl --user -u moss-certificate-renew.service -n 30 --no-pager
```

The timer checks twice daily with random scheduling. Renewal reuses lego's due-date
decision, then signals only the new web unit. New TLS handshakes receive the prepared
certificate; recordings/established connections and the model process are untouched.
The script verifies trusted served certificate identity, not merely signal delivery.
Failure stays visible in the service journal; it never falls back to a disruptive restart.
Actual DNS issuance/renewal remains unmeasured until M1 is supplied.

Operational checks: `account-current/bin/mtd-admin status --json` for content-free
work/queue/storage state, service journal for failures, and canonical HTTPS runtime
identity. Do not print cookie files, DNS credentials, or provider settings into reports.

Back up **SQLite and durable meeting audio together**, under a scheduled idle web-service
stop; leave the model running. Read exact paths from the private service profile, verify
zero active work, stop web, preserve database plus any WAL/SHM files and the complete
meeting-audio root in one private snapshot, then start web and verify identity/history.
Test restoration into separate disposable paths before trusting the backup. A database-only
backup is not an audio backup. Never restore a pre-launch snapshot over real user data.
The incomplete-cutover `restore` command is not post-release user-data rollback.

M3, only if necessary: coordinate a whole-host Windows/WSL cold-boot test around other
projects. No unscheduled host reboot. Until actually measured, cold-boot recovery remains
unqualified rather than inferred from a running systemd service.
