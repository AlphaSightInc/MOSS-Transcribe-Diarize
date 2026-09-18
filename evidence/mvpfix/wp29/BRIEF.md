# WP29 — Meetings longer than the tape bound: terminal must stay truthful, not `failed` (MEDIUM-HIGH risk, lifecycle)

Read `COMMON.md` first (full-suite gate). Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp29-tape-exhaustion`
(branch `mvpfix/wp29-tape-exhaustion`, from integrated `integration/mvp-fix-20260917` @ f5fff0b2). No GPU needed (stub decoder); one optional real confirmation ≤60 requests via
tunnel **18129**. Pane: MOSS:3.4. WP22's branch (`…-wt-wp22-memory-longrun`, read-only) holds the finding and the memory-longrun bench.

## Finding (WP22 R1, pre-existing)
When the retained tape reaches `max_tape_bytes` (57.6 MB per tape = 30 min at 16 kHz PCM16, the production-like bound; the local default was 9.6 MB = 5 min), the
exhausted-tape terminal path omits the required `gaps` field and the terminal outcome is reported as **`failed`** — although ADR-0003 D5/D8 define the contract as
truthful partial audio + `unavailable` refinement with the committed transcript intact (WP6 saw exactly that `unavailable` behaviour on the mono base with the 9.6 MB
bound; the per-lane path with three tapes now differs). A 31-minute meeting must not end `failed`.

## Prototype question (LOGIC, stub decoder, accelerated where the runtime allows)
"What exactly happens at and after tape exhaustion on the per-lane build — for the mixed tape and for each lane tape — through Stop: which terminal outcome is
reported, are committed words preserved in the saved transcript, is partial MP3 produced with the correct duration, does the UI show a truthful notice, and does
the session/lease/queue state stay clean?" Use a small isolated manifest bound (e.g. 60 s tape) with the memory-longrun/stop-lease benches to drive 90 s meetings:
cases — exhaustion during capture then normal Stop; exhaustion then client departure; exhaustion on one lane only (mic silent/zero so its tape is small); two
concurrent sessions exhausting. Dump status transitions and the terminal payload (which required fields are missing). Verdict → `NOTES.md`.

## Fix scope
Make the exhausted-tape path produce the documented outcome: terminal `final` (or the existing `unavailable`-refinement outcome) with committed words preserved,
partial audio flagged truthfully, required fields (`gaps`, etc.) populated, per-lane tapes handled consistently, UI notice content-safe. No change to `max_tape_bytes`
values or ADR-0003 policy; regression tests for each case with the stub decoder; full suites; `/new` verification; report. Also record WP22 R2 (post-final RSS not
returning to startup baseline: 616 → 1149 MiB after a 30-min meeting) with one cheap measurement of whether a SECOND meeting on the same process grows further or
reuses (stub decoder, two back-to-back 10-min stub sessions, RSS after each) — fix only if the second meeting grows again and the owner is obvious; otherwise report.
