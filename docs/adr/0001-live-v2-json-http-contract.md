# ADR 0001: Live v2 uses JSON over HTTP

## Status

Accepted.

## Context

The live path is a default-off local substrate. IDEA-028 adds a
`moss-live-service.v2` contract for two source-labelled capture lanes while
preserving the existing mono inference runtime and six-operation
`LiveServiceRuntime` interface.

The hard contract needs strict validation, deterministic JSON-compatible domain
objects, highest-common protocol negotiation, lane-qualified acknowledgements,
typed obsolete-client errors, and independent pre-mixer source-lane admission.
It must not add deployment enablement, a binary transport, WebSockets, or a
server-side mixer inside the v2 ingress/session lifecycle.

## Decision

V2 live transport remains JSON over the existing default-off HTTP adapter.
Frame PCM is base64-encoded PCM16. The descriptor declares protocol range `2..2`
and capabilities:

```json
{
  "lanes": true,
  "binary": false,
  "idempotent_frames": true,
  "resumable": true
}
```

The adapter continues to accept the existing v1 mono frame payload shape. A v2
frame is detected by its v2-only metadata fields, strictly validated first, then
admitted into one in-process `LiveV2Session` for its live session. V2
acknowledgements are lane-local and report the current mono snapshot version.
V2 ingress acknowledgement is not mono admission; IDEA-030 owns compatibility
mixing into canonical mono `AudioFrame`s.

Lane ingress independently sequences `system` and `microphone`, fences
device-epoch transitions, enforces per-lane retained-sample capacity, stores
complete immutable accepted frames including PCM and capture metadata, and
returns prior acknowledgements for bounded lane-qualified duplicates. A corrected
same-sequence retry after a rejected gap, capacity overflow, or epoch transition
can succeed because failed admissions do not mutate ingress state.

One in-process `LiveV2SessionRegistry` owns v2 session lifetime at the transport
seam. Each session exposes additive per-lane reconnect state, accounts only
whole retained frame prefixes after downstream consumer success, releases
capacity only after accounting, conserves typed lane failures as failed samples,
uses loop-owned async stop notification, supports explicit expiry, and releases
terminal registry/PCM state after clean stop, abort, terminal failure, or
explicit expiry. A rejected unaccounted stop is non-terminal and retains state
for retry or abort.

Protocol negotiation selects the highest common version. An obsolete client
range below the server minimum returns a typed payload with required minimum
version and maps to an HTTP 426-style response.

One in-process `LiveCompatibilityMixer` plus a per-session registry bridges
retained `system` and `microphone` lane frames into the unchanged mono runtime.
It interprets `capture_timestamp_ns` as the frame's first PCM sample time,
seals lane intervals with successor timestamps or final nominal ends, resamples
onto a shared 16 kHz mono grid, applies exact per-lane headroom and the
registered soft limiter, then calls `LiveServiceRuntime.accept_frame`. Source
lane prefixes are accounted only after successful mono admission.

An explicitly failed active lane is distinct from a never-observed active lane.
The mixer treats the failed lane as zero-valued input only for admission, so a
sealed healthy peer can continue to the existing mono runtime. Failed-lane PCM
is not mixed, failed samples remain failed rather than clean, and source-lane
accounting still happens only after successful mono admission. A never-observed
active lane continues to wait before final mixing and to fail closed at final
mixing.

The OS-neutral capture-adapter seam remains the existing v2 frame/lifecycle
boundary: lane, sequence, sample rate, first-sample timestamp, device epoch,
silence, discontinuity, and mono PCM16 bytes. A simulated Windows adapter under
`tests/` freezes this contract for native `float32_le` and `pcm16_le` inputs,
lane-local sequence/epoch, invalidation discontinuity, native silence, and
typed failure events. It is test-only evidence, not a Windows client, native
module, helper, installer, dependency, deployment path, or production caller.
Capture conversion becomes shared code only after real native helpers prove a
repeated production behavior that belongs behind the same OS-neutral seam.

One server-side `LiveAccessRegistry` owns live-only access at the same disabled
HTTP seam. It admits only direct private peers, requires TLS for non-loopback
live requests, issues loopback-only certificate-bound pairing payloads, persists
only capture-authority digests and revocation facts, binds live session
ownership to the capture device, grants separate short-lived view authority, and
releases authority on terminal session paths. FastAPI extracts direct peer,
scheme, and bearer headers; Uvicorn supplies the configured TLS certificate and
key with proxy headers disabled. Batch routes remain outside this authority.

