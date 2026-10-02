# R5B-C2 restored system speaker — contract before measurement

Question: which final speaker owns words restored from the live transcript?
Primitives: timed committed word; published identity (request labels are not identities);
kept final word after stitching/policy; temporal overlap as the bridge between namespaces.
Each is necessary: time locates replacement, identity groups the person, kept labels define
clean-up's partition, overlap links the two without a new voice embedding.

Hypothesis S2: retain the published system identity on committed witnesses. Keep H's admission,
text/times/order and kept labels exactly. For each restored word use the nearest kept word
which overlaps a witness of that same published identity. Resolve equidistant words by earlier
answer order. If none exists use one distinct `witness-<published ID>` final label for that ID;
existing per-lane final-to-live overlap assignment recovers the published name. Unassigned
request-scoped witnesses have no identity and retain H's neighbour label. Do not use restored
words as bridge evidence. Microphone admission and final neighbour labeling unchanged.

Invariants: all existing H thresholds, skipped fallback intervals, word gates/counters,
kept words/labels, no provider/embedding calls, File/URL and interval behavior unchanged.
A mixed-identity hole is admitted under H exactly as before then each word is labeled separately.
Unknowns: correct voice truth where unpublished; incorrect live identity can conflate people;
clean-up can split a live identity. Nearest final witness can follow that split locally, but
cannot correct an entirely omitted speaker whose live identity was wrong.

Falsifiers: any lost/doubled/changed kept word; S1-correct truth restore changes to incorrect;
truth speaker error rises >.005; fragment gets separate label although identity has kept words;
injected third-speaker omission does not keep its live name; microphone outputs change;
added two-hour label work >1s. No new thresholds or embedding proposed.

Tools: existing recorded 100-pair matrix and 45 engine receipts test preserved H population;
truth fixtures test S1-correct labels/error; production chunk schedule/stitcher at >900s with
recorded words shifted onto two chunks tests post-stitch placement (injection, not provider
qualification); recorded stress cell2 rows and a removed recorded clean-up utterance test
third-speaker custody. Frozen FIX3 replay tests product equivalence after absorption.
Stress audit compares per-lane live/saved text with temporal alignments: restoration is inferred,
never asserted from the counter. No provider calls ($0).

