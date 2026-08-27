---
id: T-28
map: map-002-phase2-multiuser
title: Phase-2 acceptance gates — adversarial isolation, revocation, voice, audio, LLM privacy
type: grilling
status: closed
assignee: codex-20260827-t28
blocked_by: [T-19, T-20, T-21, T-23, T-24, T-25, T-26, T-29, T-32]
---

## Question

What are the measured, reproducible gates that prove the Phase-2 MVP — and specifically its
isolation claim — before the team touches it?

Last ticket by design (Phase-1 precedent: gates ruled once every design was closed, then bound
into the charter). Decide, with the operator, gates covering at least:

- **Adversarial cross-user isolation** — deliberate wrong-user attempts: session-id guessing,
  cursor replay across accounts, reattach with a revoked sign-in, download of another
  account's audio/transcript/voiceprint by direct route — each structurally impossible, with a
  reproducible harness, not a code-review claim. Under concurrent load (C4's 2–4 sessions),
  text never crosses accounts — the Phase-1 G5 bar upgraded from "sessions" to "accounts".
- **Identity-architecture contract** — turn all eight accepted behaviors from *Identity and
  isolation architecture* into runnable cases: wrong-owner reads and mutations, cursor replay,
  per-session and whole-account revocation, same-account multi-device history/live parity,
  legacy-token rejection, and content-free operator observability.
- **Account lifecycle** — allowlist add/remove takes effect within the ruled latency; sign-out
  and server-side revocation kill live pollers per T-20's rulings; expiry mid-meeting behaves
  as ruled.
- **Concurrent capture** — C4 sustained with accounts on (the Phase-1 G4 bar re-run under
  authenticated multi-account load), no regression of the live-quality baseline
  (`evidence/live-g4-recovery-20260825/REPORT.md` numbers stand).
- **Voice bank** — false-match and abstention rates on the standing bench corpora with the
  T-23 thresholds; duplicate labels never select identity; the 2.0-second pending-enrollment
  path saves exactly one sample; active/history rename propagation behaves as ruled; one
  incompatible Voiceprint does not disable compatible entries; and deletion invalidates a
  deliberately paused stale in-flight match before it can relabel an active Meeting while
  preserving historical labels.
- **Audio durability** — post-Stop artifact exists, plays, matches the ruled canonical form;
  crash-mid-meeting yields the ruled partial-tape outcome; authenticated owner download works
  and cross-Account download fails. Quota, expiry, eviction, deletion, and backup remain
  operator-managed outside MOSS per *Audio retention design* and are not product gates.
- **LLM privacy** — prompts contain only the owning account's artifacts (verifiable via
  prompt logging in the harness); LLM load does not break C4's gate.
- **No regression** — the existing live/contract suites and Phase-1 gates still pass where
  applicable.

Resolution records the gate table with exact bars, the harness locations, and what is
explicitly NOT gated in the MVP — then the map has reached its destination and the spec/
charter (per *Where the Phase-2 spec lands*) is written from the closed tickets.

## Resolution

Resolved 2026-08-27 through operator grilling. The operator explicitly confirmed D1–D5 and
delegated every remaining bounded choice to Codex.

### Release evidence contract

- **D1 — Per-wave gates:** Wave 1, private Voiceprints (Wave 2), and client-configured Final
  summaries (Wave 3) remain independent releases. Every wave reruns the cumulative Account/
  isolation core; Wave 2 adds Voiceprint gates and Wave 3 adds Final-summary gates. Wave 3 does
  not rerun the full Voiceprint corpus, but a finalized transcript carrying Wave-2 labels crosses
  its privacy path.
- **D2 — Three evidence layers:** the same candidate commit must pass deterministic contract/
  adversarial tests, a deployed 600-second four-session campaign split across at least two
  Accounts, and a production-origin pre-admission canary after installation.
- **D3 — Zero-tolerance isolation:** every wrong-owner public read/mutation and direct route is
  exercised with unmistakable Account sentinels. Wrong owner is `404`, revoked/invalid session is
  `401`, unauthorized mutation changes no relevant state, and one foreign sentinel anywhere fails
  the wave. There is no leak-rate tolerance.
