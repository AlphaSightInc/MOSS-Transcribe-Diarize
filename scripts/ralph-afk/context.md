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
    — current controlling revision, the design rationale and decisions D1-D14. Authoritative.
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

Measured 2026-07-27 from MacStudio against the live hosts. Anchors are file:line on the feature
branch after the iteration-1 graft unless stated.

**Branch state.** Iteration 1 merged `acl/IDEA-044--A-034@67a27b8` into `ralph/live-meeting-mvp`
with `--no-ff` (conflict-free: A-034 branches from the same `af3ac36` and touches paths disjoint
from the Ralph scripts). Iteration 2 added the per-lane permission coordinator (A3); iteration 3
moved the portal handoff into the app (A2); iteration 4 rebuilt the tracer around the immutable
lab bundle (A4); iteration 5 made the file secret store the production default (B1); iteration 6
added the retained-until-ACK outbox (B2); iteration 7 added the 16 kHz/8000-sample wire format and
converted-nanosecond timestamps (B3); iteration 8 added the bounded concurrent transport (B4);
iteration 9 added the tracked Mac packaging/install tools (B5); iteration 10 recorded the Phase B
client gate (B6) and changed no product source.
Test totals on the branch: Swift **121 passed**
(67 → 81 → 92 → 95 → 98 → 106 → 116 → 121); Python **466 passed / 2 skipped / 346 subtests**
including `tests/test_macos_uds_tracer.py` **3 passed** (1 hung → 2 → 3) and
`tests/test_macos_packaging_tools.py` **9 passed** (new in iteration 9).

