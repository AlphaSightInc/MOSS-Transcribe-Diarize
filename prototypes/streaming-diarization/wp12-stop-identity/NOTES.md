# WP12 — overlap candidate FALSIFIED at 180 seconds

**STOP:** the supplementary 180 s same-input comparison changes attribution on
54/56 system segments (575 words). No tuning or further decoder runs followed.
Candidate implementation/tests are retained on this isolated branch for review,
not accepted or deployed. The six required 24/60 cases pass, but the user's
"any case" attribution stop condition takes precedence. See the final verdict below.

## Same-lane overlap continuation (from accepted diagnosis 60b3b584)

The user now explicitly authorizes adopting mono's overlap mapping per lane,
with acoustic fallback only for terminal segments without same-lane overlap.
The earlier measurement establishes the cost of the existing algorithm, not an
unavoidable product requirement. This new semantic choice is now in scope.

Structural question: does same-lane overlap preserve the acoustic control's
terminal attribution while removing full-tape probes? Primitives: settled
pre-terminal lane surface; terminal local speaker partition; overlap assignment;
acoustic probe for uncovered segments. The surface is exactly mono's input
(`snapshot.effective_transcript`, including accepted rolling corrections), filtered
to the producing lane. Canonical candidates retain snapshot order and lane scope.
Invariants: same decoded words, same segment attribution as acoustic control,
zero cross-lane assignments, existing thresholds/sampling/QUALITY_BOUNDS, max two
decoder calls. Unknown: assignment equivalence across the requested real inputs.
Falsifier: ANY attribution difference; stop immediately without tuning.

Tool decision: a shadow prototype calls both mapping methods on identical terminal
decoder output and settled session state, removing decoder nondeterminism from
the comparison. The existing acoustic result remains what gets saved. It reports
every changed segment's sample range and speaker, word equality, fallback audio,
and cross-lane assignments; no transcript/audio enters git. Matrix intended:
24/60 s parity, microphone minus 10 dB, same voice on both lanes. Only after all
pass: absorb prototype, regression tests, live 24/60/180 s Stop measurements.
Budget begins at 339/1200. Existing experiment wrapper checks waiting/running
before each batch and owns/tears down its 18112 tunnel and 17872 service.

Prototype command:
`WP12_ARM=overlap-shadow-p24 bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 24 parity`.
Cases `mic-minus10` and `same-voice` respectively scale mic PCM by 10**(-10/20)
and copy system PCM to mic; the unchanged 60 s public corpora are the sources.
The first 24 s parity control passes: 13/13 segment dictionaries equal,
0 cross-lane assignments, 0 fallback audio-seconds. Outcomes follow below.

Prototype verdict before production edits: **PASS, six cases / 135 segments**.
24/60 parity: 13/28 segments; mic -10 dB: 13/28; same-voice both lanes: 17/36.
Every candidate segment equals its acoustic control (words, times, speaker,
authority, source lane). Zero cross-lane assignments, zero fallback audio, and
all six acoustic final surfaces equal saved text/identity. Same decoder output
and session state in each comparison; no comparison between independent decoder
responses. `overlap-comparison.json` retains per-lane results and empty diffs.
One same-voice admission attempt refused running=1/waiting=0 before any decoder
call; a later idle check admitted it. Total now 603/1200 calls. Three new
production-seam tests fail on unchanged code: both covered-lane cases still
probe, and the uncovered-tail test sees full-tape probes on both lanes instead
of only the system 3–5 s interval. Log: `overlap-regression-before.txt`.
Proceed to absorption using the existing terminal finalizer's overlap mapping,
with bounded per-segment acoustic fallback; no new matcher or thresholds.