- **D4 — Event-bound revocation:** Account revoke returns only after every active Meeting is
  durably `interrupted`; the next request from each revoked session is `401`; no later frame/result
  commits. Single-browser sign-out preserves other sessions. MOSS has no session-expiry gate;
  cookie loss exercises the same `401` path.
- **D5 — Frozen concurrency bars:** four sessions for 600 seconds; maximum per-session p95 lag
  `<=10.0 s` (linear Type-7); continuously-ready fairness skew `<=1`; combined pre-Stop inference
  real-time factor `<1`; refinement queue depth `<=1`; vLLM cache `<=0.95`; service/inference RSS
  growth `<=4 GiB`; zero OOM/accelerator errors, gaps, stale/failed windows, terminal failures, or
  cross-Account text; per-session retryable `429` while peers progress. A short eight-session probe
  tests overload isolation/backpressure, not supported capacity.
- **D6 — Honest evidence:** all required cases pass once in one complete evidence bundle. Failed
  evidence remains; a fix creates a new complete bundle rather than retrying to green. Exact
  collected/executed/passed/failed/skipped/unmeasured denominators are mandatory. Stub inference
  may test state paths but never satisfies a real inference/capacity gate.

No new numeric threshold was invented. Concurrency, live quality, audio format/cost, Voiceprint,
and V15 contract bars come from the already measured/frozen benches linked below.

### Gate table

The cumulative core is G0–G6 plus G10. Wave 1 runs the core plus G7; Wave 2 runs the core plus G8;
Wave 3 runs the core plus G9.

| Gate | Exact blocking bar | Wave |
|---|---|---|
| **G0 Candidate/evidence identity** | One committed candidate across all layers; installed revision matches; scoped dirty state, missing raw predicates/denominators, or nonzero final active/queued state fails. | All |
| **G1 Adversarial Account isolation** | Complete Account A/B matrix across Meeting/live/File/cursor/transcript/audio/Voiceprint/Final-summary reads and feed/stop/abort/rename/rerun/delete/retry/download mutations. Wrong owner `404`; revoked `401`; zero state effect; zero foreign sentinel in UI, snapshots, events, prompts, persistence projection, status, or logs. Same-Account devices retain identical history/live state; legacy paths absent. | Core |
| **G2 Authentication and revocation** | Authlib 1.7.2 rejects bad signature/issuer/audience/expiry/state/nonce/unverified-email. Exact Google callback saves; real allowed and denied external Accounts behave as ruled; trusted TLS has no interstitial. Cookie contract/restarts pass. Allow/revoke acts at CLI return; sign-out affects one session; Account revoke satisfies D4. | Core |
| **G3 Durable Meetings/history** | Live/upload/multi-file/URL/batch items become independent owner Meetings; one item failure does not affect peers. Same-Account clients share ordered history/live state. Transcript commits and session survive restart. Crash produces durable `interrupted` Meeting with last transcript/maximal audio prefix and no capture resume. Composite ownership rejects cross-Account links; only schema v1 starts. | Core |
| **G4 Capacity and live quality** | D5 four-session/600-second and eight-session-overload bars. Fixed six-case/two-pass/12-session macro quality: immediate WER `<=.166655`; settled WER `<=.140442`; recall `>=.929636`; time-based speaker attribution `>=.876970`; DER `<=.161430`; matched-speaker accuracy `>=.911512`; reference-speech DER `<=.134804`; final WER `<=.095074`. Report per-case/category/weighted values; descriptive clocks do not become new thresholds. | Core |
| **G5 Audio durability** | Clean Live/File Stop yields playable MP3, 16 kHz mono constant 48 kbit/s, with no retained raw/WAV. Stop waits for durable transcript plus `available|partial|unavailable`. Crash publishes maximal partial prefix or unavailable; encode/storage failure preserves transcript. Owner download/filename works; wrong owner `404`; revoked `401`; path permissions/metadata reconcile. | Core |
| **G6 Operator boundary** | Admin Unix socket is local/service-owned/mode `0600`; no TCP/browser admin surface. Human/JSON status contains exactly the ruled allowlist and no Account sentinel/content/secret. Counts reconcile. Deliberately late inference after Meeting interrupt is discarded while durable transcript/partial audio remain. | Core |
| **G7 Atomic Wave-1 cutover** | Drain to zero; quarantine one full Phase-1 snapshot; install trusted TLS, empty schema v1, allowlist, authenticated `:7861`, and keep `:7860`/old routes/tokens absent. Pre-admission canary covers sign-in/isolation/audio/file+URL+batch/history/restarts plus attended real mic, meeting-tab audio, entire-screen System Audio, exact frame geometry, distinct speaker text, and owner download. Any failure restores the whole old service before traffic opens. | 1 |
| **G8 Voiceprint bank** | Standing production-embedder bench reproduces 441/470 known correct, 29 abstain, zero wrong; 470/470 unknown abstain; terminal 14/14 known correct and 14/14 unknown abstain at cosine `>=0.46`, no margin, `>=1.0 s`. Duplicate labels never select identity. The 2.0 s pending path writes exactly one sample. Active/history rename, one-entry incompatibility, owner isolation, and paused-old-revision deletion fencing all pass. | 2 |
| **G9 Final-summary privacy/lifecycle** | Two-Account fake OpenAI endpoint logs requests containing only the owner Meeting's finalized transcript, browser prompt, and request parameters. No other Meeting/history, Account ID, audio, Voiceprint, server-stored prompt/token, or foreign sentinel. One active attempt; browser serialization; identical delivery retries at 60/120/240 s; no repair call; cancellation/Retry/states/authorization pass. Recorded five-field validator fixtures pass. Maximum LLM work beside G4 leaves every G4 bar green. | 3 |
| **G10 No regression** | `pytest tests/`, frontend Vitest, TypeScript typecheck, and production build all pass with exact counts. Applicable Phase-1 real-mic, synthetic-system, failure, background-tab, fidelity, Live/File, and contract gates pass through the Account path. Superseded token/view-token behavior is absent, not preserved. | All |

