# Speaker rename and subtitle export

## A — Acknowledged names on every display surface

Pinned design read: LiveTranscribe `4ec41e0a:frontend/src/components/TranscriptPane.tsx`,
`commitSpeakerEditor` and its dialog. Reference content was not checked out or edited.
Its save first renames, then optionally saves a voiceprint.

MOSS already routes both transcript-row labels and legend chips to the naming dialog
for identified speakers with committed speech on the active capture page. The defect
was after successful naming: the component left old labels untouched until polling;
its previous test explicitly expected that stale state.

The response now updates every displayed item with the same canonical speaker ID.
Names remain display data, never identity. A meeting-scoped notification fences and
restarts an in-flight poll so an older response cannot restore the old label. History
refreshes from the persisted record; an open voice bank refreshes too. Other identities,
including people with the same visible name, are unchanged. Existing lifecycle and
S00/provisional-only restrictions remain; this does not add post-stop naming support.

The reachable falsifier is an old name after acknowledgement, including after releasing
an older poll response or reopening history. Tests exercise both click targets, repeated
rows, legend, all existing exports, history reopening, and a held pre-rename poll.
Canonical IDs and text are preserved. Host/operator behavior remains unmeasured.

The optional unchecked Save voiceprint checkbox is deferred: MOSS's naming endpoint
already atomically enrolls or queues enrollment; there is no separate enrollment action.
An unchecked checkbox would promise a behavior the API does not provide. Splitting
that established API behavior is not a cheap UI addition.

A validation: 174 frontend tests passed; typecheck/build passed; 21 built-browser /
preview / locator / upload / geometry checks passed.

## B — SRT and VTT

Both formats are now in the serializer and export menu. Each nonempty turn becomes
one numbered cue with its current display label prefixed to its words. Conversion
rounds total milliseconds before splitting hours/minutes/seconds, so rollover is
correct. SRT uses commas; WebVTT uses dots and a WEBVTT header. A turn shorter than
the one-millisecond output resolution receives a one-millisecond cue. Blank lines
inside text are folded to avoid accidentally ending the cue; markup is escaped to
keep literal transcript words. Empty turns do not produce empty cues.

The formats preserve provisional attribution honestly: SRT marks affected cues;
WebVTT uses a NOTE outside cue payloads. Existing md/txt/json behavior is unchanged.
The acceptance export loop adds SubRip (.srt) and WebVTT (.vtt) in the same commit;
other acceptance selectors are untouched.

Tests cover exact timing/rollover/escaping, empty and provisional exports, every menu
format's download filename, and the acknowledged rename in all five formats.
Additionally, real serializer output was read by local ffprobe: both formats parsed
with cue start 60.000000 seconds and duration 1.123000 seconds for input
59.9996–61.1234 seconds. No host or paid provider used.

Final frontend validation: 182 tests passed across 23 files; typecheck/build passed.
Final Python application validation: 1,283 passed, 2 skipped, 37 subtests passed,
21 warnings, 92.77 seconds. This includes 02045d0c diagnostics and 2935de6a terminal-prompt
fix; their added tests explain the increase from the earlier 1,273 baseline.
