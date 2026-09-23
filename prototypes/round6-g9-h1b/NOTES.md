# G9 H1B — content-free predicate diagnosis

Structural question: Do H1B's `owner_payloads_only` and `speech_capacity_unchanged` failures come from a product violation or stale/incomplete qualification expectations, and what exact per-check operands need to be retained to tell?

Minimum primitives:

- The production `_validate_capacity` reduction and the exact retained `summary-load/load-2` event files.
- The G4 H1B capacity artifact as a same-layer control; it is recorded PASS, but a local validator replay against its exported event rows currently returns false. The reason for that discrepancy is not yet established.
- The real browser `providerBody` path with synthetic scratch transcripts and a local HTTPS `SummaryProbeProvider`; capture only field names, scalar types, safe booleans, and segment counts. Do not persist or print transcript text.
- Named, content-free validator diagnostics and positive/negative tests at the G9 harness seam.

Invariants:

- 0 GPU, 0 real decoder/provider requests, Mac only, no host access, no tunnel, no shared services.
- No edits to product behavior, capacity bounds, identity constants, provider token minimum, owner isolation, or D45b speaker policy.
- Provider requests remain browser-owned and limited to one finalized Meeting, its prompt, and request parameters (ADR-0011).
- Preserve transcript text only in the short-lived local synthetic browser fixture; never write it to receipts, diagnostics, or status.
- Only this isolated clone may receive repo edits; append receipts to the named pane status file.

Assumptions and unknowns:

- The H1B deployed G9 raw record retains only an aggregate `RuntimeError`; the campaign retains nested session events and stop-wait observations, not the full capacity result.
- The exact capacity sub-check cannot be inferred from a false aggregate alone. Check whether the event reduction has enough retained operands; if not, report each missing aggregate field and add next-run diagnostics without claiming the cause.
- `owner_payloads_only` may compare the browser's normalized payload to raw API segments. The actual provider request, including optional fields, speaker values, and time representation, must be measured before classification.

Falsifiers:

- Payload harness-stale hypothesis is falsified if the actual request violates owner isolation, the required model/stream/token controls, or includes content outside the initiating Meeting.
- Payload product-defect hypothesis is falsified if the local browser request is owner-scoped and its schema differences are intentional presentation of the same finalized transcript under ADR-0011; any stale shape expectation must be corrected only in the harness.
- Capacity root-cause hypothesis is supported only by a named false sub-check computed from the same nested G9 observation. A reconstructed report missing required inputs is inconclusive, not a product diagnosis.

Why each tool changes the decision:

- `_validate_capacity` plus a named reduction report separates a specific capacity predicate failure from an aggregate G9 exception; a comparison control verifies the report against the same-layer G4 artifact.
- The existing local browser probe uses the production frontend and real browser HTTP/TLS shape with a fake local provider; observing its received body distinguishes browser serialization from the harness's expected shape without an external provider call.
- RED/GREEN tests prove the future diagnostic distinguishes valid product payload/capacity from a genuinely invalid control while preserving acceptance semantics.
- The prescribed full backend suite once is the requested regression gate after changes; no real decoder evidence is claimed.

Initial starting point: branch `round6/fix-g9-h1b` at `7f54b12f999cb0da5880c8e13c5ed9ec934e0f76`; runtime import verified inside this clone. Host and decoder requests: 0.

Initial controlled results:

- Local production-browser probe passed 8/8 existing checks and captured 2 loopback fake-provider POSTs. Both used the configured owner model/prompt, `stream=false`, `max_tokens=2048`, and only that synthetic owner's transcript. Compared with the stale harness expectation, actual requests add `response_format` and per-segment `source_lane`; `start`/`end` are floored `HH:MM:SS` strings; `S00` is projected to the D45b display label. Speaker values match after that approved projection. This is harness staleness, not a product privacy defect (ADR-0011; D45b).
- H1B's nested summary-load event reduction gives pre-Stop RTF 0.10845 and 0.09821 (< 1), with no terminal-failure events. Each H1B session retains 60 `text_revision_applied` events without `runtime_monotonic_ns`. The old predicate would reject these rows if the full capacity result reaches its event loop; the deployed G9 artifact does not retain enough inputs to prove this was its first or only failing check. In the exported same-layer G4 PASS control, assigning only a sentinel timestamp or excluding those rows made the complete validator pass, with no other failing checks. `text_revision_applied` is not consumed by the canonical fairness or pre-Stop compute reduction; the live producer does not assign it a runtime clock (ADR-0005 keeps text revisions separate from canonical commits). This proves a stale harness guard on G4, not that G9 product capacity passed.
- The H1B raw G9 record omits the complete nested capacity result. Missing G9 aggregates are requested/observed duration, session/account summary rows, wrong-owner probes, RSS/cache samples, journal counts, backpressure, and campaign interval. The exact first failed G9 sub-check and the D5 capacity invariant therefore remain `POSSIBLE PRODUCT DEFECT / UNMEASURED`.
- Attempts so far: payload repro 2/3; capacity offline replay 3/3 (parked). These are bounded offline/software probes, not decoder requests.

Harness changes: accept the approved D45b speaker projection and browser-owned request parameters; record content-free top-level/segment field paths; allow missing clocks only for `text_revision_applied`; and record named capacity failures in `summary-checks.json`. These changes do not relax owner, model, prompt, token, capacity, or D5 controls. No product code or capacity bound is changed.

Final QA record:

- New G9 diagnostics tests were RED on the pinned base (4 failed), then GREEN with the focused capacity/G9 suites (245 passed, 0 failed). A genuinely wrong owner payload and bad capacity still fail with content-free named reasons.
- The prescribed full suite was invoked once with the required command. The process session expired after progress reached 87%; its terminal summary and exit code were not retained. A separate collect-only pass found 2,416 tests. Full-suite outcome is UNVERIFIED; do not claim green.
- Final bounded attempts after planner steer: payload repro 2/3; capacity offline replay 3/3 (parked). Mac only; 0 GPU, 0 decoder/external provider requests, no host access.

## Planner steer — D5 invariant falsification

See [D5-INVARIANT-REPRO.md](D5-INVARIANT-REPRO.md) for the question, hypotheses, falsifiers, one command, and measured evidence. The H1B receipt is at the pinned candidate SHA and has 19 booleans, 17 true; its diagnostics field is absent. Root cause/disposition:

- `owner_payloads_only`: confirmed stale exact-shape predicate. D5 allows browser-owned request parameters; the published lane contract includes lane context in summary input. The production browser builds the body from the passed completed Meeting and sends it directly. The local stub repro measured only its synthetic owner's transcript and matched model, prompt, `stream=false`, and 2048 token controls; the old predicate rejects `response_format`, `source_lane`, string timestamps, and the D45b `S00` display projection. No D5 product defect was observed. H1B did not retain its actual provider body.
- `speech_capacity_unchanged`: the known timestamp guard is a stale predicate defect demonstrated on G4, but the H1B full capacity result is missing. The final offline replay found 60 untimed revisions/session, RTF 0.1084509/0.0982074 (<1), and zero terminal-failure events; 12 aggregate inputs remain absent. The exact first G9 failed sub-check is UNMEASURED, so preserve possible product capacity defect.
- No product behavior or acceptance bound changed; 0 GPU, 0 decoder/external calls, no host access.
