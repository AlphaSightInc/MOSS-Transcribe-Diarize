# Published transcript lane consumers

A segment has time, words, speaker identity, and optional `source_lane` (`system` or
`microphone`). Lane is origin, not person identity: the same person can have a
separate speaker ID on each lane, and both may eventually share a voiceprint/name.
An absent lane means a legacy document, not an inferred microphone/system label.

Order is start, then system before microphone, then end. Legacy-only documents
retain start/end order. If mixed, untagged segments follow tagged ones on tied starts.
Turn composition never crosses lane or speaker identity, even with identical names.
Time overlap never establishes identity. No-id row keys include lane and speaker.

The schema-v2 SQLite store already persists JSON documents without projecting fields.
No SQL migration or stored-document rewrite is needed for this optional field.
Meeting parsing, history-to-transcript projection, normalized rows, turns, exports,
and provider-body construction preserve it. Published lane-tagged effective segments
are consumed directly by the live browser; the legacy text grammar has no lane field.

Display uses one chronological column and a lane badge beside the speaker. A name
click/enrollment still targets the canonical speaker ID; lane is not an enrollment
uniqueness constraint. Markdown/text/subtitles append the lane beside the name;
JSON carries `source_lane`; legacy output has no lane decoration. SRT/VTT keep separate
speaker-labelled overlapping cues without clipping or shifting either interval.
Summary input uses chronological segments with speaker display labels and lane context.
No provider call is required to validate body construction.

Evidence: `evidence/mvpfix/wp2/NOTES.md`, corpus fixtures and consumer probe. Nine public
corpus segments exercise four IDs, two lanes, tied starts and genuine cross-lane
overlap; five legacy segments exercise absence. Three UI alternatives were compared
at 390/400/1280 px; chronological rows preserve mobile width and one reading order.
This consumer evidence does not qualify WP1's producer, real subtitle players,
voiceprint recognition, or deployed live operation.
