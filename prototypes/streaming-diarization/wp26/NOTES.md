# WP26 prototype verdict

Question: why do two terminal Lex turns with causal overlap remain unnamed, and
does the existing cropped acoustic probe recover their correct lane identity?
Primitives: lane-owned identity, terminal segment, same-lane overlap, acoustic
crop. Invariants: preserve text/timing and lane isolation; existing thresholds,
identity policy, one-to-one overlap mapper and lifecycle remain unchanged.
Falsifier: either measured crop fails to match speaker-0004 or requires evidence
from another lane. Tool: offline original-PCM replay through the production ONNX
encoder and revision preparer; no decoder run is needed for this question.

PASS before implementation: 69 accepted causal preparations reconstructed the
system album from retained embedding intervals and original repeated public PCM.
4.14 s / 14 words: Lex score .9404659566; .72 s / 2 words: .4899272409.
Both have Ackman score 0; both pass unchanged .35 score / .1 margin.
The causal intervals overlap Lex by 2.48 s / .72 s; nearest same-lane evidence
also says Lex. No need to guess by proximity when acoustic evidence succeeds.
69 preparations + two crops completed in 24.337 s (includes duplicate score
instrumentation; not incremental Stop latency). Full state: prototype-state.jsonl.

Cause: retained terminal accounting reports 3 local labels versus 2 canonical
system identities. The one-to-one overlap mapper leaves one label unmapped.
The lane adapter treats any labelled overlap as success and skips fallback even
when canonical_speaker is None. Extend its existing fallback to this unmapped
case. Already assigned overlap mappings stay authoritative. Acoustic abstention
still preserves unattributed words; do not invent a time-nearest assignment.

Provenance limit: original pre-terminal surface, terminal raw labels and runtime
album vectors were not retained. This reconstructs causal references from actual
accepted assignments/embedding intervals, not native runtime state. Exact terminal
segment geometry/words/assignments are retained. No claim of a new live rerun.
The scripted state probe substitutes for an interactive TUI to support repeatable
unattended execution; absorb it as a replay bench after implementation.

Survey population: all 18 extant WP12 final surface files plus 16 distinct WP17
final sessions (4 quality + 12 duration). WP12 accepted overlap: 2/127 segments,
16/1546 words, 4.86/493.27 summed segment seconds, 1/3 sessions affected.
WP17: 0/178 segments, 0/2010 words, 0/606.12 seconds, 0/16 sessions affected.
Historical WP12 acoustic/mono controls separately: 64/423 unnamed segments,
674/4811 words, 190.69/1419.78 seconds, 2/15 sessions. Do not pool discarded
controls into the accepted implementation's rate. Recognition sessions without
retained terminal surfaces are excluded. This is a reachable structural failure
when local labels outnumber established identities, not evidence of prevalence
across arbitrary multi-voice meetings. Repeated clips are not independent voices.