The server-hosted live portal is a separate, default-off `/live` document
attached only when live routes are enabled. It owns no live backend API and acts
only as a browser-local pull adapter to the existing same-origin `snapshot`,
`events`, `stop`, and `abort` operations. Operators manually enter the session
id and view token; the view token remains in page memory and `Authorization`
headers only. Browser cursors advance only after successful parse and render,
replayed events render once, bounded retry remains single-flight, and terminal
`closed`, `failed`, or `aborted` state stops polling and clears authority.

IDEA-044 keeps the macOS client on the existing JSON/HTTP contract. The shipped
client exchanges `mtd1.<secret>.<64-hex-pin>` at `POST /api/live/pairings`,
creates the live session with capture bearer authority at
`POST /api/live/sessions`, and pins helper HTTPS to the pairing payload's full
certificate SHA-256. `CaptureSecretStore` is the single persistence seam:
Keychain is the unconditional product adapter, while an explicit same-user
`0600` file adapter is allowed only for unattended local lab runs. The manual
portal handoff is the explicit `mtd-capture handoff` action. It verifies the
real app over authenticated UDS, copies the persisted view token to the macOS
pasteboard, and returns only a non-secret confirmation, the non-authority
`/live` portal URL, and live session id. The token is never placed in a URL,
process argument, CLI output, log, cookie, browser storage, or DOM channel.
Production `start` does not use Screen Recording preflight as a proxy for Core
Audio authority or collapse the two lanes into one permission boolean.
Microphone `notDetermined` can proceed after the explicit start action while
denied and authorized facts remain lane-specific. The tracer isolates its
deterministic denied-permission harness from real capture; real success is
accepted only when the server observes native samples on both lanes and the
real CLI completes `status` plus bounded `stop`. Local unsigned tests do not
prove signing, notarization, TCC continuity, Keychain runtime, deployed
device/tap behavior, deployment, 60/300 evidence, canary, or live enablement;
those remain Missing.

IDEA-035 adds an observation-only helper heartbeat side channel at the same
default-off live HTTP seam. The owning capture authority may post strict
`moss-live-helper-health.v1` JSON to
`/api/live/sessions/{session_id}/heartbeat`; view authority cannot write it.
`HelperPresenceRegistry.observe/snapshot/release` validates exact schema,
ordering, idempotency, helper-instance stability, and server-monotonic receipt
behind one interface. Authorized snapshots add `helper_presence` as data only.
Clean stop, abort, terminal failure release, failed-stop release, and device
revocation release the presence record with the rest of session-owned state.

IDEA-042 turns the promoted helper contracts into an unsigned runnable local
macOS bridge without changing the external live contract. One
`CaptureController` deep module keeps exactly `start/status/stop`; production
native, HTTP, health, scheduling, security, and shutdown adapters remain behind
that interface. `MOSSCaptureApp` is the long-lived composition root and
authenticated same-user UDS control server. `mtd-capture` is only a
LaunchServices plus bounded UDS client, including stdin pairing transit into
the app-owned exchange. The helper heartbeat is now an ordinary registered
`POST /api/live/sessions/{session_id}/heartbeat` route that calls the same
capture-authorized presence handler; this replaces middleware path sniffing and
does not add timeout, abandonment, failure, expiry, stop, abort, recovery, or
enablement policy. An off-callback publish or health failure is exposed as a
typed `pumpFailure` status fact; the repeating pump remains active and clears
that fact after a later successful tick. This is local retry/observability, not
server lane-failure, expiry, abandonment, or recovery policy.

The capture pump's frame POST and following heartbeat each carry a 1-second
request timeout. They run serially, so this bounds a dead-network pump turn to
2 seconds. The production raw callback queue carries 1,024 buffers per lane so
audio can survive that bounded turn and then reach the 15-second outbox. Both
limits are measured rather than inferred: a
final-SHA F2 run on 2026-07-29 left the prior 60-second URLRequest default
blocked through a 5.140-second interruption, filled the 128-buffer system-audio
callback queue, and reported `macos_buffer_overrun`; the request returned only
when the network did. A second 5.460-second F2 with the one-second request
bounds still held 128 system buffers and dropped 146 before the serial pump
turn completed: 274 buffers of measured demand. The 1,024-buffer production
capacity is 3.7 times that observation and is enforced independently for both
lanes. Stop and browser control requests keep their separate
10-second bound because they wait on the explicit 5-second server drain and do
not gate native audio collection.

