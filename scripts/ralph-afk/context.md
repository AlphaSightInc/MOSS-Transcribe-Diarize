# Context - MOSS live meeting transcription MVP

## Ground

- Repo: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize` — branch
  `ralph/live-meeting-mvp` (cut from `main af3ac36`). Keep all client and server implementation
  on this branch; merge **once** only after Phase A, production-client, server-reliability, and
  tracked deployment/install-artifact gates are all green.
- Orchestrator host: MacStudio. `python3` = pyenv 3.12.10 (pytest 9.0.2); `swift` 6.3.2.
  Do **not** use `/usr/bin/python3` (3.9.6).
- Read before editing:
  - `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/docs/live-capture-gap-and-execution-plan-20260727.md`
    — current controlling revision, the design rationale and decisions D1-D13. Authoritative.
  - `CONTEXT.md` (repo glossary — lane, mixer, v2 contract, portal, helper terms)
  - `docs/adr/0001-live-v2-json-http-contract.md`
  - `LOCAL_DEPLOYMENT.md` (server layout; Phase C updates it)
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
- Warm 12-run decode p95: 7.5 s span → **0.241 s**; 2.5 s → **0.162 s**. One pre-warm
  2.5 s request took 3.851 s, so certification must warm the resident engine before timing.
  Output already carries `[t][S01]` speaker labels.
- Live decode reuses the **already-resident** vLLM engine (`web_cli.py:87-98`) → **no extra
  VRAM**. GPU free 1328 MiB of 16376 after the probe is not a blocker.
- Latest m4mbp → 4070Ti tailnet probe: ping avg **72 ms**, max **146 ms**. Treat callback cadence
  and tailnet latency as variable; no fixed request-rate assumption is valid.
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
5. Unbounded callback-shaped blocking POSTs — native queue emission follows Core Audio callback
   sizes rather than fixed 0.5 s frames; `URLSessionCaptureHTTPClient.send` blocks on a semaphore
   and `publishPendingFrames` iterates serially. Request rate therefore varies with device
   callback cadence and can outrun the pump at the measured 72 ms average / 146 ms max RTT.
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
printf '%s\n' \
  'set -e' \
  'systemctl --user is-active moss-vllm.service moss-web.service' \
  'cd /mnt/d/Coding/MOSS-Transcribe-Diarize && git log --oneline -1' \
  'nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
    "wsl.exe -d Ubuntu -- bash -s"

# --- service reachability ------------------------------------------------
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.68.38:7860/                 # batch, must stay 200
curl -sk -o /dev/null -w '%{http_code}\n' https://100.64.0.8:7861/live               # live, target 200
curl -sk https://100.64.0.8:7861/api/live/descriptor | head -c 200

# --- Mac (read-only probe) ----------------------------------------------
ssh -o BatchMode=yes ga0@m4mbp 'sw_vers -productVersion; ls -d /Applications/MOSSCapture.app; \
  codesign -dv /Applications/MOSSCapture.app 2>&1 | head -5; codesign -d -r- /Applications/MOSSCapture.app 2>&1 | tail -1'

# --- host manifest finalization (tool arrives in Phase C) ----------------
printf '%s\n' \
  'set -euo pipefail' \
  'cd /mnt/d/Coding/MOSS-Transcribe-Diarize' \
  'python3 ops/finalize-live-provider-manifest.py --input "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json" --output "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json" --source-revision "$(git rev-parse HEAD)" --hard-cap-samples 40000 --max-retained-samples 960000 --frame-samples 8000' |
  ssh -o BatchMode=yes gyauo@ga0-alienware-rtx4070ti.local \
    "wsl.exe -d Ubuntu -- bash -s"

# --- Phase A compatibility checkpoint ------------------------------------
# Run the exact eleven registered commands from:
# /Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/context/VALIDATION_COMMANDS.md
# section "IDEA-044 attempt-2 exact commands", then:
bash scripts/ralph-afk/validate-phase-a-locality.sh

# --- one keeper merge, primary worktree stays on the feature branch -------
swift test --package-path macos/MOSSCapture
python3 -m pytest tests -q -p no:cacheprovider
test -z "$(git status --porcelain)"
bash scripts/ralph-afk/merge-keeper.sh
```

