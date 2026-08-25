# M3 (plan E3 rescoped) — gate table and disposition

**Campaign iteration 21, 2026-08-25. All 14 preregistered M3 gates pass. Nothing ships.**

The two sentences have to be read together, and this bundle exists so they cannot be separated.

---

## 1. The decision — D-M3-2 = O3

**Record E3-S1 as measured-neutral, ship nothing to production, leave the plan §18 E3 row
unsigned with this bundle plus `M3-s1-prototype/` as its evidence.**

The alternatives on the table since iteration 20 were O1 (ship the rolling speaker resolver
inside the converger) and O2 (ship it through the existing label seam so the correction clock is
untouched). Four measured facts decide against both.

**F1 — the preregistration's own reason for shipping a tie is falsified by the plan.**
`PREREGISTRATION-M3.md` §6.2 says *"a passing S1 that merely ties S0 still ships: D5's ownership
is the architecture E4 builds on"*. Plan §12.3 steps 4–5 say the terminal pass runs the existing
150/120 `WindowedRunner` over the mixed tape and resolves terminal identities there. E4 never
calls the rolling resolver. The premise failed, not the gate — which is the one kind of
deviation from a preregistration that is not gate-shopping, because it is checkable against a
document written before either.

**F2 — S1's only two output changes on the entire bench are wrong.** `lex_bill_ackman`
39.84–40.00 s *"Right?"* and 49.75–49.99 s *"You know."*, both named `speaker-0002` where the
reference says Bill. Misattributed seconds go .48 → .88. It is better on nothing.

**F3 — there was almost nothing to win, and it was known before the arm was built.** The
label-only ceiling is **.00672** trio mean DER: 63 % of the remaining confusion is published
segments that straddle a reference turn (a segment-**extent** defect no label can fix), 27 % is
sub-0.5 s microfragments (plan §11.4, a separate candidate), and only 10 % — 0.48 s in the whole
bench — is a voice match a better authority wins outright. S1 realises `0.000000` of it.

**F4 — the cost is real.** `.130594` RTF trio / `.137078` five-minute of extra WeSpeaker work,
at 1.02–1.14 s per witness embed, against a correction-after-provisional p95 that is *already*
unsigned at 8.756675 s.

Not a `.stop`: no plan §15 global stop condition fired (no case-level WER regression, file mode
unchanged, accounting exact, scorer self-tests green, no reference truth read during
reconciliation).

## 2. What the gate table does and does not certify

Preregistration §1 bound every M3 gate to **the stricter of the PRD bound and the M2 exit
measurement**, because the PRD's comparators predate E1/E2 and the M2 exit surface already beat
them with no E3 code at all. That was the right call — it stopped M3 passing by doing nothing on
the *quality* axes — but it makes every gate a **no-regression** gate, and a build that ships
nothing regresses nothing.

So read the table as two claims, and only these two:

- **The served speaker surface did not regress.** Trio mean DER `.111278`, speaker accuracy
  `.888722`, five-minute DER `.0886`, S00 seconds unchanged, one collapsed window, file mode
  byte-identical, accounting exact.
- **The S1 arm is structurally correct.** Zero D5 violations across 8 sessions and 118
  witness-owned embedded units, every local speaker mapped one-to-one or abstaining, mapping
  label-invariant.

It does **not** claim E3 delivered quality. The S1-minus-S0 delta is `0.000000` on DER, speaker
accuracy, matched-word speaker accuracy and WER, on every case, in both passes.

## 3. The table

| gate | verdict | arm | instrument | value vs bound |
|---|---|---|---|---|
| G-M3-0 D5 structural | PASS | S1 | offline-replay | 0 violations |
| G-M3-1 trio mean DER | PASS | S1 | offline-replay | `.111278` ≤ `.111278` (PRD `.1393`) |
| G-M3-2 per-case DER | PASS | S1 | offline-replay | `.127333` / `.117333` / `.089167`, all equal |
| G-M3-3 trio speaker accuracy | PASS | S1 | offline-replay | `.888722` ≥ `.888722` (PRD `.8437`) |
| G-M3-4 five-minute DER | PASS | S1 | offline-replay | `.0886` ≤ `.0886` (PRD `.0947`) |
| G-M3-5 v2 matched-word, per case | PASS | S1 | offline-replay | `.920455` / `.920000` / `.985612` / `.954856`, all equal |
| G-M3-6 9-clip identity floor | PASS | served | fresh run | `pytest` exit 0 |
| G-M3-7 no speaker collapse | PASS | S1 | offline-replay | 1 / 0 / 0 / 0, sliding screen |
| G-M3-8 S00 does not increase | PASS | S1 | offline-replay | `.33` / `.00` / `.00` / `.56` — see §4 |
| G-M3-9 one-to-one or abstain | PASS | S1 | offline-replay | 0 many-to-one maps |
| G-M3-10 combined RTF < 1, bounded queues | PASS | served + S1 cost | projected | max `.287598`, depth ≤ 1 on 8/8 |
| G-M3-11 correction p95 does not increase | PASS | served | deployed | `8.756675` = the bound — see §4 |
| G-M3-12 file mode byte-identical | PASS | served | deployed + fresh run | hypotheses identical; decoder digest `ad381d8b…` |
| G-M3-13 accepted == accounted | PASS | served | deployed | 8/8 sessions equal |

