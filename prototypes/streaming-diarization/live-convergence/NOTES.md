# live-convergence — throwaway experiments for the E0–E4 campaign

Home for the campaign's prototypes (PRD: "Throwaway experiments live under
`prototypes/streaming-diarization/live-convergence/`, never in module code"). Nothing here is
imported by `moss_transcribe_diarize/`.

| file | question it answers | verdict |
|---|---|---|
| `replay_saved_decode_dispositions.py` | do the seven real lost decodes now report the ending that happened? | yes — `evidence/live-convergence-0824/M0b-decode-disposition/` |
| `probe_file_mode_decode_identity.py` | did the A0.2 change move file-mode decoder output? | no — same bundle |
| `evaluator_v2.py` + `compare_evaluators.py` + `cases.json` | can the campaign be scored on a lens a wider timestamp cannot move? | yes — `evidence/live-convergence-0824/M0c-evaluator-v2/` |
| `run_paired_reacquisition.sh` + `verify_paired_reacquisition.py` | do the M0(d) paired gates hold on campaign code? | 4 of 5 — G2 fails on the 5-minute case, `evidence/live-convergence-0824/M0d-paired-reacquisition/` |
| `probe_decode_determinism.py` | is the deployed vLLM decoder bit-reproducible for an identical greedy request? | no when cold, yes when warm — 12 requests gave 2 outputs after an idle gap, 1 output immediately after |
| `diff_live_runs.py` | where do two live runs of the same audio *first* disagree? | 5-minute case: one span (a decode flip); the other 51 are identity cascade |
| `salvage_gates.py` + `compare_salvage_gates.py` + `PREREGISTRATION-M1a.md` | plan §9.1: O1 (hard-cap freeze) or O2 (recomputed VAD ≥ 0.5) as the salvage gate? | **O1** — same words recovered, one fewer false word, no new state; `evidence/live-convergence-0824/M1a-salvage-gate-comparison/` |
| `verify_production_salvage.py` | does the shipped `classify_live_transcript` decide what §9.1 measured? | **yes** — 184 corpus spans + 5 constructed spans agree with the adjudicated O1 column; `evidence/live-convergence-0824/M1-salvage-production/` |
| `run_paired_passes.sh` + `verify_m1_exit.py` | does the M1 build clear the plan E1 exit gates on the deployed service? | 5 of 6 — G-M1-1 misses by .0023 on a pre-M1 decode flip; `evidence/live-convergence-0824/M1-e1-exit/` |
| `attribute_wer_delta.py` | which published segment is a WER delta actually made of? | measures each segment's cost by re-scoring without it — bill's salvage is worth −.034091, the S00 flip +.011363 |
| `verify_adr_text_finalization.py` | does the text-finalization ADR still quote the plan's decisions *verbatim*, as Appendix B Q8 required? | **yes** — D1–D7 byte-identical, one contiguous block, D8–D10 absent; `evidence/live-convergence-0824/M2-text-finalization-adr/` |
| `measure_m3_baseline.py` + `PREREGISTRATION-M3.md` | how much of the deployed DER can a speaker authority even reach, and what must M3 not regress? | at most `.016445` trio DER (`.005900` on the five-minute case); comparators restated against the M2 exit — `evidence/live-convergence-0824/M3-preregistration/` |
| `compare_speaker_authority.py` + `mutate_speaker_authority.sh` | plan §11.1: does a witness-owned speaker authority (S1) beat the deployed projection (S0)? | **no — a tie to 6 dp on every gated axis**, Δ DER `0.000000`; the remaining confusion is segment extents, not voice identity; `evidence/live-convergence-0824/M3-s1-prototype/` |
| `verify_m3_disposition.py` | do the 14 preregistered M3 gates pass, and does the "ship nothing" decision hold against the tree? | **14/14 pass and nothing ships** — every gate is a no-regression gate, so read them with the delta; `evidence/live-convergence-0824/M3-disposition/` |
| `measure_m4_baseline.py` + `PREREGISTRATION-M4.md` | what must a terminal pass land on, and what does converging to the file arm cost? | trio mean WER `.131357 → .103946` is the prize; **two convergence gates are already satisfied by a build that ships nothing**, and on `lex_javier_milei` a no-regression gate is arithmetically impossible beside the PRD bound; `evidence/live-convergence-0824/M4-preregistration/` |
| `remeasure_one_case.py` + `run_paired_case.sh` | can the three-minute case M4 gates (P-M4-A) be measured with the checked-in paired driver's shape rather than a new instrument? | **yes, and it is the one case where the rolling surface beats file mode on text** — rolling WER `.122411` vs file `.126177`, so `terminal == file` fails the preregistered G-M4-3/G-M4-4 there by `.003766` / `.001883`; `evidence/live-convergence-0824/M4-three-minute/` |
| `verify_terminal_tape.py` + `mutate_terminal_tape.sh` | does a session now retain the complete mixed audio a terminal pass needs — all of it, only it, and no longer (P-M4-B)? | **yes** — tape digest equals the corpus digest and a read-back differs in `0` samples on all three trio cases, peak `accepted x 2` bytes, released to `0` bytes with the meeting, and declaring it changes nothing the meeting publishes; `evidence/live-convergence-0824/M4-terminal-tape/` |

