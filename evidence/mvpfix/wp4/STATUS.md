# WP4 implementation and acceptance status

Branch: mvpfix/wp4-oracles-n1; base 37979e539f04d4ea740a1a94d021cd3bb894a0e2.
First prototype-only stop was over-applied; user continuation supersedes it.

## Implemented
- Shared ordered lane WER, omission/addition counts, unique-vocabulary retention,
  lexical attribution and lane-unique duplication witness. Both timed/sample shapes.
- G7 predeclared operator phrase; solo operator, solo tab, then overlap protocol;
  final phrase words must belong to a distinct speaker. Existing predicates retained.
- Deterministic live protocol cases in verify_demo_lanes and workspace row 4; nine-key
  frames plus real heartbeat; pre-terminal, terminal and saved/reopened scoring.
- Downloaded md/txt/json/srt/vtt parsed against selected API meeting words/labels and
  available timing precision. Real browser 5/5 pass; corrupt-download control 5/5 fail.
- F6 fixture follows History > Voiceprints; original assertions/clock unchanged.
- File outcomes atomically persist safe failure_code/reason or speechless notice.
  Additive meeting_outcomes table opens existing v2 DBs without rewriting old data.
  Archive-conversion fallback preserved; if conversion and inference both fail,
  transcode_failed explains unsupported/damaged media. Decoder and malformed-output
  failures remain separate. Only existing confirmed-speechless diagnostics allow empty success.
- Browser-like URL User-Agent; 403/404/timeout safe codes, existing acquisition bounds.
- Failure/notice visible in history and selected meeting. Flash Lite suggested first;
  Flash/custom providers preserved; no automatic external-provider opt-in.

## Measurements and limitations
- Corrected prototype: valid corpus 154 reference words, WER 0/0, duplication 0;
  injected copy duplication 5. Legacy lane ownership remains lexical inference.
- File-boundary bench after fix: 7 failures with reasons / 1 speechless success.
- Final pre-reset suites: 805/805 Phase-2 tests, 209/209 frontend tests; typecheck/build pass.
  Fresh verification remains pending: root VERIFY.md.
- Real alternation at mic gain .03: completed, but final WER 11/106 system and 6/48
  mic; pre-terminal 16/106 and 16/48. Final attribution/duplication witnesses 2 each.
  Positive acceptance FAILED; no QUALITY_BOUNDS or identity policy values changed.
- Overlap reached 40-call total cap and was interrupted. Recovered microphone words
  0, WER 1.0; not a valid completed negative control. No calls beyond the cap.
- Initial malformed heartbeat returned 400 before audio; fixed to documented schema.
- Local harness enforces maximum two simultaneous calls, total 40. It uses the
  existing local-only SQLite-pin bypass; not release qualification or deployment.
- Actual browser downloads checked with a zero-decoder-call server after the live run.
- Paid summary check BLOCKED: no key in environment or operator shell files; calls 0.
- No real attended G7 run. No physical echo/voice identity claim from lexical metrics.

## Failed attempts and corrections
- First oracle counted ordinary shared vocabulary: 12 false duplicates. User-directed
  lane-unique predicate fixed it; original evidence retained.
- Initial targeted tests: 10 failures from bootstrap/signature fixtures; corrected.
- Initial G7 tests: four failures from nine-word fixture count for an eight-word phrase.
- First full suite: 791 passed/5 failed. Two G7 fixtures and exact schema table set
  updated; storage fixture now uses an isolated script checkout so the production
  protected-checkout guard does not intentionally cover fake-home test data.
- Second full suite: 803 passed/1 failed. Worktree-local TMPDIR made a Unix socket path
  too long; fixture uses a short relative path, preserving actual socket/lifecycle checks.
- Batch prototype rather than interactive TUI is the retained skill deviation.
- Full rendered-browser UI lane speech capture is still the existing UI smoke check;
  deterministic different-voice lane semantics are a separate protocol check in row 4.
- Required live acceptance is unresolved, not silently replaced with passing unit tests.

No push, merge, GitHub write, shared-service restart or deployment. Only own worktree
changed. Own servers/tunnel stopped. Source code, test logs and count-only evidence
committed; no private transcripts, credentials or audio in git.
