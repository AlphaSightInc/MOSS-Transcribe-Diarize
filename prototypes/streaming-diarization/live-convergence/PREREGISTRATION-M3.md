# Preregistration - M3 (plan E3 rescoped): witness-owned speaker authority

Written 2026-08-25, campaign iteration 19, **before any S1 arm exists**. Everything below is
fixed: no bound, comparator, clock or arm may be re-decided once a number is seen. The PRD's
rule is verbatim - *"Preregistered gates are immutable mid-run: no tuning thresholds to pass,
no adding arms beyond the grid."*

Scope: plan §11.1 S1 (S2 only if S1 fails gates), 2.5 s base only (Appendix B Q6 deleted the
one-second preview from this campaign). Embeddings strictly from witness-owned speaker
intervals (plan D5).

---

## 1. Why the comparators are restated

M3's PRD gates name the **pre-campaign** live arm: trio DER `.2235 / .1945 / .1112`
(mean bound `.1393`), trio `speaker_accuracy >= .8437`, five-minute DER `<= .0947`. Those
digits were measured on `prototypes/live-file-gap-baseline-20260824/`, before E1 and E2 shipped.

The M2 exit (iteration 18, `evidence/live-convergence-0824/M2-e2-exit/`) measured the surface
the deployment actually serves today, **with no E3 code at all**:

| case | DER | speaker_accuracy | matched-word (v2) |
|---|---|---|---|
| lex_bill_ackman | `.127333` | `.872667` | `.920455` |
| lex_javier_milei | `.117333` | `.882667` | `.920000` |
| lex_keyu_jin | `.089167` | `.910833` | `.985612` |
| **trio mean** | **`.111278`** | **`.888722`** | **`.942022`** |
| keyu-5m | `.088600` | `.911400` | `.954856` |

Every PRD absolute bound is already met by a build that contains no speaker-authority change:
`.111278 <= .1393`, `.888722 >= .8437`, `.088600 <= .0947`. Longer surface segments shrank the
extent artifact plan §3.4 named; the speaker axis moved as a side effect of E2.

**Gating M3 against the pre-campaign arm would let it pass by doing nothing.** So every M3 gate
below is stated against *both* the PRD's absolute bound *and* the M2 exit measurement, and the
binding one is whichever is stricter. That is a strengthening in every row - no PRD bound is
relaxed anywhere.

## 2. What E3 can reach, measured before it is built

`measure_m3_baseline.py` decomposes the deployed scorer's DER into miss / false alarm /
confusion. Only **confusion** is a label the album could have got right; **miss** is speech
nobody published, which no embedding recovers, and false alarm is `0.000000` on all four cases.

| case | DER | miss | confusion | confusion-free floor | confusion share |
|---|---|---|---|---|---|
| lex_bill_ackman | `.127333` | `.090167` | `.037167` | `.090167` | 29.2 % |
| lex_javier_milei | `.117333` | `.117333` | `.000000` | `.117333` | 0.0 % |
| lex_keyu_jin | `.089167` | `.077000` | `.012167` | `.077000` | 13.6 % |
| keyu-5m | `.088600` | `.082700` | `.005900` | `.082700` | 6.7 % |

**A perfect speaker authority - every confusion second fixed, nothing else changed - moves the
trio mean DER from `.111278` to `.094833`: a ceiling of `.016445`. On the five-minute case the
ceiling is `.005900`.** Three quarters of the trio's whole confusion budget
(`.037167` of `.049334`) is in `lex_bill_ackman`.

Unattributed seconds (`S00`, the production literal), and the two-speaker collapse screen:

| case | S00 s | S00 segments | S00 intervals | mixed windows (deployed hop / sliding) | collapsed |
|---|---|---|---|---|---|
| lex_bill_ackman | `0.73` | 3 | 29.63-29.96, 39.84-40.00, 49.75-49.99 | 3 / 9 | **1** |
| lex_javier_milei | `0.00` | 0 | - | 0 / 3 | 0 |
| lex_keyu_jin | `0.00` | 0 | - | 3 / 9 | 0 |
| keyu-5m | `0.56` | 1 | 150.08-150.64 | 5 / 27 | 0 |