`cases.json` is the corpus contract: which saved hypotheses are scored, which corpus each is
scored against, which group's mean it joins, and the means the plan already published for them.
Instance values live there so the drivers stay general.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_evaluators.py --output /tmp/v2.json
```

```bash
# M0(d) paired re-acquisition: four sequential passes, then the gates
prototypes/streaming-diarization/live-convergence/run_paired_reacquisition.sh /tmp/m0d-$(date +%s)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_paired_reacquisition.py --fresh-root /tmp/m0d-<stamp>
```

`run_paired_reacquisition.sh` detaches deliberately: a measurement pass outlives the agent that
started it, and three earlier attempts died mid-run when their caller exited.

```bash
# plan §9.1 O1-vs-O2 salvage-gate comparison over the saved 184-span corpus (zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_salvage_gates.py --output /tmp/m1a.json

# does the SHIPPED classifier still decide what §9.1 measured? (exit 0 = yes; zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_salvage.py
```

```bash
# M1 (plan E1) exit: four warm-decoder passes against the running service, then the gates
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m1-exit-<stamp>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m1_exit.py --fresh-root /tmp/m1-exit-<stamp>

# what is a per-case WER delta made of? (re-scores the real hypothesis without a named segment)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/attribute_wer_delta.py \
  <hypothesis.jsonl> --case lex_bill_ackman --drop 49.75:50.0
```

```bash
# E2 step 1: is docs/adr/0005 still the plan's D1–D7 verbatim? (exit 0 = yes; no service, no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_adr_text_finalization.py
```

`verify_adr_text_finalization.py` reads the plan for every instance fact it needs — including
*which* decisions the record must carry, parsed out of the Appendix B Q8 row's own wording — so
amending the plan's decisions fails the check until the record is amended too. The check is
symmetric: quoting one decision too many fails exactly as loudly as quoting one too few.

`run_paired_passes.sh` supersedes `run_paired_reacquisition.sh` from M1 onward: same four
sequential passes, plus the one discarded warm-up decode the campaign adopted after M0(d)
measured the decoder's cold-start flip. The M0(d) script is kept unchanged because it is that
milestone's reproducer.

```bash
# E2 step 2: plan §10.2–§10.4 rolling grid — 4 geometries × 3 stitch policies × 3 runs
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_rolling_grid.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin \
  --windows 10/5,10/10,15/7.5,15/10 --stitches char,uniform,lexical --runs 3 \
  --output /tmp/moss-rolling-grid.json
# ...replayed with NO GPU by pointing --cache-dir at the checked-in decodes:
#   --cache-dir evidence/live-convergence-0824/M2-rolling-grid/decode-cache
# five mutations, each caught by its own guard (also zero MOSS requests)
prototypes/streaming-diarization/live-convergence/mutate_rolling_grid.sh \
  evidence/live-convergence-0824/M2-rolling-grid/decode-cache /tmp/grid-mutations
