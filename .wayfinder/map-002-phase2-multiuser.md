---
label: wayfinder:map
id: map-002
slug: map-002-phase2-multiuser
title: Multi-user MOSS for a known team — accounts, isolation, voice bank, audio retention, client-configured LLM (Phase 2)
created: 2026-08-26
---

# Multi-user MOSS for a known team — accounts, isolation, voice bank, audio retention, client-configured LLM (Phase 2)

## Destination

A **decision-complete Phase-2 MVP spec** the AFK builder loop can execute with zero remaining
design questions: the server-hosted MOSS Chrome client becomes a multi-user product for a known
team (~2–10) on the tailnet — Google-account sign-in behind an operator email allowlist, strict
per-user transcript isolation at production rigor, a durable named voice bank, retained post-Stop
meeting audio, and client-configured LLM features — decision-complete across all four families,
shipping in waves with accounts, isolation, and live MP3 usable first. **This map plans; it does
not build product code.**

## Notes

**Domain:** multi-user client/server streaming ASR + diarization. Account identity (Google
OpenID Connect), per-user authorization on every create/read/stream/download/delete, relational
persistence, voiceprint banking, audio archival, client-configured LLM assistance.

**Repos and hosts:**

- Target (product, **this repo** — map and sessions live here):
  `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`. Charting ran on
  branch `ralph/live-convergence-0824` @ `7608c91` with a deliberately dirty, user-owned
  worktree — never clean/stash/switch it.
- Phase-1 product truth: branch `dev` (Chrome client at `/`, charter
  `docs/phase1-afk-charter.md`, closed map `map-001-phase1-chrome-client`). Inspect via
  `git show dev:<path>`, no checkout.
- Reference (feature source of truth, read-only over SSH):
  `ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`, branch `ralph/production` @ `6a8d0c1`,
  **dirty worktree — preserve it**; use `git show HEAD:<path>` wherever local edits overlap.
  Launcher `scripts/run_app.sh` exists but this map's tickets are source/data-flow research,
  not app runs.
- Deployed live service: `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861`
  (self-signed today; the explicit port is load-bearing).
- Older planning corpus (server portal + native helper era):
  `/Users/gao/Desktop/AI_Projects/AAgent/260724-moss-capture-wayfinder/`. Its reasoning on
  lanes/transport/privacy remains valid evidence; its "no dependency on LiveTranscribe" and
  helper-centric exclusions are **superseded** by the operator's Phase-2 request.

**Skills every session should consult:** `/grilling` + `/domain-modeling` for grilling tickets;
`/codebase-design` once terms are stable; `/prototype` for any measured-behavior ticket
(`AGENTS.md` mandates measure-before-implement); research subagents for research tickets.

**Standing evidence — extend, don't re-litigate:**

- Phase-1 closed map `map-001-phase1-chrome-client.md` (premises C1–C11 there) and the binding
  `docs/phase1-afk-charter.md` (capture spec, fidelity method, gates G1–G10).
- ADR-0001 (live v2 JSON HTTP contract), ADR-0002 (two-tier diarization fingerprint album),
  ADR-0003 (live session audio retention), `docs/design-streaming-diarization.md`.
- Live == file convergence resolved 2026-08-25: macro settled pre-Stop WER `.140442`, final WER
  `.095074` across 12 actual-live sessions (`evidence/live-g4-recovery-20260825/REPORT.md`).
- 15/10 lexical **rejected** at the causal prototype gate
  (`evidence/live-15-10-lexical-20260825/ADOPTION.md`). Do not resurrect.
- Decode is serialized (one `_TransientCanonicalPumpScheduler` worker); do **not** fix
  concurrency with multiple Uvicorn workers — device state, session ownership, runtime objects,
  mixers, event queues, and view grants are process-local.

**Charting decisions (2026-08-25/26 operator grilling).** Premises of this map, not route
steps; no ticket holds them.

| # | Decision |
|---|---|
| C1 | **Destination = decision-complete MVP spec**, handed to the AFK loop. Wayfinder plans; it does not build. |
| C2 | **Trust boundary = known team (~2–10) over the tailnet only.** No public exposure in the MVP. |
| C3 | **All four families decision-complete; ship in waves.** Wave 1 = accounts + isolation + live MP3, shippable and usable alone; voice bank and LLM land as later increments without re-planning. |
| C4 | **Capacity = 2–4 concurrent live sessions** — Phase-1's measured G4 bound carries forward as the Phase-2 gate; LLM work must fit beside it. |
| C5 | **Sign-in = any Google account via an external OAuth app; the server admits only an operator-maintained explicit email allowlist.** Covers teammates without `aisight.us` accounts; the server owns the allowlist. |
| C6 | **Isolation is production-rigor security scope** — the operator names cross-user transcript disclosure disastrous. Wrong-user delivery must be structurally unrepresentable, not a UI convention. Surgical: secure reachable product paths; no generic enterprise scaffolding. |
| C7 | **Tracker = this local-markdown map** (`.wayfinder/`, conventions in `README.md`), per handoff default; the operator did not select the `aiSight-us` GitHub tracker. **Never create planning issues on upstream `OpenMOSS`.** |
| C8 | **LiveTranscribe is evidence, not a blueprint.** Audit read-only; its single-host assumptions inform but do not dictate the client/server design. |