IDEA-043 adds source-owned native lane failure ownership inside the native dual
capture source without changing the public controller, helper health JSON,
parser, routes, server lifecycle, or mixer. `NativeLaneHealth` owns
generation-fenced ordered lane mailboxes and the reducer that projects
admitted/capturing/failed state, counters, first-cause sticky failure, and
stable `macos_*` failure codes. The system-tap and microphone adapters enqueue
raw lifecycle, permission, device, overload, and abnormal-stop facts only; they
do not own failure policy, generation policy, status projection, teardown, or
server recovery. Heartbeat publication carries the resulting lane health facts
through the existing `moss-live-helper-health.v1` shape. Local unsigned tests
and builds do not prove signing, notarization, TCC continuity, endpoint
recovery, deployed device behavior, 60/300 evidence, canary, deployment, or live
enablement; those remain Missing.

IDEA-038 closes the local portal/helper integration loop without changing the
v2 wire contract, the mono `live_service_replay.py` interface, or the portal
endpoint inventory. One test-only `LocalIntegrationReplay` composes pairing,
session create, independent strict-v2 lane frames, helper heartbeat, authorized
snapshot and events, reconnect replay, typed one-lane failure, healthy-peer
continuation, stop/drain, and terminal final into one immutable report at the
existing authenticated JSON/HTTP interface, and it executes the real built
`mtd-capture` binary resolved from the Swift package bin path rather than an
assumed build configuration. Portal timing constants are fixed and documented:
the 5-second stop-drain deadline is the only value the portal sends in a stop
request body, while a 10-second poll request timeout and an independent
10-second control request timeout bound every browser fetch on its own
controller. Rendered events share one finite cap of 200 enforced as three
separately checked bounds — the rendered identity set, `renderedEventOrder`,
and the events DOM row count — so losing any one bound is observable on its
own. Final means the terminal snapshot or event, not durable portal history or
artifacts. Local green proves unsigned local coordination mechanics only:
secure automated browser handoff, signing, notarization, TCC, Keychain runtime,
real permission/device/tap behavior, real lease value, history/artifacts,
deployment, 60/300 evidence, Windows production, canary, and live enablement
remain Missing.

Binary framing and non-HTTP transports are deferred to protocol v3.

## IDEA-035 Mutation Kill Nodes

These nodes are the Reviewer mutation contract for the native macOS helper and
observation-only presence slice. They name the expected killing check for each
single-obligation mutation; they do not claim mutation review has run.