```

`compare_rolling_grid.py` imports `prototypes/live-file-gap-context/proto_context_arms.py` as a
library — its decoder, disk cache, span loader, shared speaker timeline and scorer — instead of
rebuilding them, which is why its base control and its `10/5:char` arm reproduce that bench's
published `.19987` and `.128926` to every printed digit. Two things it adds are worth reusing:
`plan_windows` asserts the ownership regions **partition** `[0, duration]` (the literal `a2`
formula does not, once the final window is clamped, and the resulting double-publication is
invisible to a tail-vs-head duplicate screen); and `_TruthBlind` makes reading the reference raise
while an arm is being produced, so "the reconciler sees no reference" is enforced rather than
asserted. Verdict, gates and the three findings: `evidence/live-convergence-0824/M2-rolling-grid/`.

```bash
# E2 step 3a: does the SHIPPED converger reproduce the arm the grid selected? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_production_converger.py
# five mutations, in the production module itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_production_converger.sh /tmp/converger-mutations
```

`verify_production_converger.py` is to M2 what `verify_production_salvage.py` is to M1: it drives
the production class — `RollingTranscriptConverger`'s own window planning, retention and parsing —
over the trio, decoding through `M2-rolling-grid/decode-cache`, and requires the result to equal
the grid's `10/10` column at 6 dp (trio WER `.131861`, recall `.943916`, `1.000×` added decode
audio, proposals tiling `[0, 60 s)` exactly). The decoder is handed a runner that raises, so a
cache miss is a failure rather than a fresh GPU call: a module that asks for a different decode
than the one that was measured cannot quietly pass. Verdict:
`evidence/live-convergence-0824/M2-converger-production/`.

```bash
# E2 step 3b: does the SHIPPED session authority publish that arm, and attribute it? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_session_text_authority.py
# five mutations, in `live_session.py` itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_session_authority.sh /tmp/authority-mutations
```

`verify_session_text_authority.py` closes the loop the grid left open. The grid scored every arm
through `proto_context_arms.SpeakerTimeline` — an *external* relabelling step that presumed the
session would attribute rolling words from the base's own labels. This replays the baseline spans
through the real `LiveSession` publication path, feeds the production converger, applies each
proposal through `LiveSession.apply_text_revision`, and scores `snapshot().effective_transcript`.
The arm survives the trip (trio WER `.131861`, recall `.943916`) **and** the shipped projection
agrees with the measured timeline on 51 of 51 rolling segments. It also samples the surface after
every commit — 98 surfaces, 66 with a rolling prefix beside a provisional suffix — because plan
§5.1's ownership boundary is invisible at the end of a case, where six 10-second windows have
tiled the whole minute. Verdict: `evidence/live-convergence-0824/M2-session-authority/`.

```bash
# E2 step 3c: does the SHIPPED refinement queue schedule the witness without delaying the base? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_refinement_scheduling.py
# five mutations, in `live_arbiter.py` itself, restored from a backup on exit
prototypes/streaming-diarization/live-convergence/mutate_refinement_scheduling.sh /tmp/scheduling-mutations
```

`verify_refinement_scheduling.py` is the one driver here that puts **three sessions on one
arbiter**. Scheduling is a claim about ordering under contention, so it makes every unit of work
go through the real `InferenceArbiter` — the 2.5-second canonical spans as well as the 10-second
rolling windows — and then reads back what left the queue in what order: 98 dispatches, canonical
ahead of a waiting witness 14 times, a witness ahead of waiting canonical 0 times, with the arm
unchanged (trio WER `.131861`). It reuses `verify_session_text_authority.py` as a library
(`commit_span`, `label_of_canonical`) rather than restating the replay path. Appendix B deferred
the *two-session real-time stress*; this is the scheduling-correctness half, which costs no GPU.
One finding worth carrying: the converger's coalesce key is `rolling:<epoch>` and every session
starts at epoch 0, so the key identifies a session only because the runtime builds one arbiter per
session — the driver namespaces it and says so. Verdict:
`evidence/live-convergence-0824/M2-refinement-scheduling/`.

```bash
# E2 step 4: does the real RUNTIME run the witness, and land on the selected arm? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_runtime_rolling.py
# five mutations, in `live_coordinator.py` / `live_service_runtime.py`, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_runtime_rolling.sh /tmp/rolling-mutations
```

`verify_runtime_rolling.py` removes the driver. Every earlier E2 verifier replayed baseline spans
into the objects under test; this one puts audio frames into `LiveServiceRuntime.accept_frame` and
reads the arm out of the session snapshot, with the deployed endpoint configuration, real
`webrtcvad`, the real arbiter, the production canonical pump and the production decode seam
(a runner that replays the grid's recorded answers through `_validate_transcription_response`, so
M1 salvage sees exactly what it sees on the 4070 Ti). Each case runs **twice** — no window decoder,
then one — so both arms come off one instrument: base `.199870` / `.913490`, rolling `.131861` /
`.943916`, every case exact to 6 dp, zero fresh MOSS requests.

Two things it established beyond its own gates. The offline runtime reproduces the **deployed span
grid exactly** (24 / 32 / 24 frozen spans, identical to the checked-in baseline traces), which is
what makes a GPU-free end-to-end verifier possible. And its first draft measured what happens when
the base runs far ahead of the witness: the converger's `2 x window` ring evicts, names
`pcm_evicted`, and rolling stops — degrading to the base path statedly rather than silently. The
driver now paces the base within two spans, which is what real-time pacing produces. Verdict:
`evidence/live-convergence-0824/M2-runtime-wiring/`.

```bash
# E2 step 5: does the rolling witness tell its whole story on the event stream? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_rolling_events.py
# six mutations, in `live_coordinator.py` / `live_service_runtime.py`, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_rolling_events.sh /tmp/event-mutations
```

`verify_rolling_events.py` reads the §7.4 events and the §7.3 snapshot rather than the arm. It
reuses step 4's driver (`verify_runtime_rolling.run_case(..., collect_events=True)`) instead of
rebuilding one, so the runtime, the deployed configuration and the replayed decode seam are the
same ones that verifier measured — and it re-checks the arm, because an event that changed what is
published would not be serialization. Nine gates: one announcement per planned window, one
completion per admitted window carrying §7.4's whole record, revision events that reconcile with
the session's own `text_revision_version`, a **payload vocabulary read out of the production
sources** (36 names) so no payload can carry a word anybody said, JSON round-trip plus replay
reconstruction of both the events and the snapshot, and salvage named exactly where the disposition
says it happened.

Two findings worth carrying. The completion's RTF field is real but the *number* here is the replay
decoder's (~3e-5) — witness cost is §10.6's measurement, not this one's. And four of the six
mutations are caught by the T2 tests alone: a window nobody was waiting for, a refused admission, a
refused revision and a salvaged span are all branches sixty seconds of unhurried trio speech never
takes, so the corpus reading of the stream is necessary and not sufficient. Verdict:
`evidence/live-convergence-0824/M2-event-serialization/`.

```bash
# E2 step 6: does the READER see the selected arm, and is it one replacement surface? (no GPU)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_portal_surface.py
# six mutations, in `live_portal.py` itself, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_portal_surface.sh /tmp/portal-mutations
```

`verify_portal_surface.py` reads the **DOM**. Every gate above this one could stay green while a
page that appended instead of replacing showed a corrected meeting as the meeting said twice, so
this verifier renders each session's whole sequence of snapshots through the portal script the
service actually serves, parses the transcript node back with the production parser, and scores it
with the grid's own scorer. It reuses step 4's driver (`run_case(..., collect_surfaces=True)`) and
the T2 tier's own headless browser (`tests/test_live_portal._run_node_probe`, `servedPolls`), so
there is one browser emulation in this repo and one runtime driver, not two of either.

The arm is on the screen: base `.199870` / `.913490`, rolling `.131861` / `.943916`, per case to
6 dp, screen equal to snapshot on every case. The replacement property is stated as a purity
claim — at **every one of 726 polls** the transcript node equalled an independent render of *that
poll's snapshot alone* — which a page carrying state across polls cannot satisfy.

Two findings beyond its gates. The live album establishes **one canonical speaker per span** on
this instrument (16 on a one-minute two-speaker interview), which is E3's problem and not the
render's, but it is why the screen shows `S01`..`S16`. And the rolling arm prints materially
**fewer, longer rows** than the base arm for the same audio (bill 30 → 21, milei 28 → 14, keyu
26 → 16): a ten-second witness publishes sentences where twenty-four 2.5-second spans publish
fragments, and that is visible before any metric is computed. Verdict:
`evidence/live-convergence-0824/M2-portal-surface/`.

```bash
# E2 step 7: does the EXPORT carry the surface the reader was shown? (no GPU, node required)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_export_surface.py
# six mutations, in `live_speaker_accuracy.py` / `live_surface.py`, restored on exit
prototypes/streaming-diarization/live-convergence/mutate_export_surface.sh /tmp/export-mutations
```

`verify_export_surface.py` reads one meeting **three ways** — the production export, the same
export with the surface removed (the pre-§7.3 reading), and the served portal page's DOM — so the
switch is measured against both the thing it replaced and the thing it must agree with. Plan §14
T3's property, *export text equals visible effective text*, is the gate: 3 cases × 2 arms, same
speaker, same words, same seconds. The rolling arm's numbers now come out of the **export**
(`.131861` / `.943916`), which is the point of the switch — a paired rerun reports the arm the
reader is reading.

Two findings. On the base arm the surface reading and the committed reading agree word for word
with every timestamp inside **one sample**, so preferring the surface whenever the field exists
costs nothing and removes a branch. And the switch first broke the F-certification reducer, which
loads `live_speaker_accuracy.py` out of a bare checkout with `-S` and no installed package: the
display rule therefore lives in the leaf `moss_transcribe_diarize/live_surface.py`, which the
scorer imports as a sibling and `app.live_session` re-exports. Verdict:
`evidence/live-convergence-0824/M2-export-switch/`.

```bash
# E2 EXIT: the gates, measured through the DEPLOYED service (needs the running stack)
prototypes/streaming-diarization/live-convergence/run_paired_passes.sh /tmp/m2-exit-<stamp>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m2_exit.py \
  --fresh-root /tmp/m2-exit-<stamp> --output /tmp/m2-gates.json
