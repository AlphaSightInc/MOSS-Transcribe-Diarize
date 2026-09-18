# WP4 prototype verdict: stop before production fixes

Question: can the specified lane-word oracle reject missing speech, cross-lane
attribution and duplicated playback while accepting correct tagged/legacy speech?

Primitives: per-lane reference token sequences, timed observed segments, speaker
IDs and optional source_lane. Invariant: correct reference-aligned overlapping
speech must not fail just because both people use ordinary common words.

## Measurements

`evidence/mvpfix/wp4/prototype-oracle.jsonl` records counts, not transcripts:
- 2/2 small valid fixtures accepted (tagged and legacy).
- 4/4 negative controls rejected: counts only, zero mic, swapped, playback copy.
  Swapped: 10 attribution errors. Playback copy: 5 duplicate words.
- 1/1 valid public-corpus overlap FALSELY rejected: 12 alleged duplicates, despite
  system 106/106 words (60/60 unique) and microphone 48/48 words (41/41 unique).
  Ordered word-error rate is 0 on BOTH lanes.
- Existing production G7 validator accepts its two-scenario counts-only fixture,
  containing ZERO transcript words. Direct validator call, not real attendance.

The counterexample uses the first timed reference segment of each documented
public interview, at actual start/end times, with distinct speakers and correct
lane tags. No decoder involved. References contain segment timing, not word timing.
Final/pre-terminal lists have the same logical counterexample; neither live
surface was measured.

FALSIFIED: raw shared-word duplication count used as a zero-tolerance acceptance
predicate. The brief defines that raw count; zero tolerance was our prototype's
assumption, not an explicit brief threshold. This does NOT disprove feasibility
of a shared oracle. Reference-accounted excess words may resolve the false
positive, but that alternative has not been measured here.

COMMON.md says: "If the prototype FALSIFIES the design, stop the fix, record the
evidence, report". Applied at this failed predicate. No production fix attempted.
The reproducer is absorbed into the standing measurement bench as rejected-design
evidence; production does not import it.

## File boundary observations

`measure_file_boundaries.py` drives real FileMeetingTasks with controlled runner,
archive, acquirer and handle doubles. 8/8 cases finish. Acquisition 403/404/timeout,
unsupported-container and decoder exceptions yield indistinguishable failed states
(5/5). Archive preparation failure falls back to the runner, completing with
unavailable audio (1/1). Empty and malformed decoder text both complete with zero
segments (2/2). The HTTP cases are injected labels, not actual network responses.
These observations do NOT establish real music/no-speech decoder behavior.
The production windowed runner already contains PCM-based speechless diagnostics;
File-layer emptiness alone cannot prove no speech.

## Limits and scope

Exact commands: root VERIFY.md. Batch fixtures print full count/state after every
case; deviation from prototype skill: no interactive terminal UI. No audio/private
transcripts retained. Scratch files stay in this worktree. No provider/ASR calls.
No keys searched, services touched, or production sources changed.
A/B/C implementation, export comparison, F6, frontend/full Phase-2 suites and live
alternation/overlap remain unexecuted. COMMON's post-fix /new stage was not reached.
This is a prototype stop, NOT completed WP4 implementation.
