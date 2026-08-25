# Preregistration — live-file-gap-emptyspan (H3)

Written **before** any policy was measured. Throwaway prototype; delete or absorb when the
verdict is acted on.

## Question

Live spans that commit an empty transcript delete real speech permanently. **Which recovery
policy recovers the most reference words, at what decode cost, and how much of the trio's
live-vs-file coverage/WER gap would it close if deployed?**

## What Phase 1 already established (inputs, not questions)

- Trio baseline = 80 committed spans, 5 of them empty (bill 1, javier 4, keyu 0).
- Every empty span re-decodes empty deterministically through the live request shape (2/2).
- **The decoder is not silent.** Raw decode (validation bypassed) shows the model emits the
  words and omits the *closing* `[end]` timestamp (bill span02 also omits the opening one),
  so `parse_transcript` returns zero segments, `VllmRunner` raises `EmptyTranscriptionError`,
  and `RunnerBoundedWavInference` converts that to `transcript=""`. The span is a **parse
  discard**, not an empty decode.
- 2 of 5 trio empty windows contain real speech; 3 are digital silence in the source audio
  where the decoder hallucinated a refusal string ("I'm sorry, I can't assist…").

## Policies under test

| id | policy | extra decode |
|----|--------|--------------|
| P0 | baseline: commit "" (what ships today) | 0 |
| P1 | **salvage-parse**: repair the discarded text (supply the missing timestamps, clamp to the span) — no new request | 0 |
| P1v | salvage-parse gated on webrtcvad speech ratio ≥ 0.5 over the span | 0 |
| B1a | retry with **1.0 s** leading context prepended, strip words before the cutoff | span + 1.0 s |
| B1b | retry with **2.5 s** leading context prepended, strip words before the cutoff | span + 2.5 s |
| B2 | promptless retry: same WAV, alternate/neutral prompt | span |
| B3 | merge-forward: decode span + following span as one window, split back by timestamp | following span |
| B4 | pad-retry: re-decode the same span widened by 0.25 s on each side | 0.5 s |

## Gates (pass/fail, decided now)

1. **G1 metric fidelity** — recomputing TBSA from the baseline hypothesis JSONL must
   reproduce `results.json` to 1e-6 for both arms, all three cases. *(passed in D4)*
2. **G2 span-simulator fidelity** — the offline span simulator (webrtcvad mode 1 / 160-sample
   frames + deployed `EndpointPolicy` config) must reproduce every committed span boundary of
   all three baseline traces exactly, or the 3-minute tier numbers are not admissible.
3. **G3 policy admissibility** — a policy counts as a *recovery* for a span only if its output
   parses into ≥1 segment under the production `parse_transcript` and lands inside the span's
   own bounds. Anything else is a non-recovery, not a partial credit.
4. **G4 honesty of false additions** — every emitted token that is not in the window's oracle
   text counts as a false addition, including hallucinated refusal strings on silence. A
   policy that recovers 10 words and adds 16 false ones is reported as such.
5. **G5 projection** — trio movement is recomputed with the real evaluator on a real modified
   hypothesis JSONL, never extrapolated from per-span word counts.

## Oracle

Per-window ground truth = the file arm's own decode of the same audio restricted to the
window (the file arm is the accuracy target of this investigation). Reference JSONL segments
are 10–30 s long and carry no word timings, so they cannot score a 2.5 s window directly.

## Cost accounting

`extra decode seconds` = audio-seconds submitted beyond the baseline single decode of the
span. Wall time is recorded but labelled **contended** (three sibling agents share the GPU),
and request concurrency stays at 1.

## Stopping rule

Report the policy with the best recovered-words-minus-false-additions at the lowest extra
decode seconds; if two policies tie on recovery, prefer the cheaper one. No policy is
recommended for deployment on the strength of the trio alone if its false-addition count is
non-zero on silence.
