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