One command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/mic-speaker-echo/c2/run.py`
Full per-cell state/receipts live in ~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-C2/.
Prototype module is absorbed into production after measurement; retain NOTES and replay bench.

## Amendment contract — before measuring R4-F1/R4-F2

Published identity estimates who spoke; it must never authorise evidence pooling.
Add one source-partition field to each committed witness, independent of its published
speaker field. A request label gets one source partition inside that request. Link across
CONSECUTIVE rolling requests only through already committed words re-heard with the same
word (existing H letters/numeral comparison) and both endpoints within STEP=.1s.
No matches: new request-scoped partition, even if labels or published IDs equal.

Ambiguity rule, fixed now:
- One new label matches >1 earlier source partition: create a fresh partition, never
  merge/relabel the earlier evidence groups. An omitted short seam reply may be lost.
- Two new labels match one earlier partition: create separate fresh partitions. Move
  earlier matched witness words into their corresponding new partition ONLY if that word
  positively matches exactly one new label and that label matches only one old partition.
  Unmatched/ambiguous earlier words stay in the earlier partition. This splits evidence;
  it never merges distinct earlier source groups. It permits a corrected speaker prefix
  to accompany its own suffix without authorising the other voice to borrow its evidence.
- A unique one-to-one edge continues the old partition. Matches whose endpoints differ
  >.1s, or whose words differ, cannot establish correspondence.

Refresh published identity only with actually published GeminiRelabel rows, retaining
source partitions unchanged. System words keep exact H text/time custody and now published
IDs; microphone LocalVoiceEvidence groups by source_partition (plain GeminiWord fixtures
continue grouping by speaker, since they already represent one request). Existing
microphone final-neighbour labeling remains the measured G4 policy: no claim that uncertain
microphone identity is a better final answer without truth. System S2 final labels alone change.

Falsifiers: public/identity/assignment seam <5/5; alias stray>0 or reply<4/4; alias2+2>0;
pass3 mixed negatives changed; frozen text/time changes; negatives>0; cost120>10s;
counters/cache/anchor mutation; new embedding/provider calls. Probe copies print complete
witness state; never modify review sources. Regression seeds: three seam identity states,
aliased stray and2+2, positive/no/ambiguous correspondence, current relabel identity.

## Prototype verdict — PASS (before product edits)

S2:100 recorded pairs +45 archived engine cells preserve every kept word/label and H
text/times/counts. Separate restored-only labels:0 across both populations (fragments
`Yeah,`/`uh I I` never invent an identity when their published speaker has kept words).
100 word-label differences in100-pair matrix; archived differences are `I` tails only,
full lists in prototype.json. Two truth restores Cosette/there. remain S1-correct;
actual full engine truth error .0907/.1217 unchanged in own prototype receipts.
Published identity conflation control follows the nearest final split (final-b), no
new identity. An entirely omitted voice with a wrong published ID remains wrong;
no acoustic evidence exists to correct it. Added label work0.126s on36,000-word2h lane.
Initial linear nearest search added1.447s, rejected; indexed nearest search reduces
that to0.126s with the SAME nearest-interval/tie rule, not a new threshold.

Amendment:14 copied pass4/public/pass3/pass2 probe scripts all exit0. Public and
three identity-frontier cases restore5/5; controlled reassignment5/5. Alias stray0,
reply4/4; alias2+2=0; pass3 mixed stray0/reply4, same-source inherited padding control5.
Frontier same/change labels5/5; counter5->5; cache/anchor side-effect controls unchanged;
crop vectors difference0.0; accepted empty-answer fallback unchanged.120-candidate
cost result is in prototype-witness_cost.py.log; no-encoder lower bound, not full Stop latency.
930s actual chunk plan + LongFinalStitcher, recorded answer shifted880s and entire
12-word speaker omitted (INJECTION):12/12 restored under published-terminal-0002;
3 encoder calls with/without restoration. Ambiguous merge keeps old source groups
separate; split moves uniquely matching old words into distinct fresh groups;
unmatched repeated raw label gets fresh source partition. See prototype-extended.json.

Recorded raw stress provider word annotations are unavailable; cell2 D3 is an observed
row-level inference, not a recovered raw answer. Its welcome is live60.7-68s (the
saved singer row spans52-68s); receipt's52-68s describes the merged saved row. The
recorded three-speaker removal above exercises that structural shape with actual
word-level recorded answers and explicit shifted timing/omission injection.

Implement only this measured custody + S2 rule. Microphone final-neighbour behavior
retained, including uncertain identity/no-neighbour local fallback (G4). No microphone
voice truth supports replacing that final-label policy here. Source partitions never
change published rows or authorize identity; published relabels never pool source groups.

## Product verdict — PASS

Eight new numerical/ownership regressions fail on unchanged0cf8695a and pass after;
existing tests unchanged. Targeted117 passed. Full backend:2818 passed,9 skipped,
2 xfailed,27 warnings,37 subtests passed,408.00s. Required real-SQLite/no-bytecode/no-cache
command used from this worktree and its named shared venv. No frontend change.

Product14 copied review probes all pass: public/unassigned/born/changed-label/reassigned
seams5/5; aliases stray0/reply4/4, distinct2+2=0; pass3 mixed and same-source controls,
FIX2 counter5->5/cache/anchor/crop/fallback custody unchanged. Microphone120-candidate
cost1.606649s/720000 mode1 frames/360 restored words; empty~.00008s/0 frames. The cost
fixture excludes encoder/system-speech cost; physical/full Stop latency UNMEASURED.

Product vs C2 prototype:100 pairs +45 reconstructed archived cells have exact restored
state/labels; actual full-engine truth75/76 words and small chunk165 words match the
prototype exactly in text/time/label. Archived publication reconstruction uses exported
rows and can abstain on zero-duration words; it is not a substitute for actual published
IDs. The frozen product uses the engine's published IDs. Bridge added~.15s on36k-word2h
lane.930s actual schedule/stitcher injection12/12 own name, encoder calls3/3. Additional
cell2 exported-text injection (word times interpolated inside the recorded60.7–68s live
row):23/23 welcome words keep speaker-0002/"Speaker 2", never the singer. It is explicitly
an injection, not original raw stress-provider replay.

Requested FIX3 entrypoint re-executed with copied sibling scripts/output root in owned
R5B-C2/product, preserving all original sources/receipts. Only harness adaptations:
observe the new system restore helper; allow individually verified restored-only labels;
record every such difference. No measurement threshold/population/metric changed.
Frozen127cells(45 F3+19 F2+63 levels),131 actual engine receipts including4 injections:
all provider answers replayed, current product paths, cost$0. H100 pairs lost names4,
doubled adjacent units0, missing/extra mean2.06/1.25. Names236/250; F2 live/Stop/saved
206/291/310 of343.56 negative conditions/28 samples/908 words restore0;24 isolated
controls and4 whole-engine injections pass. Truth .0907/.1217 exact. No new duplicates,
row ownership failures, diagnostics counter errors or provider costs.

127cells×4 surfaces: both live/Stop row surfaces exact; terminal words text/time exact;
all microphone words/labels/rows exact; system witness text/times exact. Intentional
system changes:228 restored `I` words in114cells take the same published speaker's final
label. Kept final labels unchanged; kept saved-name temporal-overlap check differs0.
Saved system rows regroup/split in114cells because restored labels change. Those derived
row text groupings/bounds are NOT byte-identical; complete before/after rows and every
word-label change are in recorded-comparison.json and product/verdict.json. This is a
necessary consequence of assigning those restored words to a different speaker, not a
text/time change on any word. No recorded run gets a new restored-only label.

Inherited21 sweep echo-proxy flags retained, with exact microphone outputs. Raw same-label
padding can still restore unsupported words (same-source control5); source custody does
not correct a provider's own erroneous grouping. Ambiguous correspondence can withhold
short replies; no raw-label/published-ID guess fills that gap. Entirely missing/wrong live
identity and system live-only inventions remain limits. W excluded as before; no new
provider/device qualification or physical echo-cancellation claim.

Stress AUDIT.md/AUDIT.json cover8cells×2lanes:205 system words/0 microphone restored;
exact words inferred because only counters survived. Flag c5b doubled规划 and c7 doubled
got-the plus saved stutters/garbled tokens; musical/local fixture repeats are not false
findings. Their text is untouched by C2. Lead owns any text-rule follow-up and integration.
Prototype implementation absorbed into production; source retained only in owned evidence,
NOTES and reusable product replay bench retained here. Local commit only; no push/merge/PR.
