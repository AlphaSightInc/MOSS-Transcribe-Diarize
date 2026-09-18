# Independent live source lanes (WP1)

Question: does serial decoding preserve each source's words and speakers through
Stop and saving, without changing mixed-audio endpointing or lifecycle authority?

The minimum primitives are an admitted audio interval, its two aligned source
waveforms, a lane-local identity store, and a revision's ownership interval.
Source waveforms cannot be recovered from a summed recording. Identity evidence
must therefore use the producing waveform and only that lane's speaker candidates.
Public speaker IDs still come from one monotonically growing meeting allocator.

Invariants: system and microphone identities never reconcile across lanes; zero
or declared-silent source spans never reach ASR; requests remain serial; mixed PCM
owns recording, endpointing and accounting. Segments order by start, system before
microphone, then end. Only different source lanes may overlap in revisions.
Legacy AudioFrame callers without source PCM retain the mono path. No quality,
identity, readiness, frame-wire or lifecycle threshold changes.

## Implementation and failure boundaries

`live_transport` admits the unchanged nine-key frames; `live_mixer` adds aligned
PCM16 and all-silent facts to the internal AudioFrame. `live_coordinator` retains
lane audio, captures immutable work, and commits lane ownership only after session
acceptance. `live_lane_decode` composes serial decoding and lane identity evidence.
The existing process-scoped canonical scheduler and arbiter remain unchanged.
The provider bundle shares its encoder but forks albums/sweepers per source.

Canonical preview still publishes decoded text before identity preparation.
Draft, rolling and terminal producers decode each nonzero source separately.
Rolling advances only successful lane frontiers; a failed lane retains its full
committed segment even when that segment crosses the healthy lane's frontier.
The existing stop-on-refinement-failure behavior applies per lane. Terminal
failure retains that lane's prior surface while a healthy lane can finalize.
Revision identity reads lane voice evidence without mutating causal albums;
unknown identity keeps words unattributed. Timestamp overlap never assigns lane
identity. `live_session` validates and publishes the composed surface.

Mixed and two lane tapes each retain at most the existing configured capacity B:
retained tape bytes <= 3B. The 80,000-byte-cap test measures 240,000 total bytes,
capacity degradation and release. Canonical source buffers obey the existing
accepted/uncommitted sample bound R; four buffers (mixed, analysis, two sources)
retain <= 8R bytes before slice/copy overhead. Existing rolling storage and
transient extraction/encoder arrays remain additional; process peak RSS unmeasured.
The terminal reader processes sources serially and releases all tapes afterward.

`phase2_audio` still records mixed PCM. Saved source-lane schema/export/UI changes
belong to WP2. This branch measures saved lane attribution through exact ordered
saved/final text-and-speaker correspondence, not native persisted lane provenance.

## Measured decision

The throwaway real-stack experiment and its versions are retained in git history;
its implementation is absorbed into production. Run the bench with
`bash prototypes/lane-decode-proto/experiment.sh <case>` (real decoder budget
required), or `python prototypes/lane-decode-proto/failure_state.py` (no provider).
See the adjacent bench NOTES and evidence/mvpfix/wp1 for exact counts and failures.
The reachable falsifiers are erased lane words/speakers at terminal replacement,
same voice collapsing across lanes, non-speech lane hallucinations, or saved/final
mismatch. The resumed prototype passed all named falsifier cases before absorption.
Tests attack these same boundaries and provider/lifecycle failure seams.

Ordered edit distance uses each lane's full supplied reference and concatenated
saved transcript, as instructed. Omissions include unplayed reference audio;
these are not exact-cut word-error rates. No numeric accuracy acceptance threshold
is inferred from the passing architectural falsifiers. Fixed-build ladder coverage
is bounded by the cumulative 650-request authorization; omissions are reported.
