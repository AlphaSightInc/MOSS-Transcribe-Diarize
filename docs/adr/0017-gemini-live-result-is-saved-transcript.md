# ADR-0017: Gemini live result is the saved transcript by default

- Status: **Draft** (2026-09-29). The lead owns the final decision after Q-IND.
- Deciders: product owner and round-2 lead.

## Structural question

Can the Gemini engine save the speaker-attributed result already shown at Stop, or must it
transcribe the whole recording again? The choice affects final speaker quality, the wait
after Stop, and provider spend. The self-hosted MOSS engine has a separate identity model.

## Minimum primitives and invariants

- **Live surface:** the versioned transcript committed by rolling Gemini windows. It is
  the word and speaker evidence the user has already seen.
- **Stop drain:** one last window covers the accepted suffix. Later windows repair
  speaker-less committed rows; a remaining row may use a saved-audio fingerprint only
  when its best existing speaker cosine is at least .46. Otherwise it stays unattributed.
- **Final revision:** after Stop, the drained effective live surface is saved as the
  authoritative final transcript. The user's `cleanup_after_stop=true` setting instead
  runs the existing whole-recording terminal pass.

Every accepted sample remains accounted for, the live words and labels are preserved in
the default final revision, and saved voiceprint observations remain available. Speaker
guesses shown on provisional text never enter the saved transcript. This decision is
specific to the Gemini engine. ADR-0002's retrospective sweep requirement remains
binding for the self-hosted MOSS engine.

## Evidence and assumptions

P2's retained, complete-reference comparison found accept6 diarization error rate
(DER) .0994 live versus .1049 after clean-up across six clips, two runs each; long60
DER .0495 live versus .0344 after clean-up. E1 had four labels at Stop in both modes.
The terminal pass cost about 7% of provider spend and added roughly one minute of wait
per 10–15 minutes of recording. These receipts predate the round-2 default schedule and
F13 repair: `evidence/P65/p2-cleanup-skip.md`.

The P4 cached-window prototype's fingerprint veto (cosine threshold .46, margin .20)
repaired six of six observed identity collapses and did not raise DER in its passing
controls; `prototypes/gemini-live/guard/NOTES.md`. P5 rejected 60-second context:
with the veto, long60 still had DER .174 and E1 had five IDs; 90 seconds is the
shortest offered context; `prototypes/gemini-live/schedule/NOTES.md`.

Generality beyond the measured voice pair, independent meetings under the round-2
code, and the final outcome of Q-IND are **unmeasured**. These receipts support the
implementation and a candidate default; they do not by themselves qualify the product.

## Decision and falsifier

For Gemini meetings, default `cleanup_after_stop` to false. Offer true per meeting.
MOSS meetings ignore this setting and retain ADR-0002's path.

Q-IND is the decision gate: on every independent meeting with a complete reference,
live-only must show at most true speaker count +1 ID and DER no more than clean-up-ON
DER + .03. The lead compares accept6 ×6, bench5m lex ×3, Bill30m, long60, and gold9
calibration clips. Any failure is escalated to the product owner with the case table;
the default is not silently reversed. The gate and owned qualification run are in
`docs/plan-gemini-live-r2.md` §2 and §5.

The cached P2/P4/P5 receipts were reused because they test the specific cost and
identity mechanisms without new provider calls. Q-IND requires fresh product-path
measurement because it can change the default decision.
