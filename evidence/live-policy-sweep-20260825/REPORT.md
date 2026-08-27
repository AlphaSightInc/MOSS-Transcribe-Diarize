# Live policy and peer sweep — 2026-08-25

## Executive answer

**Do not change production from 10/10 yet.** Both 15/10 policies measured substantially better
pre-Stop accuracy, but this run failed two certification controls: external 10/10 reproduced the
deployed rolling prefix exactly in only **4/12** observations, and the strict canonical p95
real-time-factor gate failed on the final preregistered session (**1.070**) and its accuracy
replacement (**2.440**). The three accuracy arms are therefore useful research evidence, not a
promotion result.

Between the two 15/10 reconcilers, **stable-anchor is the small aggregate accuracy winner; lexical
is the better default research candidate**. Stable-anchor reduced macro WER from `.1084` to `.1059`
and DER from `.1535` to `.1507`, but its selected words became available about **2.00 s later on
average** (`8.05` vs `6.04` s). Lexical delivered **94% of stable-anchor's WER gain over current**,
won the monologue, is simpler, and did not depend as heavily on the single four-speaker clip.
Choose stable-anchor only if multi-speaker accuracy is worth the slower correction surface.

Production code and settings were not changed.

## Mental model

The base live lane publishes short provisional spans. A rolling window later re-hears a longer
stretch and corrects the text.

- **10/10:** hear ten seconds, advance ten. No overlap to reconcile.
- **15/10 lexical:** hear fifteen seconds, advance ten; remove repeated overlap by text alignment.
- **15/10 stable-anchor:** use words on which the two overlapping views agree as the seam.
- **Speaker-map:** after choosing words, assign each decoded segment to the session speaker owning
  the most of that time interval.

Longer overlap improves context around cuts. It also waits longer before deciding which view wins.

## Coverage and denominators

- Six fully referenced real clips: one monologue, three two-person interviews, one three-person
  discussion, one four-person conversation.
- Exact duration per pass: **619.9935 s**; every clip `<300 s`.
- MOSS accuracy: two alternating passes, **12 observations / 1,239.987 s**. A thirteenth session
  replaced the final session's unserialized accuracy surfaces after its retained RTF failure; the
  original failure remains in the stress denominator.
- LiveTranscribe: **6 fresh actual-live sessions / 619.9935 s**.
- ProjectClerk: **1 fresh attempted session; 6/6 comparison cells unmeasured** because its packaged
  binary lacked Screen Recording/System Audio permission. The attempt captured zero audio buffers.
- Five whole corpus WAVs remained byte-identical; the monologue was cut at exact PCM samples.
  Audio hashes matched on both machines.

## F1 — MOSS accuracy

Equal-case macro means; WER and DER lower is better, TBSA and matched-word speaker accuracy higher.

| Surface | WER | duration-weighted WER | TBSA | DER | matched-word speaker accuracy |
|---|---:|---:|---:|---:|---:|
| current 10/10, immediate pre-Stop | .1707 | .1573 | .8467 | .1898 | .8689 |
| current 10/10, drained pre-Stop | .1445 | .1367 | .8720 | .1662 | .9095 |
| 15/10 lexical + speaker-map | .1084 | .1060 | .8885 | .1535 | **.9296** |
| 15/10 stable-anchor | **.1059** | **.1034** | **.8903** | **.1507** | .9274 |
| MOSS post-Stop final | .0951 | .0941 | .9254 | .1056 | .9521 |

Against drained current 10/10, lexical improved macro WER by `.0361` absolute (`25.0%` relative),
while stable-anchor improved it by `.0386` (`26.7%`). Neither 15/10 arm worsened any case by more
than `.02` absolute WER or DER. MOSS post-Stop remained the best MOSS accuracy surface.

### WER by content type

| Content | current drained | 15/10 lexical | 15/10 stable | post-Stop |
|---|---:|---:|---:|---:|
| monologue | .1593 | **.0973** | .1062 | .0973 |
| two-person interviews | .1511 | .1314 | **.1284** | .1167 |
| three-person discussion | .1185 | **.0714** | **.0714** | .0697 |
| four-person conversation | .1359 | .0874 | **.0728** | .0534 |

Stable-anchor's aggregate edge is concentrated in the four-speaker conversation (`.0146` WER
better than lexical). Lexical was `.0089` better on the monologue. There is one clip in each of
those categories, so this is a measured trade-off, not a population estimate.

## F2 — Latency and work

These clocks are not interchangeable. Current MOSS correction age is provisional publication to
changed-word correction. The 15/10 shadow clock is selected word midpoint to measured window
completion; it includes audio accumulation but excludes browser paint and shared deployed queueing.

| Measurement | current 10/10 | 15/10 lexical | 15/10 stable |
|---|---:|---:|---:|
| first-publication audio age, p95 | 3.67 s | inherits base | inherits base |
| current changed-word correction age, p95 | 10.46 s | not same clock | not same clock |
| shadow-owned word availability, mean | — | **6.04 s** | 8.05 s |
| shadow-owned word availability, p95 | — | **10.99 s** | 12.68 s |
| full-window ready → decode completion, p95 | — | .707 s | .707 s |
| pre-Stop drain wait, p95 | .89 s | 0 s on these clips | 0 s on these clips |
| Stop → terminal, p95 | 8.35 s | same terminal path | same terminal path |

