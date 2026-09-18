# WP26 literal fresh-context verification

Run only after actual `/new` in MOSS:3.1. A fresh shell alone is insufficient.
First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp26-unassigned-terminal`.
Branch `mvpfix/wp26-unassigned-terminal`, base `625dbaa97b55fb5be66e06db9bfe4d8c985fd935`.
Modify nothing outside this worktree. No push/merge/deploy/GitHub, shared services,
new decoder requests or messages to peers. No tunnel needed; own reserved port 18126.

Read in order:
1. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/COMMON.md`
2. `/Users/gao/Documents/Codex/2026-09-17/new-realtime-voice-chat-2/briefs/WP26-unassigned-terminal.md`
3. `evidence/mvpfix/wp26/NOTES.md` and `prototypes/streaming-diarization/wp26/NOTES.md`.

Question: does cropped acoustic fallback recover terminal local labels that lose
the one-to-one mapping, preserving all existing mapped words and lane identities?
Primitives: terminal segment, lane-owned causal identity, overlap mapping, crop.
Invariants: no policy/threshold/bounds/sentinel/frame/lifecycle changes; existing
assigned mappings remain authoritative; failed acoustic probes remain unattributed.
Unknown: new live Stop latency and arbitrary multi-voice accuracy. P5 remains open.
Falsifiers: either Lex crop does not map to speaker-0004; cross-lane identity;
changed words/timing; probe skipped on the three-label/two-voice regression;
unexpected suite failure; policy drift. Any such failure needs diagnosis, not
weakened assertions. Replays measure the actual preparer/encoder and fallback;
runtime vectors and original raw terminal labels were not retained.

Check clean branch/import identity before execution; stop for unexpected edits.
Inspect `git diff 625dbaa9 -- moss_transcribe_diarize/app/live_lane_decode.py tests/test_live_lane_decode.py docs/design-streaming-diarization.md`.
Production diff should only extend cropped fallback to `speaker is None`, update
its reason/docstring/comments. Tests add two conflict-recovery/abstention cases.

Execute literally from this worktree:

```bash
bash prototypes/streaming-diarization/wp26/verify.sh
```

This runs the ENTIRE Python suite, full frontend suite, typecheck/build, production
real-encoder replay, complete saved-store census and audit, whitespace/asset checks
and own-port cleanup check. Logs: `evidence/mvpfix/wp26/fresh/`.
The shared dependency symlink already exists; do not install packages. Test-only
socket/temp redirection keeps fixtures within this worktree. If the script fails,
retain that log before rerunning corrected checks; explain the failure exactly.

Expected: Python 1912 passed / 2 corpus skips / 37 subtests; frontend 249 passed /
28 files; typecheck/build pass with unchanged generated assets. Replay: both Lex
crops recovered, 16 words / 4.86 s, 54 existing assignments unchanged; all 56 system
rows preserve words/times/lane. Saved census: accepted WP12 2/127 unnamed segments
in 1/3 sessions; WP17 0/212 in 0/27 sessions; historical controls 64/476 in 2/19.
The census is BEFORE this fix; it is not an expected post-fix defect count.
Audit PASS; decoder calls 0/400; no owned listener/process remains.

P5 evidence is historical mixed-waveform content loss, not same-tab conferencing
or a new live test: parity emits 184 words with source-unique retention 35/54 and
39/41; quieter second source 1/41. Do not label these WER or speaker accuracy.

Write `docs/verify/wp26/VERIFY-RESULT.md` with actual counts, pass/fail, replay
provenance limits, P5, any deviations. Commit fresh evidence and result locally.
Final report in this pane <=60 lines: branch/SHA, prototype verdict, changed files,
exact test/measurement counts, remaining limits and deviations. No early final
report or claim that an ordinary shell constituted `/new`.
