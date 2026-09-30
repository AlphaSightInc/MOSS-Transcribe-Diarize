# ADR-0017: Gemini saves the live result at Stop; clean-up improves it in the background

- Status: **Accepted** (2026-09-29; user decisions D20 = clean-up ON, asynchronous, and D21 = Balanced default).
- Deciders: product owner and round-2 lead.

## Structural question

Can the Gemini engine save the speaker-attributed result already shown at Stop, or must it
transcribe the whole recording again? The choice affects final speaker quality, the wait
after Stop, and provider spend. The self-hosted MOSS engine has a separate identity model.

## Minimum primitives and invariants

- **Live surface:** the versioned transcript committed by rolling Gemini windows. It is
  the word and speaker evidence the user has already seen.
- **Stop drain:** the browser may stop waiting while a separate server task drains
  for up to 60 s. If rolling coverage still misses accepted audio, the terminal
  transcriber reads only that uncovered tail. A failed tail recovery saves the
  meeting as incomplete/needs review; it never marks the partial transcript final.
  Later windows repair
  speaker-less committed rows; a remaining row may use a saved-audio fingerprint only
  when its best existing speaker cosine is at least .46. Otherwise it stays unattributed.
- **Orphan resolution:** before a Gemini live-only final revision, a canonical ID with
  under 2 s total committed speech is removed unless the user manually named it.
  Its rows use a same-lane established speaker only at cosine ≥ .46; otherwise their
  words remain with Speaker TBD. A public E1 0.2 s stray had best witness cosine .3083
  and therefore supports abstention (`prototypes/streaming-diarization/orphan-stop/NOTES.md`).
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

For Gemini meetings the drained live surface is saved as the authoritative transcript **at Stop**, so the meeting is
immediately usable (browse, rename, voiceprints, summaries, History, a new meeting). `cleanup_after_stop` now **defaults to
true** and runs the whole-recording terminal pass **in the background**; on success it commits an improved version mapped to the
live speaker IDs with the speaker labels current at commit time. While it runs, transcript export, audio export and passage
corrections are disabled (server 409 `refinement_running`); a durable running marker makes a restart keep the live version with a
notice. Setting it false keeps the live result only. MOSS meetings ignore the setting and retain ADR-0002's path.

Q-IND (plan §2 R-A1) was the decision gate and **failed**, which is why the default moved to ON: 10/14 paired cases passed; the four
failures (3 independent — the two Adam cases share byte-identical audio) were long60 .175 vs .034, Adam .140 vs .026, and Lex/Shapiro
.062 vs .017 (partial reference); RTFL crosstalk was the one case where live-only was better (.226 vs .302). Receipts:
`evidence/P66/qual-f962d97d/{qind.json,scorecard.md}`. Live identity also varies between runs because Gemini 3.5 Transcribe is not
deterministic on byte-identical requests (only 28/60 long60 windows matched; `prototypes/gemini-live/live-divergence/NOTES.md`), so
the background whole-recording pass is the retrospective correction for the Gemini engine.

The cached P2/P4/P5 receipts were reused because they test the specific cost and
identity mechanisms without new provider calls. Q-IND requires fresh product-path
measurement because it can change the default decision.

**2026-09-29 amendment (round 3, Q4):** the clean-up pass uses the meeting's own user key,
held only in memory. A restart therefore cannot resume it; the durable running marker
keeps the live version, as above. OpenAI-compatible meetings never run clean-up.
