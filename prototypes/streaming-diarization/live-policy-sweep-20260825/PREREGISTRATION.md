# Live policy and peer sweep preregistration

Written 2026-08-25 EDT before preparing the derived monologue or issuing benchmark inference.

Arithmetic amendment before inference: corpus preparation measured the preregistered RTFL WAV
at 89.9935 seconds, making each pass 619.9935 seconds rather than the rounded 620 seconds used
below originally. No case, arm, gate, or policy changed.

## Question

On real, fully referenced speech shorter than five minutes, how do these pre-Stop MOSS policies
trade speaker-attributed accuracy, correction latency, and model work?

1. shipped `10/10` non-overlap;
2. `15/10` lexical stitch plus session-speaker projection;
3. `15/10` stable-anchor stitch plus session-speaker projection.

How do the resulting pre-Stop and post-Stop MOSS surfaces compare with fresh actual-live
LiveTranscribe and ProjectClerk runs over byte-identical audio?

No production code or setting changes are authorized by this sweep.

## Corpus

Only fully referenced real audio is headline evidence. Every clip is PCM16 mono at 16 kHz and
strictly shorter than 300 seconds.

| ID | category | duration | reference speakers | source |
|---|---|---:|---:|---|
| `mono_javier_intro_50s` | monologue | 50 s | 1 | Javier/Lex source `[10,60]`; one complete Lex turn |
| `interview_bill_ackman_60s` | two-person interview | 60 s | 2 | Bill Ackman/Lex golden |
| `interview_keyu_jin_60s` | two-person interview | 60 s | 2 | Keyu Jin/Lex golden |
| `interview_adam_frank_180s` | two-person interview | 180 s | 2 | Adam Frank/Lex golden |
| `discussion_jamie_dimon_180s` | multi-person discussion | 180 s | 3 | Acquired/Jamie golden |
| `discussion_rtfl_90s` | multi-person conversation | 90 s | 4 | four-speaker real-audio regression golden |

Denominator per unique pass: 6 cases, 619.9935 audio-seconds (620 nominal). The monologue is selected solely from
the human reference boundary before inference. `acquired_*` partial/masked 60-second references
and the incomplete Shapiro/Destiny tail are excluded.

`prepare_corpus.py` must preserve the five whole-file PCM payloads byte-for-byte and produce the
monologue by exact sample slicing. It writes source/output hashes and rebases its one golden row
from `[10,60]` to `[0,50]`.

## MOSS execution

- Runtime: currently deployed service, application code `22dc5b8de3ed31a94dcb1b93d2256f8cb8ac75d8`.
- Two paced passes in alternating case order: 12 actual live sessions, 1,239.987 observed
  audio-seconds for current pre-Stop and shared post-Stop surfaces.
- One discarded warm-up before the matrix.
- Capture actual `pre_stop_immediate`, `pre_stop_settled`, `stop_return`, and
  `post_stop_final`; the settled wait must be recorded.
- File mode may be collected as a same-model ceiling, but is not a substitute for any live row.
- Each pass begins with a distinct absent shadow cache. Within a pass the two `15/10` stitchers
  share the same fresh greedy window decodes. One model request is issued at a time.
- A live `15/10` window is eligible before Stop only after all 15 seconds exist. Starts advance
  by 10 seconds; no clipped end-of-file window may see the future Stop boundary.
- `pre_stop_immediate` applies shadow results whose measured completion clock is no later than
  audio end. `pre_stop_settled` drains every full window admitted before audio end and records
  the additional wait.
- Base 2.5-second publication is unchanged. The shadow clock is
  `max(window_audio_ready, previous_shadow_completion) + measured_decode_wall`; it is a quiet-GPU
  bench live clock, not a browser-paint or deployed shared-queue clock.
- Differential validity check: externally reconstructed `10/10` must reproduce the production
  rolling-owned prefix in content and speaker labels. A mismatch blocks 15/10 interpretation.

### Reconciliation definitions

