---
id: T-30
map: map-002-phase2-multiuser
title: Measured MOSS Voiceprint matching and abstention rule
type: prototype
status: closed
assignee: codex-20260826
blocked_by: [T-13, T-19, T-22]
---

## Question

What cosine-similarity acceptance rule lets the production MOSS speaker encoder recognize an
Account's enrolled Voiceprint across later speech while abstaining from other people?

This prototype unblocks *Voice bank design — ownership, storage, matching, abstention,
versioning, deletion*. LiveTranscribe is the behavioral baseline, but its `0.51` fingerprint
threshold is unmeasured and uses a different encoder (WeSpeaker ResNet34 CoreML). It cannot be
copied into MOSS's WeSpeaker ResNet152 ONNX path.

Extend the standing bench at `prototypes/streaming-diarization/`; do not build parallel
measurement scaffolding. Use the production `_OnnxWeSpeakerEmbedder`, production live-path span
and album-centroid semantics, and non-overlapping real-human-speech enrollment/probe material
from the existing named corpora. Do not open a holdout already sealed by another campaign.

The prototype must:

- state one command to run and print the full evaluated state;
- model the T-22 policy: only manual naming enrolls; an automatic match never adds a sample;
- start from the LiveTranscribe baseline of cosine matching against the mean of stored
  enrollment samples, then report whether MOSS's duration-weighted album centroid requires a
  different aggregation rule;
- report same-person and different-person score distributions with exact pair counts and
  speaker/corpus denominators;
- measure causal live matching and the existing retrospective-sweep opportunity separately;
- compare a score-only rule with a score-plus-runner-up-margin rule, including false named
  matches, false abstentions, and correct matches at every evaluated operating point;
- state the minimum eligible speech/evidence needed before matching;
- return `unmeasured` for any population or condition the corpus cannot support instead of
  extrapolating; and
- record the command, measurements, and verdict in `NOTES.md` beside the prototype, then update
  `docs/design-streaming-diarization.md` section 7 if a rule is accepted.

The resolution must name the metric, threshold, margin (or explicit absence), evidence floor,
live-versus-sweep timing, corpus/denominators, and abstention label. No production code changes.

## Prototype asset

- [Measured result and one-command run](../../prototypes/streaming-diarization/voice-profile-matching/NOTES.md)
- [Throwaway measurement shell](../../prototypes/streaming-diarization/voice-profile-matching/prototype_voice_profile_match.py)
- [Pure acceptance rule](../../prototypes/streaming-diarization/voice-profile-matching/matching_rule.py)

## Resolution

Resolved 2026-08-26. The operator deferred to agent judgment and authorized later measured
optimization. Adopt the prototype's recommendation for the Phase-2 MVP:

- **Metric and rule:** production clamped cosine similarity `>= 0.46`; no runner-up margin.
- **Evidence floor:** at least `1.0 s` of eligible speech. Below the floor, below the score, or
  without an embedding, abstain and retain `Speaker N`.
- **Voiceprint aggregation:** preserve the LiveTranscribe baseline — store one centroid sample per
  manual naming and match against the L2-normalized arithmetic mean. Duration weighting tied on
  every best operating-point count, so it adds no measured benefit.
- **Causal timing:** match every eligible live identity evidence unit against the frozen private
  Account bank; an accepted name is immediately visible. Automatic matches never add samples.
- **Retrospective timing:** apply the same rule to the current Meeting's terminal album centroid;
  an accepted result may correct that Meeting's label.
- **Measured denominators:** 5 speakers, 2 English interviews, 14 enrollment samples, 470 known
  causal probes, 470 leave-true-profile-out unknown scenarios, 470 same-person and 1,880
  different-person causal pairs, 14 terminal albums, and 1,530 operating points.
- **Observed outcome:** causal 441/470 correct, 29 abstained, zero wrong names; unknown 470/470
  abstained; terminal 14/14 correct and 14/14 unknown abstained. The reference `0.51` was safe but
  lost four additional correct names; MOSS's within-session `0.35 / 0.10 / 0.5 s` rule produced
  three wrong known names and three false unknown names.

Only these five speakers and two recordings are measured. Other populations, Voiceprint banks over
five, and end-to-end terminal cluster-to-Voiceprint behavior remain `unmeasured`; later optimization
must return through the standing measurement bench and does not block this MVP decision.