# re-score the checked-in passes instead (no GPU, no service, gzipped traces are read in place)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m2_exit.py \
  --fresh-root evidence/live-convergence-0824/M2-e2-exit/passes
# its eight mutations, on a COPY of the passes (originals untouched)
prototypes/streaming-diarization/live-convergence/mutate_m2_exit.sh \
  evidence/live-convergence-0824/M2-e2-exit/passes /tmp/m2-mutations
```

`verify_m2_exit.py` scores the PRD's eight M2 gates on four warm-decoder passes; the clocks and
comparators are fixed beforehand in `PREREGISTRATION-M2-exit.md`. Seven pass: trio rolling WER
**.131357** (bound .150, grid projection .131861), per case .204545 / .096000 / .093525 against
the baseline live .2614 / .1440 / .1942, content recall **.943916** (bound .940), five-minute WER
**.082079** (bound .0985, paired file .050616), combined base+witness RTF `.133–.157` with
rolling depth never above 1, accounting exact on 8/8 sessions, file mode byte-identical.

**G-M2-4 misses and was preregistered to miss**: correction-after-provisional p95 **8.756675 s**
against `6.0 s`. Iteration 10's F3 fixed the floor from measured decode latencies before the
converger existed — with central ownership the oldest owned word has age `(L+S)/2`, so `L+S <= 12`
is required and no geometry in the plan's grid qualifies (10/5 floor 6.46 s, the selected 10/10
8.51 s). The row is unsigned; adding an unmeasured geometry is what the preregistration forbids.

Two measurements worth carrying forward. The witness's serial cost is now priced: a base span
waits behind a running window with p50 `0.6–0.8 ms` but p95 `136–214 ms` and max `0.65 s` on
`lex_javier_milei` — bounded, never dropped, well inside the 2.5 s span cadence. And speaker
quality moved without any E3 work: trio live DER `.111278` mean (baseline live `.1764`), the
five-minute case `.0886` — already inside M3's `<= .0947`, because longer surface segments shrink
the extent artifact. M3 must restate its comparators against this measurement. Verdict:
`evidence/live-convergence-0824/M2-e2-exit/`.

```bash
# M3 (plan E3) preregistration: the comparator table E3 is gated against (no GPU, no service)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py \
  --output /tmp/m3-baseline.json