Absorption: production passes `lane_base` plus that lane's canonical candidates
directly to the existing finalizer, deleting CaptureRunner/copy and the whole-tape
voice-preparation pass. Only a terminal segment lacking labelled overlap invokes
`revision_segments` on its exact PCM crop. The prototype is absorbed into the
standing bench as a frozen 60b3b584 acoustic-versus-overlap comparator; production
does not import it. Focused tests: 191 passed. Full suites, run while the shared
GPU was occupied: 1805 passed / 2 skipped / 37 subtests / 21 warnings in 143.19 s;
frontend 26 files / 230 tests, typecheck/build passed. No production changes after
these gates. All three new regression tests fail before and pass after the fix.

Two initial production timing admissions refused running=1/waiting=0, dispatching
no requests; after the full suites the idle admission check passed. Together with
the earlier same-voice refusal, there were three busy-GPU refusals, all retained in
admission.txt. Small editing-tool failures (an empty test hunk and a documentation
context mismatch) made no changes; corrected. A transient placeholder was removed
immediately and never used or committed.

Production 24 s: Stop→final 3.788534 s, drain 2.578691 s, terminal 1.100589 s,
26 decoder requests, 0 terminal embedding calls/audio-seconds. All 13 saved/live
surface segment dictionaries equal the separate 24 s acoustic control exactly.
Production 60 s: Stop→final 7.490138 s, drain 4.867833 s, terminal 2.446688 s,
62 requests, 0 terminal embedding calls/audio-seconds. All 351 ordered words retain
their lane and speaker. Of 28 independently decoded segment rows, 27 equal exactly;
mic row 9 start changes 879360→879040 samples (54.96→54.94 s), end 958080 and
speaker-0003 unchanged, text exactly equal. This is a separate-decoder comparison;
the same-input acoustic/overlap shadow has 28/28 exact equality. No attribution
falsifier fired. Details: overlap-independent-output-comparison.json.

### Final verdict — supplementary 180 s falsifier

Candidate 180 s parity: Stop→final 16.964282 s; drain 4.794547 s, terminal
11.791761 s, 184 decoder calls, zero terminal embedding calls/audio-seconds.
Both lanes complete; saved text/identity equal final. The 10 s bar is still missed.
The system has two unattributed segments, 149.61–153.75 and 160.68–161.40 s,
totalling 16 words. This justified checking the multi-window acoustic control,
also supplying the previously missing before-embedding denominator.

The clean frozen-acoustic 180 s control is **FALSIFIED** on exactly the same
decoder output/session state: system 56 segments, microphone 30. All words and
boundaries equal, zero cross-lane assignments. Acoustic system preparation
abstains for the entire lane with `same_span_cannot_link_conflict`: three local
labels S01/S02/S03 compete for two known lane speakers. Overlap instead assigns
50 segments / 543 words from None to speaker-0001 and 4 / 32 from None to
speaker-0004; two segments remain None. Mic 30/30 equal. This is an attribution
change, not a finding that either choice is source-adjudicated correct. No
threshold, conflict rule, or assignment was tuned to remove the difference.
All 54 row diffs are retained in overlap-comparison.json; concise counts/reason
in overlap-falsifier-summary.json. No additional decoder calls after detection.

Terminal embedding audio-seconds before→candidate: 24 s parity 43.08→0;
60 s 111.90→0; 180 s 335.52→0. Requested six-case matrix remains 135/135 exact
segment equality; the additional 86-segment case changes 54 rows and fails the
broader attribution criterion. The implementation remains a review candidate.

Final request ledger: **1073/1200**, peak 2 in flight. 1059 calls across 21
completed runs, plus 14 fully accounted calls in one invalidated control attempt.
There were 12 idle-only admission refusals with no dispatch. The last idle retry
became admitted while its parent was being stopped; an overlapping launch then
failed startup and the client received HTTP 409. Both were discarded as measurement
evidence, all owned processes stopped, and the 14 calls remained in the ledger.
The bench now refuses occupied measurement ports and checks its tunnel/server PIDs.
A clean, uniquely named control used `WP12_SINGLE_FLIGHT=1`: at most one own
request, waiting=0 and running<=1 at admission. Its Stop timing is not used as a
performance comparison. This is a bench-only scheduling mode, not a production
concurrency change. Final owned listeners 18112/17872 absent. An additional
documentation context patch failed without changing files and was corrected.

