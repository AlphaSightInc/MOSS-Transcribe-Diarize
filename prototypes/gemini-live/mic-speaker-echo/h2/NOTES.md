# R5B-H2 — distinguish nearby time shifts from omissions

## Contract (before measurement)

Q1 structural question: does a live run in a clean-up timing hole represent omitted
speech or the same speech timed just beside the hole?

P1 primitives: timed word locates the hole; existing comparable unit compares text
across Chinese provider grouping; consecutive run preserves order; adjacent clean-up
neighbourhood bounds evidence to the same utterance. Each is necessary; rows cannot
recover original word timing and published identity cannot establish text omission.

I1 invariants: clean-up words/text/times/labels unchanged; source partitions unchanged;
H's coverage/0.15s/fallback rules unchanged; same discovery before both lanes' admission;
File/URL and interval paths untouched. No provider calls or audio truth inference.

A1 assumptions: nearby exact ordered text is a timing shift. Genuine repetitions can
be withheld (accepted direction), count losses. Stress exports have only rows and total
restore counters: raw pre-H answers UNKNOWN. Build c5b/c7 RECONSTRUCTIONS, not replay.

F1 falsifier: reconstructed duplicates survive; H100 lost names >4, doubled units >0,
missing/extra means >2.06/1.25; new restores on negatives; frozen label changes unrelated
to removals; omitted remote name blocked merely because it occurs elsewhere.

D1 candidates, all after existing single-word jitter trimming:
H2a: whole run's comparable-unit sequence equals the suffix immediately before or
prefix immediately after it in clean-up. H2b: trim the longest whole-word edges matching
those boundaries. H2c: H2a then H2b. No interior/fuzzy/script-fold matching. Numerals use
existing equality. Original live words are never split or rewritten.

D2 proposed neighbourhood: clean-up word spans touching the preceding/following 1s
from the candidate edges, at most 12 comparable units each side; inspect only words
entirely preceding/following the candidate (one provider step overlap allowed, as H).
Suffix/prefix anchoring prevents a same name elsewhere in the sentence from vetoing
an omission. Measure .1/.25/.5/1/2s x 2/4/8/12 units to expose margin, without tuning
frozen population. Choose first sufficient candidate, H2a before H2b before H2c.

T1 tools: pure throwaway discovery patch, production restore functions and archived
word states test all candidates; frozen actual-engine replay tests final composition;
negative/isolated controls test microphone admission; reconstructed stress and explicit
repetitions expose accepted loss. Cost benchmark detects disproportionate discovery
work; full backend detects integration regression. Each failure changes verdict/fix.

One command:
`PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/mic-speaker-echo/h2/run.py`
Full state in `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-H2/`.

T2 cost protocol before cost measurement: 36,000 timed words over two hours,120 isolated
omissions; five paired original/H2 discovery calls, report every sample and median added
CPU time. Negligible gate <0.1s added discovery; excludes full microphone/encoder/Stop
latency. If exceeded simplify lookup before acceptance, without changing semantics.

## Prototype measurements before production edits

D1 selected **H2a**. H2b/c also remove the two stress shapes, but unnecessarily trim
partial runs: synthetic `thank you Cosette` becomes only `Cosette`; H2a restores the
whole run. Whole-run equality is sufficient for the reported defect and preserves
that genuine omission. It deliberately does not repair a shifted *part* of a run.

F1 G1: three explicit reconstructions (c7 phrase shifted before/after; c5b characters
against grouped `产品规划`) restore0 words vs original2 in each; text appears once.
Grouped `规划` variant also passes. Exported text/frontier confirmed in stress.py;
per-word clocks and hypothetical pre-H answer are injected, not recovered provenance.

F2 G2 discovery: all100 pairs and127 archived engine cells unchanged under each of
H2a/b/c. Lost names4; doubled adjacent units0; missing/extra means2.06/1.25.
Changed archived restored runs: **none**. Full100+127 sensitivity over20 cells
(.1/.25/.5/1/2s ×2/4/8/12units) retains those numbers and0 archived changes throughout.
Full actual-engine composition is still being measured; do not call it passed yet.

F3 neighbourhood margin: the reconstructed matching word gaps are .1–.3s
(max .200375s for the Chinese grouped boundary). All three shapes pass at .5s through
2s and at2–12units; .1s misses all, .25s misses before-shifted `got the`.
The registered1s bound leaves .7s beyond the largest reconstructed gap;12units leaves
10 beyond the two-unit defect. Those margins concern reconstructions, not original
provider clocks. Unit/time boundary tests expose >12units and >1s as outside policy.
No claim about shifts beyond these bounds or partially shifted runs.

F4 G3: distant same `Media Lab` restored2/2; nearby `thank you Cosette` retains3/3
including Cosette; clean-up-omitted `uh I I` retains3/3. Accepted loss: four deliberately
adjacent true-repetition fixtures (`yes`, `thank you`, `yes yes`, `对对对`) withhold8/8
candidate words; all recorded discovery cells lose0. No acoustic repetition truth exists
for stress stutters. This is an explicit trade-off, not inferred accuracy.

F5 G4: both lanes use uncovered_runs; microphone shifted5-word reply suppressed before
any local-run admission. Prototype pytest16/16; unchanged product11 fail/5 preservation
controls pass. One prototype test initially compared post-terminal canonical labels to
raw decoder labels; corrected to compare the no-witness terminal result. Initial log
retained; no design/population/threshold changed. Existing tests untouched.

