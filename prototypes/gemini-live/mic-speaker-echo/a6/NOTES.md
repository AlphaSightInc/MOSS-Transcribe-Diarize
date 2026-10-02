# R5B-A5 — offline diagnosis and rejected/qualified candidates

## Six-part contract, frozen before measurements

1. Structural question: why does a confirmed prefix reappear when an ongoing preview changes, and can a minimum retained cut prevent it without removing speech newer than confirmation?
2. Minimum primitives: original turn key + lane (continuity/isolation), comparable units + spans (count/render), current confirmed frontier (time authority), witnessed text cut and exact snapshot prefix (separate evidence). Storage/model/vendor are replaceable.
3. Invariants: prefix-only removal; no cross-lane borrowing; clear count state on turn end, identity loss or confirmed retreat; reset on shrink below remembered N; no additional fresh speech loss. D15 permits old omissions to disappear.
4. Unknowns: stress captures have post-trim rows, counters only in c6s, no complete raw/provider history, original keys or snapshot witness. Exact 254.45s input cannot be recovered. Publication clocks date spelling, not necessarily speech. Later-solid alignment is a proxy, not acoustic truth.
5. Falsifier: any added fresh loss on recorded evidence rejects that rule. A zero measurable proxy loss with unknown raw/timing is not qualification. Retain negative results, no tuning after seeing them.
6. Tools: offline production functions and recorded snapshots identify the real matching failure. Existing A4 populations provide original events/keys and rolling commits. Print full inputs/state/output to receipts. No provider, audio playback, hosts, ports or product edits.

## Frozen candidates and scoring

C0: current product text cuts + exact clock snapshot; original published output is baseline on stress captures.
C1: max(C0,last valid same-turn count N); keep N while confirmed frontier has not retreated and current units >=N. A shrink discards that prior N. Seed from C0; retain new maximum. Clear on final/turn removal; do not compare prefix text. Stress continuity is conditional because source keys were not captured.
C2: current text rule with only the asymmetric shown-side gap ceiling changed 16 ->24 (preview gap<=1, next block>=2), composed with unchanged remembered-prefix/time rules. 24 is the specific observed gap, not a tuned/general threshold; all other thresholds unchanged. Reproduce gap failure first, then measure this single candidate, no sweep.

Populations: complete A4 Mandarin188s (366 publications), English302s (575), R5-D cell (64); public stress c6s300s and c6 audio0–960s (965s tape incl lead/tail). Stress re-trimming already-published rows is an explicitly separate experiment, never full raw-engine parity.
Metrics: repeat residue = matched same-lane solid runs>=5 units integrated by next observation delta (units*seconds); report whole-history and bounded-tail independently. Fresh loss = later-solid frontier alignment proxy (absolute and additional over C0), plus known first-publication additions separately. Neither implies acoustic word truth. Correct-output changes = changed observations whose C0 has zero repeat and zero proxy loss when boundary is verifiable. Unknown boundaries remain unknown. Rates use input audio durations; event rates count continuous large-repeat episodes, not each poll/frontier.

One command from worktree root:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python prototypes/gemini-live/mic-speaker-echo/a6/run.py`
Full state JSONL and summary JSON: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A5/`.

## Registered additional falsifier (before execution)

The later-solid proxy selects earlier repeated phrases: c6 cut265 vs proxy263 flags
`good friends`, but those words are already in the current solid row ending644.9s.
At773.25s it selects old `out of it` at raw273 instead of the current frontier near746.
Therefore retain all6,322 C2 flags as conservative screening flags, never actual lost
speech. No candidate or original scoring tuned to erase them.

Known-clock rewrite control: use60 recorded English units as old speech published14s,
confirmed15s; publish the same original turn at20s after deleting15 old head units,
followed by20 distinct recorded Mandarin units representing fresh speech at16–20s.
65 current units >= previous60; same key/frontier; C1 must preserve all20 fresh units.
C0 production text+exact snapshot and C2 remain comparators. This artificial composition
attacks the observed rewrite primitive; it is NOT another recorded service stream or a
measured frequency. Any known fresh unit removed rejects the count rule, independent
of incomplete stress captures. Keep original corpus numbers and this control separate.

## Results and decision

**Retain C0. C1 FAILS the fresh-speech invariant. C2 is not a repair of c6s and
fails conservative fresh-loss screening on the old run.** Grey text has no per-word
clock. A count is a location in a particular spelling: a rewrite can move fresh
speech before that location. Preserving the count cannot preserve time ownership.

### Q1 — what changed at255.1s?

| Recorded input/output |254.45s |255.10s |
|---|---:|---:|
| Raw comparable units, system lane |880 |905 |
| Text-rule hidden |801 |0 |
| Additional clock hidden |0 |1 |
| Shown comparable units |79 |904 |
| Shown characters |364 |4252 |
| Rendered audio extent |240–256.492s |240–257.492s |
| Current visible-solid frontier, audio clock |239.9s |239.9s |