## Fresh-context continuation, 2026-09-18 (supersedes old budget/status below)

User explicitly authorized 1200 total decoder calls, at most two in flight,
checking vLLM waiting before each batch. Starting tree clean at a02a8491.
Concurrency 33be55ec accepted as a bounded improvement; no further concurrency
change authorized before explaining the Stop and embedding costs. Identity
premise explicitly adjudicated FALSE: the mic fixture includes Lex Fridman at
25–35 s. No identity-policy change.

Structural question: is terminal latency an avoidable repeat of existing acoustic
evidence, or the cost of producing different evidence? Minimum primitives:
pending work (owns the pre-terminal wait), terminal local-speaker partition
(owns the new speech intervals), lane reference album (owns known voices), and
one final publication (owns completion). Removing any conflates scheduling,
probe/reference evidence, or completed output. Invariants: full final text,
lane ownership, existing acoustic sampling/thresholds, max two decoder requests.
Unknown before measurement: wait owner and exact repeated embedding inputs.
Falsifier for equivalent reuse: different interval sets/averaging or changed
speaker attribution. Tools: phase timestamps identify the wait owner; real encoder
calls identify computation and samples; retained saved dictionaries check output.
No synthetic identity score or new production algorithm was introduced.

One command per matched arm (same public 24 s parity input and pacing):
`WP12_ARM=mono-traced bash prototypes/streaming-diarization/wp12-stop-identity/experiment.sh 24 parity`
Repeat with `serial-traced` and `concurrent-traced`. Source paths recorded in trace:
mono archive 37979e53, serial archive b31683a6, current production a02a8491.
All three admission checks: vLLM running=0, waiting=0. Owned tunnel 18112 only.
Read-only analysis: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <WP12_PY> prototypes/streaming-diarization/wp12-stop-identity/analyze_embeddings.py`.

### F1 — the roughly three-second wait is useful queued work, not a timer

| Measured 24 s arm | Stop to terminal | Terminal to publication | Stop to observed final | Decoder calls |
| --- | ---: | ---: | ---: | ---: |
| Mono | 0.383135 s | 1.389896 s | 1.880702 s | 13 |
| Serial lanes | 2.733792 s | 8.488729 s | 11.327668 s | 26 |
| Accepted concurrent lanes | 2.326931 s | 4.402630 s | 6.839325 s | 26 |

Serial Stop arrives during the second rolling refinement (10–20 s): remaining
0.897933 s; then queued causal span 20–22.5 s takes 1.108433 s, tail 22.5–24 s
takes 0.722543 s, final identity sweep takes 0.002924 s. Event/dispatch overhead
accounts for the remaining milliseconds. Mono already completed rolling work:
only the tail is dispatched, taking 0.369481 s, then a 0.001617 s sweep.
`_wait_for_drain` waits on completion notifications; no fixed sleep or lease delay.
The API observer polls at 0.1 s; that explains approximately 0.11 s between
publication and observed final, not the 2.7 s pre-terminal wait. Queue snapshots
alone omit the already-running refinement; phase entry/exit resolves it.

### F2 — reference reuse exists; terminal probes use different intervals

Calls below mean `_OnnxWeSpeakerEmbedder.embed`, one per decoder-local speaker.
Each interval runs the encoder once, then the returned normalized interval
vectors are averaged equally and normalized. Audio-seconds sum intervals, not
unique tape duration; mixed mono can contain overlapping local-speaker intervals.

| 24 s arm / phase | Embedding calls | Encoder intervals | Audio-seconds embedded |
| --- | ---: | ---: | ---: |
| Mono causal, including tail | 18 | 19 | 28.27 |
| Mono rolling / terminal | 0 / 0 | 0 / 0 | 0 / 0 |
| Serial lanes causal, including tail | 20 | 20 | 44.00 |
| Serial lanes rolling | 4 | 9 | 36.25 |
| Serial lanes terminal | 2 | 12 | 43.53 |

Terminal system: one local speaker, eight intervals, 21.33 audio-seconds,
3.287698 s embedding. Microphone: one local speaker, four intervals, 22.20
audio-seconds, 3.416678 s embedding. Total 6.704376 s, reproducing the earlier
roughly 6.79 s voice-preparation finding. The rest of terminal is predominantly
the two decoder jobs. Each terminal speaker is embedded over its speech across
the full 24 s tape; not one full-tape embedding per canonical album member.
Canonical album vectors are read, never re-embedded at terminal.

The lane reader already uses the causal owner's `_canonical_vector` as its
reference. What gets re-embedded is terminal decoder-local speech, to decide
which known voice owns the new label. Mono does something different:
`terminal_speaker_mapping` assigns by overlap with the existing transcript,
without acoustic probes. Mono's timing is not a cheaper instance of the same
voice-matching computation, nor a demonstration of equivalent acoustic reuse.

Of 43.53 terminal audio-seconds, 40.29 overlap causal evidence. But **0/12 terminal
intervals exactly equal causal intervals, and 0/2 complete embedding calls equal
any prior call**. One 5.28 s mic interval equals part of a rolling call. Its
individual vector is not retained: rolling returned the mean of two intervals.
Replacing terminal probes with a lane album would discard the probe needed to
identify new local labels; substituting averages of overlapping causal units would
change the encoder inputs and averaging. Neither is equivalent recomputation
removal. The representation is nonlinear; slicing/combining album means cannot
recover arbitrary new-interval vectors. No claim that every possible reuse design
is impossible: such a design changes the acoustic evidence and needs separate
identity validation. The measured dominant cost is inherent to the current
whole-speech acoustic-matching algorithm, not an inherent requirement of all
possible diarization designs. Per user's stop condition, stop optimization here.

### F3 — accepted concurrency confirmed; no new production change

Concurrent rerun embeds the same 43.53 terminal audio-seconds over 12 intervals;
it overlaps the two jobs. All 12 saved segment dictionaries equal the new serial
run exactly; 86 system and 56 microphone words, one identity per lane. All three
new runs finish `final` and equal their saved text/identity. This is preservation
and latency evidence, not human-adjudicated transcript accuracy.

65 additional calls: 339/1200 cumulative. Peak concurrency and all 11 saved/final
agreements are checked by `audit.py`. No policy, thresholds, sampling, production
code, or tests changed in this continuation. New files extend the standing
measurement bench and contain no transcripts/audio. 60 s concurrent remains the
previous measured 16.174951 s prototype; 180 s remains unmeasured. These are not
budget-blocked now: further optimization/matrix work stopped under the explicit
inherent-cost clause. Do not claim full WP12 latency acceptance.

Fresh full suites and read-only audit are recorded in root `VERIFY-RESULT.md`.
Minor failed inspection attempts: VERIFY.md first sought beside NOTES (it is at
root); two source files first sought outside app/; a trace query assumed startup
embeddings had a span reason and raised KeyError. Corrected without decoder calls.
An initial documentation patch failed a README context match and was reapplied.
The saved-dictionary audit corrected an initial prose count of 13 to 12 for the
new matched pair; 13 remains the correct historical pair's count.

## Earlier retained evidence (historical budget/status)

Exact base b31683a6; mono baseline archive 37979e53. Source package resolution
verified within this worktree. Prototype instrumentation changes no policy.

First matched parity (24 seconds): mono 1.969648 s / 13 requests; per-lane
11.803096 s / 26 requests. Saved and final text/identity equal in both arms.
Per-lane Stop requested 90108.170178; terminal begins 90111.226182 (+3.056004 s).
System terminal decoder 1.027198 s; microphone 0.803239 s. Voice preparation
occupies about 6.79 s after those decodes; terminal publication 90119.851639.
H1 decoder-only cost is insufficient. Both mono and lanes decode whole meeting;
both retain existing WindowedRunner context windows for long audio.

Candidate: concurrent independent terminal lane jobs, including read-only voice
preparation, then ordered result assembly and one publication. Same decoder input,
identity policy and acoustic evidence. Two workers correspond exactly to two
supported source lanes and existing vLLM capacity; no new timing/score threshold.
Falsifier: changed final words/attribution, cross-lane state, >2 calls in flight,
or no speed improvement. Not yet accepted; production untouched.

Failed setup/read attempts: incorrect app source paths; missing optional local
skill path; missing glob matches. None dispatched decoder calls. No hidden retries.

Identity finding: 48 s alternation reproduced 2 microphone IDs. The supplied
`interview_keyu_jin_60s/reference.jsonl` names Keyu Jin (0–25,35–55) and Lex Fridman
(25–35,55–60), so the played microphone interval 24–48 includes two voices. At
causal span 14 (35–37.5 s), the existing mic album still contains speaker-0002;
S201 scores 0.518355 (0.56 s evidence), S202 scores 0.084412 (1.56 s evidence).
Threshold 0.35, margin 0.1: S201 matches, S202 births speaker-0003 with the existing
1.0 s birth policy (below 2.0 s album admission, retained provisionally). Next span
scores 0.132620 versus old and 0.561468 versus new; subsequent old scores remain
0.019639–0.089042, new 0.490218–0.719870. No lost album or missing evidence.
The hypothesis of a single mic speaker in this fixture is falsified by its own
reference; the acoustic mismatch is supported. No identity-policy fix justified.
Exact boundary accuracy is not human-audited here.

24 s concurrent prototype: 7.715494 s versus 11.803096 s serial (-34.63%);
26 requests in both. All 13 saved segment dictionaries equal exactly, not merely
word counts. Original serial 60 s: 26.635716 s, 62 requests, 28 final segments,
197 system / 154 mic words, exact saved/final text and identity agreement.
24→60 s original serial cost grew 2.257x for 2.5x input. This is observed scaling,
not a 30-minute extrapolation or an upper bound.

Budget conflict: one 24 s parity mono/lane pair needs 39 requests; 60 s lane needs
62. The requested 12-arm paced 24/60/180 live matrix, plus 48 s reproduction and
before/after verification, cannot fit 300 at unchanged production cadence. Asked
for up to 1200 via asynchronous question; until explicitly approved cap stays 300.
Prioritize paired 24/60 parity, 48 s identity diagnosis and fixed-build verification.
Missing arms remain unmeasured; do not relabel a terminal-only control as live Stop.

60 s concurrent prototype: 16.174951 s versus 26.635716 s (-39.27%), 62 requests
in each. All 351 ordered words retain their speaker assignment (181/106/48/16
words across four speakers). Saved segment dictionaries differ in punctuation/
segmentation/timestamps: five segment rows differ, no normalized word or identity
change. Exact dictionary equality is NOT claimed for 60 s. Saved schema on this
base lacks source_lane; live final counts establish lane association, not native
saved provenance. Earlier 24 s exact equality covers saved fields only.

Prototype accepted for bounded concurrency improvement, not charter latency
acceptance: 60 s still misses 4 s and 10 s; 180 s remains unmeasured. The terminal
path still re-embeds whole-meeting speech; reducing that would change acoustic
sampling and needs a separate measured design, not an arbitrary new threshold.
Production absorbs the concurrent lane function; throwaway implementation deleted.
Existing terminal serial-order assertion becomes unordered call equality; causal
serial-order assertion remains unchanged. New real-album gap test passes before
fix; new barrier-based concurrency test fails before fix (peak 1 rather than 2).
Focused initial suite: 72 passed, 2 failures; inspect exact log, then rerun using
required worktree-local socket adapter. No tests or assertions weakened.

Focused failures adjudicated: both are `ModuleNotFoundError:
_browser_workspace_fixtures` when selecting the root lane file without collecting
phase2 tests. Add `tests/phase2` to PYTHONPATH for the focused subset. This is a
fixture import-path precondition, not a socket failure or concurrency regression.

## Full-suite adjudication and fixture corrections

Initial full suite: 1783 passed, 19 failed, 2 skipped, 37 subtests, 148.45 s.
All 19 failing nodes reproduced on an untouched b31683a6 archive INSIDE this
worktree: 128 passed / 19 failed / 9 subtests. Initial archive attempt lacked its
node_modules symlink: 123 passed / 24 failed; retained as a setup failure.
`baseline-adjudication.json` compares exact node sets, not just totals.

File-by-file contract:
- `tests/test_live_pipeline_seams.py`: 15 parameterized failures gave digital zeros
  to a real adapter now contractually skipping zeros. Tests intend to inspect an
  actual mocked backend answer/failure/token cap, so only those fixtures become
  PCM16 value 1. Even VAD-marked silence can carry nonzero low-level samples.
  Decoder-response, salvage, retry, duration and token-cap assertions unchanged.
- `tests/test_live_rolling_wiring.py`: salvage-gate comparison likewise needs a
  decoded answer; both test inputs become nonzero. Gate reasons/assertions unchanged.
- `tests/phase2/test_runner_composition.py`: prompt-on-wire test's fake tape becomes
  nonzero so the real terminal finalizer reaches HTTP construction. Assertion unchanged.
- `tests/test_live_service_replay.py`: terminal replay fixture uses nonzero samples
  to obtain a terminal surface; all other WAV fixture callers retain zero default.
- `tests/phase2/test_draft_lane.py`: snapshot had updated legacy commits but retained
  an authoritative empty effective_transcript. Production correctly displayed empty.
  Fixture now updates both fields to the same two segments; assertions unchanged.

Those five files then pass 147 tests + 9 subtests. Deliberate in-process empty
adapter/terminal outcomes plus a temporarily empty published-surface reader kill
5/5 representative tests (one per file). Frontend source restored in finally;
Python mutations disappear with the process. Fault-control source retained in bench.
No production silence guard or reader authority was changed to make tests pass.

## Final measured scope

Production 24 s parity: 7.315206 s / 26 requests; all 13 saved segment dictionaries
exactly equal the original serial 24 s run. Both live lanes retain 86/56 words and
one distinct identity each. Mono 60 s: 4.424305 s / 31 requests. Eight real-stack
runs total, 274/300 calls, trace-derived maximum concurrency 2, all eight final
surfaces agree with saved text/identity. No owned listeners remain on 18112/17872.

Unmeasured: 24/60 alternation matched pairs, all 180 s live arms, fixed-production
60 s rerun (60 s evidence is the absorbed prototype), 30-minute behavior, contention
with multiple live meetings. Budget increase was requested, never received. 300
remains the limit. Concurrency is a measured improvement, not charter acceptance.

Tool deviations: retained all temp/state and baseline archive inside the worktree;
used short relative socket paths via existing WP1 pytest adapter. Added phase2
fixture directory to PYTHONPATH. Frontend uses --configLoader runner so Vite does
not write .vite-temp through the shared node_modules symlink. No shared service or
port 7861/7862 changes, no push/merge/deploy/GitHub, no provider policy changes.

Additional failed measurement-tool attempts: saved comparison initially assumed a
source_lane field and raised KeyError; corrected to exact stored dictionaries and
per-speaker word sequences, with live snapshots used separately for source lanes.
An lsof command supplied LISTEN twice and failed parsing; corrected command found
no listeners. Neither attempt sent decoder requests or changed production behavior.

Full pre-fresh-context gate after fixture corrections: **1802 passed, 2 skipped,
21 warnings, 37 subtests passed in 145.21 s**. Full frontend: **26 files / 230 tests
passed**, typecheck passed, build passed; generated assets unchanged. Python tests
rewrite three WP2 reference PNGs; those generated-only changes were restored to HEAD.
Implementation commits: 33be55ec (terminal concurrency), 9d10e0d8 (adjudicated
fixture corrections). Fresh `/new` verification follows VERIFY.md; do not call a
same-context reread fresh verification.
