# FX-Q5 production port — design contract

## Structural question

How can the live transcript show continuous speaker turns while the underlying segment stream is still revising and settlement may replace provisional identities?

## Minimum primitives

- Ordered transcript segments and their stable source keys: preserve every word and correction target.
- Source lane plus speaker entity: define which adjacent rows can share a visible card.
- Settlement authority on each segment and the session's live label policy: separate provisional presentation from settled identity.
- A card projection with a first-source key: preserve DOM identity through text and label revision.
- Current scroll position plus the Auto-scroll control: follow new text only when the operator asks.

## Invariants

Every source segment appears exactly once in the rendered cards and retains its target key. Same-speaker short-gap rows may join across one short other-lane row; a long interjection cannot be hidden. S00 always has a visible header and cannot be named. Active unsettled system/microphone speech uses Remote/You under L-a unless it has a meaningful durable name. Settled generic speakers receive dense numbers from currently settled identities, not raw first appearance. Search, copy/export, naming, passage correction, G3/G6/G9/G10 selectors, and keyboard access remain functional. No query or environment switch, bound change, decoder request, or data persistence change.

## Assumptions and unknowns

The settlement pane will expose `authority=settled` on effective transcript segments, `live_label_policy`, and `settled_through_samples` as in `dx/combined-harness`; its product branch is not yet merged into freeze-4. Host G10 and decoder-backed Q5 quality remain unmeasured here. The D53 UI branch will be rebased after the Q5 implementation.

## Existing prototype and falsifier

`dx/combined-harness` @ `5bc7ec04` measured a three-row cross-lane example as two cards, preserved all three source rows, kept a long S00 interruption as three cards, and preserved a settled/unsettled boundary within one card. Its first-appearance number map produced gaps (reported as Speaker 1, 2, 4, 7); that policy is rejected for product. Falsifiers: omitted/duplicated text, a missing S00 header, numbering gaps after settlement, unstable card keys after revision, missing acceptance selectors, or Auto-scroll moving while off/searching.

## Tool decision

Port prototype projection to production components; use focused Vitest fixtures to attack grouping, dense numbering, authority transitions, controls, and scroll behavior. Use the clone venv and local loopback/browser tests for production-path checks. Mac G10 comparison may attribute source changes but cannot qualify the host; any real decoder command belongs to the lead.