## Candidates

Strictly ordered by phase. Mark outcomes inline (`[done <commit>]`, `[dead: <why>]`) and prune
only after the durable result is in progress.txt.

### Phase A — preserve and close IDEA-044 before widening scope

1. **A1 — graft A-034's accepted mechanics**: two-step pairing/session create,
   `PinnedCertificateURLSessionDelegate`, `FullCertificatePinValidator`, restart-safe authority
   persistence, environment-selected `FileCaptureSecretStore`, and
   `tests/test_macos_uds_tracer.py`. Keep Keychain the unconditional production default in this
   phase. Graft from `acl/IDEA-044--A-034@67a27b8`; do not rewrite.
2. **A2 — app-owned UDS `handoff`**: app reads view authority and writes pasteboard; CLI sends one
   authenticated UDS request and relays non-secret status only.
3. **A3 — explicit per-lane permission coordinator**: microphone `requestAccess(.audio)`,
   user-started system tap transition, generation-fenced pending/granted/denied, duplicate-start
   idempotence, stop-during-prompt, late-callback rejection, and typed denied-lane failure.
4. **A4 — compatibility checkpoint**: run the exact eleven registered IDEA-044 attempt-2
   commands plus `bash scripts/ralph-afk/validate-phase-a-locality.sh`. Required: 10/10, 16/16,
   zero Darwin skips, all other commands green. Commit and record the exact SHA. **Do not merge,
   push, or begin Phase B until this is green.**

### Phase B — production Mac reliability

5. **B1 — production file secret store**: now make `FileCaptureSecretStore` the default at
   `~/Library/Application Support/MOSSCapture/`; directory 0700, files 0600, atomic replacement,
   app/CLI same path. Remove the mismatched access group from the dormant Keychain opt-in.
   Replace the lab-default source assertions with behavioral permission/secrecy tests; do not
   edit the historical control-plane discriminator.
6. **B2 — retained-until-ACK outbox**: 15 s/lane keyed by `(lane, sequence)`; retry identical
   frames on timeout/429/ambiguous result; release only after ACK; typed degraded state on
   overflow. Test 5 s outage, ambiguous success, duplicate retry, 429, and overflow.
7. **B3 — 16 kHz mono conversion/coalescing**: one stateful `AVAudioConverter` per lane,
   callback work still copy/enqueue only, timestamps/sample counts preserved. Test 48 kHz and
   44.1 kHz inputs, output rate 16000, exact steady 8000-sample frames, partial terminal flush,
   duration conservation, and no callback-thread DSP.
8. **B4 — bounded concurrent transport**: 0.5 s pump; persistent URLSession; at most one
   in-flight POST per lane, lanes concurrent; no overlapping pump re-entry. Test bounded
   in-flight work and wall time—never use a sleep-only timing assertion.
9. **B5 — tracked Mac packaging/install tools**:
   `macos/scripts/bootstrap-signing-identity.sh`, `build-app.sh`, and `install-app.sh`;
   idempotent, scratch-path testable, no real keychain/app/install mutation during tests.
10. **B6 — client gate**: both Swift products build; Swift suite and full Python suite green;
   Darwin built-process tracer zero skips; retry/concurrency/conversion tests green; leak scan
   clean. Record the exact SHA. The Phase-A source discriminators are historical evidence, not
   final gates after the deliberate B1–B5 production changes.

### Phase C — server meeting reliability, then one merge

11. **C1 — session-lifecycle view authority**: active-session-only + 12 h cap + immediate revoke
    on clean terminal, abort, device revocation, or operator revoke. Test virtual 60 minutes,
    exact cap, every terminal/revocation boundary, and restart behavior. Keep tokens out of
    URL/storage/logs; do not invent post-terminal grace without persistence.
