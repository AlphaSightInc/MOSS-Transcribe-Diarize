# P75-ES durable text edit

1. Structural question: does a user edit of one settled passage survive later publication and restart?
2. Minimum primitives: owner authority (who may write), stable passage ID (what changes), durable document
   (the shared reading source), first original (audit of the correction), version (reader refresh).
3. Invariants: preserve other passages, speaker IDs/names, start/end and audio; keep first original;
   advance version; remove obsolete words; block active/running refinement before mutation.
4. Assumptions/unknowns: production live/file documents currently store passage text/start/end, no words.
   Real provider and browser behavior unmeasured; no provider calls needed for a durable correction.
5. Falsifier: a late production publication overwrites a simulated settled edit, or restart loses it.
6. Tool decision: use real SQLite/store publication methods, synthetic passages and injected SQL edit to
   measure existing publisher guards before product implementation. Failure requires a publication guard.

Hypothesis: active-only normal commits plus running-marker-only refinement prohibit late overwrite;
text edits must check the running marker inside the same store mutation.

One command (from worktree root):
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/long-meeting/p75-es/probe.py`

Verdict: PASS on base f9d13595: 3/3 late publisher methods rejected; 1/1 restart retained edit.
Existing publication guards suffice. Add running-marker check in the edit transaction; preserve
manual text on read (legacy automatic join-space cleanup must skip edited passages). Full state printed by probe; evidence retained outside the repo under P75/ES.

Product replay: same command with `--product` uses `MeetingHandle.edit_passage_text` rather than injected SQL.
Measured 3/3 late publishers blocked, 1/1 restart retained edit, matching base prototype.
Regression matrix: `tests/phase2/test_passage_text_edit.py`, 25 failed on f9d13595; 25 pass on product.
Existing passage correction and saved-reading tests: 34/34 pass; combined 59/59.
Design verdict recorded in `docs/design-gemini-live.md`, P75 E1 section.
Retained probe is throwaway measurement code; not a product runtime component.
Full backend: 2943 passed, 9 skipped, 2 xfailed, 37 subtests passed (428.68s).
Gate correction: one pre-existing geometry selector changed URL -> YouTube to match base f9d13595;
all geometry assertions retained. Baseline reproduction and both gate runs are preserved in evidence.