Instruments, never blended: **deployed** = iteration 18's four warm-decoder passes
(`M2-e2-exit/passes/`, the surface the service actually served); **offline-replay** = iteration
20's arm over those same passes, with the S0 control reproducing the deployed scorer to 1e-6;
**fresh run** = executed by this command today; **projected** = deployed measurement plus the
arm's separately measured marginal cost.

## 4. Two gates that pass for reasons worth stating

**G-M3-8 passes on `lex_bill_ackman` because S1 puts a confident wrong name on the two fragments
the projection honestly abstained on.** S00 falls `.73 → .33`; misattributed seconds rise
`.48 → .88`. "S00 must not increase" cannot see that trade. It is the clearest instance in this
campaign of a gate being satisfied by the wrong mechanism, and it is why F2 above outranks it.

**G-M3-11 passes only because nothing shipped.** The number *is* the M2 exit's own already-
unsigned p95. Iteration 20 priced the arm at 1.02–1.14 s per witness embed; run serially inside
the witness path (O1) that lands directly on this clock. That risk is what made O2 — publish
through `revise_labels` *after* the text revision — the fallback rather than O1, had the owner
wanted D5 ownership in the code regardless of measured effect.

## 5. How the scoring is kept honest

`verify_m3_disposition.py` cannot quietly agree with itself:

1. **The gate set is parsed out of `PREREGISTRATION-M3.md` §4**, both directions. Editing the
   preregistration's table without editing the driver fails the command; scoring a gate the
   table does not contain fails it too.
2. **Every numeric bound the driver applies must appear verbatim in that gate's own row.** A
   threshold cannot be tuned in the scorer to make a gate pass.
3. **`--selftest` pushes each of the 14 gates past its bound and requires it to flip**, plus the
   five disposition checks and the two gate-set contracts — 21 reactions, 0 failures.
4. **"Ship nothing" is read off the tree, not asserted**: the rolling converger is checked for
   any speaker-encoder or album import, and `moss_transcribe_diarize/` is checked to be
   unchanged since the commit the deployed passes were taken from (otherwise those passes would
   not be a fresh run of the served surface).
5. **The S1 bundle is hashed against its own `sha256.txt`** before a number is read from it.

## 6. Reproduce

```bash
# the whole table, the disposition checks and the D-M3-2 record (no GPU, no service, ~10 s)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m3_disposition.py \
  --output /tmp/m3-disposition.json

# prove every gate reacts before trusting the table
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m3_disposition.py --selftest
```

## 7. Files

| file | what it is |
|---|---|
| `gates.json` | the 14 scored gates, the gate-set contract, the five disposition checks, the D-M3-2 record |
| `console.txt` | the rendered table and decision as printed |
| `selftest.txt` | 21 reaction checks, 0 failures |
| `pytest-full.txt` | full suite at the disposition commit |
| `sha256.txt` | digests of this bundle |

Upstream evidence this bundle reads rather than repeats: `../M2-e2-exit/` (the deployed passes
and their gates), `../M3-preregistration/` (the bounds and the ceiling), `../M3-s1-prototype/`
(the arm, its per-embedding log and its cost).

## 8. What is left on the speaker axis, for the next campaign

Neither item is in this campaign's scope; both belong in the plan §18 record so the next one
starts from the decomposition rather than from the confusion total.

- **Segment extents own 63 % of it.** A published segment that contains two reference speakers
  is partly wrong whatever single label it carries. That is E2's frozen text geometry, not a
  speaker authority.
- **Microfragments own 27 %.** Sub-0.5 s `S00` fragments below the evidence floor — plan §11.4's
  causal-adoption candidate, which S1 reached for and got wrong twice.