# prove the derived quantities react before trusting them
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py --selftest
# the same instrument, pointed at an S1 arm's fresh passes
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m3_baseline.py \
  --passes-root /tmp/m3-s1-<stamp> --output /tmp/m3-s1.json
```

`measure_m3_baseline.py` answers the question M3 cannot be gated without: **how much of the
deployed DER is even reachable by a speaker authority?** It decomposes the deployed scorer's DER
into miss / false alarm / confusion, and only confusion is a label the album could have got
right. Trio: `.111278` DER over a confusion-free floor of `.094833`, so a *perfect* speaker
authority wins at most `.016445`, three quarters of it in `lex_bill_ackman`; the five-minute case
can win at most `.005900`; `lex_javier_milei`'s confusion is exactly `.000000`, so any DER
movement there is a regression by construction. It also reports S00 seconds and intervals, and
counts two-speaker collapse on two screens — the deployed 10 s grid, and a screen that keeps the
window but hops by the deployed base-span cadence, because `lex_javier_milei`'s only reference
turn lands exactly on a window boundary and hides from the aligned grid entirely (0 mixed windows
aligned, 3 sliding). Gates use the sliding screen. Instance values come from production
(`UNATTRIBUTED_SPEAKER`, `DEFAULT_ROLLING_GEOMETRY`, `ALBUM_BIRTH_MIN_SECONDS`, and the hard cap
read from each pass's own manifest), never from this file. Contract: `PREREGISTRATION-M3.md`;
verdict and mutation sweep: `evidence/live-convergence-0824/M3-preregistration/`.

---

## `compare_speaker_authority.py` + `mutate_speaker_authority.sh` — iteration 20, M3 step 2: the S1 arm

Verdict: **S1 is measured-neutral.** All four cases, both passes, every gated quality axis
identical to S0 at six decimal places (Δ DER `0.000000`). Full bundle:
`evidence/live-convergence-0824/M3-s1-prototype/`.

```bash
# the arm -- trio costs ZERO MOSS requests (the §10.2 grid already decoded this geometry)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py \
  --cases lex_bill_ackman,lex_javier_milei,lex_keyu_jin,keyu-5m --runs A,B \
  --decode-cache evidence/live-convergence-0824/M3-s1-prototype/witness-decodes.json \
  --output /tmp/m3-s1-all.json