### Harness and evidence locations

The AFK build must create the missing acceptance driver/tests at these exact locations; absence
means unimplemented, never waived:

- deterministic suite: `tests/phase2/`;
- one-command driver: `scripts/phase2-acceptance/run.py`;
- retained bundles: `evidence/phase2/wave-<n>/<UTC>-<git-short-sha>/`;
- Voiceprint bench: `prototypes/streaming-diarization/voice-profile-matching/`;
- concurrency bench: `prototypes/streaming-diarization/concurrency/`;
- audio-format bench: `prototypes/streaming-diarization/audio-retention-format/`;
- fake endpoint/output fixtures: `prototypes/client-configured-llm/`.

One command prints full relevant state and writes the evidence bundle:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/phase2-acceptance/run.py \
  --wave <1|2|3> --output evidence/phase2/wave-<n>/<UTC>-<git-short-sha>
```

The binding implementation handoff is
[`docs/phase2-afk-charter.md`](../../docs/phase2-afk-charter.md); hard-to-reverse decisions are
recorded in ADR-0006 through ADR-0012.

### Explicitly not gated

- Public/open signup, horizontal/multi-process scale, Safari, Windows Chrome parity, native
  helpers, or the measured-rejected 15/10 lexical candidate.
- Non-Google fallback, Google-side revocation of an existing MOSS session, admin content access,
  sharing/ownership transfer, legacy compatibility, or importing Phase-1 content.
- Audio perceptual quality, quota, expiry, eviction, product deletion, backup, storage UI/file
  manager, byte ranges, or embedded playback; these remain operator-managed where applicable.
- Voice populations beyond five speakers/two English recordings, banks over five, automatic
  learning, merge/upload/standalone enrollment, or embedder migration.
- LLM providers/models/endpoints beyond the tuning setup, LAN/cloud bearer behavior, blind
  holdouts, meetings beyond 30 minutes, non-English output, or broader semantic quality.
- New fixed thresholds for historical first-publication/correction/drain/Stop clocks, deployed
  MP3 conversion time, or any other quantity the operator never accepted as a gate.

No new Wayfinder ticket or fog surfaced. With this resolution, every child decision is closed and
the map's planning destination is reached. This is specification closure, not product readiness.