All effective solid rows (text, authority, lane and extents) are identical between
these samples. Saved counters have no overflow/errors (max pending46). A rolling
replacement of visible solid does **not** explain this jump. The next observed
frontier change is265.05s (254.8s audio clock). FIX5A invalidates only when a rolling
revision removes a provisional-authority solid row. These observations show no
such removal; exact intervening calls and remembered-cut memory were not captured,
so internal invalidation is not asserted impossible.

Production `_repeated_head` on the255.10s exposed text returns0 against that exact
solid. SequenceMatcher's run breaks at preview index399 (`yeah`, zero based), after
24 unmatched solid units and0 unmatched preview units. The next block has size1:
it fails both8/8 and16/1-with-next-size>=2 joining rules. The earlier eligible head
blocks cannot reach the solid frontier, so the complete head rule returns0.

The one missing raw unit is not recoverable. As a separate reconstruction hypothesis,
prepend `been` (the next fully exposed final at256.4s starts `been Alt Universe`). This
produces exactly905 units and still a0 cut. It introduces an earlier73/1 gap after
the initial common `been` singleton, but later head candidates get past that false
start and still stop at the24/0 singleton gap. The cause does not depend on guessing
the missing unit. The gap text corresponds to the interviewer speaking over the
answer; the provider preview omits it.

A remembered prefix requires exact comparable-unit equality through801 units;
a publication whose first two units already disagree with its eligible snapshot
cannot use that snapshot as proof. This is consistent with a provider rewrite
invalidating the remembered cut. **Exact254.45s raw head, exact remembered prefix,
exact snapshot text/clock, and exact provider-final event remain UNKNOWN.** A full
causal claim about which internal memory entry was dropped is not supportable.
Numerical diagnostics identify the two independently reproducible failure boundaries:
text alignment stops at the large gap; clock proof stops at the rewritten head.

### Q2 — why only1 clock unit?

The time rule cuts the exact unit prefix shared with the latest eligible same-turn
snapshot, not a time-proportional fraction of the905 units. Additional clock cut1
with text cut0 proves agreement at raw index0 and the first disagreement at index1.
Published unit0 is `alt`, so raw unit1 is `alt`; the witness's unit1 differs. The
removed raw unit0 is UNKNOWN (`been` is only supported by the next final). Neither
witness nor raw pre-cut text is logged; do not fabricate their complete wording.

Confirmed sample3,838,400 /16000 =239.9s is an audio clock. Receipt offset2.946s
makes it236.954s elapsed (~237.0s in the brief). Snapshot-prefix comparison and
published post-cut comparison therefore have different first units; the visible
`Alt Universe` starts *after* the1-unit clock cut. A maximum of text/time cuts cannot
recover the801-unit cut once both proof paths fail.

### Q3 — old build and A4 rates

Old c6 at653.81s: the304-unit published system row starts `I you know it took me a
while to exit…`; production head cut0. Its matching run stops at preview index252
because the solid contains22 additional units, preview gap0, next block13. This is
the same >16 gap boundary. The old page receipt measures up to320 repeated units,
147.6 seconds with>=10 repeat over the960-second source (server151.0s). Its long
source narrative remains exposed through803.72s. Counting one narrative episode,
not each frontier-dependent threshold dip:1/960s =3.75 observed episodes/hour.

c6s: one long episode255.10–277.89s in snapshots (22.79s); page receipt22.3s with
>=10 units, worst833.1/300s =12 observed episodes/hour. The two runs overlap public
audio but have independent provider transcriptions/builds: **do not treat these
small-sample rates as forecasts or pool them as independent unique audio**.

A4 complete product replay: Mandarin366 publications, maximum whole-history
row-overlap13 units; English575, maximum6; R5-D64, maximum0. No>=100-unit episode
and no same-original-turn positive cut collapsing to0 while frontier is nonretreating
and row count remains>=the previous cut:0/187.89s,0/304s,0/40s (each0 observed/hour).
The historical `en-302s` bench label is retained, but its loader's source `audio_s`
is **304.0**; use304s for measured duration. Short script/rewrite residue remains;
0 occurrences of this large symptom does not mean all preview duplication is fixed.

### C0/C1/C2 matrix

Repeat residue below = same-lane, whole-history matched runs>=5, summed across rows,
integrated by next observation delta, **unit-seconds**. This can count genuine later
repetition. Bounded-tail results are separate in the JSON; counts are not page metrics.
Fresh column = **additional later-solid proxy flags over C0**, in unit-observations,
not distinct spoken words. Correct-output changes require zero C0 repeat and a
verifiable proxy boundary with no baseline loss.

| Population / seam |C0 repeat |C1 repeat |C2 repeat |C1 / C2 added proxy loss |C1 / C2 already-correct changes |
|---|---:|---:|---:|---:|---:|
|Mandarin187.89s, complete pipeline366 |328.00 |327.00 |328.00 |0 /0 |0 /0 |
|English304s, complete pipeline575 |38.50 |38.50 |38.50 |0 /0 |0 /0 |
|R5-D40s, complete pipeline64 |0 |0 |0 |0 /0 |0 /0 |
|c6s300s, published repair478 |18868.27 |1730.19 |18868.27 |0 /0 |0 /0 |
|c6960s, published repair868 |73988.68 |73988.68 |2636.83 |0 /6322 |0 /0 |

