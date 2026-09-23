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
- H1B's nested summary-load event reduction gives pre-Stop RTF 0.10845 and 0.09821 (< 1), with no terminal-failure events. Before the harness correction, `_validate_capacity` first failed on `text_revision_applied` lacking `runtime_monotonic_ns`; each H1B session retains 60 such events. In the exported same-layer G4 PASS control, assigning only a sentinel timestamp or excluding those rows made the complete validator pass, with no other failing checks. `text_revision_applied` is a transcript-revision fact that is not consumed by the canonical fairness or pre-Stop compute reduction; the live producer does not assign it a runtime clock (ADR-0005 keeps text revisions separate from canonical commits). This is a stale harness guard.
- The H1B raw G9 record still omits the complete nested capacity result, so the G9 event reduction alone cannot prove that this was its only failed capacity check. Missing aggregates are requested/observed duration, session/account summary rows, wrong-owner probes, RSS/cache samples, journal counts, backpressure, and campaign interval. The updated validator reports the exact failing check on the next run; the current bit is classified `HARNESS GUARD IDENTIFIED; H1B exclusive causality UNMEASURED`.
- Attempts so far: payload repro 1/3; capacity offline replay 2/3. These are bounded offline/software probes, not decoder requests.

Harness changes in progress: accept the approved D45b speaker projection and the current browser payload shape under ADR-0011; record content-free top-level/segment field paths; allow missing clocks only for `text_revision_applied`; and record named capacity failures in `summary-checks.json`. No product code or capacity bound is changed.

Final QA record:

- New G9 diagnostics tests were RED on the pinned base (4 failed), then GREEN with the focused capacity/G9 suites (245 passed, 0 failed). A genuinely wrong owner payload and bad capacity still fail with content-free named reasons.
- The prescribed full suite was invoked once with the required command. The process session expired after progress reached 87%; its terminal summary and exit code were not retained. A separate collect-only pass found 2,416 tests. Full-suite outcome is UNVERIFIED; do not claim green.
- Final bounded attempts: payload repro 1/3; capacity offline replay 2/3. Mac only; 0 GPU, 0 decoder/external provider requests, no host access.
