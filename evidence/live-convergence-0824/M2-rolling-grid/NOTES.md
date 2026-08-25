# M2 step 2 — plan §10.2–§10.4 rolling-convergence grid

Campaign run `20260825-042645-70858`, iteration 10, branch `ralph/live-convergence-0824`.
Preregistration: `prototypes/streaming-diarization/live-convergence/PREREGISTRATION-M2-grid.md`
(written before the first decode; its sha256 is recorded inside `grid.json`).

## Answer in one paragraph

**Every geometry in the plan's grid closes most of the live-vs-file text gap, and the plan's own
selection rule picks the cheapest one: a 10-second window on a 10-second stride.** It moves the
trio from live WER `.199870` to `.131861` and content recall from `.9135` to `.9439`, at
`1.000` added decode-audio-second per audio-second — half the GPU work of the previously measured
reference arm, which it also beats on recall. Eleven of the twelve arms pass G1–G3; the twelfth
(`10/5:uniform`) misses G3 at `.9346`. Three findings qualify that verdict and each needs one
owner decision: **(F1)** the selected geometry has no window overlap, so its "stitch policy" is a
no-op and all three policies are literally the same arm; **(F2)** at 10/10 *every* policy publishes
a duplicated phrase at one join per run and zero overlap leaves no stitcher able to remove it,
whereas the overlapping geometries duplicate only under character-proportional ownership and not at
all under uniform or lexical;
**(F3)** *no* arm in the plan's grid can satisfy plan §1.3 G6 (rolling correction p95 `<= 6.0 s`)
at full-window granularity — the best structural floor in the whole grid is `6.46 s`, and the
selected arm's is `8.51 s`.

## Command

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --windows 10/5,10/10,15/7.5,15/10 \
  --stitches char,uniform,lexical \
  --runs 3 \
  --output evidence/live-convergence-0824/M2-rolling-grid/grid.json
