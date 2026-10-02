# UI3 account-session deletion

1. Question: can a terminal session and its owned audio disappear while saved voiceprints still match?
2. Minimum primitives: account ownership (write boundary), lifecycle (active writer exclusion), session dependents (delete unit), nullable voiceprint source (independent saved identity), inline confirmation (intent).
3. Invariants: no other account mutation; no running work removed; all session rows and canonical audio removed; saved vectors unchanged; UI rollback on failure.
4. Unknowns: filesystem failure is not transactional with SQLite; provider quality and deployed behavior unmeasured. Post-Stop refinement is an active writer despite a completed meeting row.
5. Falsifier: remaining dependent data, lost matching vector, foreign deletion, active-session removal, or late writer resurrecting deleted data.
6. Tools: production-schema probe tests FK order and detach; product regressions test routes/interaction; real Chrome screenshots test actual layout. No provider needed.

Hypothesis: detach only voiceprint_samples.source_meeting_id, delete session children then parent, remove canonical audio before committing rows. Protect recording, File/URL work and post-Stop refinement.

Run: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/ui3/probe.py`

Prototype measured: direct delete blocked by FK = true; remaining sessions after detach/delete = 0; saved vector unchanged = true; source detached = true. Accepted. Product must reproduce detach with a matchable production profile, not merely a blob.

Product reproduction on production base f9d13595: all 9 deletion backend cases pass, including preserved production
voiceprint matching (not just vector storage), three terminal statuses, active Live and File protection, ownership,
repeat-delete 404, disk-failure retention, post-Stop refinement protection and retained File/YouTube staging cleanup.
The 7 frontend cases cover Delete/Cancel/Esc, failure rollback, real total plus search-hidden text, empty history,
automatic panel-open refresh and Live/File/refinement disabled states. Older rename/refresh tests now trigger the
existing refresh event; browser acceptance/geometry/summary probes follow that event instead of the removed button.

Chrome run: `PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/ui3/chrome_check.py`
(after `cd frontend && /opt/homebrew/bin/npm run build`). Real Chrome 154.0.8037.98 on loopback 18986; 3 one-second
synthetic sessions through product frame/Stop routes -> 2 after per-card delete -> 0 after Delete All and reload.
Open transcript empties; Cancel and immediate Esc work. Provider/external calls 0, browser errors 0; server stopped.
Screenshots and JSON: ~/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/ui3/.

Deviation: protect post-Stop refinement, a still-running writer on a completed session; report "Wait for transcript
clean-up to finish." and disable its trash. No resume work included. Filesystem cleanup can partly remove files
before a later disk error; rows remain for retry, but removed files cannot be restored. Provider quality, deployed
behavior and real-device audio remain unmeasured; this feature does not require those to qualify local deletion.

Final gates on f9d13595 + UI3: frontend 585 passed (40 files), typecheck/build passed; full backend 2925 passed,
11 skipped, 2 xfailed, 37 subtests passed in 449.73 s. All nine backend and seven frontend deletion regression cells
were also measured failing against unchanged production f9d13595. Real Chrome check and all four screenshots passed.
The final two-browser test was updated from a generic toolbar-button click to the existing History refresh event;
its original convergence and read-only assertions now pass. Product is locally qualified; deployment unmeasured.
