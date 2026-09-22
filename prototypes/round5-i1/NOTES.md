# D31 production L1 gate — harness-only implementation

**Structural question.** Can the production `verify_demo_lanes` L1 gate observe
the final spoken tail at the D31 paused-live boundary—capture still active and
before Stop—using the production HTTP frame path and public snapshot/events
facts, rather than interpreting Stop as an endpoint?

**Minimum primitives.** Real lane frames and Stop through the existing HTTP
capture loop; production `LiveServiceRuntime`/`LiveCoordinator`/endpoint/mixer
composition; a browser-shaped silent tail; public snapshot and event polling;
and numeric/enum receipt retention. Removing any one either changes the
product path or makes the observation boundary unverifiable.

**Invariants.** No product behavior, decoder, scheduler, thresholds, endpoint
geometry, nine-key protocol, reference, scorer, or request budget changes.
Silence frames retain the stream sequence, capture timestamp, and heartbeats.
The five-second wait is a harness timeout only.

**Assumptions / unknowns.** The loopback stub can drive canonical completion
without decoder traffic. Exact live-decoder tail latency is not measured here;
the stub's decoder-call count estimates added requests only.

**Falsifier.** With browser-shaped trailing silence, either arm reaches no
settled active pre-Stop snapshot within five seconds, its tail is absent from
that snapshot, or its span ends by `stop_flush`; any result falsifies this
harness boundary. The no-silence violating control must instead preserve the
old `stop_flush`/missing-pre-tail behavior.

**Why these tools change the decision.** The production e2e harness exercises
the real HTTP/capture/Stop composition; the local loopback stub exposes the
same HTTP decoder shape without spending decoder requests; retention tests
prove the decision facts survive qualification output; the full suite detects
unintended harness integration changes.