## Decisions so far

<!-- one line per closed ticket: enough to judge relevance, then open the ticket for detail -->

- [LiveTranscribe voice bank internals](tickets/T-13-livetranscribe-voice-bank-internals.md) —
  WeSpeaker ResNet34 CoreML 256-dim; one JSON file per profile; cosine, fingerprint-first at
  0.51 vs clusters 0.55; live-capture-only; rename decoupled from the bank; embedder-version
  change bricks the bank (strict hash equality, no migration); deletion touches only the file.
- [LiveTranscribe LLM layer inventory](tickets/T-14-livetranscribe-llm-layer-inventory.md) —
  6 features (30 s format cycle, 60 s summary cycle, auto-title at stop, off-by-default name
  enrichment, manual re-format, disabled reconciliation); **no in-process runtime** — an
  OpenAI-compatible HTTP client, default LM Studio `127.0.0.1:1234/v1` / `qwen3.6-35b-a3b`;
  "local" is user-machine policy (ADR-0015), not architecture.
- [LiveTranscribe audio persistence and session history internals](tickets/T-15-livetranscribe-audio-and-history.md) —
  recording ON by default, streamed to disk during capture; WAV s16le 16 kHz mono, ~115 MB per
  lane-hour (dual ≈ 230 MB/h); per-source `local.wav`+`remote.wav`, mixed lane structurally
  never persisted; history = SQLite authoritative + JSON projection with crash-aware terminal
  commit ordering.
- [Google sign-in for an allowlisted external app](tickets/T-16-google-signin-allowlisted-external-app.md) —
  fits C5+C2 on paper: sign-in-only scopes exempt from verification **and** Testing-mode
  caps/expiry; no refresh tokens involved; redirect-URI rules don't forbid the `:7861` tailnet
  origin and Google never contacts it (self-signed breaks nothing Google touches); key on
  `sub`, email is only the allowlist input; risks left: console acceptance of the exact URI,
  publish-time domain-verification demands.
- [Database for multi-user MOSS](tickets/T-17-database-sqlite-vs-postgresql.md) — green-field
  (no DB in code today); measured shape tiny (~16 inserts/s host-wide worst case, ~2M durable
  rows/yr); SQLite paper-fits with ≥10× margin but Litestream is unsupported on Windows;
  process-local snapshot serving can keep the DB off the poll path entirely; prototype
  `sqlite-wal-poll-latency` fully specified if T-21 judges the case close.
- [MOSS multi-user-relevant current state](tickets/T-18-moss-multiuser-current-state.md) —
  shared token = one principal, cross-user isolation zero by construction; pairing code wired
  but Chrome never pairs; 12 authed session/job choke points **plus 8 job routes with no auth
  even in live mode** and an unauthenticated plaintext batch service on 7860; vector journal
  default-ON (biometric derivative) while audio retention is deployed OFF; no DB, sessions
  memory-only, loopback = root; inference globally single-threaded.
- [Biometric consent and voiceprint privacy boundary for a team deployment](tickets/T-22-biometric-consent-and-voiceprint-privacy.md) —
  Private per-user bank for any manually named voice; always on, owner-deletable, no expiry,
  historical labels retained, and no Phase-1 journal migration.
- [Where the Phase-2 spec lands and how the AFK loop consumes it](tickets/T-27-spec-landing-and-afk-handoff.md) —
  ADR-per-family plus one binding Phase-2 charter in the product repo; private `aiSight-us`
  implementation tickets; every agent may self-merge under the serialized Phase-1 protocol;
  the Wayfinder owner commits the path-scoped planning set after map closure and before launch.
- [Identity and isolation architecture — structurally unrepresentable cross-user delivery](tickets/T-19-identity-and-isolation-architecture.md) —
  Many single-owner Accounts share one server; account-scoped Meeting handles prevent global
  lookup, all same-account devices share history, and legacy token compatibility is removed.
- [Authentication decision — Google OIDC with email allowlist, sessions, revocation, fallback](tickets/T-20-authentication-decision.md) —
  Separate MOSS client in the existing Google project; exact-email SQLite admission,
  non-expiring revocable server sessions, and trusted existing-origin TLS through NS1 DNS-01.
- [Persistence decision — database choice and schema ownership boundaries](tickets/T-21-persistence-decision.md) —
  SQLite 3.53.4 via one owner-scoped aiosqlite connection; relational text/vectors plus file
  audio, composite Account ownership, no migration framework, and one cold backup bundle.