| ID | Killing node |
|---|---|
| M01 | `repro.py` source inventory plus `swift test --package-path macos/MOSSCapture` reject ScreenCaptureKit, virtual-driver, or client-premix replacement. |
| M02 | `testNativeSourceVectorsUseRequiredMacOSCapturePaths` and `repro.py` reject a muted system tap or missing private transient aggregate/HAL callback path. |
| M03 | `testRealtimeCallbacksOnlyCopyAndEnqueueNativeBuffers` and the source fence reject resample, encode, network, disk, Keychain, or logging in callback sources. |
| M04 | `testNativeSourceVectorsUseRequiredMacOSCapturePaths` and `repro.py` reject microphone capture that is not `AVAudioEngine.inputNode.installTap`. |
| M05 | `testStartStatusStopPublishesIndependentFakeLaneFrames`, `testRealtimeQueueIsBoundedAndFrameEmitterKeepsLaneStateIndependent`, and `repro.py` reject shared lane sequence or epoch state. |
| M06 | `testShimCommandsStayControlOnlyAndAudioFrameworkFree` and `repro.py` reject CLI audio-framework imports, TCC ownership, frame ownership, or bearer ownership. |
| M07 | `testHTTPTransportPostsStrictV2FramesWithBearerHeaderOnly`, `testHTTPHealthPostsVersionedHeartbeatWithoutBearerLeakage`, `testUnixDomainControlClientUsesStoredControlSecretOnlyInUDSPayload`, CLI channel assertions, and `git diff --check` reject secrets or PCM in query/body/output/log/git channels. |
| M08 | `testSecurityAdaptersExposeKeychainFullCertificatePinAndUDSInventory`, HTTP bearer tests, and `repro.py` reject non-Keychain device secret storage or missing full-certificate SHA-256 pin comparison. |
| M09 | `testSameUserUDSAuthenticatorRequiresPrivateSocketPeerUIDAndSecret` and `repro.py` reject group/world-readable sockets, skipped local peer checks, skipped control-secret checks, or different uid acceptance. |
| M10 | `repro.py` controller inventory and Swift interface tests reject expanding the helper external interface beyond `start/status/stop` or moving private choreography into callers. |
| M11 | `testBundleMetadataPinsHelperContractWithoutSandbox` and `repro.py` reject missing `LSUIElement`, bundle identity, macOS 14.2 floor, purpose strings, audio-input entitlement, Keychain group, or added App Sandbox. |
| M12 | `test_versioned_health_parser_rejects_unknown_missing_or_invalid_fields` and `repro.py` reject schema/version drift, unknown or missing fields, invalid lanes, invalid states, or invalid counters. |
| M13 | `test_new_sequence_advances_injected_server_last_seen_and_may_skip_values` and route snapshot assertions reject wall time or helper-sent time as server freshness authority. |
| M14 | `test_new_sequence_advances_injected_server_last_seen_and_may_skip_values`, route duplicate assertions, and `repro.py` reject duplicate heartbeats that refresh `last_seen_monotonic_ns`. |
| M15 | `test_regression_changed_duplicate_non_advancing_time_and_instance_switch_fail_closed` and route conflict assertions reject lower sequence, changed duplicate, non-advancing helper time, or helper instance switch mutations without state mutation. |
| M16 | `test_new_sequence_advances_injected_server_last_seen_and_may_skip_values` and `repro.py` reject contiguous-sequence requirements by accepting sequence `0 -> 2`. |
| M17 | `test_heartbeat_is_capture_only_authority`, route ownership assertions, and `repro.py` reject view-authority heartbeat writes or cross-device capture writes. |
| M18 | `test_helper_heartbeat_route_is_capture_owned_and_visible_in_authorized_snapshot` and `repro.py` reject missing authorized `helper_presence` snapshot exposure. |
| M19 | `test_helper_presence_releases_on_terminal_and_revocation_paths`, failed-stop release coverage, and `repro.py` reject retained presence after clean stop, abort, failed stop release, terminal release, or device revocation. |
| M20 | `test_release_removes_snapshot_without_policy_side_effects`, `repro.py`, and the protected source fence reject mapping reported health to `.fail_lane(`, `.expire(`, stop, abort, or lifecycle transition. |
| M21 | `repro.py`, ADR/context no-policy text, and protected diff gates reject heartbeat timeout, grace deadline, background detector, abandonment closure, or CTR-066 closure claims. |
| M22 | The fixed-base protected diff command plus promoted mixer/lifecycle/Windows/portal and full-suite gates reject v2 frame/ack/descriptor, ingress, lifecycle, mixer, runtime, portal, batch, provider, ops, dependency, frontend, or default-off changes. |
| M23 | This ADR, `CONTEXT.md`, and `repro.py` docs gates reject treating unsigned local compile/tests as signing, notarization, TCC, real-capture, device, deployment, 60/300, canary, or enablement proof. |
| M24 | Git inventory, `.gitignore`, protected diff, and `git diff --check` reject committed `.build`, `.app`, credentials, pins, PCM, transcripts, signing artifacts, or generated helper artifacts. |
| M25 | Swift test identifiers, Python test collection/count floors, promoted suite floors, and full-suite gates reject deleting, narrowing, renaming out of collection, or weakening promoted coverage. |

## IDEA-036 Mutation Efficacy Nodes

These nodes are the Reviewer mutation contract for the explicit helper-lease
failure-policy slice. They name the expected actual killing node for each
single-obligation mutation. They do not claim mutation review has run: every
row still needs a non-no-op patch, byte-identical restore, and observed failing
command. A mutation apply error, missing node, renamed-out test, or green
survivor is red.

