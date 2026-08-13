---
label: wayfinder:map
id: map-001
slug: map-001-phase1-chrome-client
title: Zero-install Chrome client for MOSS live + file transcription (Phase 1)
created: 2026-08-12
---

# Zero-install Chrome client for MOSS live + file transcription (Phase 1)

## Destination

A **decision-complete Phase 1 spec** that the existing AFK builder loop can execute with
zero remaining design questions: a remote operator opens Chrome (no install), streams
microphone **and** meeting/system audio to the MOSS server, and watches a live diarized
transcript render in the reference project's exact visual design — plus file-mode upload
through the same UI, and live-transcript export to file.

The map is done when the spec exists as target-repo ADR/design-doc plus a control-plane PRD,
and nothing in it is still an open question. **This map plans; it does not build product code.**

## Notes

**Domain:** remote client/server streaming ASR + speaker diarization. Browser capture
(`getUserMedia` / `getDisplayMedia` / AudioWorklet), HTTP frame ingest, polled event
delivery, per-session identity.

**Repos:**

- Target (product, **this repo** — the map lives here and sessions run from here):
  `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`
- Control plane: `/Users/gao/Desktop/AI_Projects/0.AISIGHT_LOOP/moss-transcribe-diarize` —
  AFK loop state, ledgers, evidence, review decisions. Holds no product code.
- Reference (UI source of truth): `/Users/gao/Desktop/AI_Projects/LiveTranscribe` —
  Preact + Vite + `@preact/signals`, Swift/Vapor backend. Full product, not a mockup.
- Deployed live service: `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`
  (self-signed, tailnet-only; **the explicit port is load-bearing** — omitting it silently
  targets unconfigured 443).

**Skills every session should consult:** `/grilling` + `/domain-modeling` for grilling
tickets; `/prototype` for prototype tickets (target repo's `AGENTS.md` mandates
measure-before-implement); `/research` subagent for research tickets.

**Standing evidence — extend, don't re-litigate:**

- `docs/research-chrome-capture-mvp-2026-08-03.md` (target repo) — Chrome two-lane capture
  **Gate 1 PASSED**, attended, measured. Read it before specifying anything about browser
  capture. Frame geometry, activation ordering, error taxonomy, and the lane design are
  settled there.
- ADR-0001 (live v2 JSON HTTP contract), ADR-0002 (two-tier diarization fingerprint album),
  ADR-0003 (live session audio retention).
- `frame_samples` / `sample_rate` / bounds are **deploy-manifest values, not code
  constants** — the client must read `/api/live/descriptor`, never hardcode.
- Decode is **serialized today**: one `_TransientCanonicalPumpScheduler` worker drains
  sessions round-robin. Ingest is concurrent and fair; decode is not parallel.
- Do **not** fix concurrency with multiple Uvicorn workers — device state, session
  ownership, runtime objects, mixers, event queues, and view grants are all process-local.

**Charting decisions (2026-08-12 operator grilling).** These are the map's premises, not
route steps; no ticket holds them.

| # | Decision |
|---|---|
| C1 | **Destination = locked spec**, handed to the AFK loop. Wayfinder does not build. |
| C2 | **UI fidelity = same pixels, drop controls that cannot work.** Do not reinterpret host-local affordances, and do not add a superset. Reference controls with no remote meaning (output-volume, native file/folder pickers, server-side device enumeration, export-to-folder, server-side mic mute) are **removed**, not re-plumbed. |
| C3 | **Transport = keep MOSS polling.** No WebSocket. Frontend's `api/ws.ts` is replaced by a poller feeding the identical `dispatchWsEvent()` seam; `state/`, `components/`, `lib/` are untouched. Cadence is **adaptive: 250 ms while capturing, 2 s while finalizing/idle.** MOSS's `/events?since_seq` + `/snapshot?since_version` cursors are strictly stronger than the reference's cursor-less WS. |
| C4 | **Concurrency target = 2–4 concurrent live sessions, measured.** Gate 3 is in scope. The GPU on `ga0-alienware-rtx4070ti` is available **without scheduling limitation** (operator, 2026-08-13), so T-04 has no GPU-window constraint. |
| C5 | **Phase 1 auth = one shared bearer token from server config; no pairing.** Consequence to be specified in *Shared-token trust posture and client identity*, not assumed. |
| C6 | **Phase 1 lanes = both** (microphone + display/system audio), with the preflight flow the research doc requires. |
| C7 | **Routing:** new app at `/`; existing Subtitle Studio moves to `/studio` unchanged; Phase 1 file mode runs through a thin adapter over the certified `/api/jobs` pipeline. |
| C8 | **Toolchain:** lift the reference's own `vite.config.ts` / `tsconfig.json` / `package.json` / bundled fonts **verbatim** so its CSS and components build byte-identically. Reuse only A-010's server-side static-serving pattern. A-010 stays unmerged and closes as superseded. |
| C9 | **Voice bank (Phase 2) is keyed on `device_id`.** Phase 1 must therefore not destroy device identity even though it drops pairing — this is what makes C5's consequence load-bearing. |
| C10 | **LLM API key = one operator key in server config.** Browser stores only prefs. The LLM settings modal itself is **out of Phase 1** (inert without an LLM layer) and returns in Phase 2. |
| C11 | **Client-side judgment is minimized; the server is authoritative for capture health.** Client-side *processing* is already at its floor — capture APIs are browser-only and the worklet is required to obtain samples at all; server-side resampling would cost ~512 kB/s versus ~85 kB/s for two lanes and re-litigate ADR-0001. What is removable is client *decision-making*, so the browser reports raw facts via `HelperHeartbeat` and renders the server's verdict. Zero-install and Chrome/macOS+Windows parity are already satisfied by the browser platform itself and are not arguments for moving work server-side. |

