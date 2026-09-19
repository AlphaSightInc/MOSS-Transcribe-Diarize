# Attended publication and correction check

**Outcome:** measure the integrated candidate’s physical capture and saved-result truth. This guide has not been run. It grants no deployment, microphone, acoustic-quality, or release claim.

## A1 — Freeze the candidate

- Use ordinary Chrome on the microphone host. Open the local product route `https://127.0.0.1:7861` only after the engineer records the integrated commit and confirms that exact commit is served there.
- Stop if Chrome shows a certificate warning, the runtime/commit cannot be tied to the candidate, or another origin/port is substituted. Do not use a certificate exception.
- Record Chrome/macOS versions; microphone and output-device names; fixed microphone position, system input gain, output volume, and room; selected shared tab/screen; candidate commit; start/end wall times.
- Use a public spoken clip with an exact transcript. Keep raw recordings, transcripts, cookies, and screenshots private.

## A2 — Actual product settings

Run H first, then S. Do not change gain, microphone position, clip, or volume between them.

| Run | Product **Listening setup** | Requested microphone constraints | Output route |
|---|---|---|---|
| H | **Headphones** | echo cancellation off; noise suppression off; automatic gain control off | Headphones |
| S | **Speakers** | echo cancellation on; noise suppression off; automatic gain control off | Physical speakers |

For each run: click **Enable microphone**, allow the intended device, click **Share audio**, choose the meeting tab with **Share tab audio** enabled, and verify both product meters move before **Start capture** becomes enabled. Record the browser-reported track settings if the evidence collector exposes them; requested settings alone are not proof that Chrome honored them.

## A3 — Fixed speech reference

Use two consenting people. Read each line once at natural pace, without paraphrase:

- P1: “Amber kites drift past nine silver towers.” — 8 ordered words.
- P2: “Copper lanterns glow beside four quiet harbors.” — 8 ordered words.

In each run, collect the same sequence: P1 alone; P2 alone; public clip alone; P1 and clip together; P2 interrupts P1 once; then ten seconds of ordinary alternating conversation. Mark the source-clock start/end of every scripted region. Do not replay recordings as a substitute for attendance.

## A4 — Saved-result and correction journey

1. During capture, confirm microphone/system lane badges are truthful and identity is visibly provisional. Passage reassignment must not be offered while automatic processing is active.
2. Click **Stop** once. Wait for saved settlement; do not reload or start another capture while Stop is draining. Record Stop→saved duration and any notice.
3. Reopen the saved meeting from History. Compare every scripted phrase and lane against the references. If unresolved speech exists, it must keep its words and display **Speaker uncertain** plus **Needs review**.
4. Select one settled passage and **Reassign passage → New person**. Enter `Attended P2`. Confirm only the selected passage changes.
5. Select a different settled passage and reassign it to an **Existing person**. Unknown values must not appear in that list. Confirm the first correction and all unrelated words remain unchanged.
6. Reload and reopen. Export Markdown, text, JSON, SRT, and VTT. Each format must agree with the reopened speaker labels and carry the review notice while any uncertainty or partial-processing notice remains.
7. Compare Voiceprints before/after. Passage reassignment must add none; the dialog must never offer voiceprint enrollment.

Record exact segment IDs, before/after labels, transcript versions, word strings, review state, voiceprint counts, HTTP status for both correction requests, and all five exported files.

## A5 — Interruption boundary

In a separate short run, after both meters and some words are visible, close the capture tab or use the documented abort path. Reopen History and record whether the partial meeting, committed words, audio state, and interruption/refinement notice survive. **Do not resume the same meeting.** Use **Reset capture**, then start a new recording with a new meeting ID. Failure to preserve the partial result or creation of a same-meeting resume path fails this check.

## A6 — Stop conditions and verdict

Stop immediately and retain the first state; do not silently retry if any of these occurs:

- candidate/origin/TLS identity is uncertain;
- either meter stays silent, the wrong device is selected, or tab audio was not shared;
- a lane dies, transport/backpressure/terminal error appears, Stop does not settle, or saved/reopened text differs;
- words disappear when identity is uncertain, an active edit succeeds, correction changes an unselected passage, exports disagree, or a voiceprint appears;
- speakers mode does not actually request echo cancellation, or actual settings contradict the requested route.

Report H and S separately as PASS, FAIL, or BLOCKED with the exact failed predicate. A headphones pass cannot substitute for speakers plus echo cancellation. Stub/browser tests and a successful API response cannot substitute for listening to and source-checking the physical recording.