# the derived quantities react
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/compare_speaker_authority.py --selftest
bash prototypes/streaming-diarization/live-convergence/mutate_speaker_authority.sh /tmp/m3-mut-out
```

This is plan §11.1's S0-vs-S1 comparison. S0 is not recomputed: it is the M2 exit bundle read
through the production export, and the run refuses unless that export reproduces each pass's own
`live-hypothesis.jsonl` and the deployed `results.json` axes to `1e-6`. S1 embeds each 10 s
witness's **owned** speaker intervals with the production WeSpeaker encoder and matches them
against a causally-rebuilt production `FingerprintAlbum` using the production matcher
(`assign_speakers`); a local speaker the album cannot name is left to the session's projection,
and the witness never births a canonical speaker (plan §6 M4 step 5). Every identity rule --
`min_segment_samples`, the admission and birth floors, `min_match_score`/`min_match_margin`,
the encoder asset -- is read from the DEPLOYED provider manifest, never spelled here.

Why S1 ties, and it is the finding worth keeping: the surface's remaining confusion is **not a
voice-identity error**. Post-hoc decomposition (no arm reads truth) puts 63 % of the bench's
4.73 confused seconds in segments that *straddle a reference turn* -- a segment-extent defect no
label from any authority can fix -- 27 % in `S00` fragments below the 0.5 s evidence floor
(plan §11.4's separate candidate), and only 10 % (0.48 s in the whole bench) in the one class a
better voice match wins outright. The label-only ceiling is `.00672` trio mean DER, not the
`.016445` the confusion-free floor suggested, and S1 realises none of it: its only two changes
are 0.16 s and 0.24 s microfragments on `lex_bill_ackman` where it replaces `S00` with a name the
reference says is the wrong one.

Cost, measured: marginal WeSpeaker RTF `.1306` (trio) / `.1371` (5 m) on top of the M2 exit's
`.133-.157`, at ~1.0-1.1 s per witness embed. That per-window latency is why P7 is at risk: a
resolver serial on the witness path would very likely breach G-M3-11's `8.756675 s` correction
p95, which is already unsigned.

Probes: `I1` swapping every local `Sxx` name changes nothing (the label-invariance plan §11.1
requires); `M1` collapsing every witness segment onto one local moves S1's DER `.127333 ->
.135833`; `M2` an album that enrols nobody produces 6 abstentions and 0 relabels; `M3` a
corrupted export fails the S0 control and exits 1; `M4` one second of prepended context produces
14 D5 violations *and* changes the mapping, which is D5's premise measured rather than asserted.


## `verify_m3_disposition.py` — iteration 21, the M3 exit: score the gates, record D-M3-2

```bash
# the 14 gates, the disposition checks and the decision record (no GPU, no service, ~10 s)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m3_disposition.py \
  --output /tmp/m3-disposition.json