F6 G5 cost: fixed36k-word/2h/120holes discovery benchmark,5 pairs; prototype median
added .013710s (<.1s registered gate). Provider calls0/cost$0; full Stop latency excluded.
Prototype numbers, complete word state and20-cell sensitivity stored in owned evidence.

F7 stress audit: reran original audit algorithm read-only on8cells×2lanes; system counter
205/microphone0 remains historical, not recomputed. F1/F2 would be suppressed under the
reconstructed timing-shift hypothesis. F3 omitted `uh I I` preserved. F4/F5 stutters:
no blanket removal; preserved absent adjacent whole-run equality, exact pre-H result
UNKNOWN. F6 distinct-time repeated long clauses/mixed-script garble unchanged; F7 collapsed
row projection unchanged and original word durations UNKNOWN. Audit lists are retained.

## Prototype verdict — PASS (before production edits)

Actual127engine cells(45F3+19F2+63levels) plus4injections all replayed,0 execution
errors, all provider receipts replayed,$0. Exact C2 comparison:0 final-word text/time/
label differences,0 restored-run changes,0 live/Stop/saved-row differences in127cells.
H100 exact pair state unchanged.56negative conditions/28samples/908words restore0;
24isolated controls and4injections pass. Names236/250; F2 live/Stop/saved206/291/310
of343. Truth speaker error.0907/.1217 unchanged;21 inherited sweep echo-proxy flags
remain, not new H2 failures. C2 extended930s seam injection restores12/12 with its
own published name; exported welcome injection23/23 with its own name; encoder3/3.

Proceed with H2a only,1s/12units, in shared uncovered_runs after existing edge jitter
trimming, before either lane admits candidates. No other threshold/order changes.

## Product verdict — PASS

Production change confined to shared `gemini_coverage.uncovered_runs`: after existing
edge jitter removal, withhold whole-run adjacent suffix/prefix equality,1s/12units.
Both lane callers consume that same result; microphone admission and system identity
bridging untouched. Design note updated. No existing test changed;11 new failing cases
become passing,5 preservation controls remain passing;16 new cases total. Targeted91 pass.

Full backend required real-SQLite/no-bytecode/no-cache command from named worktree:
**2834 passed,9 skipped,2 xfailed,27 warnings,37 subtests passed,410.15s.** Frontend
untouched. No File/URL,interval,10s fallback,provider request,voice threshold or source
partition changes.

Product vs H2a prototype AND C2: **127 exact engine cells**,0 changed final words/
text/times/labels,0 changed restores,0 changed live/Stop/saved rows. Every cell whose
restored words change: **none**.131 actual engine receipts including4injections;
all provider calls replayed,0 cost.56negative conditions/28samples/908words restore0;
24isolated controls and4injections pass. Names236/250; F2 live/Stop/saved206/291/310
of343; truth speaker error.0907/.1217 exactly.21 inherited sweep echo-proxy flags
retained, with exact C2 outputs. No unsupported broader echo/identity claim.

H100 full state exact:4 lost names,0 doubled units,2.06/1.25 missing/extra means.
All synthetic patterns exactly reproduce prototype, including3reconstructed stress
shapes restored2→0 each,8/8 deliberately repeated words withheld,0 recorded loss,
and omitted `uh I I`3/3. C2 extended930s/name/partition receipt exactly matches
prototype:12/12 seam utterance,23/23 welcome,encoder3/3.

Discovery benchmark median added prototype .013710s vs product .001482s on36k words/
2h/120holes,5paired samples each; entire sample lists retained. Product reuses existing
sorted word/span indexes instead of prototype's second sort. Same rule, no threshold
change. Negligible gate<.1s; excludes encoder and whole Stop latency.

Stress original audit rerun exactly matches original AUDIT.json. Product stress.py
confirms F1/F2 reconstruction fixes and conditionally preserved/unknown F3–F7 as above;
no real205-counter recalculation is possible without pre-H words. Nearby genuine
repetitions and partly/out-of-bound shifted runs remain limits; no new provider/device
qualification. $0,no provider calls,no deployment.

Reusable bench defaults to product verification and asserts serialized complete state
against frozen H2a. Original prototype code/snapshot retained only in owned evidence;
no production import points there. One bench assertion initially compared Python tuple
metrics with JSON lists: corrected to compare the same serialized schema; failure log
retained. No population/metric/algorithm tuning or test expectation weakened.

Replay commands from this worktree (named shared venv):
- `h2/run.py`:100pairs+127 archived discovery cells+synthetic full-state parity.
- owned `R5B-H2/product/product_verify_all.py`:actual127engine cells+controls/injections.
- `h2/verify.py --product`:exact C2 and H2 prototype engine/row/restore parity.
- `h2/cost.py --product`, `h2/stress.py --product`:cost and reconstruction/audit verdicts.
Prefix paths with `prototypes/gemini-live/mic-speaker-echo/` for h2 scripts; set
`PYTHONDONTWRITEBYTECODE=1` and use `../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python`.
Full receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-H2/`.
Local commit only; lead owns review/merge/cutover. No implementation blocker or additional
human decision required under the accepted-loss direction in the brief.