- [Measured MOSS Voiceprint matching and abstention rule](tickets/T-30-measured-voice-profile-matching.md) —
  Production-path evidence accepts cosine `>= 0.46`, no margin, `>= 1.0 s`, arithmetic-mean
  Voiceprints: 441/470 causal correct, zero observed wrong names, 470/470 unknown abstentions.
- [Voice bank design — ownership, storage, matching, abstention, versioning, deletion](tickets/T-23-voice-bank-design.md) —
  One server-side private bank per Account; stable Voiceprint IDs and non-unique labels, measured
  `0.46` matching, rename-time quality-gated enrollment, live revision invalidation, and
  owner-only deletion behind one Account Speaker Identity module.
- [Audio retention design — formats, lanes, ownership, lifecycle, download](tickets/T-24-audio-retention-design.md) —
  Always-on owner-private mixed-only 48 kbit/s MP3; synchronous Stop, partial salvage, authenticated
  download only, with WSL files managed by the deployment operator outside MOSS.
- [Wave-1 boundary and Phase-1 cutover — accounts, /studio, /live, existing data](tickets/T-26-wave1-boundary-and-phase1-coexistence.md) —
  Authenticated `/` only; empty-data start; Account-owned Live/File/batch history plus live MP3;
  legacy surfaces, tokens, and external `:7860` removed through an atomic drain-to-zero cutover.
- [Client-configured LLM browser path and hybrid-summary policy](tickets/T-31-client-configured-llm-browser-prototype.md) —
  Chrome/controller and full-first delta-fallback shape accepted; unchanged summary prompt rejected
  on measured quantity/length defects, with a focused replacement prototype surfaced.
- [Revised summary prompt and deterministic output contract](tickets/T-33-revised-summary-prompt-and-output-contract.md) —
  One V15 request shape over the finalized transcript; no rolling or output-repair calls; a
  five-field JSON contract with deterministic shape/timestamp validation; 7/7 valid measured
  outputs at 2.207 s median / 3.360 s maximum, with broader quality and holdouts unmeasured.
- [Client-configured LLM functions, ownership, artifacts, and UI](tickets/T-25-local-llm-scope-and-placement.md) —
  Browser-owned OpenAI-compatible configuration and calls produce one account-owned Final
  summary per finalized Meeting; calls serialize, delivery retries are bounded, and server ASR
  never hosts or schedules the model.
- [Post-Wave-1 sequencing — private voice bank or client-configured LLM next](tickets/T-32-post-wave1-sequencing.md) —
  Private voice bank ships in Wave 2; client-configured LLM follows independently in Wave 3.
- [Operator observability — metadata-only multi-user health and capacity](tickets/T-29-operator-observability.md) —
  Host-local CLI and structured logs expose allowlisted Account, Meeting, capture, queue, error,
  and storage metadata; a narrow local control seam can revoke Accounts or interrupt active
  Meetings but can never open content.
- [Phase-2 acceptance gates — adversarial isolation, revocation, voice, audio, LLM privacy](tickets/T-28-phase2-acceptance-gates.md) —
  Each wave must pass deterministic, deployed four-session, and production-canary evidence;
  cross-Account delivery has zero tolerance, with exact inherited capacity, quality, Voiceprint,
  audio, and Final-summary bars bound into the Phase-2 charter.

## Not yet specified

None.

## Out of scope

Ruled beyond this destination by operator decision (2026-08-25/26 grilling). Later phases are
fresh maps, not resumptions.

- **Public exposure / open signup** — C2 fixes a tailnet-only known team.
- **Horizontal scale-out, multi-process serving** — C4 keeps the 2–4 bound; process-local
  state stands.
- **Building Phase-2 product code from this map** — planning only (C1).
- **Native capture helpers** as the product path — Phase 1 settled Chrome as the capture
  surface; the MCW-era helper corpus stays evidence only.
- **Safari capture client** — Phase-1 measured exclusion stands (no display audio track).
- **Windows Chrome parity gate** — orthogonal to multi-user scope; its own effort if revived.
- **15/10 lexical candidate** — measured-rejected 2026-08-25; not part of any Phase-2 route.
- **In-product audio file management** — quota, expiry, eviction, deletion, backup, and storage
  UI are operator-managed outside MOSS, as ruled in
  [Audio retention design — formats, lanes, ownership, lifecycle, download](tickets/T-24-audio-retention-design.md).
- **Non-Google sign-in fallback** — the MVP is Google-only; no local password, invite token, or
  emergency bypass, as ruled in
  [Authentication decision — Google OIDC with email allowlist, sessions, revocation, fallback](tickets/T-20-authentication-decision.md).

## Implementation tracker

Planning destination reached 2026-08-27. Binding artifacts are ADR-0006 through ADR-0012 and
`docs/phase2-afk-charter.md`. Implementation tickets are cut only after the path-scoped planning
commit reaches `dev`, on private `aiSight-us/MOSS-Transcribe-Diarize`, never upstream.
