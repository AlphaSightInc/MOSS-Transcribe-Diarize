# P74-RC browser recovery bench

1. Structural question: can the originating tab recover the same active recording with its original media choices and server clock, while a duplicated/replaced page remains a reader?
2. Minimum primitives: a tab record identifies capture intent/settings; server cursors identify accepted audio; page identity fences writers; silent lanes account for unavailable sources; separate gap metadata preserves missing time without making speech.
3. Invariants: one meeting and writer; increasing lane sequence/epoch and heartbeat order; both timestamps offset; exact microphone constraint/no substitution; 120 s expiry never reopens; interruption lines excluded from speech/summaries.
4. Unknowns: physical microphone continuity, ordinary Chrome display picker behavior and provider recovery. Lead R1 resolves immediate reload with retry_after_ms/about 500 ms automatic retry, bounded to 8 s after load, while media opens in parallel. Lead R2 lists only completed capture_interruptions with adjacent sample_rate in the live snapshot session and saved transcript document.
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

Chrome receipts retain failed chooser/harness runs and the pre-R1 refusal. The R1 baseline
received retry_after_ms=2926 but never retried and emitted no frames. Updated protocol emits
R2 metadata only for completed gaps. Gestureless display refusal is injected because Chrome's
chooser automation bypasses that native requirement; native picker behavior stays unmeasured.

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

**PASS locally under lead R1/R2.** Real Chrome 154.0.8037.98: immediate microphone reload
resumes in 3.048 s, tab + microphone in 3.050 s, zero clicks, 32/32 accepted frames each,
7 same-page-id automatic requests each. Acquisition activation is false. One share click
restores non-silent system frames. Live gap lines render separately; scripted saved documents
retain both completed gaps with sample_rate=16000. Eligible return after 3.2 s away retains
14/14 accepted frames each, first in 0.594/0.596 s, zero clicks. 125 s virtual expiry stops;
duplicate retries 17 times over 8 s, sends no frames, becomes a viewer, original continues.
Receipt: evidence/P74/resume-client/chrome-20261002-145513/result.json and screenshots.

Prior immediate-reload baseline failure (retry_after_ms=2926, no retry/no frames) is retained.
The two corrected fixture failures are retained: unchanged snapshot: null, and the baseline
no-speech saved transcript: null. The fake seam injects R2's gap-only saved document; this
measures browser consumption/formatting, not production-server persistence. Open gaps are
excluded from the wire list. Server integration, physical devices, native human display picker,
provider and summary behavior remain unmeasured. All local servers stopped. Final full-suite
results, product size, local commits and commands are in P74-RC-STATUS.md.