- **Lexical + speaker-map:** truth-blind text alignment trims the duplicate prefix of each new
  window against the accumulated text. Resulting segments are projected onto the settled session
  speaker timeline by interval overlap.
- **Stable-anchor + speaker-map:** exact normalized words agreed by both overlapping views form
  anchors. Keep the prior coherent view through one anchor and the new coherent view after it;
  if no anchor exists, cut once at the overlap midpoint. Project resulting segments onto the same
  settled session speaker timeline.
- Neither policy can read the reference or evaluator during construction.

## Peer execution

One fresh actual-live pass per peer: 6 sessions and 619.9935 audio-seconds. No confidence interval.
Audio and references are copied from the prepared corpus and hashes must match.

### LiveTranscribe

- Existing signed packaged binary SHA-256
  `5a59299c1a8fd157cd456e809f6fbd0996970fd3fb462abd411cbec99d72358b`.
- Source checkout HEAD is recorded for context but is not claimed as binary provenance because
  the worktree is dirty and the login keychain is locked. The binary hash is authoritative.
- Run committed `scripts/agent_driven_live_capture.sh` in API-only `speaker` mode, LLM disabled,
  default calibration profile, default refined-live settings, browser disabled, system audio via
  `afplay`, output volume 20 with restoration.
- Capture `/transcript` before Stop after canonical drain, then persisted terminal segments.

### ProjectClerk

- Existing TCC-authorized packaged binary SHA-256
  `106c10081ae758de27208ad053522c05e69ca15a5f91215f270f2a1461311c0c`.
- Source checkout HEAD is context only, not binary provenance; its worktree is dirty.
- Run English mode, microphone muted, system-audio capture, automatic speaker count, `afplay` at
  volume 20 with restoration. LLM note generation is not an accuracy surface and its wait is
  excluded after the terminal transcript save is stable.
- Capture visible live rows before Stop through macOS Accessibility. The UI exposes timestamps
  only as floored `m:ss`; collect all virtualized pages. Capture the first raw save after Stop and
  the stable post-recluster save separately when observable.
- ProjectClerk persists row starts but not ends. Reconstruct each end as the next row start and the
  final end as clip duration. Report this timestamp limitation beside every DER/TBSA comparison.

If a peer cannot capture or export the stated actual-live surface, write `unmeasured` with the
exact failed precondition. Do not substitute file import.

## Accuracy and latency

Score every raw timestamped surface only in this repo, with the same evaluator and golden:

- WER, TBSA, legacy DER, text coverage, content recall;
- speaker accuracy, matched-word speaker accuracy, reference-speech DER;
- per case, category macro, six-case macro, and duration-weighted mean.

TBSA is the headline balanced text-plus-speaker objective. WER and DER remain independent
diagnostics. For a MOSS 15/10 arm to remain production-research eligible it must improve WER
materially on the six-case and category means, have no case worse than current by more than `.02`
absolute WER or DER, and report matched-word speaker accuracy. This sweep does not auto-promote.

Report separately:

- first visible/publication latency;
- provisional-to-correction age or the nearest honest peer clock;
- pre-Stop drain wait;
- Stop-to-terminal latency;
- decode request count, decoded-audio work, measured decoder wall, RTF, queue/failure state where
  the product exposes them.

Hardware/model latencies are provenance, not a cross-product speed ranking. Browser paint is
unmeasured unless directly instrumented.

## Stress and integrity gates

- exact corpus audio/reference hashes match across systems;
- all MOSS PCM accepted/accounted exactly;
- one MOSS inference request in flight; quiet queue at launch/end;
- MOSS queue bounded, zero refusals/failed windows/terminal failures, combined RTF `<1`;
- every raw transcript surface is retained, not only scores or hashes;
- post-Stop is never reported as pre-Stop;
- peer failures stay in denominators as failures/unmeasured, never silently disappear;
- no peer worktree is edited, cleaned, stashed, reset, fetched, or pulled.

## One command

The completed prototype will expose:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/run_sweep.py \
  --output evidence/live-policy-sweep-20260825
```

The command must print the full corpus, run state, surface state, and final denominators.
