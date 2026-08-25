# M2 step 3a — the rolling converger, shipped (plan §10.5 step 1)

**Verdict: the production module reproduces the arm the grid selected, to every printed digit.**
Trio WER `.131861`, content recall `.943916`, six windows per case, `1.000×` added decode audio,
rolling PCM high-water `160000` samples against a bound of `320000`. Those are not numbers this
module was asked to agree with in prose — they are the numbers
`evidence/live-convergence-0824/M2-rolling-grid/grid.json` recorded for arm `10/10`, and the
verifier reads them out of that file and refuses at 6 dp.

## What shipped

| File | What it is |
|---|---|
| `moss_transcribe_diarize/app/live_transcript_convergence.py` | M2, the rolling transcript converger (new, ~330 lines with its reasoning) |
| `moss_transcribe_diarize/app/live_session.py` | `EffectiveTranscriptSegment` + `TextRevisionProposal` — plan §7.1/§7.2, inert data, +54 lines |
| `tests/test_live_transcript_convergence.py` | 21 T1 tests over the four-method interface |

Nothing else in `moss_transcribe_diarize/` changed. No runtime is wired to the converger yet:
that is plan §10.5 steps 2–7, and the order there is not negotiable.

### The interface, and why it is this small

Four methods (plan §6 M2): `accept_pcm`, `observe_base`, `complete`, `stop`. What they hide is
bounded PCM retention, window planning, one-witness-at-a-time admission, stale-work recognition,
monotonic frontier advancement, and work accounting.

What they do **not** hide is a stitcher, because the selected geometry has none. Plan §10.4 chose
a 10-second window on a 10-second stride, and at stride == window there is no overlap: the grid's
three ownership policies produced byte-identical word sequences on 9/9 case-runs (grid finding
F1). A window's words replace exactly `[lo, hi)` and the frontier advances to `hi`. No ownership
arithmetic, no lexical alignment, no word-time interpolation — materially less code than plan §6's
M2 sketch, and the reason is measured rather than asserted.

`RollingGeometry` therefore **refuses** a stride shorter than its window
(`UnmeasuredRollingGeometry`). An overlapping geometry needs a stitcher, a stitcher needs a
measured selection, and neither exists. Widening the geometry is a new grid run, not a config edit.

### Failure behaviour is plan §5.2's, and each branch names itself

| Condition | Behaviour | Status |
|---|---|---|
| a window's decode publishes nothing | keep the surface, record the window, plan no more | `window_failed` |
| a completion arrives for a request no longer awaited | refused, surface unchanged | (counted) |
| the ring reaches the `2 × window` bound | drop, say so, plan no more | `pcm_evicted` |
| the session declines a proposal | the next window is never planned | (no new state) |

The last row is the one worth reading twice. A window is planned only once the session's own
`canonical_through_sample` has reached that window's first sample, so a refused proposal stops the
grid instead of burning GPU on revisions the session must keep declining. That removed a whole
piece of state rather than adding one.

**Why a failed window stalls rather than continuing.** Plan §5.2 says later windows "may continue
only from the existing monotonic frontier". At zero overlap, no later window *begins* at a stalled
frontier — window `k+1` starts where window `k` ended. Continuing would mean either inventing words
for the gap or publishing an owned interval with nothing in it, and D4 forbids a prefix with a hole.
So the converger stops planning, the session keeps every word it had, and the base suffix stays
provisional and complete. Measured occurrences at this geometry: **0 of 54 window decodes**
(`grid.json` `decode_health`, 3 runs × 3 cases × 6 windows). The carry-forward alternative — reprint
the base's words over the failed region so the frontier can advance — is a real option and is
recorded here as the thing to build **if a soak ever observes a failed window**, not before.

## Gates

`prototypes/streaming-diarization/live-convergence/verify_production_converger.py` drives the
production class over the trio — its own planning, its own retention, its own parsing — decoding
through the grid's checked-in cache. Zero MOSS requests by construction: the decoder is handed a
runner that raises, so a cache miss is a failure rather than a fresh GPU call.

