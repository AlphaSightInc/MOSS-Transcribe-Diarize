# Saved-transcript browser rendering probe

**THROWAWAY — prepared, not run.** Do not execute until the root agent confirms shared capacity work has ended.

## Contract

**Structural question:** Can the real built saved-transcript UI render and search the tail of a 201-minute transcript without dropping passages or failing in the browser?

**Minimum primitives:**

- committed `_workspace_html` and `frontend_assets`, served through existing Playwright route fixtures;
- 5/30/201-minute meetings containing exactly 120/720/4,824 passages;
- deterministic public text that brings the 201-minute JSON fixture to the retained 2.03 MB payload scale;
- two alternating people so no adjacent passages can group into a smaller DOM;
- unique final-passage words searched through the product Find control;
- retained fixture JSON, viewport screenshots, exact DOM values, errors, and elapsed times.

**Invariants:** Every source passage becomes one `.utt`; the last passage is in the viewport; its words remain byte-for-text equal before and after search; search reports one match and keeps all rows; no console, page, or request failure is accepted. No decoder, microphone, API server, cookies, authentication state, or product mutation participates.

**Assumptions and unknowns:** The 1,440×900 headless Chrome path represents the supported desktop built UI. Timing acceptability is **unknown** because no latency threshold is authorized; the probe reports raw `load_to_tail_visible_ms` and `search_tail_ms`. Matching the retained JSON byte scale does not estimate real transcript word density or mobile performance.

**Falsifier:** Any wrong row count, missing or changed tail words, failed unique-tail search, invisible final row, browser/request error, or browser crash disproves the 200-minute saved-rendering claim. High latency is retained for explicit human judgment rather than silently called acceptable.

**Tool decision:** Existing Playwright drives Chromium and the real committed bundle. Route fixtures isolate rendering from decoder, persistence, network, and microphone capacity. jsdom and a new package would not answer the browser-rendering question and are not used.

## One command — only after capacity release

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python prototypes/saved-transcript-render/probe.py
```

Default evidence path: `evidence/mvpfix/wp25/saved-transcript-render/`. It must be absent or empty; evidence is never overwritten. Use `--output PATH` for an alternate empty directory.

The command exits nonzero on correctness failure. A zero exit proves the specified browser correctness predicates only; it does not convert raw timing into an acceptance claim.
