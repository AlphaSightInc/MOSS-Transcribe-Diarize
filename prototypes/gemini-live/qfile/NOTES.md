# Q-FILE qualification runner

Structural question: do completed Gemini File meetings preserve speaker-attributed timing and saved-audio enrollment on the exact public Q-FILE population?

Minimum primitives: a fixed worktree SHA, one loopback Account server, the registered public clip and reference, the saved HTTP Meeting transcript, the specified scorer, and the post-completion naming response. Remove any one and the result cannot attribute quality or enrollment to a real product run.

Invariants: send only `common/corpus.py` accept6 and long60 audio; use `h1_offline.score_case` for accept6 final DER and `common/score.py` for long60; record every selected clip, including failures; derive full gate verdict only from all seven clips; stop the server on every exit.

Assumptions and unknowns: File Meeting responses may expose no provider usage cost. In that case cost is `null` and `UNMEASURED`; audio duration is not a billing receipt. Long60 has a complete reference in the registered corpus. The dry run measures runner plumbing on one clip, not the seven-clip gate.

Falsifier: any selected clip fails to reach a saved completed Meeting, scores above its bound, or cannot enroll a named speaker. A scorer mismatch or missing corpus input stops before provider send.

Tool decisions: HTTPS loopback is required to exercise the real Account API. The frozen H1 scorer is imported to retain its exact denominator. The production scorer handles long60. A single public 60 s clip dry run can reveal launch, upload, scoring, or enrollment defects while staying under the $0.10 dry-run bound. The full seven-clip run waits for the lead's exact integration SHA.

Dry-run verdict (2026-09-29): preflight of the first scratch path found a 113-byte Unix control socket path, so server startup refused before any provider send. The runner now rejects that path before launch. With a 97-byte path, 1/1 public 60 s Keyu Jin File upload completed in 8.051 s to terminal and 12.058 s through naming, with 4 saved rows, 2 speakers, H1 final DER 0.036667, and enrollment `enrolled` from 43.1 s of that speaker's rows. The real API exposes no File usage cost, recorded `UNMEASURED`. This is a plumbing verdict for 1/7 Q-FILE cases; macro and long60 gates remain `UNMEASURED`. Evidence: `evidence/P66/wp3/qfile-dryrun/qfile.json`.