**Phase B client gate: GREEN at `3fb5567` (iteration 10).** Product-tree SHA `3fb5567`; the
checkpoint commit adds only `scripts/ralph-afk/*`, so
`git diff --name-only 3fb5567 HEAD -- ':!scripts/ralph-afk'` is empty. Recorded: both Swift products
build from an empty scratch path in 8.7 s with **zero warnings**; `swift test` **121 passed /
0 failures**; `pytest tests` **466 passed / 2 skipped / 346 subtests** (the two skips are
`tests/test_large_upload.py`'s pre-existing Python-3.10 compatibility contract, not Darwin skips);
the Darwin tracer is **3 passed / 0 skips** *from a deleted lab bundle*, so the whole chain from no
bundle to a paired built app is proven cold; B1/B2/B3/B4 filters 5/10/11/5 passed; attempt-2
discriminator **10/10**; `leak-scan: clean`; and MacStudio is left with no
`~/Library/Application Support/MOSSCapture`, no `/Applications/MOSSCapture.app` and no
`moss-signing.keychain-db`. **Phase C is open.**

**IDEA-044 attempt-2 checkpoint: GREEN at `1ede498` (iteration 4).** Discriminators **10/10** and **16/16**;
all eleven registered commands plus `validate-phase-a-locality.sh` pass; tracer is 3 passed /
**0 Darwin skips**. That commit is the frozen historical evidence — do not try to reproduce
16/16 on the tip.

**Deliberate post-checkpoint delta (iteration 5, B1).** On the tip the attempt-2 discriminator is
still **10/10**, but `idea-044-real-uds-tracer/repro.py` is **14/16**: checks **09** and **15**
fail by design because they assert `keychain_still_default` and the `MOSS_CAPTURE_SECRET_STORE_PATH`
literal inside each `main.swift`. B1 removed both — the default is now the file store and the
env-key literal lives only in `CaptureSecretStoreSelection`. Their replacement evidence is
behavioral (see below). Never edit those control-plane scripts to recolor this.

**`validate-phase-a-locality.sh` is historical from iteration 6 on.** Its own header says later
production phases widen scope, and its allowlist is the thirteen registered A4 paths. It is
**green at the frozen checkpoint** — `git diff --name-only af3ac366 1ede498` is exactly that
allowlist — and it now fails on the tip on `CaptureController.swift` plus the new
`CaptureOutbox.swift`, `NativeLaneWireFormat.swift`, `CapturePublishPump.swift`, `macos/scripts/*`
and `tests/test_macos_packaging_tools.py`, which Phase B is authorized to add. Verify it against
`1ede498`, never against the tip, and do not add paths to the script.

**Lab bundle contract (new, iteration 4).** The tracer's one fixed path is
`macos/MOSSCapture/.build/idea044-lab/MOSSCapture.app` (gitignored via `macos/MOSSCapture/
.gitignore:1`), held under an exclusive `flock` on `install.lock` for the whole pytest process.
It is installed **once** — copy the built `MOSSCaptureApp`, write the product `Info.plist`
verbatim (identifier `com.alphasight.moss.capture`, both `NSAudioCaptureUsageDescription` and
`NSMicrophoneUsageDescription`), ad-hoc sign — and its identity is recorded in a sibling
`first-install-evidence.json` (`schema: idea044-lab-bundle-evidence.v1`): per-file inventory
hashes, `executable_sha256`, `bundle_sha256`, `designated_requirement`
(`designated => cdhash H"…"`), and the provenance `built_product` `{macho_uuid, sha256}`.
Every later node re-observes the bundle and asserts the recorded evidence *and* that the evidence
file's own inode/mtime/bytes did not move — so a rebuild at the same path is not continuity
proof. A reinstall happens only when the built product's Mach-O UUID or sha256 changes, and it
rewrites the evidence as a new first install. Everything else — certificate, server, port, UDS,
secret store, artifacts — stays per-test temporary. Ad-hoc signing means the cdhash is stable
across runs, so the lab bundle is the only surface on which real TCC continuity could later be
observed; that observation is still the E3 human step. Measured in iteration 10: deleting the whole
`idea044-lab` directory and re-running reproduces `bundle_sha256 990bc18f…`,
`executable_sha256 5b0f5c98…` and `designated => cdhash H"d01b39e2…"` byte for byte, so the identity
is a property of the built inputs, not of the surviving directory.

**Secret-store contract (new, iteration 5).** `CaptureSecretStoreSelection.makeDefault()` is the
only resolver and both composition roots call it with no arguments, so app and CLI cannot drift:
the path is `defaultPath(homeDirectory:)` = `~/Library/Application Support/MOSSCapture/secrets.json`,
overridden only by a non-empty `MOSS_CAPTURE_SECRET_STORE_PATH` (what the tracer uses). The
returned store is always `FileCaptureSecretStore`; `KeychainCaptureSecretStore` is dormant,
unreachable from either product, and no longer carries an access group. Construction is
side-effect free — `mtd-capture` printing usage must not create a directory in the user's home —
so the 0700 directory is materialized on first write. A save writes a fresh `O_EXCL` file at
exactly 0600, `fsync`s it, and `rename(2)`s it over the live path: readers never see a partial
document and the live path never exists wider than 0600. A widened *directory* is tightened on the
next save (it cannot expose a 0600 file); a widened *document* is refused with
`secretStorePathNotPrivate` (its bytes may already have been read). `validateFile` uses `lstat` and
demands a regular file, so a symlink planted at the path is rejected.

**Outbox contract (new, iteration 6).** `CaptureFrameOutbox` (`CaptureOutbox.swift`) sits between
`source.pendingFrames()` and `transport.publish`. It is the authority for **wire identity**: it
stamps the `(lane, sequence)` a frame keeps for every attempt, so the emitter's per-lane counter is
only a source-local production count. Capacity is **15 s of audio per lane**, measured from each
frame's own `sampleCount / sampleRate`, so it survives B3's rate/frame-size change unedited. Audio
is released **only** by `acknowledge(lane:sequence:)` after a 2xx publish; every failure — 429,
5xx, `URLError`, even a fatal 401 — leaves the frame queued. On overflow the outbox **refuses the
new frame** rather than evicting a retained one (evicting would leave a permanent hole in the
lane's sequence stream and the server rejects every later frame as out of order), counts it in
`refusedFrames`, sets sticky `degradation` (`overflowedLaneRetention` / `undeliverableFrame`, never
cleared by later success), and marks the next frame that lane admits `discontinuity = true`.
`reset()` runs on every `start`, because a new server session counts each lane from zero.
The pump flushes in **global admission order** and stalls only the failing lane (one head retry per
lane per tick, no backlog hammering); `CaptureStatus.outbox` and
`ControlChannelResponse.outboxRetainedFrames` / `.outboxDegradation` expose depth and the typed
degraded state. The `moss-live-helper-health.v1` heartbeat wire is untouched.
`CaptureFrameRetryPolicy` is the single classifier: 0/408 → `ambiguous`, 429 → `backpressure`,
5xx → `serverUnavailable`, the transient `URLError` set → `ambiguous`; 4xx, `missingCaptureBearer`,
`missingCertificatePin`, `secureConnectionFailed`, `cancelled` → not retryable.

**Wire-format contract (new, iteration 7).** `NativeLaneWireFormat.swift` holds everything that is
unsafe on a Core Audio callback thread, and `NativeLaneFrameEmitter` is the only caller.
`NativeLaneWireFormat.live` is the domain contract (16000 Hz, 8000 samples); the emitter takes it
plus a `MachHostTimeConverting` and a resampler factory, all defaulted, so the products get the
contract and tests can state a timebase. Per lane, `NativeLaneWireStream` runs: convert host ticks
→ ns; downmix to mono; resample through **one stateful `AVAudioConverter`** (identity short-circuit
when the device is already on the grid); coalesce into exact 8000-sample frames. Timestamps are
**re-derived from every buffer's own converted capture instant** (`pendingStartNS = capturedNS −
duration(pending)`), never accumulated from the frame cadence, so a meeting-length run tracks the
device clock instead of drifting; the cost is ≤ 1 wire sample (62.5 µs) of cadence jitter and a
fixed converter group delay measured at 0.67 ms. A frame is emitted **only** at full size; the
trailing partial leaves through `flush()`, which `NativeDualCaptureSource.stop` calls before
parking the tail for one last `pendingFrames()`, and `CaptureController.stop` now drains once after
stopping the source so that tail actually reaches the wire. An unusable capture instant — zero
ticks, `AVAudioTime` without `isHostTimeValid`, `AudioTimeStamp` without `.hostTimeValid` — makes
the buffer be **refused**, counted (`drainRejectedBufferCounts()` → a `.discontinuity` lane fact),
and the lane's next frame `discontinuity = true`. Never fabricate a timestamp. A device-timeline
gap beyond one wire sample, a `deviceEpoch` change, or a driver-flagged buffer breaks the timeline
the same way. `MachTimebaseHostTimeConverter` divides before multiplying and returns `nil` rather
than wrapping.

**Transport-pump contract (new, iteration 8).** `CapturePublishPump.swift` holds
`CaptureFramePublishPump`, the only thing that calls `transport.publish`. It bounds the transport
two independent ways. *Width*: one pre-created serial `DispatchQueue` per lane, so a lane has at
most one request in flight (its stream must arrive in sequence order) and the lanes run at the same
time; in-flight work is `CaptureLane.allCases.count`, never a function of backlog, meeting length or
tick count. A lane's first failure ends that lane for the pass only — the one-head-retry-per-tick
rule from B2 is unchanged — and the reported failure is chosen in lane order so it is deterministic.
*Time*: passes never overlap. `Contention.skip` (the periodic tick) gives up the turn; `.wait`
(start and stop) takes it after the running pass, because the meeting's final frames reach the wire
only through the stop's pass. Critically, the retained-frame list is read **inside** the pass, never
before it — a waiting caller that snapshotted first would re-send identities the running pass still
had in flight (found by the stop node, not by review). A skipped tick still emits health: a long
recovery drain must not read as a dead helper against the 30 s lease. `CapturePumpContract.interval`
= 0.5 s (was a 0.25 s literal in the app) — exactly one canonical wire frame per lane per tick.
`PinnedURLSessionCaptureHTTPClientProvider` now caches one `URLSessionCaptureHTTPClient` per pin and
`invalidate()`s a superseded one; before this every frame built a fresh ephemeral `URLSession`,
which re-handshook TLS twice a second per lane and leaked a session + pinning delegate per frame for
the whole meeting (a session retains its delegate until invalidated). The app builds **one**
provider and gives it to frames, heartbeat and pairing; `httpMaximumConnectionsPerHost` is lanes + 1.
Cross-lane publish *order* is now undefined by design — the server aligns lanes by capture
timestamp, and only per-lane order is contractual — so tests assert per lane
(`FakeCaptureTransportAdapter.publishedFrames(lane:)`).

**Packaging-tool contract (new, iteration 9).** `macos/scripts/` holds three tracked tools plus
`moss-tool-lib.sh`, which fixes one output discipline: `--dry-run` prints the ordered `plan:` and
the `rollback:` command and mutates nothing; the `rollback:` line is printed **before** the first
mutation; a re-run prints `unchanged:` instead of mutating; `evidence: key=value` lines carry the
observed facts and never a secret.
*`bootstrap-signing-identity.sh`* creates the dedicated `moss-signing.keychain-db` (random password
in a 0600 file), a self-signed `extendedKeyUsage=critical,codeSigning` certificate, imports it with
`-T /usr/bin/codesign`, sets the key partition list, appends the keychain to the user search list
keeping every existing entry, and accepts only if a scratch `codesign` run succeeds. It refuses the
login/System/default keychain outright.
*`build-app.sh`* composes and signs `MOSSCapture.app` plus `mtd-capture` into build output only
(it refuses an install location), derives the signing entitlements from the tracked file with
`keychain-access-groups` dropped, and reads the embedded entitlements, identifier and DR back out of
the signature with `codesign -d` — what was passed in is an input, not evidence. Identical inputs
give an identical bundle digest and DR, and a re-run over the same output re-signs nothing.
*`install-app.sh`* verifies the source signature/identifier/entitlements first, does **nothing** when
the installed bundle is already byte-identical (the inode and therefore the TCC grants survive),
moves a replaced bundle aside to `<installed>.backup-<utc>` instead of deleting it, reports loudly when the
new DR differs from the installed one (that is exactly when the human loses the grants), and
re-verifies the installed bundle's DR against the source.

**Signing mechanics — measured on MacStudio, iteration 9.** `codesign --keychain <kc> --sign <name>`
is accepted and **ignored**: with the identity only in `<kc>` it fails `no identity found`, while
`security find-identity <kc>` lists it as `CSSMERR_TP_NOT_TRUSTED`. The same command succeeds once
the keychain is in the **user keychain search list** (`security list-keychains -d user -s <existing…>
<kc>`) — no trust change, no `add-trusted-cert`, `find-identity -v -p codesigning` still reports 0
valid identities. So search-list membership, not the flag, is what makes an identity reachable, and
D7's DR claim reproduces here: two different binaries signed by that identity both get
`designated => identifier "…" and certificate leaf = H"421b…"`. `security delete-keychain` also
removes the search-list entry, so the recorded rollback is complete.

**Handoff contract (new, iteration 3).** View authority is app-only. `ControlCommandDispatcher`
owns `case "handoff"` and an injected `CapturePortalHandoffAdapter`
(`CaptureSecurity.swift`); `MOSSCaptureApp/main.swift` is the only composition root that builds
`PasteboardCapturePortalHandoff`, so only the app reads `capture-view-token` and writes the
pasteboard (honouring `MOSS_CAPTURE_PASTEBOARD_NAME` in the *app* process). The CLI sends one
`ControlChannelRequest(command: "handoff")` and relays the response verbatim; `handoff` no longer
costs two round trips. The non-secret confirmation rides on `ControlChannelResponse` as
`viewAuthority` ("copied-to-pasteboard"), so `{ok, sessionID, portalURL, viewAuthority}` is the
whole wire answer. Missing authority → typed `portalHandoffUnavailable`; a pasteboard refusal →
typed `pasteboardUnavailable`; neither reaches stdout as anything but a sanitized error name.

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
   capture_bearer}`; server exposes only `pairing-codes` → `pairings` → `sessions`
   (`live_transport.py:114-173`) and returns the view token from session create.
   **Closed on the feature branch by the iteration-1 graft** — `URLSessionCapturePairingExchangeAdapter`
   now posts `/pairings` then `/sessions` (`CaptureSecurity.swift:823-890`).
2. No pinning on `main`. **Closed by the iteration-1 graft**:
   `PinnedCertificateURLSessionDelegate` + `FullCertificatePinValidator` +
   `PinnedURLSessionCaptureHTTPClientProvider` (`CaptureHTTPTransport.swift:65-118`); both
   product entrypoints build their HTTP clients from the stored pin.
3. Frame loss on any send failure — `queue.drain()` does `removeAll()`
   (`NativeAudioBuffers.swift:60-64`) and `publishPendingFrames` abandoned the current and all
   remaining drained frames on a throw. **Closed on the feature branch by iteration 6 (B2)**: the
   drained frames go straight into `CaptureFrameOutbox` and only an ack releases them. Two adjacent
   defects found and closed with it: (a) a publish throw inside `start` failed the start while
   leaving `state.running == true` with no pump task — a zombie capture; a retryable failure is now
   a degraded start and an unretryable one unwinds the source and rolls back; (b) a raw `URLError`
   (what a pinned `URLSession` throws on a real outage) typed as `CapturePumpFailure.unexpected`
   instead of `.transportUnavailable`.
4. Viewer expiry — `VIEW_TTL_SECONDS = 900` fixed at `bind_session`, no renewal. Reproduced:
   authorized at t=899, rejected at t=3600.
5. Unbounded callback-shaped blocking POSTs. **Closed on the feature branch by iterations 7 and 8**:
   B3 fixed emission at two 0.5 s frames per second per lane, and B4 bounded the transport — lanes
   concurrent with one request each, no overlapping pass, one pinned session per pin. A 15 s
   recovery backlog is 30 frames per lane drained on two threads (~2.2 s at the measured 146 ms max
   RTT) instead of 60 sequential round trips, and later ticks skip instead of piling on.
   `URLSessionCaptureHTTPClient.send` still blocks its lane thread on a semaphore; that is now the
   *definition* of one request in flight per lane, not an unbounded cost.
6. Secret store broken — code requested access group `com.alphasight.moss.capture.shared` while
   the entitlement declares `$(AppIdentifierPrefix)com.alphasight.moss.capture`; strings differ and
   a self-signed identity has no Team ID. Keychain writes also fail `-25308` from any non-GUI
   session. **Closed on the feature branch by iteration 5 (B1)**: the file store is the default,
   the Keychain store is dormant with no access group. The residue is **closed by iteration 9
   (B5)**: the tracked `Resources/MOSSCapture.entitlements` still declares `keychain-access-groups`
   with the unresolvable `$(AppIdentifierPrefix)` literal, deliberately, as documentation of intent
   for a future real Team ID — `build-app.sh` derives the *signing* entitlements from it with that
   key dropped and refuses to finish if the key reappears in the signature. Rehearsed: without the
   drop the literal really is embedded verbatim.
7. No client-side 16 kHz conversion — devices stayed at their native rate and the server mixer
   resampled by linear interpolation with no anti-alias filter (`live_mixer.py:305-327`).
   **Closed on the feature branch by iteration 7 (B3)**: both lanes leave the Mac at 16 kHz mono in
   exact 8000-sample frames, so the mixer grid is 1:1 and uplink drops to 0.68 Mbit/s. Measured
   duration conservation: 96×1024 at 48 kHz → exactly 32768 output samples; 129×1024 at 44.1 kHz →
   47926 vs 47925 ideal (one sample of ratio remainder).
8. Wire timestamps were mislabeled — raw `AVAudioTime.hostTime` / `AudioTimeStamp.mHostTime` ticks
   travelled as `capture_timestamp_ns`, collapsing the timeline by the 125/3 timebase.
   **Closed on the feature branch by iteration 7 (B3)** — see the wire-format contract above. The
   drivers still hand raw ticks to the queue on purpose; conversion happens off the callback thread
   and is source-gated by `testRealtimeCallbacksNeitherConvertHostTimeNorResample`.
9. **Undetermined microphone permission hung `start` forever** — **closed by iteration 2**.
   `MicrophoneCapture.start` used to throw only on `.denied` and let `.undetermined` fall through
   to `driver.currentInputDeviceID()`, whose `engine.inputNode` access blocks inside
   `AVAudioEngineImpl::UpdateInputNode` → `_dispatch_sync_f_slow` → `kevent_id` forever, because a
   non-GUI process cannot answer the TCC prompt. Every SwiftPM rebuild is ad-hoc signed with a new
   cdhash, so `.undetermined` is the *normal* state, not an edge case. `start` now requires
   `.granted` before touching the engine, and `NativeLanePermissionCoordinator` runs the explicit
   `AVCaptureDevice.requestAccess(for: .audio)` transition instead.

**Lane admission contract (new, iteration 2).** `NativeDualCaptureSource.start` never waits on a
user decision. Per lane: `.granted` → admit inline; `.denied` → typed lane failure; `.undetermined`
→ one `requestAccess` and lane state `pending`. The source is *running* only if at least one lane
is actually capturing; a pending lane joins the running capture when the answer grants it. When no
lane is capturing, `start` retires the permission generation (so a late grant cannot start capture
behind a failed start) and throws the pending lane's typed `permissionDenied`. System audio has no
preflight or request API, so its user-initiated recording start *is* the request
(`SystemAudioPermission`); it resolves synchronously and never sits pending. `stop` retires the
generation before teardown.

**Open risk — system-tap prompt on a GUI host (M36).** `AudioHardwareCreateProcessTap` is the
documented System Audio Recording prompt trigger and is still called on the control thread. On
MacStudio it returns promptly (iteration-1 `sample` proved the hang was in the microphone path,
not the tap), but nothing yet proves it returns promptly on m4mbp while its prompt is on screen.
If E3 shows it blocking, move system admission onto the coordinator's own thread in Phase B; do
not add a Screen Recording preflight in its place (M31 forbids it).

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
`codesign` succeeds — never gate on `find-identity`. The exact mechanics are in the signing-mechanics
note above; `macos/scripts/bootstrap-signing-identity.sh` (iteration 9) implements them.

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
# present since the iteration-1 graft. It builds/bundles/ad-hoc-signs the real products, so it
# needs both Swift products built first. Currently 3 passed, 0 skipped (~7 s).
python3 -m pytest tests/test_macos_uds_tracer.py -q

# Reinstall the fixed lab bundle from scratch (safe: gitignored build output). Do this only to
# re-prove the first-install path; normal runs must reuse it.
rm -rf macos/MOSSCapture/.build/idea044-lab

# --- Phase A discriminator (the A4 gate; run it before and after any Phase-A change) --------
PYTHONDONTWRITEBYTECODE=1 python3 \
  "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-044-attempt2-red-control/repro.py" \
  --target "$PWD"        # 10/10 since iteration 4; must stay 10/10
# The 16-check sibling is historical after B1 and reads 14/16 on the tip (09 and 15 assert the
# superseded Keychain default). Its frozen green is commit 1ede498, not the tip.

# --- B1 secret-store behavioral nodes (the replacement for discriminator 09/15) ------------
swift test --package-path macos/MOSSCapture --filter 'SecretStore|ProductEntrypoints|DormantKeychain'

# --- B2 outbox behavioral nodes (8 nodes: outage, ambiguous/duplicate, 429/5xx/401, overflow,
#     stalled lane, wire-sequence authority, per-session numbering, start unwind) --------------
swift test --package-path macos/MOSSCapture \
  --filter 'Outbox|Ambiguous|RetryPolicy|Stalled|NumbersItsLane|Unwinds'

# --- B3 wire-format behavioral nodes (11: timebase, steady frames, 48/44.1 kHz duration,
#     cross-lane domain, refused instant, terminal flush, gap splice, source+controller tail, and
#     two realtime-callback source gates) --------------------------------------------------------
swift test --package-path macos/MOSSCapture \
  --filter 'HostTicks|CanonicalFrames|ConserveDuration|HostTimeDomain|CaptureInstant|TerminalFlush|TimelineGap|RealtimeCallbacks|FlushedTail'

# --- B4 bounded-transport behavioral nodes (5: lane rendezvous + per-lane in-flight bound, late
#     tick skips, stop waits, one session per pin, shipped cadence/provider) --------------------
swift test --package-path macos/MOSSCapture \
  --filter 'LanesPublishConcurrently|ATickArrivingDuringADrain|StopWaitsForTheRunningPass|PinnedProviderKeepsOneSession|ProductionPumpTicksOnce'

# --- B5 packaging tools (9 nodes: entitlement drop, reproducible bundle, install-location
#     refusal, untouched idempotent install, backup + working rollback, tampered-bundle refusal,
#     three dry-run plans, keychain refusals). Scratch paths only; no keychain/app is mutated. ---
python3 -m pytest tests/test_macos_packaging_tools.py -q

# --- B5 tools by hand (build output is gitignored; ad-hoc signing needs no identity) --------
macos/scripts/build-app.sh --configuration debug --no-build \
  --output /tmp/moss-build --sign-identity -
macos/scripts/install-app.sh --bundle /tmp/moss-build/MOSSCapture.app \
  --cli /tmp/moss-build/mtd-capture --applications /tmp/moss-apps --bin-dir /tmp/moss-bin
macos/scripts/bootstrap-signing-identity.sh --dry-run   # never run for real on MacStudio
# Real signing identity + install belong to E1/E2 on m4mbp, not to this host.

# --- Phase A locality is historical from iteration 6: check the frozen checkpoint, not the tip
git diff --name-only af3ac3667393a0411616f52f76339eff01dc13e2 1ede498 --   # == the 13 allowed paths

# --- wide checkpoint -----------------------------------------------------
# Keep executable builds explicit because tests/test_live_integration.py and the A-034 tracer
# execute the real products and error when they are absent. Swift 6.3 currently builds both
# executables incidentally during `swift test`; the gate must not depend on that behavior.
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
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

# --- secret-hygiene scan (lives with the tracer spike, not in scripts/ralph-afk) ----------
bash "/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/spikes/idea-044-real-uds-tracer/leak-scan.sh"

# --- Phase A compatibility checkpoint (historical; frozen at 1ede498) ----
# Run the exact eleven registered commands from:
# /Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize/context/VALIDATION_COMMANDS.md
# section "IDEA-044 attempt-2 exact commands". `validate-phase-a-locality.sh` belongs to that
# checkpoint and now fails on the tip by design — see the locality note above.

# --- one keeper merge, primary worktree stays on the feature branch -------
swift build --package-path macos/MOSSCapture --product mtd-capture
swift build --package-path macos/MOSSCapture --product MOSSCaptureApp
swift test --package-path macos/MOSSCapture
python3 -m pytest tests -q -p no:cacheprovider
test -z "$(git status --porcelain)"
RALPH_MERGE_DRY_RUN=1 bash scripts/ralph-afk/merge-keeper.sh   # fences only, no merge
bash scripts/ralph-afk/merge-keeper.sh                          # builds products itself in the temp worktree
```

## Candidates

Strictly ordered by phase. Mark outcomes inline (`[done <commit>]`, `[dead: <why>]`) and prune
only after the durable result is in progress.txt.

### Phase A — preserve and close IDEA-044 before widening scope

1. **A1 — graft A-034's accepted mechanics** `[done — iteration 1, `--no-ff` merge of
   `acl/IDEA-044--A-034@67a27b8`]`: two-step pairing/session create,
   `PinnedCertificateURLSessionDelegate`, `FullCertificatePinValidator`, restart-safe authority
   persistence, environment-selected `FileCaptureSecretStore` (Keychain still the default with no
   `MOSS_CAPTURE_SECRET_STORE_PATH`), and `tests/test_macos_uds_tracer.py`. Grafted verbatim, not
   rewritten.
2. **A2 — app-owned UDS `handoff`** `[done — iteration 3]`: `case "handoff"` plus
   `CapturePortalHandoffAdapter`/`PasteboardCapturePortalHandoff` now live in
   `CaptureSecurity.swift` next to the dispatcher, injected only by `MOSSCaptureApp/main.swift`;
   `CaptureCommandLine.swift` sends `ControlChannelRequest(command: "handoff")` and keeps no
   view-token or pasteboard authority. Discriminator checks 1-4 green.
3. **A3 — explicit per-lane permission coordinator** `[done — iteration 2]`:
   `NativeLanePermissionCoordinator` in `NativeDualCaptureSource.swift`,
   `AVCaptureDevice.requestAccess(for: .audio)` in `MicrophoneCapture.swift`, and
   `SystemAudioPermission` in `SystemAudioTap.swift`. Discriminator checks 5-9 green; tracer
   `2 passed`.
4. **A4 — compatibility checkpoint** `[done — iteration 4]`: the tracer now installs one
   immutable lab bundle at the fixed path and re-asserts its first-install evidence across nodes;
   the eleven registered commands plus the locality script are all green at **10/10 / 16/16 /
   0 Darwin skips**. The SHA is recorded in progress.txt. **Not merged and not pushed** — the one
   keeper merge stays at C4. Residue: M38's *granted* dual-lane node still cannot run because no
   TCC grant exists on MacStudio; the tracer takes its typed-failure branch instead and the
   granted branch is exercised for real only at E3. That is a recorded gap in the mutation
   evidence, not a gate failure — the registered A4 gate does not require it.

### Phase B — production Mac reliability

**Gate opened by iteration 4's green A4 checkpoint.** From here the Phase-A source
discriminators are historical evidence: B1–B5 deliberately supersede the lab-only
source/locality expectations and need their own behavioral tests plus the full-suite gate. Never
edit the control-plane discriminator scripts to keep them green.

5. **B1 — production file secret store** `[done — iteration 5]`: `makeDefault()` returns a
   `FileCaptureSecretStore` at `~/Library/Application Support/MOSSCapture/secrets.json` for both
   products; 0700 directory, 0600 `O_EXCL`+`fsync`+`rename` replacement, no access group on the
   dormant Keychain store. The lab-default source assertions were replaced by behavioral nodes
   (see Validation); the control-plane discriminator was left untouched at 14/16.
6. **B2 — retained-until-ACK outbox** `[done — iteration 6]`: `CaptureFrameOutbox` holds 15 s of
   audio per lane keyed by the wire `(lane, sequence)` it stamps itself, retries the identical
   frame on timeout/429/5xx/ambiguous answers, releases only on an ack, and refuses new audio on
   overflow with a sticky typed degradation plus a discontinuity on the lane's next admitted frame.
   Eight behavioral nodes cover 5 s outage, ambiguous success, duplicate retry, 429/5xx/401,
   overflow, per-lane stall isolation, wire-sequence authority, and per-session numbering.
   The serial-flush residue this left is closed by iteration 8 (B4).
7. **B3 — 16 kHz mono conversion/coalescing + real nanosecond timestamps** `[done — iteration 7]`:
   `NativeLaneWireFormat.swift` + the rewritten `NativeLaneFrameEmitter` convert host ticks with
   `AudioConvertHostTimeToNanos`, run one stateful `AVAudioConverter` per lane, and coalesce exact
   8000-sample 16 kHz frames; the drivers still only copy and enqueue. Eleven nodes cover the
   injected 125/3 timebase, exact steady frames, 48/44.1 kHz duration conservation, one shared
   cross-lane time domain, a refused unusable capture instant, the terminal partial flush and its
   delivery through `CaptureController.stop`, a spliced gap, and the no-callback-DSP source gates.
   Residue for C2: the client now really does send 8000-sample 16 kHz frames, so the manifest
   bounds the server admits them against (`bounds_config.max_frame_samples`, `frame_samples`,
   `max_retained_samples` — read from the host provider manifest via
   `live_provider_bundle.py:269,912`) must be the retuned contract values before D-phase pairing.
8. **B4 — bounded concurrent transport** `[done — iteration 8]`: `CaptureFramePublishPump`
   (`CapturePublishPump.swift`) is the only caller of `transport.publish`; one serial queue per
   lane makes in-flight work exactly the lane count, `Contention.skip`/`.wait` stops passes from
   overlapping, the app's pump interval is `CapturePumpContract.interval` (0.5 s, was 0.25 s), and
   `PinnedURLSessionCaptureHTTPClientProvider` keeps one pinned session per pin instead of one per
   request. Five behavioral nodes (see Validation); five mutation rehearsals recorded in
   progress.txt. Residue: `stop`'s final drain is unbounded in time — it waits for whatever pass is
   running plus its own. That is correct for the tail but means a stop during a full-window
   recovery can take seconds; if F2/F3 shows a slow stop, bound it with the stop deadline the
   `stop(deadline:)` signature already carries rather than by skipping the drain.
9. **B5 — tracked Mac packaging/install tools** `[done — iteration 9]`:
   `macos/scripts/{moss-tool-lib,bootstrap-signing-identity,build-app,install-app}.sh` with one
   dry-run/rollback-first/idempotent output discipline (see the packaging-tool contract above).
   Nine acceptance nodes run against scratch paths only; the suite creates no certificate,
   keychain, search-list entry or installed file. The signing incantation itself was proven for
   real once on MacStudio in a temp keychain and rolled back — `codesign --keychain` is ignored,
   search-list membership is what works. Residue for E2: `install-app.sh` defaults the CLI to
   `~/.local/bin` and reports `bin_dir_on_path`; if that is not on m4mbp's PATH, pass `--bin-dir`
   rather than editing a shell profile from the loop.
10. **B6 — client gate** `[done — iteration 10]`: green at product-tree `3fb5567` — see the Phase B
   client gate block above for the recorded numbers. The Phase-A source discriminators stayed at
   10/10 but are historical evidence, not final gates, after the deliberate B1–B5 production
   changes. Residue for C4: this gate is the *client* half; the keeper merge re-runs it plus the
   Phase C reliability tests on the merge commit.

### Phase C — server meeting reliability, then one merge

**Gate opened by iteration 10's green B6 checkpoint.** Server work may now start; the Mac client is
frozen except for defects the server work exposes.

11. **C1 — session-lifecycle view authority**: active-session-only + 12 h cap + immediate revoke
    on clean terminal, abort, device revocation, or operator revoke. Test virtual 60 minutes,
    exact cap, every terminal/revocation boundary, and restart behavior. Keep tokens out of
    URL/storage/logs; do not invent post-terminal grace without persistence.
12. **C2 — bounds retune**: `hard_cap_samples=40000`,
    `max_retained_samples=960000`, `frame_samples=8000`; generated bundle hashes, never hand
    edited. Test descriptor/config admission and capacity headroom.
13. **C3 — tracked deployment and certification bundle**: manifest finalizer, TLS generator,
    live env/service templates, start-web overrides, two-port Windows networking, loopback
    pairing helper, deployment docs, and an **app-owned latency probe**. The app—not the CLI—
    uses view authority, maps `committed_samples` to converted client capture timestamps, and
    emits only redacted p50/p95/max plus snapshot/events fetch timings. Test
    generation/default-off/secrecy/7860-preservation and deterministic latency math without host
    mutation.
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
