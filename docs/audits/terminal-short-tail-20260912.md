# Terminal short-tail repair — 2026-09-12

## F1 — Reproduced mechanism

Round 11 at c70a96e2 retained four overload failures: session ordinals 7/8 in both
layers, condition `unparseable_text`, wrapped `EmptyTranscriptionError`, window 1
[120.0,120.5), refusal null. Each accepted/accounted 1,928,000 samples and closed,
but finalization failed. Source: `/tmp/moss-round11-stage/result/report.md` (MacStudio-local (not in repo)), F6.

The 150-second window / 120-second stride planner creates starts while start is
less than tape duration. At 120.5 seconds, window 0 already reads [0,120.5), but
window 1 redundantly reads [120,120.5). A failed decode of that redundant half-second
window invalidates the entire terminal result. This is a planner/empty-result
classification defect, not an identity or quality-bound decision.

Before the repair, the focused reproduction had five failures: redundant plans at
120.5/240.5, the actual terminal-finalizer path on a 120.5-second tape, and malformed
silence at .5/2 seconds. The one-second boundary and malformed-speech controls passed.
The decoder is controlled; PCM speech detection, WAV extraction, window runner,
complete tape and terminal finalizer are production implementations. No host replay
or new model-quality claim is made.

## F2 — Smallest sufficient repair and invariants

Primitives: bounded decode interval, its uniquely owned interval, decoded text,
and existing PCM speech evidence. A sub-second final window already fully covered
by its predecessor is removed; ownership extends to the tape end. Its audio is
still decoded by the predecessor. Diagnostics retain `short_tail_window_merged`,
tail coordinates and the receiving window. With the shipped overlapping geometry:

| Tape | Before decode windows | After decode windows |
|---|---|---|
| 120.5 s | [0,120.5), [120,120.5) | [0,120.5) |
| 240.5 s | [0,150), [120,240.5), [240,240.5) | [0,150), [120,240.5) |
| 121 s | [0,121), [120,121) | unchanged |

No window exceeds 150 seconds. No PCM is dropped, no ownership gap/duplicate is
introduced, and the existing identity resolver and terminal publication fencing
are unchanged. The six quality corpus durations and 600-second capacity geometry
are unaffected. Checkpoint resume retains tail words once and reproduces diagnostics.
Uncovered tails in other injected geometries are not silently discarded or extended
beyond the configured window bound.

Both typed `UNPARSEABLE_TEXT` and raw malformed output now use the **existing**
speechless check, retaining `unparseable_speechless` plus PCM/VAD counts and no
response text. Its mode 0 / 20 ms / .0001 fraction threshold is unchanged. Malformed
real speech, including a .5-second utterance, stays a failure. Missing VAD or unreadable
PCM also stays a failure. Short duration alone does **not** authorize discarding speech.

## F3 — What the one-second floor means

The model processor accepts any nonempty audio; there is no documented hard
one-second model input minimum. Its default audio representation is 12.5 tokens/s
(`processing_moss_transcribe_diarize.py`); .5 seconds supplies about seven audio
positions, one second about thirteen. Combined with the observed .5-second failure,
1.0 seconds is a conservative operational floor for **redundant tail planning**,
not a newly measured universal minimum for accurate transcription. Valid short
speech is still kept, and ambiguous short speech is never automatically excused.
The floor does not alter live canonical/rolling scheduling or identity admission.

The falsifiers are tested directly: an isolated sub-second tail still dispatched;
a tail word missing/duplicated; an input exceeding the existing window bound;
malformed real speech accepted; unavailable speech evidence accepted; or resumed
checkpoints losing the condition. The malformed-silence test deliberately replaces
the previous policy test that required silence to fail solely because formatting
was malformed. Numeric quality bounds, _validate_quality and identity policy are untouched.

## Validation

Focused window/speechless/terminal-finalizer suite: **81 passed + 19 subtests**.
Full Python: **1,532 passed + 37 subtests, 22 expected skips** (20 browser, two
unprovisioned corpus tests), 0 failures. Run with an empty Playwright browser path
and the scratch-only system-browser discovery shim used in the prior preflight.
All 24 required files and all required named cases pass the acceptance denominator
check, with no missing/failed/skipped required case. Frontend: **202 passed**.
No frontend changes or rebuild. Raw logs: `/tmp/moss-short-tail-python.log` (MacStudio-local (not in repo)),
`/tmp/moss-short-tail-python.xml` (MacStudio-local (not in repo)), `/tmp/moss-short-tail-frontend.log` (MacStudio-local (not in repo)).

After rebase onto peer `1dab0bb8`, full Python rerun again passed **1,532 + 37
subtests**, 22 expected skips; all required coverage remains green. Rebased logs:
`/tmp/moss-short-tail-rebased.log` (MacStudio-local (not in repo)), `/tmp/moss-short-tail-rebased.xml` (MacStudio-local (not in repo)).
