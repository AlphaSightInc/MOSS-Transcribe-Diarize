# WP12 prototype — in progress

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