| ID | Actual killing node |
|---|---|
| M01 | `test_live_enablement_requires_positive_helper_lease`, `test_web_cli_live_startup_names_each_missing_security_input`, `test_web_cli_live_startup_rejects_non_positive_helper_lease`, `test_start_web_is_the_single_environment_adapter`, and `repro.py` reject a default, omitted, or non-positive live helper lease. |
| M02 | `test_muted_alive_duplicate_heartbeat_does_not_renew_lease`, `test_new_sequence_advances_injected_server_last_seen_and_may_skip_values`, and `repro.py` reject duplicate renewal or helper/wall-time freshness. |
| M03 | `test_stale_lease_callback_after_renewal_is_noop`, `test_stale_lease_callback_after_renewal_does_not_abort_live_session`, and `repro.py` reject stale timer expiry after renewal. |
| M04 | `test_muted_alive_degraded_recovering_do_not_fail_live_session`, `test_degraded_and_recovering_health_renew_without_lifecycle_mutation`, `testPumpFailureIsTypedAndLaterTicksContinue`, and `repro.py` reject silence, degraded, recovering, or transient transport facts as direct failure triggers. |
| M05 | `test_explicit_failed_lane_requires_stable_non_empty_code`, `test_versioned_health_parser_rejects_unknown_missing_or_invalid_fields`, and `repro.py` reject a failed lane without a stable non-empty `failure_code`. |
| M06 | `test_explicit_failed_lane_calls_fail_lane_once_and_keeps_peer_timer_live`, `test_explicit_failed_lane_heartbeat_calls_v2_fail_lane_without_releasing_peer`, and `repro.py` reject missing `LiveV2Session.fail_lane` on explicit lane failure. |
| M07 | `test_typed_lane_failure_conserves_retained_samples_and_keeps_sibling_usable`, `test_failed_lane_contributes_silence_while_sealed_peer_admits_and_accounts`, and `repro.py` reject failing both lanes for one explicit failed lane. |
| M08 | `testPumpMapsCaptureHTTPTransportErrorToTransportUnavailableAndRecovers`, `testPumpFailureIsTypedAndLaterTicksContinue`, `testRepeatingSchedulerContinuesUntilExplicitCancellation`, `testHTTPHealthSerializesTypedLaneFailureCode`, route behavior tests, and `repro.py` reject transport unavailability as native lane failure instead of degraded/retrying until lease expiry. |
| M09 | `test_helper_failed_and_all_lanes_failed_are_terminal_without_renewing_timer`, `test_helper_lease_expiry_aborts_mono_expires_v2_and_releases_cleanup`, and `repro.py` reject helper or all-lane failure that avoids terminal expiry. |
| M10 | `test_helper_lease_expiry_expires_v2_aborts_mono_and_releases_registries_once`, `test_registry_expiry_returns_terminal_snapshot_and_releases_session`, and `repro.py` reject lease expiry without the real `LiveV2SessionRegistry.expire` path. |
| M11 | `test_helper_lease_expiry_aborts_mono_expires_v2_and_releases_cleanup`, mono late-commit assertions, and `repro.py` reject expiry that leaves the mono runtime able to commit late output. |
| M12 | `test_helper_lease_expiry_expires_v2_aborts_mono_and_releases_registries_once`, `test_helper_presence_releases_on_terminal_and_revocation_paths`, and `repro.py` reject omitted mixer, presence, access, or timer cleanup after terminal failure. |
| M13 | `test_explicit_failed_lane_calls_fail_lane_once_and_keeps_peer_timer_live`, `test_explicit_failed_lane_heartbeat_calls_v2_fail_lane_without_releasing_peer`, and `test_failed_lane_contributes_silence_while_sealed_peer_admits_and_accounts` reject release on partial lane failure. |
| M14 | `test_helper_lease_expiry_is_cancelled_by_release`, `test_helper_lease_expiry_expires_v2_aborts_mono_and_releases_registries_once`, stale-timer tests, and `repro.py` reject duplicate terminal actions or non-idempotent release. |
| M15 | `testControllerSharedStatusIsSynchronizedUnderConcurrentPumpStatus`, `testCaptureControllerStateSharedAccessInventoryIsLockFenced`, and `repro.py` reject shared running/configuration/counter/health/failure state outside the private synchronization owner. |
| M16 | `testHTTPHealthSerializesTypedLaneFailureCode`, `test_versioned_health_parser_rejects_unknown_missing_or_invalid_fields`, and `repro.py` reject dropped or untyped lane failure codes. |
| M17 | `testNativeRuntimeErrorsAreTyped`, `testHTTPHealthSerializesTypedLaneFailureCode`, and native lane-health transition coverage reject swallowing permission/device failure as healthy or stopped. |
| M18 | `testPumpFailureIsTypedAndLaterTicksContinue`, `testRepeatingSchedulerContinuesUntilExplicitCancellation`, and `repro.py` reject stopping the helper pump after transient transport failure or clearing failure before a later successful tick. |
| M19 | `testCaptureControllerPublicInterfaceIsLimitedToStartStatusStop` and `repro.py` reject expanding public `CaptureController` beyond `start/status/stop`. |
| M20 | `repro.py` module/interface/seam source fences and route tests reject putting lease/failure policy in HTTP routes, portal, mixer, or native adapters instead of `LiveHelperFailureCoordinator`. |
| M21 | Protected diff, promoted focused gates, and full-suite gates reject v2 audio schema, v1, batch, mixer DSP, access scope, portal, provider, frontend, grammar, dependency, ops, or default-off drift outside the lease-forwarding repair. |
| M22 | `CONTEXT.md`, this ADR, deployment-doc gates, configuration tests, and `repro.py` reject a scheduler-derived grace value or any claim that local green certifies a production timeout. |
| M23 | `CONTEXT.md`, this ADR, `testIDEA036ContextKeepsEvidenceTierMissingFence`, and `repro.py` reject treating local unsigned tests as signing, notarization, TCC, real device behavior, deployment, 60/300 evidence, canary, or enablement proof; all remain Missing. |
| M24 | Reviewer mutation-efficacy audit rejects any row whose named node stays green, applies nowhere, or changes no bytes. |
| M25 | `testPromotedSwiftTestIdentifiersRemainCollected`, Python collection/count floors, Git artifact fences, and `git diff --check` reject weakened coverage or committed generated, credential, pin, audio, socket, signing, or transcript artifacts. |

