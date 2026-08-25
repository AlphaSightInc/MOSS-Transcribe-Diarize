# M1 — plan E1 exit gate, paired rerun on the M1 build (2026-08-25)

**Verdict: five of six gates pass. The bounded salvage does exactly what it was projected to
do — measured, to five decimal places — and G-M1-1 still fails, by .0023, on a segment that
entered the instrument before M1 was written.** The M1 row is signed on G-M1-2..6 and stays
**unsigned on G-M1-1 pending an owner ruling**, the same disposition M0(d)'s G2 has. No `.stop`:
under the preregistered protocol this failure does not survive attribution (below), and nothing
in the convergence approach is refuted by it.

## What was run

The dev `web_cli` was restarted onto the M1 build — pid 22561, started **2026-08-25 02:11:11
local**, repo working tree at `b15503a` (`ralph: iteration 7 — M1 production salvage shipped`).
`restart-pre.txt` / `restart-post.txt` hold the before/after descriptors: **identical**, so the
restart changed the build and nothing else. The previous service (pid 82706, the M0d build) was
stopped first; the 4070 Ti host was not touched.

```bash
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m1-exit-20260825-021153
prototypes/streaming-diarization/live-convergence/verify_m1_exit.py --fresh-root /tmp/m1-exit-20260825-021153
prototypes/streaming-diarization/live-convergence/attribute_wer_delta.py \
    <bill live hypothesis> --case lex_bill_ackman --drop 49.75:50.0 --drop 5.0:7.5
```

Passes: `trio-A` 06:11:57–06:16:12Z, `trio-B` 06:16:16–06:20:31Z, `keyu5m-A` 06:20:35–06:25:50Z,
`keyu5m-B` 06:25:53–06:31:09Z (UTC), strictly sequential, one in-flight vLLM request throughout,
each preceded by one discarded warm-up decode (`run_paired_passes.sh`, the campaign protocol
fixed in `../M1-salvage-production/PREREGISTRATION.md`). The trio driver exits 1 on its fifth
case (`acquired_nfl`, empty reference `text`) — pre-existing, after every scored case is written.

## Gates

| Gate | Verdict | Measured |
| --- | --- | --- |
| G-M1-1 trio live WER `<= .190` | **FAIL** | **.192294** (projection .1885) |
| G-M1-2 no per-case live WER regression | **PASS** | bill −.02273, milei 0, keyu 0 |
| G-M1-3 file mode byte-identical | **PASS** | 5/5 cases × 2 passes, sha256 vs the 2026-08-24 baseline |
| G-M1-4 zero extra MOSS requests | **PASS** | 24 / 32 / 24 / 27 / 128 decodes, both passes |
| G-M1-5 no refusal boilerplate, no digital-silence words published | **PASS** | 0 rows inside any refused span; 4/4 salvaged spans found |
| G-M1-6 identity receives only salvager-emitted intervals | **PASS** | 4 salvaged spans, all reproduced from the corpus, intervals equal |

`gates.json` has the full detail. Six mutations of the artifacts, each caught by the gate it
targets and by no other (`mutations.txt`).

## What M1 did, measured

Both trio passes produced **identical published text** on every case; the only A/B differences
are ±10–20 ms extent moves on 1 (bill), 1 (milei) and 4 (keyu) segments — the F4 provider-side
jitter, already on record.

| case | 2026-08-24 baseline live | M0d (pre-M1 build) | **M1** | M1 salvages |
| --- | --- | --- | --- | --- |
| lex_bill_ackman | .261364 | .272727 | **.238636** | 1 |
| lex_javier_milei | .144 | .144 | **.144** | 0 (4 refused) |
| lex_keyu_jin | .194245 | .194245 | **.194245** | 0 |
| trio mean | .199870 | .203657 | **.192294** | |
| keyu-5m (reported, not gated) | .1464 | .1464 / .1477 | **.146375 / .147743** | 0 (6 refused) |

Salvage fired on exactly the spans the §9.1 corpus said it would: `lex_bill_ackman#02` and
`acquired_jamie_dimon#22`, one each per pass, and nowhere else. The 5-minute case has six
zero-parse spans and salvages none of them — all six are non-`hard_cap` freezes, so the gate
refuses them, and its WER is unmoved (mean .147059 here, .147059 on the M0d build).

## Why G-M1-1 fails, attributed

`attribute_wer_delta.py` re-scores the real bill hypothesis with one segment withheld at a time,
on the drivers' own scorer. Two segments separate this run from the projection:

| withheld segment | bill WER without it | that segment is worth |
| --- | --- | --- |
| `[5.00,7.50] S01 "The difference between, you said the stock market."` | .272727 | **−.034091** |
| `[49.75,50.00] S00 "You know."` | .227273 | **+.011363** |

- The first is **M1's whole effect**, and it is the projection exactly: plan §9.1 projected bill
  `.2614 → .2273`, a delta of .0341; measured, the salvaged span is worth −.034091.
- The second is **not M1's**. A per-segment diff of the three bill hypotheses (baseline →
  M0d → M1) shows M0d added it and M1 added nothing but the salvaged span:

  ```
  baseline -> M0d :  + (49.75, 50.0, 'S00', 'You know.')      <- appeared before M1 existed
  M0d      -> M1  :  + (5.0, 7.5, 'S01', 'The difference between, you said the stock market.')
  ```

  It sits inside **span 19, samples 760000–800000 (47.5–50.0 s)** — the exact span
  `probe_decode_determinism.py` caught flipping in M0(d), where 12 identical greedy requests
  gave 2 distinct outputs (20 vs 37 generated tokens) after an idle gap. This run decoded it at
  **37 tokens**, the longer variant; the 2026-08-24 baseline decoded the shorter one and
  published nothing at 49.75. Warming the decoder before each pass did not change it, so the
  server settled into that variant, and the 4070 Ti host is read-only by PRD constraint.

So: **bill without the flip is .227273, and the trio mean without it is .188506** — to six decimal places the .188506 the
§9.1 prototype projected, under the bound. The .0023 by which the gate misses is one 0.25-second
`S00` fragment that arrived with the instrument, not with the change.

The preregistered protocol says the verdict comes after attribution, and that "a delta whose
whole cause is a single decode flip is reported as noise with its span id". That is this delta,
with its span id. The failure therefore does not survive attribution as an M1 defect, which is
why no `.stop` was written — but the gate is worded as an absolute bound on the deployed
service, and on the deployed service the number is .192294. **Both facts are the record.**

### The question for morning review

The PRD's comparators (`.2614 / .1440 / .1942`) and the `.190` bound were preregistered against
the 2026-08-24 instrument, whose bill arm has since moved +.0114 for decoder-side reasons the
campaign cannot control and must not re-roll. One decision settles it:

- **O1 — score G-M1-1 on the frozen instrument.** M1 passes at .188506. Consistent with the
  campaign's own rule that the preregistered comparators stand and the re-acquisition explains
  their noise (M0d).
- **O2 — score G-M1-1 as measured.** M1 fails at .192294 and the row stays unsigned. Note this
  costs nothing operationally: **M2's gate is `<= .150` on the same trio**, strictly stronger,
  and is measured on the current instrument.

Recommendation: **O2 for the record, and proceed to M2** — leave the row unsigned, because the
deployed number is the deployed number, and let M2's stronger bound settle it on the instrument
that will actually be used. Nothing in the ladder is blocked either way.

## Also learned here

- **Two passes of the same corpus are text-identical on the trio.** Live WER per case is
  bit-stable across A and B on all three cases; only extents move (±10–20 ms, one webrtcvad
  frame). The 5-minute case still spreads: WER .146375 / .147743 (.0014), DER .113033 / .110
  (.0030). That is a first N=2 reading of the per-case noise floor candidate 4c asks for, and it
  says the trio needs no repeat budget while the 5-minute case does.
- **M0d's 5-minute decode count of 115 was an artifact of the truncated trace**, not a decode
  count. The complete M0e trace and both M1 passes all read **128** `canonical_processed`
  events. G-M1-4 uses M0e as the 5-minute comparator and says so.
- The last span of a meeting is flushed on stop and emits **no `span_frozen` event**, but
  `canonical_processed` carries `committed_samples` and `frozen_span_sample_count`, which place
  it. `verify_m1_exit.py` derives its bounds that way rather than leaving it unchecked —
  `lex_javier_milei#31`, the 0.24 s `stop_flush` tail that M1a adjudicated, is a refused span
  and publishing nothing is exactly what the trace shows.
- A gate over *published words* has to be anchored to the span that produced them. The first
  draft of G-M1-5 searched the whole transcript for a refused span's words, and the corpus holds
  the one-word decode `[0.00][S01]And.` — "and" appears in a minute of speech regardless. The
  gate now asks whether the refused span published any row inside its own bounds (it did not,
  22/22) and uses the salvaged spans as a positive control (4/4 found), so it cannot pass
  vacuously.