```

Exit 0. Per run the grid issues 170 logical requests (80 base spans + 90 windows across the four
geometries) which resolve to **143 distinct audio ranges** — the four geometries share windows, so
e.g. `[0,10]` is decoded once and used by both 10/5 and 10/10, and all three stitch policies replay
one decode of each window. 429 distinct decodes over three independent runs; one in-flight request
throughout, greedy, `DEFAULT_PROMPT` unchanged, `canonical_decode_token_cap` for every request.
Fresh-decode console:
`grid-console-fresh-decodes.txt` (114.8 s wall). The checked-in `grid.json` is a cache replay of
those same decodes through the final script; `decode-cache/run{0,1,2}.json` makes the whole grid
reproducible **with no GPU at all** — point `--cache-dir` at it.

No production code was touched and no service was restarted. File mode has nothing to compare
here and byte-identity is not claimed.

## Controls (all three passed before any arm was read)

| control | measured | published | verdict |
|---|---:|---:|---|
| **P1** base = the recorded 2.5 s span grid, decoded alone | WER `.199870` / recall `.913490` | `.19987` / `.91349` | exact |
| **P2** `10/5:char` reproduces `proto_context_arms` arm `a2` | WER `.128926` / recall `.948477` | `.128926` / `.948477` | exact to 6 dp |
| **P3** at zero overlap the three policies are one arm | identical WER **and** recall, 9/9 case-runs | — | holds |

P1 and P2 landing on the published numbers to every printed digit is the strongest statement this
bundle makes: the bench is the same instrument that produced the `.1289` the plan cites, and the
grid's twelve arms are measured against a base that reproduces the campaign's live baseline
exactly.

**Noise floor at N=3: zero.** All twelve arms and the base returned *identical* WER and recall on
all three runs (`spread` is `0.000000` everywhere in `grid.json`), across three independently
decoded sets of 143 audio ranges. This extends iteration 8's N=2 trio finding to N=3 with fresh
decodes each time and confirms `probe_decode_determinism.py`: a warm decoder is a function.

## The grid

Mean over three runs. `added` is decode-audio-seconds per audio-second beyond the 2.5 s base.
`dup` is joins per run that republished a run of ≥ 2 words. `corr p95` is the **structural floor**
of plan §1.3 G6, in seconds — see F3.

| arm | added | WER | recall | bill | milei | keyu | dup | corr p95 | G1–G3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `10/10:char` | 1.000 | 0.131861 | 0.9439 | 0.198864 | 0.096000 | 0.100719 | 1 | 8.51 | pass |
| `10/10:lexical` | 1.000 | 0.131861 | 0.9439 | 0.198864 | 0.096000 | 0.100719 | 1 | 8.51 | pass |
| `10/10:uniform` | 1.000 | 0.131861 | 0.9439 | 0.198864 | 0.096000 | 0.100719 | 1 | 8.51 | pass |
| `15/10:char` | 1.500 | 0.120262 | 0.9571 | 0.170455 | 0.104000 | 0.086331 | 0 | 11.64 | pass |
| **`15/10:lexical`** | 1.500 | **0.107466** | **0.9597** | 0.170455 | 0.080000 | 0.071942 | 0 | 12.98 | pass |
| `15/10:uniform` | 1.500 | 0.127220 | 0.9520 | 0.176136 | 0.112000 | 0.093525 | 0 | 12.81 | pass |
| `15/7.5:char` | 1.750 | 0.129463 | 0.9530 | 0.198864 | 0.096000 | 0.093525 | 1 | 12.98 | pass |
| `15/7.5:lexical` | 1.750 | 0.113920 | 0.9552 | 0.181818 | 0.088000 | 0.071942 | 0 | 12.98 | pass |
| `15/7.5:uniform` | 1.750 | 0.120106 | 0.9578 | 0.193182 | 0.088000 | 0.079137 | 0 | 12.81 | pass |
| `10/5:char` | 1.833 | 0.128926 | 0.9485 | 0.198864 | 0.080000 | 0.107914 | 1 | **6.46** | pass |
| `10/5:lexical` | 1.833 | 0.121618 | 0.9552 | 0.176136 | 0.088000 | 0.100719 | 0 | 7.75 | pass |
| `10/5:uniform` | 1.833 | 0.146014 | 0.9346 | 0.204545 | 0.104000 | 0.129496 | 0 | 7.75 | **FAIL G3** |

Comparators (frozen `prototypes/live-file-gap-baseline-20260824/trio-60s/results.json`, read at
full precision and asserted to round to the PRD's printed values): live WER trio `.199870`, bill
`.261364`, milei `.144000`, keyu `.194245`. Paired **file** arm on the same audio: `.103946`.
Every arm improves every case; G2 is never the binding gate.

Rolling-PCM high-water mark: `320000` bytes (10 s) or `480000` bytes (15 s) of retained 16 kHz
mono PCM. Request concurrency is 1 by construction, so the endpoint counters the §10.6 resource
gate collects have no offline analogue here; per-arm request counts and per-decode wall times are
in `grid.json` under `cost`.

## Selection — plan §10.4, applied verbatim

> "Choose the least expensive arm passing G1–G3 and all per-case gates. Do not select by TBSA
> alone. If no arm passes, do not implement rolling production code."

Eleven arms pass. Cheapest = `1.000` added, three-way tie at 10/10, broken by name.

**SELECTED: `10/10` — a 10-second witness window on a 10-second stride.**

`mutations/m4-select-by-wer.txt` shows what a different rule would have chosen: ranking on quality
instead of cost selects `15/10:lexical` (WER `.107466`, `1.500` added). The rule is what picks the
arm, and it was fixed before the numbers existed.

## F1 — at 10/10 there is no stitcher, and that is a simplification, not a caveat

Stride equals window, so consecutive windows do not overlap, every window owns its whole range,
and there is no cut to decide. The three "policies" produce byte-identical word sequences (P3).
**Production consequence:** the M2 converger for the selected arm needs no ownership arithmetic,
no lexical alignment, and no word-time interpolation — a window's words replace exactly
`[lo, hi)` and the frontier advances to `hi`. That is materially less code than plan §6's M2
sketch anticipated, and it is the plan §10.4 rule that bought it.

## F2 — the selected arm publishes a duplicated phrase at one join per run

Measured, reproducible, and caused by the decoder rather than by the stitcher:

```
lex_bill_ackman, 10/10, join 4→5 at t = 50.0 s
  window [40,50] tail : ... value, but uh, the. You know.
  window [50,60] head : You know, it's many investors, you know, ...