## IDEA-042 Residual Kill Nodes

- N1: `testCaptureControllerPublicInterfaceIsLimitedToStartStatusStop` plus
  `repro.py` inspect the whole `CaptureController` public surface, including
  initializer count, methods, storage/properties, subscripts, nested public
  types, and conformances.
- N2: `testFullCertificatePinValidatorRequiresExactValidSHA256` exercises the
  real full-certificate pin comparator and rejects mismatch or malformed pin
  inputs.
- N5: `test_live_portal_is_enabled_no_store_and_does_not_add_live_api_routes`
  inventories registered FastAPI routes and requires
  `POST /api/live/sessions/{session_id}/heartbeat`.
- Fix-cycle CLI nodes:
  `testCLIAppLaunchDecisionAndFailureArePropagated`,
  `testLaunchServicesAdapterInvokesInjectedOpenAndPropagatesFailure`,
  `testCLIPairingPayloadCrossesStdinThroughRealUDSWithoutOutputLeak`, and
  `testCLIPrintsAppFailureResponseAndReturnsNonzeroWithoutSecretLeak` drive
  launch decisions, the launcher adapter, real UDS pairing transit, exact app
  responses, exit codes, and output-channel secrecy.
- Fix-cycle pump/evidence nodes:
  `testPumpFailureIsTypedAndLaterTicksContinue`,
  `testRepeatingSchedulerContinuesUntilExplicitCancellation`,
  `testPromotedSwiftTestIdentifiersRemainCollected`,
  `testIDEA042ContextKeepsEvidenceTierMissingFence`, and
  `testIDEA042ResidualKillNodesNameExistingActualTests` pin typed retry state,
  collection floors, the local-only Missing fence, and this node map.

## IDEA-038 Portal/Helper Integration Kill Nodes

These nodes are the Reviewer mutation contract for the local portal/helper
integration slice. They name the expected killing check for each
single-obligation mutation; they do not claim mutation review has run.

