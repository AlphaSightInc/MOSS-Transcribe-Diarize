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
