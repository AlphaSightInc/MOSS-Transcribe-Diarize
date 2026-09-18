# Part 0
Phrase prototype: 5/5 intended outcomes; 7/8 in-order accepted, 6/8 and reverse rejected.
Regression suites: 64 passed. Runbook now documents subsequence and disjoint speakers.

WP4 recorded predicates, unchanged QUALITY_BOUNDS:
- pre_terminal: system 16/106 <= .166655; microphone 16/48 > .166655;
  attribution 2, duplication 0. Thus microphone WER and attribution failed.
- final/reopened: system 11/106 and mic 6/48 both > .095074;
  attribution 2 and duplication 2. All four predicates failed.
- file/URL .15 bar: both final lanes pass; pre-terminal both fail. That separate
  contract does not justify silently replacing the existing live quality contract.
- Original retained counts have no segment timestamps: boundary vs interior UNKNOWN.
  Added count-only attribution segment diagnostics and exact switch-straddle tolerance;
  explicit lane identity and inside-window errors remain failures. No numeric time radius.

One authorized rerun: 20/20 decoder requests, then harness cap interrupted capture
(heartbeat/Stop HTTP 409); no completed semantic confirmation. No retry. Existing
54-second alternation needs at least 22 canonical 2.5-second spans before finalization,
so the 20-call budget cannot finish that realtime fixture on this manifest.
Original trace: alternation-run.txt. No claim that attribution was confirmed or fixed.
