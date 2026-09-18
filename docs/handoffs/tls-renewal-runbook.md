# TLS renewal preparation — WP13

**Prepared, not installed.** On 2026-09-18, an ordinary Python TLS client rejected
`:7861` (self-signed) and accepted `:7862` (Let's Encrypt; expires 2026-12-09
21:32:04 UTC, 82.70 days remaining). Evidence: `evidence/mvpfix/wp13/live-{7861,7862}.json`.
This is client trust evidence, not attended Chrome proof or host configuration proof.

## Contract and decision

A certificate is a hostname identity signed by a trusted authority. Renewal updates
files; the running server must also load those files. Every listener needs checking:
renewing a shared file does not prove either port serves it.

**D1 — Prepared mechanism:** reuse installed lego v5 DNS-01 issuance, its own due-renewal
policy, and existing SIGHUP reload; reconcile both listeners after every run. This
avoids restarting recordings and recovers a prior partial reload. No new application
code or renewal scheduler is needed. Reject this design if a new handshake keeps the
old certificate, a held request is interrupted, or an invalid pair replaces a good one.
Local real-socket measurement passed all three; details: `ops/tls/NOTES.md`.

**D2 — Authority remains pending:** final-review ledger I10-D05 has no approved
supersession authority. Code presence and the local test do not authorize enabling
live reload. The actual 7861 owner has no reload action: this design is not
install-and-run on the current host. Obtain explicit owner approval for DNS challenge writes, certificate
issuance/installation, unit changes, SIGHUP on both services, and timer activation.
All those actions are **UNEXECUTED by WP13**. If reload is not approved, the owner
must schedule an attended restart/cutover; WP13 does not implement that fallback.

## Existing layout and traps

- **F1 — Name:** `ga0-alienware-rtx4070ti.tailnet.aisight.us`, same DNS Subject
  Alternative Name (SAN) on both ports. Ports are not certificate identities. Test
  this canonical name from each supported LAN/tailnet client; an IP URL is not equivalent.
- **F2 — Readers:** `app/phase2_web_cli.py` requires `--tls-certfile/--tls-keyfile`,
  builds Uvicorn's TLS context, and calls `serve_with_certificate_reload`.
  `app/tls_reload.py` prepares a new context on SIGHUP, keeps established connections,
  and rejects invalid pairs. `ops/account-web-launcher.sh` gets paths from
  `MOSS_TLS_CERTFILE/MOSS_TLS_KEYFILE` and fixes the web port at 7861.
- **F3 — Units:** `ops/systemd/moss-web.service` has `ExecReload=/bin/kill -HUP $MAINPID`.
  **Live inventory differs:** active `moss-web.service` serves 7860 and has no
  ExecReload. Active `moss-live-web.service` owns 7861 and has no ExecReload.
  `moss-internal.service` owns 7862, has HUP ExecReload, and reads the production
  lego pair. The prepared command targets `moss-live-web.service`/7861 and
  `moss-internal.service`/7862, not the unrelated 7860 service. Qualify the admitted
  phase2 runtime on the 7861 unit before activation; adding ExecReload alone can
  terminate a process without the signal handler. Evidence: `host-readonly.json`
  and `host-ports-readonly.json` under `evidence/mvpfix/wp13/`.
- **F4 — DNS/client:** `ops/manage-certificate.sh` uses lego v5, `--dns netlify`,
  `NETLIFY_TOKEN_FILE`, separate staging/production roots, and public recursive
  resolvers `1.1.1.1:53,8.8.8.8:53`. Netlify uses NS1 infrastructure: the old
  production-plan's NS1 wording does not mean a direct NS1 API credential works.
  MagicDNS SOA lookup previously returned NOTIMP; do not remove explicit resolvers.
  Headscale's custom name does not establish hosted Tailscale `.ts.net` issuance.
  Read-only host inspection confirmed lego 5.3.1 and both private input files at
  mode 0600; contents/permissions at the DNS provider were not inspected.
- **F5 — Old automation:** `ops/manage-certificate.sh --renew` and
  `ops/install-certificate-renewal.sh` only reconcile `moss-web.service`/7861.
  Do not use that installer for the two-port setup. The prepared `ops/tls/renew.py`
  shares its operation lock but checks/reloads both actual TLS services.
  Both renewal service and timer are currently absent (LoadState=not-found). Existing timer template
  is reusable after the service's ExecStart is changed as below.

