# Published transcript lane consumers

A segment has time, words, speaker identity, and optional `source_lane` (`system` or
`microphone`). Lane is origin, not person identity: the same person can have a
separate speaker ID on each lane, and both may eventually share a voiceprint/name.
An absent lane means a legacy document, not an inferred microphone/system label.

Order is committed before provisional, then start, then system before microphone,
then end. The draft tail stays below committed text. Legacy-only documents
retain provisional-last, then start/end order. If mixed, untagged segments follow tagged ones on tied starts.
Turn composition never crosses lane or speaker identity, even with identical names.
Time overlap never establishes identity. No-id row keys include lane and speaker.

The schema-v2 SQLite store already persists JSON documents without projecting fields.
No SQL migration or stored-document rewrite is needed for this optional field.
Meeting parsing, history-to-transcript projection, normalized rows, turns, exports,
and provider-body construction preserve it. Published lane-tagged effective segments
are consumed directly by the live browser; the legacy text grammar has no lane field.

Display uses one chronological column and a lane badge beside the speaker. A name
click/enrollment still targets the canonical speaker ID; lane is not an enrollment
uniqueness constraint. Markdown/text/subtitles show the resolved speaker label only;
JSON carries `source_lane` separately and uses the same undecorated `speaker_label`.
Legacy output has no lane decoration. SRT/VTT keep separate
speaker-labelled overlapping cues without clipping or shifting either interval.
Summary input uses chronological segments with speaker display labels and lane context.
No provider call is required to validate body construction.

Evidence: `evidence/mvpfix/wp2/NOTES.md`, corpus fixtures and consumer probe. Nine public
corpus segments exercise four IDs, two lanes, tied starts and genuine cross-lane
overlap; five legacy segments exercise absence. Three UI alternatives were compared
at 390/400/1280 px; chronological rows preserve mobile width and one reading order.
This consumer evidence does not qualify WP1's producer, real subtitle players,
voiceprint recognition, or deployed live operation.


## WP11 export label reconciliation

The speaker display name (or existing ID fallback) remains the export label. Lane
is a namespace, represented by the UI badge and JSON `source_lane`, not by changing
the name. This supersedes WP2's export decoration chosen to match its UI option A;
WP2 recorded no additional user-facing requirement for decorated export labels.
Text/subtitle formats deliberately omit lane metadata; JSON retains it separately.
The independent export oracle projects identical labels and verifies JSON lane
metadata as well as words, identity and represented times. Overlapping cues remain
separate, without time shifts. Evidence: `evidence/mvpfix/wp11/NOTES.md`.