The one collapsed window is `lex_bill_ackman` `[20.0, 30.0)`: the reference carries Bill
(20-29 s) and Lex (29-30 s, exactly at the 1.0 s birth floor), and the surface names only
`S01` there - the second voice is *detected* but published as `S00` at 29.63-29.96. Every S00
fragment on both cases is 0.16-0.56 s, i.e. below the 0.5 s matching floor: these are plan
§11.4's microfragments, and §11.4 is a separate candidate, not M3.

Two collapse screens are reported because the deployed one is alignment-dependent:
`lex_javier_milei`'s only reference turn falls exactly on a 10 s window boundary, so the
deployed grid sees **no** mixed window on that case at all. The sliding screen (hop = the
deployed base-span cadence read from the pass manifest, 2.5 s) slides past every turn. **Gates
below use the sliding screen.**

## 3. Arms

| arm | what it is | when it runs |
|---|---|---|
| **S0** | the deployed surface: witness text, speaker labels projected from the 2.5 s base spans (`_project_canonical_speaker`) | already measured - the M2 exit bundle IS S0 |
| **S1** | plan §11.1: embed **witness-owned** speaker intervals, reconcile against the existing album | always |
| **S2** | S1 plus label-invariant disagreement routing between overlapping witnesses | **only if S1 fails a gate** (plan §11.1 wording, kept verbatim) |

The 10/10 geometry does not overlap, so S2's "overlapping witnesses" premise does not exist at
the selected geometry. If S1 fails and S2 is therefore due, that fact is recorded as the reason
S2 cannot be run as written rather than quietly substituting a different arm.

