# Provider-aware queue-depth floor search

## Question

For a fresh configured `WebRtcSpeechProvider` and `EndpointPolicy`, what is the
maximum number of canonical work items one client frame can require when every
complete WebRTC VAD observation may be speech or silence?

## Command

```sh
.venv/bin/python evidence/phase1/y5-guardrail-and-floor/probe_queue_depth_floor.py \
  --frame-samples 40000 --vad-frame-samples 160 \
  --min-speech-samples 160 --min-silence-samples 320 \
  --hard-cap-samples 1600 --search-worst-case \
  --json-output evidence/phase1/y5-guardrail-and-floor/iteration-04-vad-worst-case.json
```

## Verdict — 2026-08-17

The aggressive geometry has 250 VAD decisions per 40,000-sample frame. The
probe runs both Boolean outcomes through the production `EndpointPolicy` and
merges only endpoint states with identical future behavior, so it exactly
evaluates all `2^250` patterns without sampling them. Its `100`-repeating
witness requires 166 frame spans; replay through the production WebRTC adapter
reproduces 166. The Stop tail is one span. A queue of 165 therefore cannot
admit this fresh frame.

This is not yet a configuration-time floor: it starts a fresh provider and
endpoint policy, as the original one-frame measurement asked. A loader guard
must first account for every legitimate pre-frame coordinator/provider state
and prove the chosen bound on `preview_frame_work_items`; parsing this probe is
not evidence that such a guard is correct.

## Reachable-state extension — 2026-08-17

Iteration 5 added `--search-reachable-worst-case`. It represents the real
WebRTC carry rule at every possible split of a VAD frame, uses cached calls to
the production `EndpointPolicy`, and replays a finished witness through the
production `LiveCoordinator.preview_frame_work_items` path. The 160-sample toy
geometry finishes and its direct preview replay agrees at one work item
(`iteration-05-reachable-toy.json`).

The aggressive 40,000-sample all-state search did not finish within three
30-second measurement intervals, so it produced no floor. Its design is a
re-runnable probe, not evidence that 166 is sufficient across prior state.
`iteration-05-reachable-search.txt` records the exact commands and the next
required reduction: progress/state-count evidence or a proven dominance rule.

## Rejected split-point reduction — 2026-08-17

Iteration 6 tested direct enumeration of a source VAD frame's 160 possible
split points. Though that transition set is equivalent, it postpones merging
until the VAD-frame boundary and creates the cross product of all starting
states and split positions. It did not finish even the one-VAD-frame toy
geometry, while the retained sample-at-a-time algorithm does. The experiment
was reverted; see `iteration-06-split-enumeration.txt`. Any future reduction
must retain the per-sample merge point, or first add bounded state-count
progress to that existing algorithm.

## Bounded reachable-search progress — 2026-08-17

Iteration 7 added `--reachable-progress-output`, an atomically replaced JSON
snapshot written every 16 sample transitions by the retained sample-at-a-time
algorithm. It records only horizon/frame/sample position, merged-state counts,
and transition-cache counts; it never serializes mutable policy state or
changes the search transition/merge rule. A small run completes with
`status=reachable_boundary_complete` and matches the existing one-work-item
preview result (`iteration-07-reachable-toy.json` and
`iteration-07-reachable-progress-toy.json`).

The re-runnable aggressive command was deliberately terminated after 15
seconds. Its durable snapshot records 90,161 equivalent boundary states after
3 of the 12 required VAD-frame horizon, with 230,721 cached production-policy
transitions (`iteration-07-reachable-progress-aggressive-15s.json`). It did
not emit a final all-state result, so it is progress evidence only and does
not establish a queue-depth floor. The next reduction must preserve the
existing per-sample merge point and be proved equivalent before it can support
the config-load guard.

## Active-candidate canonicalization — 2026-08-17

Iteration 8 retained the sample-at-a-time merge point and reduced only state
that `EndpointPolicy` cannot read again. Once `speech_active` is true,
`_observe_speech` skips its activation branch; both candidate fields are then
cleared by `_reset_speech_state` before a later activation can inspect them.
The key therefore replaces those stale candidate values with their canonical
empty values only while active. Conversely, an inactive state has no
last-speech end after that same reset, so that value is canonicalized only
while inactive. The production policy remains unmodified.

The pre-change prototype varied the active candidate values and exhaustively
compared every seven-sample Boolean continuation (128), including the Stop
tail; emitted spans were identical. The fresh aggressive search still replays
166 spans, while its terminal classes fall from 56 to 28
(`iteration-08-fresh-canonicalized.json`). The completed hard-cap-160 toy
still returns a required depth and production preview count of 1
(`iteration-08-reachable-toy.json`).

