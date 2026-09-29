# Stop tail deadline prototype

Structural question: does the browser's short Stop wait constrain the server's own
finalization drain and allow a missing accepted tail to be marked final?

Primitives: accepted frontier, rolling frontier, one Stop task, browser wait deadline,
server drain deadline, terminal fallback. Invariant: `final` means every accepted sample
reached a successful rolling or terminal-tail decode; an unresolved tail is incomplete.

Hypothesis/falsifier: a 10 ms browser wait with a 50 ms tail decoder currently leaves
the accepted second without words while reporting final. The fixed behavior returns
pending, continues decoding server-side, then finalizes with both rows.

One command from the WP1 worktree, with no provider access:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/stop-tail/probe.py
```

The first raw script invocation resolved the shared venv's installed package rather than WP1; discard that result. The WP1 red tests confirmed the defect: the 10 ms request prevented the 50 ms drain from completing, and the session finalized without the tail. With an independent 60 s server drain, the corrected WP1 script returned pending to the browser, then saved both `first` and `tail` with `finalization_status=final`. Separate tests cover terminal-tail recovery and an unavailable outcome when recovery fails.