```
lex_bill_ackman    wer=0.198864 (grid 0.198864) recall=0.926136 windows=6 added=1.000x pcm_high_water=160000/320000 tiles=True
lex_javier_milei   wer=0.096000 (grid 0.096000) recall=0.920000 windows=6 added=1.000x pcm_high_water=160000/320000 tiles=True
lex_keyu_jin       wer=0.100719 (grid 0.100719) recall=0.985612 windows=6 added=1.000x pcm_high_water=160000/320000 tiles=True
TRIO               wer=0.131861 (grid 0.131861) recall=0.943916 (grid 0.943916)
decode cost: 18 requests, 0 fresh (0 = no GPU)
PASS
```

- **G1** per-case WER equals the grid's `10/10` column to 6 dp — 3/3
- **G2** trio means equal `.131861` / `.943916` to 6 dp
- **G3** the proposals tile `[0, 60 s)` exactly — every proposal starts at the previous one's end,
  no overlap, no gap, frontier reaches `960000` on all three cases
- **G4** six windows planned, six completed, none failed or stale; `1.000×` added decode audio;
  status still `rolling` at `stop`
- **G5** retained rolling PCM never exceeded the plan §6 M2 bound (`160000` of `320000` samples)
- **G6** zero fresh MOSS requests

Reproduce with no GPU:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_converger.py
```

## Mutations — five, in the production file itself

`mutate_production_converger.sh` backs the module up, breaks one property, runs both the verifier
and the T1 suite, and restores from the backup on exit (including on failure). `mutations.txt`:

| # | Defect | Caught by |
|---|---|---|
| M1 | overlapping stride with the geometry guard removed | G1 (WER `.801136` vs `.198864`), G4, and the T1 refusal test |
| M2 | token cap no longer derived from the window it decodes | `CacheMiss` — the shipped module stopped asking for the decode the grid measured |
| M3 | the window index never advances, so audio is re-owned | the frontier check (`proposal starts at 0, frontier is 160000`) + 3 T1 tests |
| M4 | retained audio is never released | G1, G4 status `pcm_evicted`, and the T1 retention test |
| M5 | an empty window proposes anyway | **T1 only** — and that is the finding: the corpus has no empty window, so only a test can hold this |

Control passes before and after the sweep. M5 is the honest one: the verifier is blind to it
because 0 of 54 window decodes at this geometry published nothing, which is exactly why plan §5.2's
failure branch needs a test rather than a corpus.

## Checks that had to hold and did

- `tests/` full suite **1033 passed, 2 skipped, 386 subtests** (1012 before this change; +21 new).
- File-mode decoder A/B against a `HEAD` worktree: byte-identical,
  `sha256 ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` — the same digest
  iteration 7 recorded, so file mode has not moved across two production changes.
- No service restart was needed and none was performed: nothing the running `web_cli` executes
  changed. The converger has no caller yet.

## What this does not do, on purpose

- **No attribution.** Every proposed segment carries `canonical_speaker=None`. A decoder's local
  `S01` is not a meeting identity, and witness-owned speaker evidence is E3's (plan D5). The grid
  scored every arm through the frozen baseline speaker timeline, i.e. it *presumed* a label
  projection — so **M3 must implement that projection**, or rolling words will publish as `S00` and
  the speaker metrics the E2 gates assume will not appear. This is the sharpest carry-forward from
  this iteration.
- **No session seam.** `LiveSession.apply_text_revision` and the §7.3 snapshot fields are §10.5
  step 2. Until they exist, `observe_base` is typed against `BaseTranscriptSurface` — the four
  fields the converger reads — and `LiveSnapshot` satisfies it once M3 adds them.
- **No scheduling.** `submit_live_refinement` is §10.5 step 3. The converger already emits the
  `coalesce_key` that queue will use (`rolling:<epoch>`) and admits one witness at a time.
- **No G6 claim.** Grid finding F3 measured a structural correction-latency floor of `8.51 s` at
  this geometry against a `6.0 s` gate. Nothing here changes that; it is measured for real in the
  §10.6 soak and the row stays unsigned if it misses.