In a controlled 15-second aggressive run, the snapshot reached VAD frame 4,
sample 64 after completing frame 3. Its boundary state set is 51,841 rather
than iteration 7's 90,161 at the same completed-frame boundary (42.5% fewer),
and it advanced beyond that boundary before termination. It did not write a
final all-state result, so it remains progress evidence only; the loader guard
and 166-depth seam must stay unchanged.

## Further bounded frontier — 2026-08-17

Iteration 9 left the canonicalized search unchanged and ran the same
aggressive geometry under a 45-second supervisor cap. Its atomically written
snapshot completed four of the twelve VAD-frame horizon and reached sample 64
of frame 5: 116,080 boundary states, 146,800 decided states, 101,616
undecided states, and 403,728 cached production-policy transitions
(`iteration-09-reachable-progress-aggressive-45s.json`). No final JSON was
written. This is progress evidence only, not a bound: the bundle loader and
the RED 166-depth seam remain deliberately unchanged. The exact command and
verdict are in `iteration-09-reachable-search.txt`.

## Packed reachable-history prototype — 2026-08-17

Iteration 10 measured a storage-only reduction before changing the reachable
search. At each completed VAD-frame boundary, every state currently retains a
tuple of `(carried_samples, decision)` history entries solely to rebuild the
one eventual production-preview witness. A fixed-width integer can encode each
entry using `ceil(log2(2 * vad_frame_samples))` bits while retaining the known
boundary depth for lossless decoding.

The prototype independently runs the current tuple and packed forms through
the production `EndpointPolicy` transition cache, preserving the
sample-at-a-time merge point. On the existing one-VAD-frame toy and a distinct
six-frame small horizon, their terminal policy keys and every decoded history
match exactly. The direct retained size of the state map is 32.66% and 34.96%
lower, respectively, with indistinguishable measured time. Full command and
state are in `iteration-10-packed-history-prototype.txt`; the re-runnable
prototype is `prototype_packed_reachable_history.py`.

This is not an all-state bound and does not authorize a loader guard. The next
step is to absorb the packed representation into the existing probe, prove its
current toy result and production-preview replay unchanged, then run the same
bounded aggressive command. Keep the deliberate RED seam and loader unchanged
until the all-state result exists.

## Packed reachable history retained — iteration 11

The production probe now stores each completed-VAD-frame witness entry as a
fixed-width integer symbol and decodes it only for its one final
`preview_frame_work_items` replay. Its sample-at-a-time policy transition and
state keys are unchanged. The existing hard-cap-160 reachable toy completed
with required depth 1 and a real production preview replay of 1
(`iteration-11-reachable-toy.json`; its progress snapshot is
`iteration-11-reachable-progress-toy.json`).

The same 45-second aggressive supervisor command did not write a final JSON.
Its durable snapshot completed 4/12 VAD frames and reached sample 48 of frame
5 with 116,080 boundary states, 139,120 decided states, 106,000 undecided
states, and 390,144 cached production-policy transitions
(`iteration-11-reachable-progress-aggressive-45s.json`). This verifies the
retained representation on the real replay path, but the bounded progress
snapshot is neither an all-state floor nor a reliable speed comparison with
iteration 9. Keep the loader and deliberate RED seam unchanged.

## Derived candidate duration — iteration 12

For an inactive `EndpointPolicy`, a live speech candidate has accumulated
exactly `accepted_until - speech_candidate_start` samples.  Once speech is
active the existing canonicalization already removes both candidate fields.
`prototype_derived_candidate_duration.py` ran the original and reduced
sample-at-a-time searches through the production policy: their terminal keys
and packed witness histories matched on the existing one-VAD-frame toy and a
distinct six-frame horizon.  The direct terminal-map footprint fell 2.40%
(668 to 652 bytes) and 3.18% (475,648 to 460,508 bytes), respectively
(`iteration-12-derived-candidate-duration-prototype.txt`).

The retained probe now stores only the candidate's relative start and
reconstructs duration when materializing a cache-miss policy.  It raises if a
production policy state ever violates the derivation.  The fresh aggressive
search is unchanged at 28 terminal classes, 166 frame spans, and a one-span
Stop tail (`iteration-12-fresh-candidate-derived.json`); the hard-cap-160
reachable toy still completes at depth 1 and real preview count 1
(`iteration-12-reachable-toy.json`).  This is a small storage reduction, not
an all-state result: it does not establish a config-load floor or authorize
changing the intentionally RED seam/loader.
