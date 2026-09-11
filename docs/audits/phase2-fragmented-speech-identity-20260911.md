# Fragmented speech: identity admission mechanism

Code baseline: 7104afc7. Verdict: repeated speaker births are permitted within one
session when independently embedded fragments fail similarity matching. A pause
itself does not reset identity. Whether the operator's voice actually produced
those scores is UNMEASURED. No production or policy changes; no host operations.

## Investigation contract

Structural question: can pause-separated speech repeatedly create identities while
continuous speech builds one stable reference?
Minimum primitives: endpoint spans bound each observation; decoder-local speaker
intervals select its audio; the encoder supplies a vector; matching chooses an
existing identity; birth and album admission have distinct duration floors; the
session retains references and a sweep can revisit assignments. None substitutes
for another: speech duration alone does not establish voice similarity.
Invariants: keep 2.0/1.0-second admission/birth and 0.35/0.1 score/margin unchanged;
never treat injected vectors as measurements of a real speaker.
Unknowns: operator span boundaries, decoded local groups, retained durations,
embeddings, match scores and reference histories. Host configuration not inspected.
Falsifier: identity resets solely on silence, or the production matcher births on
margin ambiguity, would refute this trace. Real fragmented speech consistently
matching above the threshold would reject low-similarity births for that recording.
Tool decision: inspect production boundaries and execute controlled vectors through
its provider/preparer to distinguish temporal resets from evidence-dependent births.
No decoder is required for that conditional mechanism; acoustic causality needs
fresh production embeddings and actual live-path intervals.

## Findings

**F1 — Gap changes the observation boundary, not the identity bank.**
`app/live_endpoint.py:146` closes a speech span when observed silence reaches the
maximum of configured minimum silence and post-speech padding. A shorter pause
need not close it; hard-cap boundaries can still split continuous speech. Endpoint
speech-state reset is not a session identity reset. `app/live_provider_bundle.py:601`
reconciles the previous committed reference before scoring the next span; neither
matching nor album retention has a pause-expiry clock.

**F2 — There is a provisional interval between birth and enrollment.**
Production provider (`live_provider_bundle.py:675`) defers unmatched births below
1.0 second of retained local-speaker evidence. At 1.0 through less than 2.0 seconds,
a new identity may be created but has only a provisional reference. At 2.0 seconds,
the observation qualifies for the admitted reference bank. These are retained
transcript-interval durations, not wall time or a guarantee of clean voiced audio.
Each interval must first clear min_segment_samples; with 8000 samples at 16 kHz,
intervals below 0.5 seconds are dropped individually. Surviving intervals of the
same local speaker within ONE span have their durations summed. Separate spans do
not pool their durations to reach either floor (`live_provider_bundle.py:1047`).
The encoder embeds each surviving interval separately and averages its normalized
vectors (`speaker_identity.py:596`), rather than embedding 50 seconds of accumulated
session audio.

**F3 — Low similarity births; insufficient margin abstains.**
For one decoded local speaker, a score below 0.35 against every existing reference
leaves it unmatched (`live_identity.py:307`). With at least 1.0 second of evidence,
preparation then births another canonical speaker (`live_identity.py:127`). Thus:
1. First 1.2-second observation births speaker 1, provisionally.
2. Next 1.2-second observation scoring 0.30 against speaker 1 births speaker 2.
3. Another such observation scoring below 0.35 against BOTH births speaker 3.
This is a conditional score example, not observed microphone evidence.
Conversely, 0.60 and 0.55 against two references fails the 0.1 margin and abstains
for the whole span; it does NOT birth speaker 3. With one local and one canonical
speaker, the runner-up defaults to zero, so any passing 0.35 score also clears 0.1.
Below-1-second unmatched fragments remain unattributed; short matched fragments
can still receive an existing label. No rule says every short utterance births.

**F4 — Repeated fragments need not improve the reference.**
`live_identity_album.py:201` keeps the longest provisional observation, retaining
the incumbent on equal duration; it does not average or accumulate short turns.
Three matching 1.2-second turns therefore still leave zero admitted exemplars,
despite 3.6 seconds total. A successfully assigned >=2-second observation replaces
the provisional vector outright. Once admitted evidence exists, short observations
cannot overwrite it. Longer duration is the selection proxy; there is no check here
that a longer provisional observation is acoustically cleaner.
Continuous speech gives repeated opportunities to admit longer observations and
build a duration-weighted reference centroid. It is NOT one 50-second embedding:
with the 2.5-second live span cap used by this project's bench, the monologue is
also split. Continuous speech is not guaranteed to match or to supply >=2 seconds
of retained evidence in every span. The proposed asymmetry is opportunity for
stronger references, not a special monologue mode.

**F5 — Later correction does not guarantee rescue.**
The sweep reuses existing vectors; it does not re-embed joined fragments. Its
normal cadence is 60 seconds of meeting time (triggered by a later span), plus
session-end finalization. It cannot be relied upon to repair a split within the
first few seconds. Canonical merges require admitted banks on BOTH sides and the
existing 0.70 merge threshold (`live_identity_sweep.py:611`). Provisional-only
identities cannot merge. Historical labels can still be reassigned when evidence
supports it; 'cannot merge' does not mean 'can never relabel'. No new values proposed.

**F6 — Decoder-local grouping is another unmeasured input.**
The preparer trusts local speaker groups in each span and maps them one-to-one.
At cold start, multiple local groups can each birth if each clears the birth floor;
it does not compare these groups to each other to discover that they are one voice.
Later, competition for one existing identity may instead cause whole-span
abstention. Therefore three displayed speakers does not, by itself, prove three
low-score inter-span births. Actual local groups and assignment diagnostics matter.

## Local verification

`tests/test_live_identity_fragment_mechanism.py` runs the actual evidence provider,
preparer and album with a scripted encoder and controlled pre-segmented transcripts.
It models accepted snapshot succession, not a full capture/endpoint/decoder replay.
Sweeper omitted in this causal-birth test; existing sweep tests run separately.
Identical inputs repeated with 0, 0.6 and 10-second gaps give identical outcomes:

| Three observations | Controlled cosine geometry | Identities | Admitted exemplars |
|---|---|---:|---:|
| 1.2 s each | identical vectors | 1 | 0 |
| 1.2 s each | mutually orthogonal vectors | 3 | 0 |
| 0.8 s each | mutually orthogonal vectors | 0 | 0 |
| 2.2 s each | identical vectors | 1 | 3 |

These vectors deliberately isolate the decision; they are not claimed to represent
one human voice. Changing the gaps does not simulate acoustic effects of a pause.
Command:

```sh
.venv/bin/python -m pytest -q tests/test_live_identity_fragment_mechanism.py tests/test_live_identity.py tests/test_live_identity_album.py tests/test_live_provider_bundle.py tests/test_live_identity_sweep.py
```

144 passed, including 12 new controlled cases. This verifies the permitted mechanism,
not real-speaker fragmentation accuracy or a deployed qualification result.

## Decision

Keep policy unchanged. Before attributing the operator complaint to weak short
embeddings, measure the operator recording's per-span local groups, retained speech
durations, cosine scores against each then-current reference, birth/abstention
outcomes and provisional/admitted state. Fresh acoustic evidence must establish
whether the same voice crosses below 0.35; duration and three visible labels alone
cannot. A matched continuous/fragmented recording comparison would distinguish
reference-support effects from microphone/channel effects. No such measurement
was performed or substituted with reference-derived labels here.