```

The speaker says "you know" across the 50-second cut; each window transcribes its own side plus
its own reading of the straddling phrase. **With zero overlap there is no shared audio and
therefore no evidence any stitcher could use to detect the repeat.** This is seam severance
(`prototypes/live-file-gap-context/diagnosis.json`) reappearing at the witness layer.

The geometries that *do* overlap show the complementary result: character-proportional ownership
duplicates one join per run (`10/5:char`, `15/7.5:char` — e.g. milei's "on the brink of / brink of
hyperinflation"), because a word straddling the ownership boundary is emitted by both windows with
different interpolated midpoints; **uniform and lexical ownership duplicate nothing anywhere**.

This does not violate ADR-0005's D4. D4 buys *interval* discipline — one owner per interval — and
every arm here has it. What the measurement shows is that interval discipline **does not by itself
prevent duplicated words**, because the duplication is produced upstream by two decoders each
transcribing speech that straddles their shared boundary. If "no word published twice" is to be a
property of the rolling surface, it needs overlap plus a lexical join, not an ownership rule.

## F3 — no arm in the plan's grid can pass G6 at full-window granularity

Plan §1.3 G6 and PRD M2 require rolling correction p95 `<= 6.0 s` after provisional publication.
A word owned by window `[lo, hi]` cannot be corrected before `hi + decode(window)`; it was
published provisionally at `span_end + decode(span)`. `grid.json` reports that difference over
**changed regions only** (G6's own definition), from this run's measured decode latencies. It is a
floor: queue wait, scheduling and portal render only add to it.

| geometry | best floor p95 in the grid | over 6.0 s by |
|---|---:|---:|
| 10/5 | 6.46 s (`char`) | +0.46 |
| 10/10 | 8.51 s | +2.51 |
| 15/10 | 11.64 s (`char`) | +5.64 |
| 15/7.5 | 12.81 s (`uniform`) | +6.81 |

The arithmetic is structural, not incidental. With central ownership the oldest word in a window's
owned region has age `(L + S) / 2`, so `L + S <= 12` is required for a 6-second p95 — and the
plan's cheapest geometry is `L + S = 20`. **Cost and latency rank the geometries in opposite
orders**: the arm §10.4 selects is the second-worst on latency, and the best-latency arm is the
most expensive.

The preregistration fixed this floor as *reported, not selecting*, so the selection above stands
unchanged. But M2 cannot close on G6 with any grid geometry, and that is now known before the
production converger is written rather than after its soak.

## Owner decisions this bundle asks for (one each)

- **D-M2-1 — cost or quality?** §10.4 selects `10/10` (WER `.1319`, `1.000×`). Fifty percent more
  GPU buys `15/10:lexical` (WER `.1075`, recall `.9597`), which is within `.0035` of the paired
  **file** arm's `.103946` and has no join duplicates. Recommendation: **ship `10/10`**, because
  the rule was preregistered, it passes every preregistered gate, and M4's terminal pass — not the
  rolling surface — is where file-parity is gated. Record `15/10:lexical` as the measured upgrade
  path if M2's soak or F2 forces it.
- **D-M2-2 — what happens to G6?** The gate is unreachable inside the plan's grid. Options: (a)
  keep G6 and let M2's row go unsigned on it, as M0d's G2 and M1's G-M1-1 already are; (b) amend
  G6's threshold, which the PRD forbids mid-run; (c) authorise a geometry outside §10.2 with
  `L + S <= 12`, which the PRD also forbids mid-run ("no adding arms beyond the grid").
  Recommendation: **(a)** — measure G6 for real in the §10.6 soak, report it against the floor
  predicted here, and leave the row unsigned if it misses. Nothing downstream is blocked.

## Mutations — five, each caught by its own guard and no other

`mutations.txt`, full console in `mutations/`. Every mutation replays the decode cache, so the
sweep issues **zero MOSS requests**; each runs on a throwaway copy of the script, so neither the
grid nor the plan was edited.

| # | mutation | caught by | result |
|---|---|---|---|
| M1 | the reconciler reads the reference | `_TruthBlind` tripwire | exit 1, `ReferenceReadInsideReconciler` |
| M2 | milei's comparator drifts `.1440 → .1450` | round-trip assert in `load_baseline_scores` | exit 1, `comparator_drift` |
| M3 | ownership regions computed by the literal `a2` formula | `RegionsDoNotTile` invariant | exit 1, invariant raised |
| M4 | selection ranks on WER instead of cost | (none — this is the demonstration) | exit 0, selects `15/10:lexical` instead |
| M5 | the provisional base loses half its spans | P1 bench validity | exit 1, base `.5583` → INVALID, no verdict |

**M3 is the one that changed the code.** The mutation restores `proto_context_arms`'s literal a2
ownership formula (`lo ± (L∓S)/2`). At 15/10 on a 60 s clip the last window's start is clamped
from 50 s to 45 s, and that formula then hands `[47.5, 52.5]` to two windows at once. The
join-duplicate screen — the guard tried first — stayed **silent**, because it compares the
committed *tail* with the fresh *head* while this defect duplicates words in the *middle* of the
previous window's take. It was visible only as a WER regression (`.1203 → .1891`), i.e. only
because it happened to hurt. `plan_windows` now asserts the regions partition `[0, duration]`, and
the mutation is caught at its source.

## Files

| file | what |
|---|---|
| `grid.json` | the full artifact: per run, per case, per arm — scores, cost, every decode window, its ownership region, every selected and dropped word, per-join duplicate check, decode health, correction-age floor, and the final hypothesis |
| `grid-console.txt` | console of the checked-in replay (exit 0) |
| `grid-console-fresh-decodes.txt` | console of the original 516-decode run (exit 0, 114.8 s) |
| `decode-cache/run{0,1,2}.json` | the three runs' decodes; replays the whole grid with no GPU |
| `mutations.txt`, `mutations/` | the five-mutation sweep |