## Decisions so far

<!-- one line per closed ticket: enough to judge relevance, then open the ticket for detail -->

- [Shared-token trust posture and client identity](tickets/T-01-shared-token-trust-posture.md) —
  **single trust domain accepted**: anyone on the LAN may read any transcript. No client-asserted
  `device_id` (security theatre). Kills the `403` isolation criterion for T-11 and makes pairing
  a Phase 2 precondition for the voice bank.
- [Where the Phase 1 spec lands and how the AFK loop consumes it](tickets/T-03-spec-landing-and-afk-handoff.md) —
  **several ADRs under `docs/adr/`**, continuing the 0001–0003 sequence; `.wayfinder/` is
  committed and git-tracked; planning artifacts live with the code.
- [Serving cutover — new app at /, Studio at /studio, one origin](tickets/T-09-serving-cutover-and-origin.md) —
  `/` new app, `/studio` unchanged, `/live` **kept as operator diagnostic**; bundle committed;
  **`vite build --watch`, no dev server** (same-origin is load-bearing for capture); origin always
  carries `:7861`; A-010 closes as superseded.
- [Poll contract — MOSS snapshot/events mapped onto the reference event model](tickets/T-02-poll-contract-event-model.md) —
  **only 5 of the reference's 9 events are reachable**; the four `llm_*`/`speaker_renamed` are
  declared unreachable, not left dangling. One `CanonicalCommit` → many `TranscriptItem`s via
  `TranscriptStreamParser`. Provisional tail parsed and merged into the list; corrections shown
  **silently** (`revised_transcript ?? transcript`); `speaker_entity_id` = album canonical id;
  `prefix_hash` carried but unverified. Snapshot is a full replacement keyed by `version`, so
  replay is a no-op. **Capture health is SERVER-authoritative** (corrected 2026-08-13): the
  browser is just another "helper" posting `HelperHeartbeat`; the server fuses browser-only
  facts with frame facts and publishes one status line. Trap recorded: heartbeats must be
  worklet-driven, since a backgrounded tab throttles timers to ~1/min and can trip the helper
  lease on a healthy session.
- [Voice-bank persistence](tickets/T-12-voice-bank-persistence-does-not-exist.md) —
  Phase 1 **journals vectors, does not build the bank**: album centroid appended at session end,
  session-keyed (T-01 removed `device_id`), stamped with pinned-embedder identity. Journaling
  defaults **ON**; raw-audio retention stays **OFF** — ADR-0003's posture deliberately not
  inherited. Biometric-consent decision remains **open** for any rollout beyond the LAN.

## Not yet specified

In scope for Phase 1, not yet sharp enough to ticket:

- **Windows Chrome parity (Gate 4).** Windows has offered tab audio since Chrome 74 and
  entire-screen system loopback for years, so it is expected to be the *easier* platform —
  and the inference host is itself a Windows machine, so it can be tested attended on
  existing hardware. Unclear whether Phase 1 *requires* a passing Windows run or merely
  must not preclude one. Sharpen once the capture-page spec exists.
- **Operator observability.** How an operator sees N active sessions, per-session queue
  depth, and 429 backpressure. Shape depends on the concurrency-dispatcher outcome. Narrowed
  2026-08-13: the product UI shows none of it (two meters + one status line), so this is purely
  an operator-surface question — `/live` and logs are the current answer.
- **Biometric consent for banked voiceprints beyond the LAN.** T-12 rules journaling ON for the
  guarded tailnet deployment and explicitly does **not** settle consent, deletion, or
  right-to-remove for participants who never agreed to enrollment. Sharpens into a ticket if
  the deployment widens past the operator's own meetings.
- **TLS posture beyond the tailnet.** The MVP deliberately keeps a self-signed cert with a
  one-time same-origin interstitial click-through. The trigger and target for graduating to
  a trusted certificate is undecided.
- **Preflight screen visual design.** The two-lane preflight (meters, share-audio guidance,
  headphones-vs-speakers echo choice, clipping warning) has **no reference pixels** — the
  reference never needed it. Will graduate out of the capture-page spec ticket.

## Out of scope

Ruled beyond this destination by operator decision (2026-08-12). Phase 2 is a **fresh map**,
not a resumption of this one.

- **Phase 2 product surface** — voice bank (durable, `device_id`-keyed), speaker rename +
  retroactive relabel, URL mode (download an https media source, then run file mode), batch
  mode, the full LLM layer (settings + live reformat overlay + summary + status), and session
  history with titles and reattach. All are absent from MOSS today; all deferred so Phase 1 ships.

  **Carve-out (T-12, 2026-08-12):** this deferral covers *building* the voice bank, **not** the
  decision to *discard*. Verified against the tree, the bank is not CRUD over an existing store —
  no embedding is written to disk anywhere in the product, and the one banking mechanism built
  (`0983339` on `ralph/dl2-postreview-rails`) is absent from `main` and from production RC
  `fb83ba5`. Whether Phase 1 knowingly discards enrollment vectors is therefore a **Phase 1**
  decision and stays on the frontier as *Voice-bank persistence — Phase 2's store does not exist
  and Phase 1 does not create one*.
- **Real user accounts / SSO.** C5 ships a shared token; C9 keys the future voice bank on
  `device_id`. Account-based identity is a later redesign.
- **Safari as a capture client.** Measured: Safari gets microphone but supplies **no**
  display audio track (`video=1 audio=0` for both window and monitor). C6 requires both
  lanes, so Chrome-only is the correct Phase 1 scope. Revisit only on a WebKit release
  claiming display-audio support.
- **Multi-process / horizontal scale-out.** Excluded by C4 and by process-local state.