# 21 reactions: every gate pushed past its own bound, plus the disposition and gate-set contracts
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_m3_disposition.py --selftest
```

**All 14 gates pass and nothing ships.** Those are one result, not two, and this driver exists so
they cannot be quoted apart. Preregistration §1 bound every M3 gate to the stricter of the PRD
bound and the M2 exit measurement — the right call, since the M2 surface already beat the PRD's
pre-campaign comparators with no E3 code — but it makes every gate a **no-regression** gate, and a
build that ships nothing regresses nothing. The table certifies exactly two things: the served
speaker surface did not regress, and the S1 arm is structurally correct (zero D5 violations,
one-to-one or abstain, label-invariant). It does not certify that E3 delivered quality; the
S1-minus-S0 delta is `0.000000` on every axis of every case.

D-M3-2 = **O3, ship nothing**. `PREREGISTRATION-M3.md` §6.2 said a passing S1 ships even on a tie,
and gave one reason — *"D5's ownership is the architecture E4 builds on"*. Plan §12.3 steps 4–5
falsify it: the terminal pass runs the existing 150/120 `WindowedRunner` over the mixed tape and
resolves terminal identities there, so E4 never calls the rolling resolver. Deviating because a
preregistered *premise* is falsified by a document written before it is a different act from
deviating because a number came out wrong; the other three reasons (S1's two wrong relabels, the
`.00672` ceiling it realises none of, the `.1306` RTF) are all measured too.

Four properties keep the scoring from agreeing with itself: the gate id set is parsed out of the
preregistration in **both** directions; every numeric bound the driver applies must appear
**verbatim in that gate's own row**, so no threshold can be tuned here; `--selftest` flips all 14
gates plus the 5 disposition checks and 2 gate-set contracts; and "ship nothing" is read off the
tree (no speaker-encoder import in `live_transcript_convergence.py`, `moss_transcribe_diarize/`
unchanged since the commit the deployed passes were taken from — otherwise those passes would not
be a fresh run of the served surface).

Two gates pass for reasons worth stating, both in the bundle NOTES §4: G-M3-8 ("S00 must not
increase") passes on `lex_bill_ackman` because S1 trades an honest abstention for a confident
wrong name, which the gate cannot see; G-M3-11 passes only because nothing shipped — the number
*is* the M2 exit's own already-unsigned p95.


## `measure_m4_baseline.py` + `PREREGISTRATION-M4.md` — iteration 22, M4 step 1: the terminal comparator

```bash
# the comparator table M4's gates are written against (no GPU, no service, ~20 s)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py \
  --output /tmp/m4-baseline.json

# every derived quantity pushed until it reacts
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py --selftest
```

M4 is the only milestone in this campaign gated against a **target** rather than a no-regression
bound: plan G8 (`terminal WER within .010 of the paired file arm`) plus the owner-directed
prerelease DER companion (`.020`). The comparator is the file arm of the *same pass*, and it is
stable — identical to the pre-campaign file arm on all four scored axes and all four cases with a
pass, across eight production changes. If terminal lands on it, trio mean WER goes
`.131357 → .103946` and the five-minute case `.082079 → .050616`.

Three things had to be written down before any terminal number existed:

**Two of the ten convergence readings are already satisfied by the surface shipped today.**
`lex_javier_milei` WER sits `+.008000` from its file arm against a `.010` tolerance;
`lex_keyu_jin` DER sits `+.010167` against `.020`. Those two gates cannot demonstrate that a
terminal pass did anything, and the instrument prints `ALREADY INSIDE` on exactly those rows.

**Converging to file is a regression on one case, and a no-regression gate there is
arithmetically impossible.** On `lex_javier_milei` the file arm is worse than the rolling surface
by `+.034500` DER, `-.034500` speaker accuracy and `-.036069` coverage — each beyond the
convergence tolerance, so every value the PRD bound admits is worse than what the deployment
already publishes. A campaign gate may only *strengthen* a PRD bound, so these are recorded as
decision D-M4-2, not as gates.

**The extent-free axes say four fifths of that regression is the metric, not the surface.**
Evaluator v2 over VAD speech regions: terminal == file costs that case `0.000000` content recall,
`0.000000` matched-word speaker accuracy and `+.007255` speech-region DER, while gaining `.008`
WER. Every other case improves on every v2 axis. That is why D-M4-2 accepts the deployed-metric
regression and requires all seven numbers published together — never the trio mean alone.

Structural facts read from production (`plan_windows`, `WindowedRunner` 150/120,
`LIVE_SAMPLE_RATE`, `PCM16_BYTES_PER_SAMPLE`): the terminal pass plans **1 / 2 / 3** windows at
60 / 180 / 300 s, so on the trio it is the *same call* file mode makes and `terminal == file` is
an identity there; and the largest complete tape in scope is **9.155 MiB**, which is what makes
D-M4-1 (the tape lives in memory, not on `live_tape.py`'s opt-in disk store) safe — enabling the
disk store would change the deployment posture every gate in this campaign was measured against.

Three preconditions block the milestone, and the instrument names rather than hides the first:
`lex_adam_frank` (3 min) has **no live pass in this campaign**, so M4 gates 3 of 5 cases until it
is acquired; no session retains a complete tape today; and the three §7.4 terminal events plus the
`running`/`failed`/`unavailable` finalization statuses have no producers.

## The three-minute comparator (P-M4-A, iteration 23)

`lex_adam_frank` (180 s) had never been through the live path in this campaign, so two of M4's
five gated cases had no comparator. Two warm-decoder paired passes against the deployed service
close that precondition — `measure_m4_baseline.py` now prints `MISSING COMPARATOR: none`.

The case is the corpus's counterexample. On every other case the paired file arm is ahead on
text by `.008` to `.045`; here the **rolling surface is ahead by `.003766`** (WER `.122411` vs
`.126177`). Three preregistered consequences, all fixed before the pass existed:

- G-M4-1 is **already inside** on this case (`.003766` ≤ `.010`) — the third of ten convergence
  readings a build that ships nothing passes, where the preregistration predicted two.
- G-M4-3 binds terminal WER at the pass's own rolling arm, `.122411`, and P1 predicts terminal
  equals the file arm, `.126177`. **They cannot both hold.** The gate is still satisfiable in
  principle (any terminal WER in `[.116177, .122411]` clears both), so it stays a gate, and its
  bound is not moved.
- G-M4-4 fails the same way on the extent-free axes: v2 content recall and matched-word speaker
  accuracy are `.951036` rolling against `.949153` file, `-.001883`.

Everything else the case contributes is a gain for converging: DER `-.026667`, speaker accuracy
`+.026667`, coverage `+.024238`, v2 speech-region DER `-.012130`. Terminal plans **2 windows**
(`[0, 150)`, `[120, 180)`) — the same plan file mode runs, so `terminal == file` is an identity
here too.

Both live passes are **word-identical** (546 words) and both file arms byte-identical; the only
spread is segment extent, `3.3e-4` on DER — the trio's signature, not a decode flip. `runs_agree`
is `False` only because that flag compares every axis exactly.

`remeasure_one_case.py` is the checked-in five-minute driver's shape with the case lifted out of
the constants, and its `--selftest` checks that instead of asserting it: the replay keywords and
base URL are parsed out of `remeasure_5m_case.py` with `ast`, and its scoring path must reproduce
a checked-in campaign pass's own numbers to `1e-12` (it reproduces them exactly).

```bash
# acquire a paired comparator for any allowed case (needs the running service)
prototypes/streaming-diarization/live-convergence/run_paired_case.sh /tmp/m4-3min-<stamp> \
  adam3m lex_adam_frank \
  prototypes/streaming-diarization/data/real/calibration_diarization_3min/samples/lex_adam_frank

