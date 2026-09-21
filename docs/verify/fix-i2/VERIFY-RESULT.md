# Fix I2 verification result

PASS on branch `round4/fix-i2` from base `85aec978`.

- Backend: 2,205 passed, 0 failed, 5 skipped, 2 xfailed, 37 subtests; 216.49 s.
- Frontend: 312/312 passed; TypeScript and Vite build clean.
- Focused I2 controls: 12/12 passed, including the two unchanged review assertions.
- S17 plan-only: 184 planned requests; decoder/provider/network/tunnel calls 0/0/0/0.
- Product diff: only `live_lane_decode.py`, `live_transcript_convergence.py`, and
  `terminal_label_capture.py`; prohibited F1/F2 files unchanged.
- Capture remains passive: off/on/writer-refusal proposal-byte equality passed;
  terminal capture contains no preparer import.
- Secret search and `git diff --check`: clean.

One non-gate focused invocation collected `test_live_lane_decode.py` without the
full suite's `tests/phase2` import path: 113 passed and 2 collection-order import
failures. The mandated full backend population subsequently passed all 2,205 tests.

## H-1 follow-up

- Backend: 2,216 passed, 0 failed, 5 skipped, 2 xfailed, 37 subtests; 373.83 s.
- Focused qualification controls: 60/60 passed; unchanged Claude T5 and promoted
  pane-3.3 S2 pass.
- Loopback controls: 502, 503, timeout, connection reset, retry, duplicate ID,
  missing ID, unowned event, unreconciled counter, and unique owned 2xx.
- Plan-only: S17 184; bundle 2,238; summaries 3 decoder + 6 provider; actual
  decoder/provider/network/tunnel calls 0/0/0/0; long capacity remains required-not-run.
- H-1 diff is harness/tests/docs only; secrets and diff checks clean.

## Lead fresh-context verification (2026-09-21T22:02:06Z)

**Verdict: FAIL.** The implementation behavior passes, but check 2 explicitly
forbids adding any skip/xfail marker under `tests/`; HEAD adds
`@pytest.mark.skipif(not HEAD, reason="I4 accounting exists only on HEAD")` at
`tests/test_qualification_proxy_accounting.py:23`. No repair was made.

- **C1 PASS — scope.** `git diff --stat 85aec978 -- moss_transcribe_diarize`
  names only `live_lane_decode.py` (6 additions),
  `live_transcript_convergence.py` (6 lines changed), and
  `terminal_label_capture.py` (14 additions). All other changed paths are under
  `tools/qualify`, `prototypes/feature-rows`,
  `prototypes/s17-identity-rerun`, `tests`, or `docs` (16 paths total;
  1,271 insertions/44 deletions).
- **C2 FAIL — invariant markers.** COMMON-R4 constants are unchanged: base and
  HEAD retain album admission 2.0, birth 1.0, score 0.35, margin 0.1, live
  limit 2, and terminal poll 0.5; `QUALITY_BOUNDS` is in an unchanged file.
  However, the added `skipif` marker above violates the requested zero-added-
  skip/xfail condition. It is not active because `HEAD = True`, but the marker
  itself is present.
- **C3 PASS — passive capture.** Targeted controls 13/13: proposal bytes are
  equal capture-off/capture-on/writer-refusal; observer has no preparer
  dependency; every row has schema/Meeting/run custody; raw and mapping rows
  retain `source_lane`; normalization-dropped raw spans remain lane-scoped;
  S17 refuses missing owner/lane evidence.
- **C4 PASS — accounting.** Targeted accounting controls 15/15: proxy attempt
  IDs are unique per accepted POST; only owned upstream 2xx complete; 502, 503,
  timeout, connection reset, duplicate client ID, unowned event, and
  unreconciled counters force summaries/default-bundle INCOMPLETE. A missing
  client request ID alone reconciles. Combined focused recipe: 33/33 passed.
- **C5 PASS — production-shaped loopback.** Fresh scratch
  `/tmp/fix-i2-production-shaped.py` used the real `VllmRunner` request path
  (multipart Content-Type plus Authorization; no client ID/row header), a
  `Decoder` row owner, and a loopback fake upstream. All-2xx: attempted 2,
  completed 2, failed 0, distinct attempts 2,
  `accounting_incomplete=false`. One-503: attempted 1, completed 0, failed 1,
  `accounting_incomplete=true`.
- **C6 PASS — zero-call plans.** S17 184; default bundle 2,238;
  summaries 3 decoder/6 provider, cumulative 8/10; actual calls 0/0;
  `capacity_2x1800` remains `REQUIRED-NOT-RUN`.
- **C7 PASS — suites.** Prescribed runtime backend: 2,218 passed, 0 failed,
  5 skipped, exactly 2 Jamie xfailed, 37 subtests, 255.33 s. Frontend 312/312;
  TypeScript and Vite clean. Targeted capture/accounting matrix 28/28 passed.
- **C8 PASS — hygiene/calls.** Secret search empty; `git diff --check
  85aec978` clean; protected F1/F2 product files unchanged. Decoder/provider/
  external-network/tunnel calls: 0/0/0/0; loopback fakes only.

Independent two-axis review: standards PASS. Spec concerns about duplicate
completion count are superseded by the 17:35 rule requiring one attempt ID per
accepted POST; duplicates still force INCOMPLETE. S17 proxy accounting is
conditional ("if it uses the proxy") and is not part of the zero-call plan-only
row. The summaries runner correctly fails INCOMPLETE if row ownership is absent;
the required production-shaped control supplied the owner explicitly.
