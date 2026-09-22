# I4b — media-source fresh-context prototype

## Structural question

Can the real workspace harness replace its browser context after row 5 while
recreating the separate system-audio source page, without turning a row-10
attempt into a Playwright exception that prevents row 8?

## Minimum primitives

1. One isolated local stack whose only decoder upstream is the loopback P2
   SSE stub; it proves transport shape without authorising decoder dispatch.
2. The unmodified workspace command shape from `tools/qualify/run.py:597-612`:
   `verify_workspace.py` with the real corpus and Chromium media-source tab.
3. A prototype-only wrapper around `_fresh_row10_context` that records the raw
   Playwright message outside the harness result; the harness result itself
   continues to retain only the exception class.
4. Rows `4` (which invokes 5), `10`, and `8` in that order. A missing stub
   enrollment name is a valid row-10 outcome, but row 10 must not throw and row
   8 must receive the meeting created by row 10.

## Invariants

- Product code, decoder endpoint geometry, and production evidence sanitization
  do not change.
- Chromium opens a real `source.html` audio page and uses the existing harness
  capture/Stop/close paths; no media API is replaced.
- The only decoder process is the loopback P2 stub, which emits token usage.
  Real decoder/provider/GPU requests remain exactly zero.
- Raw error text is retained only under this throwaway prototype; row JSON stays
  class-only.

## Assumptions and unknowns

- The P2 transcript may not create `E2E Rowan`; therefore `bank_missing_name`
  is permitted and does not establish recognition latency.
- Loopback exercises harness control flow, not real decoder quality or timing.

## Falsifier

The harness fix is falsified if the prototype records a raw fresh-context
Playwright error, row 10 has an `exception`, or row 8 lacks the second-live
meeting after the ordered run.

## Tool decision and command

`run.py` starts the same local-stack command used by the bundle, invokes the
actual workspace verifier with the media source enabled, and writes all observed
row state plus an optional raw Playwright message:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  prototypes/round5-i4b/run.py --loopback --out /private/tmp/i4b-run
```

## Verdict

`SUPPORTED` for the harness control flow; not a decoder-quality qualification.

The unmodified harness reproduced the bundle failure with the P2 usage-emitting
stub and real Chromium. The prototype-only raw capture retained the exact
Playwright text that the row JSON correctly reduces to `Error`:

```text
Page.evaluate: TypeError: Failed to execute 'fetch' on 'Window': Failed to parse URL from /api/meetings/hovDjIASFArF4Dt1cg1vqOXc
    at eval (eval at evaluate (:311:30), <anonymous>:1:28)
    at UtilityScript.evaluate (<anonymous>:318:18)
    at UtilityScript.<anonymous> (<anonymous>:1:44)
```

The replacement context created its workspace page at `about:blank`; the
next durability fetch was relative, so Chromium rejected it before a row-10
capture began. The harness now calls `open()` after recreating the media source
and before durability. The focused lead-shaped GREEN receipt at
`/private/tmp/moss-i4b-focused-green/summary.json` records: row 5 PASS; row 10
non-throwing `bank_missing_name` after one attempt; and row 8 PASS on the
row-10 meeting. It completed 115 loopback requests and zero real decoder,
provider, or GPU requests. Stub transcript quality remains unmeasured.