References: [lego Netlify provider](https://go-acme.github.io/lego/dns/netlify/) and
[lego v5 run/renewal behavior](https://go-acme.github.io/lego/obtain/), read 2026-09-18.
Existing ops files, not the historical handoff, establish the prepared command shape.

## Now: safe, read-only checks

From the repo, `python3 ops/tls/renew.py --dry-run` prints the offline plan. It reads
no private files, spawns no commands, and does not test prerequisites. **Dry-run is
not ACME staging:** a staging run still writes DNS challenges and account files.

```sh
python3 ops/tls/verify.py ga0-alienware-rtx4070ti.tailnet.aisight.us 7861
python3 ops/tls/verify.py ga0-alienware-rtx4070ti.tailnet.aisight.us 7862
```

Exit 0 requires normal system-root trust, hostname match, identical leaf across
verified/diagnostic connections, and every served certificate at least 21 days from
expiry. Exit 1 means fail (including unreachable/unparseable); argparse exits 2 on
invalid syntax. JSON contains certificate metadata, no HTTP content or credentials.
The diagnostic connection never turns a trust failure into success. Chrome has its
own trust environment; do not import this certificate as a root to make the test pass.

## Later: authorized operator execution only — UNEXECUTED

1. Read active units and TLS paths as the service-owning WSL user (`devcontainers`
   in the prior ops layout). Confirm both services actually run the qualified reload
   code and their ExecReload sends HUP only to their own main process. Confirm which
   files each reads. Both must use the production lego pair below before automation.
   Current blocker: 7861's `moss-live-web.service` lacks reload. Install the admitted
   phase2 runtime under that unit only in the approved cutover; establish its TLS paths
   and qualify its signal handler before enabling ExecReload. The prepared script
   fails at this preflight before any DNS issuance. Record existing paths and keep
   the last known good pair privately for rollback.
2. Privately provision/check mode-0600 `~/.config/moss-transcribe-diarize/netlify-token`
   and `certificate.env` containing one literal `MOSS_ACME_EMAIL=operator@example.com`
   assignment. Use the actual contact privately. Never paste either value into chat,
   a report, or git. Confirm Netlify authority for `_acme-challenge.` + canonical name;
   use the narrowest available account permissions. Do not change A records/network.
3. On the authorized host, first `bash ops/manage-certificate.sh --check`, then
   `--staging` in the separate staging root. Only after that succeeds, use `--issue`
   if initial production issuance is needed. Never force production renewal as a test.
   None of these commands is part of WP13's executed work.
4. The production pair is under
   `~/.local/share/moss-transcribe-diarize/acme/production/certificates/`, named
   `ga0-alienware-rtx4070ti.tailnet.aisight.us.crt` and `.key`; private key mode 0600.
   Wire both services to this pair during the approved installation/cutover. Changing
   environment paths requires the separately approved restart/cutover; HUP rereads
   the existing configured paths and cannot change them. Never install staging files.
5. Install `renew.py` and `verify.py` together in the private
   `~/.local/share/moss-transcribe-diarize/certificate-ops/tls/` directory (0700;
   scripts 0500). Prepare `moss-certificate-renew.service` from the existing template,
   replacing ExecStart with
   `/usr/bin/python3 %h/.local/share/moss-transcribe-diarize/certificate-ops/tls/renew.py --apply`.
   Keep UMask=0077. Use `TimeoutStartSec=20min` for issuance plus both verification
   loops. This is an operator installation step, not a deployed file in WP13.
6. After explicit reload authority and prerequisite validation, run that command
   manually once. It uses lego's due decision (no forced renewal), validates the pair,
   compares exact leaf bytes (no added fingerprints), and reloads mismatched listeners.
   Repeating a successful run sends no HUP. A saved certificate with one stale listener
   is retried on the next run. Provider stdout/stderr is suppressed; only fixed events
   and port/status are logged. On failure, use a private attended diagnosis; never paste
   raw ACME output into evidence. Do not restart automatically.
7. Run both verifier commands from the client. Then attended Chrome: fresh normal
   profile, no certificate exceptions or ignore flags; open each canonical HTTPS URL,
   inspect trusted connection/certificate/SAN/expiry, confirm secure context and
   microphone permission flow. Retain content-safe certificate/error details only.
   Test LAN and tailnet resolution separately. Chrome trust remains **UNMEASURED** here.
8. Once manual renewal/reload and attended trust pass, install the existing timer
   template, daemon-reload and enable it under the approved host session. Existing
   twice-daily schedule is retained. Check next/last trigger and service result;
   arrange operator review of failures and the 21-day client check. No timer is enabled
   by this repository change. A no-op run before expiry is not proof of actual renewal;
   observe the next real due renewal (or an approved isolated staging renewal rehearsal).

## Failure and rollback

If DNS/issuer fails, do not reload. If the pair is invalid, the script fails before
signals; the server also retains its last valid context. If one listener fails client
verification, exit nonzero and keep the other service running; record which port failed.
Stop/disable the timer in the authorized session, restore the backed-up cert/key to
both configured file paths, then perform the approved reload and verify both ports.
If configuration paths changed, restore the unit/profile and use the approved cutover
procedure. An expired/untrusted backup is not a recovery: schedule owner intervention.
No script silently changes trust roots, DNS provider, hostname, or restarts services.