Bounded-tail repeat unit-seconds C0/C1/C2: Mandarin197.5/196.5/197.5;
English38.5/38.5/38.5; R5-D0/0/0; c6s6264.06/1637.69/6264.06;
c634295.42/34295.42/2231.04. Two stress lanes are included; whole-history stress
metrics can count the fixture's genuine repeated microphone questions.

C1 changes1/366 Mandarin calls (at69s:144->145 cut),0/575 English,0/64 R5-D;
c6s36/478 (conditional same-source identity), c60/868. C2 changes0 complete calls,
0 c6s and129 c6 calls. Raw/history missing in old c6 means C1's observed0 changes is
**not** evidence of0 changes on its original raw service stream. C6s seeds the801-unit
count from counters, then uses observed overlapping rows: original identity/lifecycle
were not logged. No full raw stress product-vs-prototype parity claim.

Absolute baseline later-solid proxy flags: Mandarin337 over37 row-observations;
English297 over202; R5-D0. Unknown boundary rows77/81/21, c6s107, c6445. First-
publication-clock hidden counts1416/2165/192 in complete populations remain separate:
preview latency can publish spelling of older speech after confirmation, so these
are **not actual newer-speech loss**. The6322 C2 flags include demonstrated false
alignments (`good friends` already solid, and an earlier `out of it` selected instead
of the current frontier). They reject conservative screening, not establish6322
fresh words lost. Actual stress acoustic fresh loss remains UNMEASURED for both arms.

| Known-clock rewrite control (separate constructed sequence) |C0 |C1 |C2 |
|---|---:|---:|---:|
|Old60 units, delete15 head units, append20 fresh; current65>=60 |cut45 |cut60 |cut45 |
|Known fresh units wrongly hidden |0 |**15 FAIL** |0 |

Thus C1 fails an explicit, reachable rewrite primitive even though the observed
recorded populations report0 added proxy loss. C2 gap24 cannot join the c6s singleton;
changing a gap constant tofit one omission does not establish a rewrite-safe cut.
No rule/threshold was tuned after the results. Initial receipts retained.

### Recommendation, risk, size, limits

**D1 retain C0; do not implement C1 or C2.** Risk accepted: the recorded22.8-second
large grey repeat remains. Saved/solid speech is unaffected by this prototype.
Future work must establish where old *occurrences* end after a rewrite; count alone
is insufficient, and an arbitrary wider gap is not that evidence. A complete raw
preview/origin/snapshot/cut trace on recorded public streams would make a subsequent
$0 replay reviewable; this task does not add product instrumentation or request calls.

Recommended product change: **0 lines**. C1 as prototyped would be approximately
20–35 runtime lines (per-original-turn count/frontier plus application/reset using
existing origins), but is rejected; safe replacement size UNKNOWN. C2 would be one
literal `16 ->24` change in `_repeated_head`, also rejected. No frontend change.
Cost of future implementation, physical device behavior, raw stress lifecycle parity,
provider variance, exact word-time truth, and safe rewritten occurrence identity remain
UNMEASURED. No tests added/changed; fail-before/pass-after product gates N/A. The
common brief's full backend result is appended below once complete.

Artifacts: diagnosis.json, old-c6-head-probe.json, measurement.json,
{zh-188s,en-302s,r5d-cell}-full-state.jsonl, {c6s,c6}-published-state.jsonl,
fresh-loss-examples.json, rewrite-control.json/log and full-backend.log under the own
R5B-A5 evidence directory. The one command prints every replay input/state/output and
runs the diagnosis and known-clock control; all speech snippets come from public records.

### Final lifecycle clarification and verification

The exposed long row's audio end stays257.492s from255.1s onward; a second row
starts257.492s. The long row disappears by277.89s as the nominal publication frontier
moves to270s. **Do not equate this disappearance with the original provider turn
ending at277.89s.** Provider final flags were not logged. Product hybrid marks cached
final turns finished (`gemini_hybrid_engine.py:288`), and snapshots are cleared after
that publication. This is consistent with the one clock unit acting once, then0 on
cached final republications. Whether the255.1 publication itself was final is UNKNOWN.

C1's36 stress changes are therefore an **overlap-conditioned repair experiment**, not
an exact replay of provider-final reset semantics. Complete A4 replays apply original
keys and observed finished flags; the stress experiment lacks those flags. Keeping
an already-finished cached row's count through retirement is a different lifecycle
choice requiring explicit measurement; none is silently implemented here. This limit
does not weaken the known15-unit fresh-loss rejection of the count-only rule.

One-command replay completed successfully after adding full stdout state/diagnosis/
control to the same command; measurement-initial.json vs measurement.json exact parity.
No candidate/scorer changed. Full backend required by common brief: **2897 passed,
9 skipped,2 xfailed,37 subtests passed,27 warnings in395.31s**. Command:
`MOSS_TEST_REAL_SQLITE=1 PYTHONDONTWRITEBYTECODE=1
../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python -m pytest -q -p no:cacheprovider tests`.
Receipt: own `full-backend.log`. No product/test edits or provider calls.
