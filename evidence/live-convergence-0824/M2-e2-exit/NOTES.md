# M2 (plan E2) exit — the rolling arm measured through the deployed service

**2026-08-25, iteration 18. Seven of eight gates pass. G-M2-4 (correction p95) misses, exactly as
iteration 10 preregistered it would, and its row stays unsigned.**

The rolling witness now runs inside the deployed dev service, and the campaign's live numbers
come off the surface a reader is shown. On the fully-referenced trio, live WER falls
**.199870 → .131357** and content recall rises **.913490 → .943916**; on the five-minute case
WER falls **.1464 → .082079**, better than the `<= .0985` bound and within **.0315** of the
paired file arm (`.050616`). The witness costs `.030–.048` of real time; combined base + witness
inference RTF is `.133–.157` against a bound of 1.

| Gate | Bound | Measured | Verdict |
|---|---:|---:|---|
| G-M2-1 trio rolling WER mean | `<= .150` | **.131357** | PASS (grid projection .131861) |
| G-M2-2 per-case below baseline live | `<` .2614 / .1440 / .1942 | .204545 / .096000 / .093525 | PASS (−.0568 / −.0480 / −.1007) |
| G-M2-3 trio content recall mean | `>= .940` | **.943916** | PASS (= the grid projection to 6 dp) |
| G-M2-4 correction-after-provisional p95 | `<= 6.0 s` | **8.756675 s** | **FAIL — preregistered** |
| G-M2-5 combined RTF, bounded queues | RTF `< 1` | .133–.157, depth `<= 1`, 0 refusals | PASS |
| G-M2-6 five-minute rolling WER | `<= .0985` | **.082079** | PASS |
| G-M2-7 accepted == accounted | exact | 8/8 sessions exact | PASS |
| G-M2-8 file mode byte-identical | sha256 | 5 cases × 2 passes | PASS |

## Instrument

- Service restarted 2026-08-25 05:52:14 local (pid 44278) onto repo working tree `4d6cb29`,
  same argv as every campaign restart, log
  `~/.local/share/moss-transcribe-diarize/g3/web_cli-campaign-20260825-055214.log`. Descriptor
  identical before and after (`restart-pre.txt` / `restart-post.txt`): the build changed and
  nothing else. The 4070 Ti host was not touched.
- Four sequential passes by `run_paired_passes.sh`, each preceded by one discarded warm-up
  decode, 09:55:14Z–10:14:29Z: `trio-A`, `trio-B`, `keyu5m-A`, `keyu5m-B`. `trio-A/B` exit 1 on
  `acquired_nfl` (pre-existing empty reference, after every scored case is written) — the same
  known ending as the M1 exit passes.
- Gates by `verify_m2_exit.py`; definitions fixed before launch in
  `prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M2-exit.md`.

## What the numbers say

**Every prediction on record held.** The preregistration predicted trio WER "near .131861"
(measured .131357), recall "≈ .9439" (measured .943916 — the grid's digits exactly), combined
RTF "≈ 0.2" (measured .133–.157), and a G-M2-4 p95 "in the 8–12 s band" (measured 8.757 s). The
one genuinely open question — the five-minute case, called a coin flip at a projected .0966
against a .0985 bound — came in materially better at **.082079**.

**The five-minute case is now reproducible.** Both passes returned identical WER, DER, recall and
segment counts on all four scored cases, including the five-minute case, which spread .0014 WER /
.0030 DER across the M1 exit passes. Fewer, longer decodes leave the deployed decoder fewer
opportunities to flip: the 5-minute session issues 128 span decodes plus 30 window decodes, and
the published surface is dominated by the 30.

**Speaker quality moved without an identity change.** Live DER on the trio is .127333 / .117333 /
.089167 (mean **.111278**) against the baseline live .2235 / .1945 / .1112, and duration-weighted
speaker accuracy is .8727 / .8827 / .9108 (mean **.888722**) against .8437 as M3's floor. The
five-minute case reads DER **.0886** against M3's `<= .0947`. Nothing in E3 has shipped: the
rolling surface publishes longer segments whose canonical speaker is projected from the same base
timeline, so the extent artifact that inflated live DER shrinks. **M3's gates are stated against
the baseline live numbers and are now partly met by M2's text work; M3 must restate its
comparators against this measurement or it will grade itself against a surface nobody serves.**

**The witness's serial cost is now priced (iteration 14's D2).** A running window holds the
session's single in-flight inference slot, so a base span can wait behind it. Measured canonical
queue wait: p50 `0.62–0.76 ms` on every session, but p95 `136–214 ms` and max `649–654 ms` on
`lex_javier_milei`, and max `251–266 ms` on the five-minute case. The waiting span is never
dropped and never overtaken — one window at a time, canonical always ahead of a *waiting* witness
— and a 0.65 s wait sits well inside the 2.5 s span cadence. Rolling's own queue wait is the
mirror image: p50 `0.016 ms`, max `133 ms` on the five-minute case, i.e. a window waiting for
canonical work to clear.