No threshold in the identity stack may move to pass a gate: album `min_match_score .35`,
`min_match_margin .10`, `ALBUM_ADMISSION_SECONDS 2.0`, `ALBUM_BIRTH_MIN_SECONDS 1.0`, the 0.5 s
evidence floor and the 2.5 s hard cap are all frozen for this milestone. Re-calibrating them is
a separate campaign (Appendix B's precedent for the one-second cap).

## 4. Gates

`[PRD]` = named by the PRD's M3 milestone. `[C]` = campaign gate, **stricter** than the PRD,
added because the PRD's comparator is stale (§1) or because the axis is otherwise unfalsifiable.

| id | gate | bound |
|---|---|---|
| G-M3-0 `[C]` | **D5 structural**: every embedding input is a subset of one witness-owned local speaker interval. No prefix, no context, no mixed-window audio, no interval spanning two local speakers. Verified from the arm's own per-embedding log, not asserted. | zero violations |
| G-M3-1 `[PRD]` | trio mean DER | `<= .1393` **and** `<= .111278` |
| G-M3-2 `[PRD]` | per-case DER, no regression | bill `<= .127333`, milei `<= .117333`, keyu `<= .089167` |
| G-M3-3 `[PRD]` | trio mean `speaker_accuracy` | `>= .8437` **and** `>= .888722` |
| G-M3-4 `[PRD]` | five-minute DER | `<= .0947` **and** `<= .088600` |
| G-M3-5 `[C]` | evaluator-v2 matched-word speaker accuracy, per case, no regression (PRD requires it *reported*; a reported number nobody may fail is not evidence) | bill `>= .920455`, milei `>= .920000`, keyu `>= .985612`, 5m `>= .954856` |
| G-M3-6 `[PRD]` | 9-clip identity floor stays green | `pytest tests/test_live_identity_real_corpus.py` exits 0 |
| G-M3-7 `[PRD]` | no speaker collapse on two-speaker mixed windows, sliding screen, per case | bill `<= 1`, milei `<= 0`, keyu `<= 0`, 5m `<= 0` |
| G-M3-8 `[PRD]` | S00 duration does not increase, per case | bill `<= 0.73 s`, milei `<= 0.00 s`, keyu `<= 0.00 s`, 5m `<= 0.56 s` |
| G-M3-9 `[PRD]` | every local speaker maps one-to-one to a meeting identity or abstains (§11.2) | zero many-to-one maps among non-abstentions |
| G-M3-10 `[PRD]` | single-session combined RTF (base MOSS + rolling MOSS + WeSpeaker) `< 1`, refinement queue bounded as at the M2 exit: depth `<= 1`, zero admission refusals, zero stale completions, zero failed windows | as stated |
| G-M3-11 `[C]` | correction-after-provisional p95 does not increase. G6 is already unsigned at `8.756675 s` (arithmetic floor of the 10/10 geometry); adding WeSpeaker to the witness path must not make it worse | `<= 8.756675 s` |
| G-M3-12 `[PRD constraint]` | file mode byte-identical, **both** readings: (a) every pass's `file-hypothesis.jsonl` equals `prototypes/live-file-gap-baseline-20260824/`'s, as G-M2-8 checks; (b) the decoder A/B probe against a HEAD worktree (`probe_file_mode_decode_identity.py`) still hashes `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` | both hold |
| G-M3-13 `[PRD constraint]` | accepted samples == accounted samples, exactly, every session | equality |

Clocks and instruments, fixed here:

- DER / miss / false alarm / confusion / `speaker_accuracy` / WER: the **deployed** scorer's
  `results.json`, produced by `run_paired_passes.sh` against the running service - the same
  path M1 and M2 exited through. Two passes per corpus, means reported, per-pass values shown.
- matched-word speaker accuracy and v2 DER: `evaluator_v2.score_v2` with WebRTC VAD speech
  regions (`webrtcvad_mode1_10ms`).
- S00: `live-hypothesis.jsonl` read through the production `UNATTRIBUTED_SPEAKER`.
- collapse: 10 s windows (the deployed rolling geometry), hop = the deployed hard cap read from
  each pass's own `replay-manifest.json`, second-voice floor = production
  `ALBUM_BIRTH_MIN_SECONDS`.
- latency, queues, RTF, accounting: the §7.4 event stream, read exactly as `verify_m2_exit.py`
  reads it.

## 5. Predictions

Falsifiable, recorded before the arm exists. Being wrong is a finding, not a failure.

- **P1** S1's trio mean DER lands in `[.094833, .111278]`. It cannot beat the confusion-free
  floor without changing what text is published, which is E2's surface and frozen here.
- **P2** Any DER gain is concentrated in `lex_bill_ackman`: it holds 75.3 % of the trio's
  confusion budget.
- **P3** `lex_javier_milei` cannot improve on DER at all (confusion is exactly `.000000`). Any
  DER movement on that case is a **regression**, and G-M3-2 will catch it.
- **P4** The five-minute case moves by less than `.003` absolute DER (ceiling `.0059`).
- **P5** `lex_bill_ackman`'s S00 seconds **decrease** below `0.73`: a 10 s witness segments the
  29 s / 40 s / 50 s turn boundaries once each, where three separate 2.5 s base spans each
  produced a sub-floor fragment. If S00 seconds instead rise, the witness is fragmenting more
  than the base did, which is the opposite of D5's premise.
- **P6** Combined RTF stays below `.30` (M2 exit measured `.133-.157` without WeSpeaker) and
  refinement queue depth stays at `<= 1`.
- **P7** G-M3-11 holds: WeSpeaker work per window is bounded by ~2 local speakers x ~10 s of
  owned audio, which is small beside the 10 s witness decode already on that path.

## 6. Selection and disposition

1. Run S1 on the standing bench (trio + five-minute, two passes each, the M2-exit procedure).
2. **Ship S1 iff every gate above passes.** A passing S1 that merely ties S0 still ships: D5's
   ownership is the architecture E4 builds on, and "no regression" is the stated bar.
3. If S1 fails any gate, run S2 per §11.1 - or record why the arm as written does not exist at
   the selected geometry (§3) - and gate it identically.
4. If neither passes, **E3 ships nothing**: the deployed S0 surface stays, the measurement and
   the failure are written to `evidence/live-convergence-0824/M3-*/`, and the plan §18 row is
   left **unsigned**. That is the same disposition M0(d) G2, M1 G-M1-1 and M2 G-M2-4 received.
5. `.stop` is reserved for a plan §15 **global** stop condition: ambiguous corpus provenance,
   a failing scorer self-test or degenerate control, truth read during reconciliation, a
   promoted authority regressing case-level WER without an accepted trade-off, file mode
   changing, accepted/accounted equality failing, real time not sustained, or terminal audio
   unavailable. A gate miss that trips none of those does not stop the campaign.
6. Losing a gate is never answered by moving a threshold, adding an arm, or re-running the bench
   until the number falls the right way.

## 7. Reproduction

```bash
# the comparator table this preregistration is written from (no GPU, no service)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py \
  --output /tmp/m3-baseline.json

# prove the derived quantities react before trusting them
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py --selftest

# the same instrument, pointed at an S1 arm's passes
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py \
  --passes-root /tmp/m3-s1-<stamp> --output /tmp/m3-s1.json
```
