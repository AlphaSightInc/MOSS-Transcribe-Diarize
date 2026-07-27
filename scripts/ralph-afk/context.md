# Context - MOSS live meeting transcription MVP

## Ground

- Repo: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize` — branch
  `ralph/live-meeting-mvp` (cut from `main af3ac36`). Merge to `main` only at the W1 and W2 gates.
- Orchestrator host: MacStudio. `python3` = pyenv 3.12.10 (pytest 9.0.2); `swift` 6.3.2.
  Do **not** use `/usr/bin/python3` (3.9.6).
- Read before editing:
  - `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md`
    — revision 3, the design rationale and decisions D1-D13. Authoritative.
  - `CONTEXT.md` (repo glossary — lane, mixer, v2 contract, portal, helper terms)
  - `docs/adr/0001-live-v2-json-http-contract.md`
  - `LOCAL_DEPLOYMENT.md` (server layout; W3 updates it)
- **Ignore `scripts/aisight-coding-loop/`** — an inert older loop bundle with identically named
  `prd.md`/`context.md`/`prompt.md`/`progress.txt`. This loop lives only in `scripts/ralph-afk/`.
- Key code paths:
  - `moss_transcribe_diarize/app/live_auth.py` — view/capture authority, peer allowlist, pairing
  - `moss_transcribe_diarize/app/live_transport.py` — the live HTTP routes
  - `moss_transcribe_diarize/app/live_coordinator.py` — PCM → endpoint → decode → publish
  - `moss_transcribe_diarize/app/live_mixer.py` — lane mixdown and resampling
  - `moss_transcribe_diarize/app/live_ingest.py`, `live_lane_contract.py` — v2 lane ingress, replay
  - `moss_transcribe_diarize/app/live_provider_bundle.py` — manifest admission and config hashes
  - `moss_transcribe_diarize/app/live_portal.py` — the `/live` page
  - `moss_transcribe_diarize/app/web_cli.py` — `--live` flags, TLS wiring, runner proxy
  - `macos/MOSSCapture/Sources/MOSSCaptureCore/*` — capture, transport, security, native lanes
  - `ops/` — env, start scripts, systemd units, Windows networking

## Current state

Measured 2026-07-27 from MacStudio against the live hosts. Anchors are file:line on `main af3ac36`
unless stated.

**Feasibility — settled, do not re-litigate.**
- Decode is nearly free: 7.5 s span → **0.233 s** median on the running 4070Ti engine
  (RTF 0.031); 5 s → 0.137 s; 2.5 s → 0.162 s. Output already carries `[t][S01]` speaker labels.
- Live decode reuses the **already-resident** vLLM engine (`web_cli.py:87-98`) → **no extra
  VRAM**. GPU free 1360 MiB of 16376 is not a blocker.
- m4mbp → server tailnet: HTTP 200, connect 20 ms, ping avg **27 ms** (max 49, stddev 15.6).
- Uplink: 48 kHz lanes = 2.05 Mbit/s of base64 JSON; 16 kHz lanes = 0.68 Mbit/s.

**Confirmed defects.**
1. Pairing contract mismatch — client posts `/api/live/pair` expecting `{session_id,
   capture_bearer}` (`CaptureSecurity.swift:472-491`); server exposes only `pairing-codes` →
   `pairings` → `sessions` (`live_transport.py:114-173`) and returns the view token from session
   create. Client never calls `/sessions`. **Fixed already on `acl/IDEA-044--A-034@67a27b8`**
   (`pairings` line 854, `sessions` line 878) — graft, do not rewrite.
2. No pinning on `main`; `PinnedCertificateURLSessionDelegate` + `FullCertificatePinValidator`
   exist on A-034 (`CaptureHTTPTransport.swift:80-118`).
3. Frame loss on any send failure — `queue.drain()` does `removeAll()`
   (`NativeAudioBuffers.swift:60-64`) and `publishPendingFrames` abandons the current and all
   remaining drained frames on a throw (`CaptureController.swift:242-247`).
4. Viewer expiry — `VIEW_TTL_SECONDS = 900` fixed at `bind_session`, no renewal. Reproduced:
   authorized at t=899, rejected at t=3600.
5. Sequential blocking POSTs — `URLSessionCaptureHTTPClient.send` blocks on a semaphore and
   `publishPendingFrames` iterates serially; 8 POSTs per 250 ms pump ≈ 240-720 ms at measured RTT.
6. Secret store broken — code requests access group `com.alphasight.moss.capture.shared`
   (`CaptureSecurity.swift:32,89-90`) but the entitlement declares
   `$(AppIdentifierPrefix)com.alphasight.moss.capture`; strings differ and a self-signed identity
   has no Team ID. Keychain writes also fail `-25308` from any non-GUI session. A-034 already ships
   `FileCaptureSecretStore` + `CaptureSecretStoreSelection.makeDefault`.
7. No client-side 16 kHz conversion — tap defaults 48 kHz (`SystemAudioTap.swift:70`), mic uses
   device rate (`MicrophoneCapture.swift:332`); mixer resamples by linear interpolation with no
   anti-alias filter (`live_mixer.py:305-327`).

**Server state.** Deployed `163e969`; `origin/main` also `163e969`; local `main` is +84.
`/api/live/descriptor` and `/live` → 404. `MOSS_LIVE_ENABLED=0`. `webrtcvad-wheels 2.0.14` and
`onnxruntime 1.23.2` installed with metadata; WeSpeaker ONNX staged and hash-verified;
`live.crt`/`live.key` staged but SANs cover only `ga0-alienware-rtx4070ti.local` +
`IP:192.168.68.38` (**no tailnet SAN**); provider manifest is
`live-provider-manifest.provisional.json` with `source_revision:
"PROVISIONAL-UPDATE-AFTER-KEEPER"`.

**Mac state.** macOS 26.5.2, Xcode 26.5, Swift 6.3.3. `/Applications/MOSSCapture.app` absent.
Checkout is at upstream `40cf854` with `origin` = **OpenMOSS upstream**, not the AlphaSight fork.
Login keychain is **locked to SSH sessions** — `LiveTranscribe Local Dev` signing fails
`errSecInternalComponent`. A scripted self-signed identity in a dedicated keychain **does** sign
over SSH with a designated requirement that is byte-identical across rebuilds (plan D7).
`security find-identity -v -p codesigning` reports 0 valid identities for such a cert even though
`codesign` succeeds — never gate on `find-identity`.

**Gotcha — remote shell quoting.** Nested quoting through Windows conhost → `wsl.exe` → bash
fails ("The system cannot find the path specified"). Always pipe a script on stdin:
`ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s" < script.sh`.
Binary transfer: embed a `base64 -d` heredoc in that script.

## Validation

```bash
# --- narrow: live server slice (~5 s) ------------------------------------
python3 -m pytest tests/test_live_auth.py tests/test_live_portal.py -q
python3 -m pytest tests/test_live_service_runtime.py tests/test_live_provider_bundle.py \
  tests/test_live_mixer.py tests/test_live_ingest.py -q

# --- narrow: Mac client --------------------------------------------------
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
swift test --package-path macos/MOSSCapture
swift build --package-path macos/MOSSCapture --show-bin-path   # resolve real product dir

# --- real-process tracer (darwin; needs a live private-address TLS server)
# arrives with the A-034 graft as tests/test_macos_uds_tracer.py
python3 -m pytest tests/test_macos_uds_tracer.py -q

# --- wide checkpoint -----------------------------------------------------
python3 -m pytest -q

# --- server (read-only probe) -------------------------------------------
cat > /tmp/probe.sh <<'EOS'
systemctl --user is-active moss-vllm.service moss-web.service
cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git log --oneline -1
nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv
EOS
ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local "wsl.exe -d Ubuntu -- bash -s" < /tmp/probe.sh

# --- service reachability ------------------------------------------------
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.68.38:7860/                 # batch, must stay 200
curl -sk -o /dev/null -w '%{http_code}\n' https://100.64.0.8:7861/live               # live, target 200
curl -sk https://100.64.0.8:7861/api/live/descriptor | head -c 200

# --- Mac (read-only probe) ----------------------------------------------
ssh -o BatchMode=yes ga0@m4mbp 'sw_vers -productVersion; ls -d /Applications/MOSSCapture.app; \
  codesign -dv /Applications/MOSSCapture.app 2>&1 | head -5; codesign -d -r- /Applications/MOSSCapture.app 2>&1 | tail -1'

# --- manifest hashes: regenerate, never hand-edit -----------------------
python3 - <<'PY'
import json, sys
from moss_transcribe_diarize.app.live_provider_bundle import (
    LiveProviderBundleConfig, compute_live_provider_bundle_hashes)
cfg = LiveProviderBundleConfig.from_manifest(sys.argv[1] if len(sys.argv)>1 else "manifest.json")
print(json.dumps(compute_live_provider_bundle_hashes(cfg), indent=2, sort_keys=True))
PY

# --- gate merge (W1/W2 only, after the item's gate is green) -------------
git checkout main && git merge --no-ff ralph/live-meeting-mvp && python3 -m pytest -q
```

## Candidates

Ranked, highest leverage first. Mark outcomes inline (`[done <commit>]`, `[dead: <why>]`) and
prune once recorded in progress.txt.

1. **W1a — graft A-034's accepted mechanics** onto `ralph/live-meeting-mvp`: two-step pairing +
   session create, `PinnedCertificateURLSessionDelegate`, `FullCertificatePinValidator`,
   `FileCaptureSecretStore` + `CaptureSecretStoreSelection`, restart-safe authority persistence,
   and `tests/test_macos_uds_tracer.py`. Evidence: defects 1, 2, 6 above; A-034 diff is 10 files /
   +2434 lines. Validate: `swift test`, `python3 -m pytest -q`, tracer green.
2. **W1b — make `FileCaptureSecretStore` the production default** and remove the mismatched
   keychain access group so it cannot fail silently. Evidence: defect 6; `-25308` measured.
   Validate: app and CLI share one store in the tracer; no `kSecAttrAccessGroup` left in the
   production path.
3. **W1c — app-owned UDS `handoff`**: the app reads view authority and writes the pasteboard; the
   CLI loses all access to the view token and pasteboard and relays only non-secret status.
   Evidence: control-plane CTR-086 rejected A-034 for exactly this. Validate: a test proves the CLI
   cannot obtain the view token; tracer exercises `handoff`.
4. **W1d — explicit per-lane permission transitions**: `AVCaptureDevice.requestAccess(for:
   .audio)` for the microphone plus a system-audio tap-start transition, generation-fenced, with
   pending/granted/denied per lane, duplicate `start` idempotent, stop-during-prompt safe, late
   callbacks harmless. **A denied lane must emit a typed lane failure** — a never-observed lane
   stalls the mixer frontier forever. Validate: state/race tests including the denied-lane path.
5. **W1e — retained-until-ACK outbox**, 15 s per lane keyed by `(lane, sequence)`, idempotent
   retry on timeout/429/ambiguous, drop only on successful ack, typed degraded state on overflow.
   Evidence: defect 3. Validate: tests for outage, ambiguous ack, duplicate retry, overflow.
6. **W1f — transport pacing**: 0.5 s frames, 0.5 s pump, two lanes posted concurrently on a
   keep-alive session. Evidence: defect 5, 27 ms RTT. Validate: a test asserting per-pump wall
   time and that lane posts are concurrent.
7. **W1g — 16 kHz mono conversion on the Mac** via `AVAudioConverter` for both lanes. Evidence:
   defect 7; 3× uplink reduction; makes the mixer grid 1:1. Validate: emitted frames report
   `sample_rate: 16000` and `sample_count` 8000; a conversion unit test.
8. **W1 gate + merge** — full suites, tracer zero skips, discriminator red→green, then merge to
   `main`.
9. **W2a — session-lifecycle view authority**: active + 2 h grace + 12 h cap + immediate revoke on
   abort/device-revocation/operator revoke, replacing the fixed 900 s. Evidence: defect 4.
   Validate: tests at the cap boundary, grace boundary, revoke, and a virtual 60-minute run.
10. **W2b — bounds retune** in the provider manifest: `hard_cap_samples` 40000,
    `max_retained_samples` 960000, `frame_samples` 8000. Evidence: 7.5 s cap gives p95 ≈ 9.2 s and
    fails the 6 s gate; 2.5 s gives ≈ 4.6 s. Validate: descriptor reflects the values; latency
    recomputed in the canary.
11. **W2 gate + merge** — deterministic reliability tests green, then merge to `main`.
12. **W3a — publish**: push `main` (84 commits) to `origin`, then fetch and checkout the exact SHA
    on the server. Validate: three-way `git rev-parse HEAD` equality.
13. **W3b — final provider manifest** from the provisional one: real `source_revision`, retuned
    bounds, hashes regenerated with `compute_live_provider_bundle_hashes`, assets keeping their
    verified sha256. Validate: `LiveProviderBundleConfig.from_manifest(...).preflight()` clean on
    the server.
14. **W3c — reissue TLS** with `DNS:ga0-alienware-rtx4070ti.tailnet.aisight.us,
    DNS:ga0-alienware-rtx4070ti.local, IP:100.64.0.8, IP:192.168.68.38`; record the new pin hash.
    Validate: `openssl x509 -noout -ext subjectAltName -fingerprint -sha256`.
15. **W3d — dedicated live service**: `ops/moss-live.env` + `ops/systemd/moss-live-web.service` on
    port 7861 with its own runs dir, `MOSS_LIVE_ENABLED=1`, lease 30 s, auth state 0600; teach
    `ops/start-web.sh` to honour port and runs-dir overrides. Evidence: `--live` turns the whole
    port to HTTPS and would break plaintext 7860. Validate: 7861 → 200 and 7860 → 200 plaintext.
16. **W3e — Windows forwarding for 7861**: extend `ops/configure-windows-network.ps1` (currently a
    single scalar `$listenPort`) to portproxy and firewall both ports. Validate: from m4mbp,
    `curl -sk https://100.64.0.8:7861/live`.
17. **W3f — `ops/live-pair.sh`**: mint a pairing payload from server loopback, print it once with
    the current pin hash, never to a log or file. Validate: run it, confirm no secret lands on disk.
18. **W3g — update `LOCAL_DEPLOYMENT.md`**: addresses, the 7860/7861 split, rollback commands.
19. **W4a — `macos/scripts/bootstrap-signing-identity.sh`**: idempotent self-signed codeSigning
    identity in a dedicated keychain with a 0600 password file, `set-key-partition-list` for
    codesign, reusing an existing cert so the designated requirement never changes. Validate:
    `codesign` exit 0 and a stable DR across two builds — **not** `find-identity`.
20. **W4b — `macos/scripts/build-app.sh`**: assemble `MOSSCapture.app` (Info.plist, entitlements),
    sign `--options runtime`, verify bundle id / entitlements / DR, print the DR hash.
21. **W4c — install**: add the AlphaSight fork as a remote on m4mbp, fast-forward to the exact SHA,
    install the app to `/Applications/MOSSCapture.app` and the CLI to `/usr/local/bin/mtd-capture`.
22. **W4d — TCC grants (human step)**: launch from the GUI, one `start`, then physical clicks for
    Microphone and System Audio Recording. Record the exact click sequence as a blocker and move
    on; never retry, never touch the TCC database.
23. **W5a — 60-second canary** per prd.md acceptance bar.
24. **W5b — 300-second locked certification**, including the 5-second interruption and the
    mic-granted / system-audio-denied variant.
25. **W5c — rehearse and record rollback**, then restore.

## Non-candidates

- **The RTX 4090.** The operator fixed the 4070Ti as the target; the 4090 is committed elsewhere.
- **Resuming the governed `aisight-coding-loop`.** Its `.stop-after-current-role` sentinel stays;
  two autonomous writers would interleave branches and promotions.
- **Provisional/partial decode.** Measured decode makes span-cap tuning sufficient;
  `begin_provisional`/`publish_provisional` stay test-only.
- **Server-side resampler rework.** Converting on the Mac (candidate 7) makes the mixer grid 1:1,
  so the linear-interpolation path stops mattering.
- **Durable transcript persistence, export, speaker rename/merge, search, browser-initiated
  capture start, linking `/live` from the batch UI.** Post-MVP.
- **Developer ID, notarization, Gatekeeper or SIP changes.** A local self-signed identity is
  proven sufficient.
- **Windows client / IDEA-041.** Deferred until the Mac path is certified.
- **Intermittent-speaker identity calibration (CTR-043 / IDEA-027).** A pre-existing batch quality
  issue, not a live blocker.
- **30-minute live soaks.** Certification is 60 s and 300 s only.
