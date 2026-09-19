# WP53b-P2 durable batch owner — prototype verdict

Verdict: **SUPPORTED**, prototype only. No production implementation is authorized or made.

Run one command:

```sh
prototypes/durable-batch-owner-p2/run.sh
```

## Structural contract

- Question: can the existing durable File Meeting remain the sole restart owner?
- Minimum primitives: durable meeting identity; canonical owner directory; retained local
  source; immutable checkpoint contract plus contiguous committed prefix; terminal publish.
- Invariants: owner/source/contract must match; resume begins after the committed prefix;
  terminal publication happens once; URL resume reads the retained local source; cancellation
  stops dispatch before durable terminal transition, then removes artifacts.
- Assumption: lifecycle discovery/composition remains unimplemented. SQLite 3.50.4 versus
  required 3.53.4 is an explicit semantic-store-only prototype allowance.
- Falsifier: any violating control decodes or publishes; either positive arm replays a
  committed window, duplicates output, publishes twice, refetches URL input, or leaks artifacts;
  cancellation dispatches past window 40 or removes artifacts before terminalization.
- Tool decision: production `Phase2Store`, `MeetingHandle`, `WindowedRunner`, checkpoint
  records/stitching, and terminal publication measure the actual seams. Deterministic 201-minute
  extraction isolates lifecycle semantics; it does not claim acoustic quality.

## Measured result

- File and URL: 40 committed before restart; 61 new calls, windows 40–100; reopened completed
  surface has 101/101 unique segments; second publication refused; artifacts removed.
- URL resume: retained local source, zero remote refetches.
- Wrong account, meeting, source, inference options, and broken prefix: 5/5 refused before
  decode or publication. Reasons are retained in `results.json`.
- Cancellation: one call at window 40, zero publication, then `interrupted`, then cleanup.

The prototype contests a second durable job owner: meeting plus canonical retained artifacts
is sufficient. A production lifecycle composition decision remains for the lead.
