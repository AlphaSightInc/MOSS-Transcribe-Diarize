# P74-RC browser recovery bench

1. Structural question: can the originating tab recover the same active recording with its original media choices and server clock, while a duplicated/replaced page remains a reader?
2. Minimum primitives: a tab record identifies capture intent/settings; server cursors identify accepted audio; page identity fences writers; silent lanes account for unavailable sources; separate gap metadata preserves missing time without making speech.
3. Invariants: one meeting and writer; increasing lane sequence/epoch and heartbeat order; both timestamps offset; exact microphone constraint/no substitution; 120 s expiry never reopens; interruption lines excluded from speech/summaries.
4. Unknowns: physical microphone continuity, ordinary Chrome display picker behavior and provider recovery. Contract conflict: automatic takeover refuses <3 s heartbeat age, which also rejects ordinary immediate reload. Product follows refusal -> viewer, so zero-click G2 cannot pass in that case without a lead contract ruling.
5. Falsifier: a required gate fails, duplicate steals living capture, expiry reopens, offsets regress, missing media blocks continued capture.
6. Tool decision: unit tests isolate state/headers/UI/timeline; real Chrome measures actual AudioContext/worklet/media behavior; scripted backend and prototype protocol replace providers at existing seams. Fake protocol measures client only and cannot qualify server integration.

One command (from worktree root):
`../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/long-meeting/resume-client/browser_probe.py`

Full state and screenshot receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-client/`.
Product changes are frontend only. Everything in this bench is throwaway. No keys or provider/network service calls; local HTTPS only on 18986.

Measured regression: same-speaker grouping previously combined speech on both sides of a gap,
placing the marker after the combined row. Both turn grouping and card projection now break at
interruption boundaries. The transcript UI regression failed on the prior code and passes on
the candidate; exports keep markers separate and chronological, including hours >= 1.

Chrome receipts retain failed chooser/harness runs. The binding living-page veto refuses
immediate reload in both source cases; eligible same-tab navigation after 3.2 s away resumes
with zero clicks and first accepted frames in approximately 0.6 s. Gestureless display refusal
is injected because Chrome's chooser automation bypasses that native requirement. This is
an explicit fixture limit, not evidence that stock Chrome permits/refuses the automatic picker.

Strict automatic-media check: no Playwright JS evaluation/polling during the first 4 s after
load. This removes synthetic transient activation. The initial product order awaited
AudioContext.resume before getUserMedia and hung; the prototype acquired the microphone
first. A red regression records that dependency. Candidate now acquires the exact stream
before starting its clock; silent graphs may attach suspended and expose missing-source
recovery, and a replacement live stream starts the clock. Earlier activation-assisted
receipts remain separate and are not proof of native automatic microphone restoration.
The one-command bench builds its own bundle under evidence; never stages product assets.

Lost-response recovery follows the prototype's measured idempotent repeat: retry the same
old-to-new page pair once for a lost/timeout response, never create another meeting/writer.
An explicit "Resume recording here" click uses the contract-supported null expected id
so an uncertain earlier response cannot trap the operator behind a stale compare-and-swap.
Automatic resume keeps the recorded expected id and the living-page veto unchanged.

## Verdict

**BLOCKED on the binding immediate-reload contract, candidate implemented.** Strict Chrome
154.0.8037.98 now acquires media with activation false after the autoplay-order correction.
Eligible return after 3.2 s away: microphone-only first frame 0.598 s, both sources 0.591 s,
14/14 frames each, zero clicks, same meeting. One share click restores non-silent system
frames. Immediate reload in both cases receives capture_page_alive and sends 0 frames until
explicit takeover; this is a measured failure of the zero-click gate, not scored as a pass.
125 s virtual expiry refuses resume and takes the stopped path. Duplicated tab remains a
viewer while the original writer continues. Local server stopped; all prior failures retained.
Full suites and final receipt pointers live in P74-RC-STATUS.md; the lead must decide the
3 s veto/reload conflict and integrate the server candidate before any shipment claim.
