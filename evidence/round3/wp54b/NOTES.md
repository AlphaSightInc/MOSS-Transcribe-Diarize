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

Deterministic pre-spend verdict: **SUPPORTED**, `7 passed in 0.02 s`.
Decoder use at this verdict: **0/200**.