12. **C2 — bounds retune**: `hard_cap_samples=40000`,
    `max_retained_samples=960000`, `frame_samples=8000`; generated bundle hashes, never hand
    edited. Test descriptor/config admission and capacity headroom.
13. **C3 — tracked deployment bundle**: manifest finalizer, TLS generator, live env/service
    templates, start-web overrides, two-port Windows networking, loopback pairing helper, and
    deployment docs. Test generation/default-off/secrecy/7860-preservation without host mutation.
14. **C4 — final local gate and single keeper merge**: Swift/full Python/tracer/reliability
    gates green on the feature tip; then run `scripts/ralph-afk/merge-keeper.sh`. It creates and
    tests the one no-ff merge in a temporary `main` worktree while the primary Ralph worktree
    remains on the feature branch. Record feature + merge SHAs. After this point, only Ralph
    evidence files may change on the feature branch; no tracked product source may change.

### Phase D — publish and enable the 4070Ti

15. **D1 — publish reviewed `main`**: push the merge SHA to `origin`, then fetch/checkout that
    exact SHA at `/mnt/d/Coding/MOSS-Transcribe-Diarize` on
    `gyauo@ga0-alienware-rtx4070ti.local`. Record rollback before mutation; verify three-way SHA
    equality.
16. **D2 — host manifest/TLS**: run the reviewed finalizer and TLS generator; verify merge SHA,
    generated hashes, four SANs, and fingerprint; rotate pin/pairing together.
17. **D3 — install reviewed live service/networking**: create host-local env/auth state, install
    reviewed 7861 unit, apply reviewed two-port forwarding/firewall, start only live service.
18. **D4 — verify/pair**: 7861 TLS live + descriptor 200, 7860 plaintext batch 200, use reviewed
    loopback helper once, verify no secret artifact. No tracked product/deployment edits after
    merge; only Ralph evidence may advance on the feature branch.

### Phase E — Mac install and human permission boundary

19. **E1 — run reviewed signing tool**: create/reuse dedicated-keychain self-signed identity;
    validate `codesign` and stable designated requirement, never `find-identity`.
20. **E2 — run reviewed build/install tools**: verify identifier, entitlements, DR, and pin; add
    AlphaSight remote on m4mbp; fast-forward exact SHA; install app and CLI. Record rollback first.
21. **E3 — TCC human step**: GUI launch and one `start`; report exact Microphone and System Audio
    Recording clicks. Never touch TCC DB or retry autonomously. Continue only after operator
    confirms both grants.

### Phase F — certification and rollback

22. **F1 — 60 s canary** per prd.md.
23. **F2 — 300 s locked run** with 5 s interruption and the system-audio-denied variant.
24. **F3 — 16-minute active-view soak**: capture and `/live` polling stay active with periodic
    two-lane audio; same authority works after minute 15; clean stop immediately revokes it.
25. **F4 — rehearse/record rollback, restore service, and close** only when every PRD acceptance
    item has evidence.

## Non-candidates

- **The RTX 4090.** The operator fixed the 4070Ti as the target; the 4090 is committed elsewhere.
- **Resuming the governed `aisight-coding-loop`.** Its `.stop-after-current-role` sentinel stays;
  two autonomous writers would interleave branches and promotions.
- **Provisional/partial decode.** Measured decode makes span-cap tuning sufficient;
  `begin_provisional`/`publish_provisional` stay test-only.
- **Server-side resampler rework.** Phase-B conversion makes the mixer grid 1:1,
  so the linear-interpolation path stops mattering.
- **Durable transcript persistence, export, speaker rename/merge, search, browser-initiated
  capture start, linking `/live` from the batch UI.** Post-MVP.
- **Developer ID, notarization, Gatekeeper or SIP changes.** A local self-signed identity is
  proven sufficient.
- **Windows client / IDEA-041.** Deferred until the Mac path is certified.
- **Intermittent-speaker identity calibration (CTR-043 / IDEA-027).** A pre-existing batch quality
  issue, not a live blocker.
- **30-minute live soaks.** Certification is 60 s, 300 s, and one 16-minute active-view soak.
