# WP54b source-word visibility instrument

Prototype gate: round-2 semantics verdict `SUPPORTED`; no semantic re-prototype.
The headed arm is new and may run only after deterministic fixtures pass.

Structural question: when did each independently referenced word first appear
correctly and remain correct on the API and rendered transcript surfaces?

Minimum primitives: ordered reference-word ID, source interval end, ordered
transcript observation, and surface-local elapsed time. IDs keep repeated words
distinct; interval ends establish the source frontier; ordered observations
preserve revisions; separate clocks avoid cross-host subtraction.

Invariants: every reference word stays in the denominator; wrong/deleted words
retain null first/stable times; API, DOM, and server decoder/queue clocks remain
separate; no latency threshold is introduced; frontend source is untouched.

Assumptions/unknowns: interval end is the honest existing source granularity,
not an invented word-level alignment. Hidden-tab behavior remains UNMEASURED
unless headed Chrome actually reports `document.hidden === true`.

Falsifier: any wrong/omitted word receives a finite time, a finite population
p95 is produced after dropping nulls, or bucket coverage is accepted as
visible-word evidence.

Tool decision: exact ordered Levenshtein alignment reuses
`lane_word_oracle.distance`; a headed Playwright harness observes existing
`.utt-text` nodes and live API states and retains content-free server events.

Deterministic pre-spend verdict: **SUPPORTED**, initially `7 passed in 0.02 s`.
Decoder use at this verdict: **0/200**.

Headed verdict: **INCOMPLETE / receipt rejected**. One 300-second headed
Chromium session used 165/200 requests, peak one in flight, with 916 reference
words, 150 API state changes, 138 DOM state changes, and 586 visibility
observations. Chrome reported hidden zero times, so hidden-tab behavior is
UNMEASURED. The session reported `closed` while finalization still reported
`running`; no terminal event was retained. More importantly, the first flat
ordered implementation allowed repeated words to align across non-overlapping
source intervals, producing a minimum near -293 seconds. Those are not valid
final visible-word latencies. The receipt is retained as a falsifying attempt,
not evidence. No rerun is possible inside the remaining 35-request budget.

Post-falsifier correction: matching now requires observed and independently
authored source intervals to overlap, while retaining the existing ordered word
score separately. A new repeated-word violating control keeps the late
occurrence missing. Deterministic suite: **8 passed in 0.02 s**. The headed
harness now also waits for terminal finalization, but is unmeasured after this
correction.