## G-M2-4: the miss that was predicted before the code existed

`8.756675 s` against a `6.0 s` bound, pooled over 160 corrections in the primary trio (mean
4.760 s, p50 5.407 s, max 10.890 s). On the five-minute case the same clock reads p95 `10.39 s`.

Iteration 10's F3 fixed the structural floor from measured decode latencies **before the
converger was written**: with central ownership the oldest owned word has age `(L+S)/2`, so
`L+S <= 12` is required, and the plan's grid offers `10/5` (floor 6.46 s), `10/10` (8.51 s),
`15/10` (11.64 s) and `15/7.5` (12.81 s). **No geometry in the preregistered grid can pass G6.**
The selection rule §10.4 chose on cost among the arms passing G1–G3, and D-M2-2 recorded, before
this measurement, that G6 would be measured honestly and left unsigned if it missed.

What this is not: it is not a defect, not a queue problem (depth never exceeded 1, zero admission
refusals, zero stale completions, zero failed windows), and not a regression — the base path's own
first-publication latency is unchanged. It is the price of the geometry: a reader sees a
provisional 2.5 s span in ~0.6 s and its corrected form when the 10 s window it belongs to
completes.

The owner decision this leaves open (**D-M2-3**): accept `10/10` with ~8.8 s corrections, or
authorise a geometry outside the measured grid (`L + S <= 12`, e.g. 6/6 or 8/4) and re-run the
§10.2 grid to select it. Adding an arm now is exactly what the preregistration forbids, so this
iteration does not do it.

## Mutations — is each gate reading its own evidence?

`mutate_m2_exit.sh` works on a copy of the passes; every mutation is restored and the control is
re-scored identically afterwards.

    M1 one case's live WER inflated to .40        -> G-M2-1 (and G-M2-2, .40 > its baseline too)
    M2 one case set to exactly its baseline WER   -> G-M2-2 (the gate is a strict improvement)
    M3 half a case's published rows deleted       -> G-M2-3
    M4 rolling completions shifted 5 s earlier    -> G-M2-4 FAIL->PASS, p95 8.756675 -> 3.756675
    M5 a second admitted window in flight         -> G-M2-5 (depth 2 > 1)
    M6 five-minute WER inflated to .20            -> G-M2-6
    M7 one second unaccounted in a summary        -> G-M2-7
    M8 a file arm gains one row                   -> G-M2-8

M4 is a sensitivity probe, not a caught mutation: a gate the measurement already fails cannot be
caught by breaking it further, so the probe moves the clock in the direction that would make it
pass. It moves the p95 by exactly the 5.000000 s it shifted, which is what shows the number is
read off the runtime clock rather than asserted.

Three probes were rewritten after their first run reported nothing — M2 patched only one of the
two passes the gate averages, M4 shifted one session out of six, M6 assumed a gate that turned
out to pass. Those were broken probes, not tuned gates: no bound, comparator or definition moved.

## Files

    NOTES.md                this file
    gates.json              every gate, every per-session number, the §10.6 soak block
    gates-console.txt       the verifier's own output
    mutations.txt           the eight mutations and the gate each one flipped
    mutations/              each mutation's patch script and the control gate reading
    restart-pre.txt         service, HEAD and descriptor before the restart
    restart-post.txt        same after (descriptor identical)
    passes/                 the four measurement passes, traces gzipped
    passes/runner.txt       the runner's own log with pass start/exit stamps

Reproduce (needs the deployed service):

    prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m2-exit-<stamp>
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/verify_m2_exit.py \
      --fresh-root /tmp/m2-exit-<stamp> --output /tmp/m2-gates.json

Re-score the checked-in passes with no GPU and no service:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/verify_m2_exit.py \
      --fresh-root evidence/live-convergence-0824/M2-e2-exit/passes