All eligible 15/10 windows ended at least five seconds before these clip boundaries, so every one
completed before Stop; immediate and drained 15/10 accuracy were identical. This is corpus geometry,
not a guarantee for arbitrary meeting lengths.

Across two passes, a complete external 10/10 grid made 122 requests over 1,220 decoded audio-seconds
and used 50.04 decoder-wall seconds. The shared 15/10 grid made 112 requests over 1,680 seconds and
used 59.22 wall seconds: **37.7% more decoded audio and 18.3% more decoder wall**. Lexical and
stable-anchor share those model calls. Base plus 15/10 measured combined RTF was `.169`, below 1.

## F3 — Fresh peer comparison

Peer hardware/model timing is provenance, not a speed ranking. LiveTranscribe timestamps were
shifted from session time to playback time using its UTC-second playback receipt, so DER/TBSA have
approximately one-second alignment resolution.

| Product/surface | WER | TBSA | DER | state |
|---|---:|---:|---:|---|
| MOSS 15/10 stable pre-Stop | **.1059** | **.8903** | **.1507** | shadow policy, formal gate blocked |
| MOSS current 10/10 drained | .1445 | .8720 | .1662 | actual live |
| LiveTranscribe drained pre-Stop | .1536 | .7538 | .4007 | actual live, 6/6 terminal |
| MOSS post-Stop final | **.0951** | **.9254** | **.1056** | actual live |
| LiveTranscribe post-Stop final | .1812 | .7471 | .3913 | actual live, 6/6 terminal |
| ProjectClerk | — | — | — | unmeasured: system-audio permission missing |

LiveTranscribe's first visible text ranged from `4.56–9.00 s` audio age. Its pre-Stop drain averaged
`1.05 s`; Stop-to-terminal ranged from `58.12–108.72 s`. Five cases showed no non-append segment
correction in one-second snapshots; the four-speaker clip showed one at `14 s`.

## F4 — Stress and integrity findings

1. **G1 — PASS:** all MOSS sessions reached terminal; accepted/accounted samples matched exactly;
   queue depth stayed at one; no admission refusal, stale completion, failed rolling window, or
   terminal failure occurred.
2. **G2 — FAIL:** strict canonical p95 RTF exceeded 1 on the final preregistered monologue session
   (`1.06971`) and again on the accuracy replacement (`2.4403`). Combined pre-Stop RTF remained
   below 1 (`max .1674`); the strict short-span tail is the failure.
3. **G3 — FAIL:** external 10/10 content-plus-speaker reproduction passed only `4/12` observations.
   The two 15/10 passes themselves were byte-stable per case, but the preregistered rule blocks
   production interpretation when the shipped differential fails.
4. **G4 — FAIL:** both 180-second Jamie sessions entered `pcm_evicted` after five rolling windows;
   rolling authority reached only about 40 seconds. The quiet-GPU 15/10 shadow covered the planned
   full grid, so its accuracy is an upper-bound research surface, not proof the deployed scheduler
   can sustain it.
5. **G5 — BLOCKED:** ProjectClerk's existing binary hash matched preregistration, but ScreenCaptureKit
   stopped with `audioBuffers=0`; the UI exposed “system audio not enabled.” No file import was
   substituted for actual live.
6. **G6 — PASS:** runtime descriptor stayed unchanged; both peer source checkout HEADs and dirty
   statuses stayed byte-for-byte unchanged; no peer repo was edited, cleaned, reset, fetched, or pulled.

## Decision

- **D1 — Production:** keep current 10/10. The sweep is not promotion-grade because G2–G5 failed.
- **D2 — Next research arm:** use **15/10 lexical + speaker-map** as the default. It captures nearly
  all measured accuracy gain with lower content-availability age and less reconciliation complexity.
- **D3 — Stable-anchor:** retain as the accuracy-first challenger for multi-speaker conversations.
  Promote it over lexical only after more fully referenced multi-person clips show that its edge is
  not driven by the single RTFL case and its extra correction age is acceptable.
- **D4 — Before any new sweep:** first fix/measure the production `pcm_evicted` path and make the
  external 10/10 control reproduce the shipped surface. Grant ProjectClerk Screen Recording/System
  Audio permission before rerunning its six actual-live cells.

## Reproduce and audit

One-command fresh runner:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-policy-sweep-20260825/run_sweep.py \
  --output evidence/live-policy-sweep-20260825-fresh
```

Primary artifacts:

- `corpus/corpus-manifest.json`
- `moss-recovered/moss-results.json`
- `moss-recovered/shadow-latency.json`
- `peer-scores/peer-results.json`
- `peers/projectclerk-unmeasured.json`
- `peers/peer-provenance-start.json` and `peer-provenance-end.json`
- every raw MOSS JSONL surface and every LiveTranscribe pre-/post-Stop JSON under their case folders

