# WP20 — lane-local endpoint experiment (in progress)

Q1: which overlap-dependent stage damages immediate/final text?
P1: admitted lane PCM (content), endpoint interval (context), decoder response
(recognition), published surface (selection), reference words (truth). Each is
necessary to distinguish a boundary error from a decoder or publication error.
I1: same WebRTC mode/config, 40000-sample hard cap, mixed recording/accounting,
identity/readiness/lifecycle/quality/protocol untouched. No production changes.
U1: mixed endpoint damage, rolling replacement, and full-tape silence context are
hypotheses, not established causes. Exact word-level reference timing unavailable.
F1: no clear canonical win, any final worsening, contract change, or queue/Stop
regression disqualifies promotion. A shadow replay cannot certify scheduling.
T1: trace actual accepted PCM and production decoders; replay the same intervals
alone, then change only endpoint ownership. Full-reference captures score WER;
24/48-second arbitrary cuts have no exact reference and use differential counts.
Do not infer partial references by proportion or call decoder text ground truth.

One-command capture (isolated stack required):
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/streaming-diarization/wp20/capture.py`
Shadow endpoint policies run on the admitted source bytes with separate production
WebRTC providers. Scripted state output replaces interactive TUI for repeatability.
Audio/raw public transcripts remain ignored in runs/wp20. Persisted counts are
measurement evidence, not a prototype database dependency.

## Verdict — 2026-09-18

REJECT promotion: full-reference overlap boundaries identical for both lanes,
canonical WER unchanged at system 18/106 and microphone 9/53. Alternation mic
improves 11/53 ->9/53, insufficient and unrelated to the overlap claim. Shadow
experiment absorbed into the standing bench as replay/instrumentation helpers;
no prototype hook is imported by production. No production implementation added.
Full evidence, per-stage table, falsifiers and limits: evidence/mvpfix/wp20/NOTES.md.
The hypothesis test is complete; local scheduler/timing admission not attempted
following the explicit no-win stop. No word-aligned per-span truth was available.
