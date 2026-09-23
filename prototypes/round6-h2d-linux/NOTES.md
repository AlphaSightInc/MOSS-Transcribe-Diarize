# H2-D diagnosis

- Structural question: which H1 failures reflect production behavior, which reflect assertions or host-specific tools?
- Minimum primitives: frozen host observations/XML, production acceptance validator and probes, focused tests, Linux Docker Python 3.12, pinned macOS runtime.
- Invariants: preserve acceptance bounds/populations, source ownership, committed transcript and partial-audio truth, and zero decoder requests.
- Assumptions/unknowns: H1 observations are from frozen f7fe4adc; Linux ffmpeg and filesystem behavior may differ; host concurrency is absent locally.
- Falsifier: replaying each receipt through the frozen validator does not reproduce its reported failure, or the Linux tests do not fail for the same assertion.
- Tool decisions: XML and observations identify exact failed fields; focused tests exercise the production seam; Docker distinguishes Linux from macOS; full backend and bundle detect collateral changes.

## Verdict and measured controls

- H1 deployed G3: 1/1 producer PASS; `lost_commits=1` and `durable_document_mismatches=1` fail validation. Audio bytes/metadata match, resumed capture is 0, and the row is interrupted.
- H1 G6: 1/1 producer PASS in each layer; `transcript_unchanged=false` alone fails validation. Both have partial playable audio, late frame 409, and the queued item discarded without processing.
- Production store control: active and interrupted snapshots retain version 1 and one segment; terminal presentation changes unknown speaker `S00` to `Speaker uncertain`; literal document equality becomes false. The H1 receipts do not contain before/after versions, so this is a proven mechanism, not proof that the host lost no words. The producer fix compares exact transcript/version after product terminal presentation; changed words/version still fail. Host rerun decides whether this fully resolves G3/G6.
- Host Linux XML: 8 duration assertions (`60084` versus `60000`), 4 missing `F_GETPATH`, 1 retained prefix. Docker RED reproduced the first 12 (12 failed, 4 passed). Docker directory order selected window 0, so retained RED came from host XML; direct production control with two records showed deleting window 0 refused, deleting last accepted. The correction explicitly selects window 0.
- Docker and macOS focused GREEN: 16/16 for Linux-only tests; G3/G6 producer tests RED 14/52 then GREEN 53/53 including a changed-content/version control. The MP3 decoded sample count is exactly 960000 while Ubuntu FFprobe container duration is 60084 ms.
- 0 real decoder requests, no host access, no acceptance bound or population change.
