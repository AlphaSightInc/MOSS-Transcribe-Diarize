# Next-span canonical text preview

D2 implemented on isolated `fix/canonical-preview-20260911`, based on production
`887e76a0`. D1/D3 remain decided: identity policy unchanged, no new merging,
accumulation, sub-chunk ASR, or channel-specific behavior. No host operations.

## Contract

Question: can already-decoded words reach the browser before identity completes,
without changing canonical ordering or leaving duplicate text?
Primitives: one frozen audio span, its decoded text, the committed audio prefix,
the runtime publication lock, and the reader's provisional rows. The span bounds
what may be previewed; the prefix and lifecycle authorize it; the lock makes that
check atomic with publication; identity remains a separate canonical operation.
Invariants: preserve words when identity is uncertain; claim no speaker linkage
from preview; use no future identity evidence; remove fully committed preview rows;
refuse late publication after abort. Unknown: attended word-to-screen latency gain.
Falsifier: words remain hidden during held identity, a future span becomes visible,
after-abort decode publishes, another session sees the preview, or a committed span
leaves duplicate rows. Tools: existing peer prototype establishes the design seam;
barrier-controlled runtime/HTTP tests and actual source/built readers test integration.

## Implementation

- `LiveCoordinator.prepare_work_item` optionally hands already-decoded text to the
  runtime before its existing identity-preparation call. It performs no session
  publication itself. No second decode; empty outcomes retain their existing path.
- `_publish_canonical_preview` acquires the runtime's existing lock, checks terminal
  failure, active/closing lifecycle, epoch, next pending span ID, and equality of
  span start with committed_samples. Only that span's bounded text is published,
  using the existing unattributed renderer (S00). Segment boundaries remain intact;
  S00 is absence of identity, not a claim that speakers are the same person.
- The existing publication observer is notified through a `canonical_preview` event
  with span/sample identifiers, no text in the event. This matters: Phase-2 HTTP
  reads its owner-bound published projection, not arbitrary raw runtime mutations.
- Identity preparation and atomic canonical submission retain their original order.
  Normal commit clears the server preview and advances committed_samples.
- The poller now reads that existing committed_samples field and drops retained
  preview rows fully covered by the audio prefix. Text equality or containment is
  not used: multiple segments or an empty commit both retire covered preview.
  Failed/aborted/closed sessions do not retain stale preview rows. Active missing
  previews ahead of the committed prefix retain the existing stale indication.
- Bundled app.js and source map rebuilt from source; no CSS/layout changes.

## Verification

`tests/phase2/test_canonical_preview.py` holds identity after decoding and reads
actual owner-bound HTTP snapshots. Those snapshots pass through the real TypeScript
poller/signal reducer. The normal-commit arm also serves the rebuilt app in Chromium:
exactly one provisional row becomes exactly one confirmed row. The served source
map contains the current poller source verbatim.

Other arms cover identity failure preserving S00 words, Stop entering its drain
while identity is held, abort during identity, and decode finishing after abort.
Two meeting IDs verify no preview leaks to the untouched session. Tests assert
publication owns the runtime lock, one decode per previewed span, and no identity
or committed-prefix advance while identity is held. Stop's final audio tail is a
second legitimate span, not a preview duplicate.

Runtime boundary tests refuse wrong epoch, future pending span and wrong prefix,
keep two local-speaker segments separately as S00, and refuse publication after abort.
Reader tests cover one/two/zero committed segments, missing preview without a commit,
and terminal clearing. Two confirmed speakers retain distinct entity IDs.

Validation results recorded below after completion. No current production latency
claim follows: this removes identity work from the text dependency, not audio
accumulation, decoder, queue, network or polling delay.

## Broader collection limits

An unrestricted repository-root pytest collection includes archived prototypes:
`l15` rejects production drift from its frozen 9089b332 pin; that same failure was
reproduced on unchanged production 887e76a0. Two `l2-stage0` tests require an ignored
local acquired_alphabet/harness_cache.npz absent from this isolated checkout.
Neither frozen evidence nor tests were weakened to turn those into passes.

Final validation:

- `.venv/bin/python -m pytest -q tests`: 1,259 passed, 2 skipped,
  37 subtests passed. No application test failures.
- `npm test -- --reporter=dot` in frontend: 163 passed, 21 files.
- `npm run typecheck` and `npm run build`: passed.
- Five HTTP/source-reader scenarios (including built-browser parity) rerun after
  adding explicit decode-count assertions: 5 passed.
- `git diff --check`: clean. Identity policy modules and acceptance bounds/validator
  unchanged from 887e76a0. No deployment, production-branch update or host operation.