# the comparator table, now five measured cases (no GPU, no service)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/measure_m4_baseline.py --output /tmp/m4.json
```


## `verify_terminal_tape.py` + `mutate_terminal_tape.sh` — iteration 24, M4 step 3a: the complete tape

`PREREGISTRATION-M4.md` §3's precondition **P-M4-B** said no session retains a complete tape, so a
terminal 150/120 pass had nothing to run over. It does now: `CompleteMixedTape`
(`app/live_tape.py`), declared through `LiveServiceBounds.max_tape_bytes`, held by the coordinator
beside the two retentions it already had, released at `session_closed` and at any terminal failure
with one `session_tape_released` event carrying the accounting. The decision record is the
**2026-08-25 addendum to ADR-0003 (D8)**, which is where ADR-0005 deferred it.

The verifier runs each trio case twice through the real runtime — once with a declared capacity and
once with none — so inertness is a before/after on one instrument. Trio: tape samples `960 000`,
peak `1 920 000` bytes, gap manifest empty, read-back differing samples **0**, max absolute delta
**0**, bytes after release **0**, and zero fresh MOSS requests (294 replays). The capacity table
read from `LIVE_SAMPLE_RATE` / `PCM16_BYTES_PER_SAMPLE` reproduces prediction P5 exactly:
`1 920 000 / 5 760 000 / 9 600 000` bytes at 60 / 180 / 300 s.

Two design points worth not re-deriving. A hole is **refused, never zero-filled** — zero-filled PCM
is silence, and a terminal pass may not decode silence the meeting never contained, so a
non-contiguous frame degrades the tape by name and the gap manifest reports the interval. And
`retained_high_water_samples` on the rolling ring is reported rather than compared, because two
identical no-tape runs already disagree about it (208000 vs 168000 measured across repeats); the
verifier runs the control arm twice so the reader can see that rather than take it on trust.

**Still owed by E4 before its exit measurement:** the deployed service declares no capacity, so it
still retains no tape. Declaring `bounds_config.max_tape_bytes` in the deployed manifest (and
recomputing its `bounds_config_hash` / `component_config_hash`; `combined_config_hash` is
`f(decoder, endpoint, identity)` and does not move) plus a restart is a step the terminal build
owes.

```bash
# nine gates on the real runtime over the trio; no GPU, zero MOSS requests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_terminal_tape.py --output /tmp/tape.json

# every property is load-bearing (production files restored on exit, including on failure)
prototypes/streaming-diarization/live-convergence/mutate_terminal_tape.sh /tmp/tape-mutations
```