| ID | Killing node |
| --- | --- |
| M05 | `test_built_mtd_capture_executable_is_resolved_from_the_package_bin_path` re-resolves the package bin path in the test module and rejects any probe executable that is not the real built `mtd-capture`. |
| M06 | `test_built_cli_usage_and_missing_app_socket_probes_stay_silent_about_authority` and the resolved-executable node reject removing the built CLI usage and missing-app/socket process probes. |
| M19 | `test_live_portal_event_identity_order_and_dom_share_one_cap` rejects an unbounded rendered-event identity set after over-cap replay. |
| M20 | The same node's DOM-row bound rejects pruning identity/order while leaving `nodes.events.children` unbounded. |
| M21 | The same node's identity and order bounds reject pruning only the DOM while identity/order state grows. |
| M23 | `test_live_portal_browser_contract_polls_renders_controls_and_stops`, `test_live_portal_control_timeout_uses_independent_10_second_abort`, and `test_idea_038_context_and_adr_keep_portal_constants_and_evidence_tier_missing` reject a stop drain other than 5 seconds or a poll/control timeout other than 10 seconds. |
| M24 | The terminal-final assertions in `test_reconnect_replay_typed_failure_and_final_terminal_state` plus the documented "terminal snapshot or event, not durable portal history or artifacts" claim reject treating final as durable history. |
| M25 | `test_idea_038_context_and_adr_keep_portal_constants_and_evidence_tier_missing` requires every `Missing` fact in both documents and rejects certification phrasings. |

## Consequences

- The current mono decoder, coordinator, scheduler, transcript grammar,
  accounting, finality, provider selection, and batch behavior remain unchanged.
- Lane-labelled v2 data now terminates at an in-process source-lane session
  lifecycle and a server-owned compatibility mixer. This proves local
  retention, compatibility mixing, downstream accounting, failure, finality,
  explicit expiry, and cleanup mechanics only; it does not prove helper-crash
  detection, provider quality, deployment, or live enablement.
- Simulated Windows coverage freezes the adapter-side contract without changing
  the transport, portal, server, lifecycle, mixer interface, or mono runtime.
  Real WASAPI capture, endpoint privacy/recovery, native helper reliability,
  signing, deployment, 60/300 evidence, canary, and enablement remain open.
- Prior acknowledgements use an ingress-local 256-entry replay window,
  independent of retained PCM/metadata and the runtime event-ring bound. The
  oldest acknowledgement is pruned when the window fills, so new frames continue
  and replaying a pruned key returns the typed `v2_pruned_replay` conflict.
- Device-epoch advancement requires a marked discontinuity, stale epochs return
  a typed conflict, retained-sample overflow returns typed backpressure, and
  stop fails closed while accepted v2 lane frames remain unaccounted by the
  future mixer. Clean stop requires exact accepted/accounted equality with zero
  failed, retained, or pending work. Abort and explicit expiry may discard a
  session with terminal accounting.
- Clients can discover the v2 contract through the default-off descriptor and
  can fail with a stable machine-readable obsolete-client response.
- JSON plus base64 is less efficient than binary transport, but keeps the MVP
  auditable and compatible with the existing disabled HTTP route seam.
- Server-owned mixing keeps JSON/HTTP and independent source retention intact,
  but makes the server responsible for timestamp alignment, limiter behavior,
  mono runtime admission, and post-admission source accounting.
- A single deep access authority keeps pairing, TLS admission, capture/view
  scopes, ownership, and revocation out of route closures. The trade-off is
  that live startup now needs explicit TLS certificate, TLS key, and private
  auth-state inputs before enabled live routes can listen.
- Live authentication is intentionally narrower than web-app authentication:
  it protects the default-off live surface only. Existing batch upload,
  runtime, media, render, and download routes remain unauthenticated and scoped
  to trusted LAN/Tailscale deployment limits.
- Pairing binds to the configured full TLS certificate fingerprint so a future
  helper can compare the observed certificate before exchanging the payload.
  This server decision does not prove native helper pin comparison, Keychain
  storage, certificate provisioning, rotation, signing, TCC, or deployed
  network reachability.
- Device revocation is explicit operator control that invalidates capture and
  view authority and releases owned live state. It is not helper-loss detection
  or an inactivity heartbeat.
- The `/live` portal is an L-tier manual operations view. It does not create,
  feed, pair, exchange, revoke, list sessions, contact a helper or localhost
  bridge, persist secrets, expose history or artifacts, or automate secure
  helper-to-browser bootstrap.
- A helper heartbeat is telemetry, not liveness policy. A delayed exact
  duplicate does not refresh last-seen; helper-sent time and wall time are not
  server freshness authority; failed/degraded health does not call lane
  failure, expiry, stop, abort, recovery, abandonment, or enablement logic.
