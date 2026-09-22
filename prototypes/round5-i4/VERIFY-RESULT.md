# D34 fresh-process verification result

**PASS (harness semantics); PARKED_CRITICAL (loopback reachability).**

1. **Custody — PASS.** Branch is `round5/impl-row10`; prescribed Python imports
   `/private/tmp/moss-round5-i4/moss_transcribe_diarize/__init__.py`; diff check
   is clean.
2. **D34 structure — PASS.** The bound is exactly `2.5 + 1.5 + 0.5`, cap is
   exactly five, each attempt uses the fresh-context/durability path, and only
   `workspace_row_10/BEST_EFFORT_FAIL` becomes non-required.
3. **Controls — PASS: 58.** First pass stops the loop; five valid recognition
   misses retain all timing-attribution/meeting-number records and become
   `BEST_EFFORT_FAIL`; a missing bank and ordinary `FAIL` still block. The bundle
   keeps that status and reason visible without failing its aggregate.
4. **Loopback receipt — PARKED_CRITICAL, confirmed.** The final proxy-shaped
   Chrome/stub attempt ended during row-5 seed (before row 10): 76 accepted and
   completed stub requests; 0 real decoder/provider/GPU requests; 0 active/rejected/
   upstream/client-write failures; stack, proxy, and stub listeners closed. It is
   therefore invalid to claim five row-10 loopback attempts or `BEST_EFFORT_FAIL`.

The result is a fresh-process verification, not an independent human/agent review.
