# WP6 capacity prototype — local retention correction

## Contract

- **Question:** do four distinct private workspaces retain lifecycle, ownership,
  and acknowledged-content contracts for four simultaneous 600-second sessions?
- **Primitives:** workspace owns authority; session owns ordered lane frames;
  acknowledgment owns the content obligation; decoder request owns compute;
  timestamped observation owns measured evidence. None substitutes for another.
- **Invariants:** private ownership, identical-byte retries, heartbeat each frame,
  nine frame keys, Stop deadline 30, original production policies unchanged.
- **Unknowns:** latency, resource growth, content accuracy, fairness, durability,
  shared-host contention. A prepared runner is not evidence of capacity.
- **Hypothesis/falsifier:** current base meets existing charter G4 bars; an owner
  read other than 404, acknowledged/accounted mismatch, failed/interrupted
  session, or exceeded applicable measured bar falsifies it.
- **Tool decision:** real API replay establishes lifecycle; independent cookies
  establish ownership; events measure canonical lag/fairness/inference; local
  RSS and shared read-only metrics observe resource costs. No synthetic decoder
  can answer this question. Offline preparation only validates corpus/imports.

## 2026-09-18 correction and authorized continuation

F1 applies to the LOCAL August measurement manifest, not a demonstrated deployed
product limit. Round 16 recorded four 600-second finals; its exact tape bound is
not recorded in this checkout. See evidence/mvpfix/wp6/MANIFEST.md. User authorized
one rerun with an isolated 30-minute manifest; finalizer admission passes with no
coupled rolling-bound change. Shared manifest never written.

`copy_manifest.py` creates the ignored copy and `run.py --manifest` forwards it
through stack.py to run_local_stack.py. Actual executing production source remains
37979e53; the manifest preserves its historical revision field, recorded separately.
This is a local measurement adaptation, not staging or deployment.

Original speaker totals included the unassigned bucket. Named counts are 2/2/1/4
for reference 2/2/1/3, not 3/2/2/5 people. Original birth counters were not retained.
The rerun records identity_counts, and recover_run.py independently reads saved
content, probes MP3s and reports named versus unassigned speech. The running runner
is preserved as runner-used.py; the subsequent reporting-only count correction in
run.py excludes unassigned segments for future runs. No identity policy changed.

Commands:
```sh
python prototypes/capacity-campaign/copy_manifest.py
python prototypes/capacity-campaign/run.py --sessions 4 --seconds 600 --manifest .wp6-tmp/manifest-30m.json
python evidence/mvpfix/wp6/recover_run.py evidence/mvpfix/wp6/<new-run>
```

## Original verdict and authority (300-second local cap)

MEASURED / NOT ACCEPTED. Four workspaces each accepted 600 seconds and saved a
completed transcript, but the supplied 9,600,000-byte retention declaration caps
both audio stores at 300 seconds. All four archived partial 300-second MP3s and
reported terminal refinement unavailable. Runtime refusal matches ADR-0003 D5/D8;
no production policy was changed. Eight-session overload was correctly skipped.
Total decoder requests: 1,612 including the preserved interrupted harness attempt.
See evidence/mvpfix/wp6/REPORT.md for exact measurements and limits.

User explicitly authorized the existing vLLM decoder through this
lane's own 18106 forward, the 1x120 -> 2x300 -> 4x600 ladder, and conditional
8-session overload. Shared vLLM restarts/reconfiguration and ports 7861/7862 remain
forbidden. Pause after more than one consecutive foreign-load sample; resume when
clear. Previous decoder-authorization block is superseded.

Part 0 is complete; see evidence/mvpfix/wp6/PART0.md. The import-mutation premise
was falsified; the defect is pytest directory-autouse registration across ordered
file arguments. Production SQLite pin remains unchanged.

## Commands (cwd = this worktree)

Use the COMMON.md Python, with PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.

```sh
python prototypes/capacity-campaign/run.py --sessions 4 --seconds 600 --prepare-only
# Authorized ladder:
python prototypes/capacity-campaign/run.py --sessions 1 --seconds 120
python prototypes/capacity-campaign/run.py --sessions 2 --seconds 300
python prototypes/capacity-campaign/run.py --sessions 4 --seconds 600
# Only after reviewing the clean 4x600 result and its limitations:
python prototypes/capacity-campaign/run.py --sessions 8 --seconds 120 --four-session-result evidence/mvpfix/wp6/<4x600>/result.json
```

Inspect each result before progressing. Eight sessions cannot start without a
clean 4x600 result. Actual GPU requests are whatever sessions generate (WP6-specific
budget supersedes COMMON's 200); stack.py enforces at most two own requests in
flight. This measurement-side limiter must be retained on the integrated rerun.
No production policy/mixer/decoder math is changed.

The runner creates and stops its own 18106 tunnel and 17866 HTTPS stack, uses
relative state paths under .wp6-tmp to fit the Unix socket limit, and writes only
metadata to evidence. Local state/audio/certificates/logs remain in ignored
.wp6-tmp; never commit them. Corpus audio is read, never added to git.

## Measurement definitions and limits

- Charter G4 canonical p95 lag: runtime event time minus committed audio end,
  linear Type-7; compare <=10 seconds. Coverage buckets are additionally reported,
  including missing denominator buckets, but silence is not a new failure bar.
- First text: API poll from replay start; compare 4 seconds descriptively. This is
  not the attended browser row-4 onset/paint test or enrolled-label gate.
- WER: ordered edit distance against complete looped reference. If the last loop
  ends within a reference sentence, exact WER is null and partial-row count retained.
  Unique vocabulary is a witness, not accuracy. QUALITY_BOUNDS are reported; the
  six-case/two-pass quality macro is not inferred from this different population.
- Clean means measured local campaign predicates, not deployed G4 certification.
  Remote process-tree RSS, remote journal errors, full source-content cross-talk
  adjudication, and the fixed quality corpus remain unmeasured. Local RSS alone
  cannot prove the charter's combined service/inference RSS bound.
- Foreign-load detection compares shared running+waiting with observed own active
  calls. Excess proves contamination; absence cannot exclude brief/interleaved
  foreign requests between 30-second samples. From the two-session step onward,
  shared completed-request deltas also detect calls exceeding the maximum our stack
  could have completed in that interval. More than one consecutive foreign sample
  pauses ingress and decoder dispatch while heartbeats continue. Resume requires a
  zero queue AND no excess completions in the interval. Resumed runs stay contaminated
  and cannot pass; audio cadence excludes the pause rather than catching up in a burst.
  A busy preflight waits and resamples every 30 seconds without dispatch.
- Reference-aligned halves supply distinct clips for eight sessions from six source
  files. WER with a cut final sentence is deliberately unmeasured, never fabricated.
- Retryable 429 is retried byte-for-byte for up to the existing 30-second Stop
  budget (harness timeout, not a new production acceptance bar); retry/progress
  observations are retained. HTTP 429 bodies on this base do not all expose the
  internal retryable_queue_backpressure keyword. The runner records actual code.
- The original collector missed `unavailable`, waited 90 seconds, and omitted
  terminal metrics for the four-session run. It now recognizes that declared ending,
  keeps exact replay/Stop anchors and a local ignored final snapshot, and records
  Stop-to-final as null when no final exists. Original failures are preserved;
  `recover_four.py` reads the saved transcript/audio offline and labels timing bounds.
  The original ladder was not retried; the later isolated-manifest rerun has separate explicit user authorization.
- Paused-run wall-clock lag and decoder elapsed timing include pause/dispatch waits;
  they are not uncontended inference measurements. Words/minute uses audio duration.
- Setup failures and exceptions write failed results, then terminate every owned
  subprocess. No production repair should follow a harness-only failure.

Retain this explicitly provisional harness for the integrated-build rerun, per
WP6 brief (exception to deleting the throwaway prototype). Live results and failed harness attempts are retained under evidence/mvpfix/wp6/.


## Authorized rerun verdict: retention corrected, capacity NOT ACCEPTED

Run 20260918-002944-4x600 used the isolated 30-minute cap exactly once.
4/4 MP3s are 600.000 seconds; 2/4 final, 2/4 helper-lease interrupted. Stop-to-final
39.686738/29.489338 seconds for sessions 1/2; unavailable for 3/4. Foreign traffic
in 12/32 samples, three pauses totaling 269.986569 seconds. All 9,600 lane frames
acknowledged; no wrong-owner success in 9,600 probes. 1,275 decoder calls completed,
max own in-flight 2; WP cumulative 2,887. App RSS growth 466.265625 MiB, not a remote
process-tree or leak claim. No eight-session step because the prerequisite failed.

The exception path omitted HTTP status/body and failed-session snapshots. Saved
SQLite and app logs establish interrupted status/lease expiry and complete-length
partial MP3s, but not an exact causal Stop sequence or birth counters for 3/4.
STOP-ASSESSMENT.md records the hypotheses and missing evidence. No production fix
is justified from this contaminated run. Subsequent reporting-only edits preserve
last-observed counters and HTTP status/code; no live retry of those edits.

## Full-suite environment adjudication

Initial full Python run used the original VERIFY.md TMPDIR inside this checkout:
4 failed, 1698 passed, 2 skipped, 21 warnings, 37 subtests (161.06s).
- tests/phase2/test_browser_workspace.py: the inherited long TMPDIR makes the
  temporary control socket exceed the 104-byte host limit. No production bug.
- tests/phase2/test_candidate_storage.py: both dry-run parameters place the test
  victim under the protected PROJECT_DIR because TMPDIR is inside the checkout.
  The staging retention tool correctly refuses to prune that protected subtree.
- tests/phase2/test_voiceprint_latency_measurement.py: the existing fixture has
  Private voiceprints/button while Harness.bank expects Meeting history/Voiceprints
  tab. This is COMMON.md's explicitly tolerated pre-WP4 failure, not changed here.

The full suite is rerun using an isolated short /private/tmp/wp6-verify.* directory,
with source/tests unchanged. Both attempts remain committed. Frontend initially
could not find vitest; adding COMMON.md's prescribed node_modules symlink gives
24 files/206 tests passed. An invocation wrapper also used zsh's read-only `status`
variable after tests finished; the exact pytest/vitest output is retained, and
subsequent wrappers use wp6_test_status. No test result is inferred from that wrapper.

Short-temp full-suite result: **1 failed, 1701 passed, 2 skipped, 21 warnings,
37 subtests passed in 158.38s**. Only the documented WP4 fixture failure remains.
Both environment hypotheses were confirmed without changing source or tests.

## WP30 — repeated sessions and safe overload (in progress)

Q1: does finalized-session ownership accumulate in a single process?
Q2: does one process-scoped canonical worker fairly serve 8/16 active lanes?
Primitives: workspace authority, acknowledged PCM, pending canonical work,
immutable published result, mutable identity evidence and process memory.
Invariants: frame schema, policies, queue capacity, leases, lane separation,
acknowledged accounting and saved words must survive unchanged.
Hypothesis: bounded work makes overload retryable; final releases expendable
session evidence. Falsifiers: non-404 foreign reads, acknowledged/accounted loss,
terminal failures, unfair dispatch, or retained mutable owners after final.
Unknowns: residual native allocation, recognition accuracy, deployment capacity.

Tool decision: timed stub at the real decoder boundary preserves production VAD,
ONNX identity, HTTP, scheduler, persistence and lifecycle. Tracemalloc plus native
RSS distinguishes Python owners from process totals. Full speech on BOTH lanes;
Ackman system / Keyu Jin microphone, looped at original amplitude. Workspace
isolation uses distinct cookies even though the speech inputs are identical.
Stub words are synthetic: PCM acknowledgements do not label words, so a word-loss
count versus acknowledged audio is unknown. Saved/final ordered word equality
and accepted/accounted samples are measured separately. No synthetic WER claim.

One-command runs (COMMON Python; PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.):
```
python prototypes/capacity-campaign/run.py --sessions 1 --seconds 600 --repeat 6 --stub-latency .6
python prototypes/capacity-campaign/run.py --sessions 4 --seconds 600 --stub-latency .15
python prototypes/capacity-campaign/run.py --sessions 8 --seconds 300 --stub-latency .15
python prototypes/capacity-campaign/run.py --sessions 4 --seconds 300 --wp30
```
The first command uses one unchanged server process for all six sessions.
The real command owns 18130/17890, hard caps requests at 600 and own concurrency
at two. Contention is recorded without pauses. No real calls during stub work.
The copied measurement manifest retains the whole requested duration; only its
max_tape_bytes increases if necessary, preserving other bounds/policies.
Local SQLite runtime pin bypass inherited from the existing bench.
Scratch/audio/certificates/databases stay ignored under .wp30, inside this tree.
Telemetry prints checkpoints and records all owner/queue samples every five seconds.
Scripted actions replace the prototype skill's interactive TUI, per WP30's exact
campaign requirement. Benchmark instrumentation is retained in the shared bench.

Smoke 1x10 s, 0.6 s stub: final/completed, 40 acknowledged frames, 160000 accepted
and accounted samples, saved words identical, 12 stub requests. All tapes empty;
lane albums and sweep ledgers remain reachable after final. This is a witness of
ownership, not yet evidence of a material repeated-session leak.

Candidate release experiment (not production): final public snapshot, identity
counts and immutable enrollment/match observations are the lasting contract;
mutable per-lane preparers/album/sweep evidence is used only until terminal
fallback completes. Cache the immutable observations, then drop preparers after
`_run_terminal` returns final. Never release at Stop while the final decoder
still needs lane evidence. Falsifier: changed snapshot/counts/observations, or
weak references proving preparers survive. `release_prototype.py` records before
and after traced bytes and all equality checks. Enable only in a subsequent
stub process with `WP30_PROTOTYPE_RELEASE=1`; baseline stays unchanged.

Baseline in-flight observation: the first 600 s session finished with all 2400
frames accounted and exact saved text, but Stop-to-final was 313.107411 s.
After capture the canonical queue drained, while rolling refinement continued
through its ten-second windows before terminal finalization began. This is a
measured slow-stub latency limit, not a crash or a canonical scheduling deadlock.
First immediate final checkpoint: RSS 991.8125 MiB, traced 60.63 MiB, 480 retained
lane sweep spans. SSL transport buffers also appear in traced allocations; these
can await cyclic collection. Candidate before/after deltas collect already-dead
cycles first, avoiding misattribution of that unrelated reclamation to lane release.

Concurrent fixture choice: use the brief's 0.15 s endpoint for Q2/Q3. The
measured single-session canonical rate is approximately 480 calls / 600 s;
four sessions at 0.6 s require 1.92 decoder-seconds per wall second before
identity work. That setting would overload four by construction. Q1 retains
0.6 s unchanged; Q2/Q3 record 0.15 s explicitly, with production identity cost
still present. No production threshold or dispatch policy changes.

Release prototype verdict: PASS (20260918-054242-2r-1x10). Two final sessions,
four lane preparers, zero surviving weak references; snapshot, journal, matches
and counts unchanged in both. Traced release deltas 75,697 / 70,726 bytes on
these short meetings after removing unrelated dead cycles. This establishes
ownership release, not a native RSS promise. Production regression reproduces
retention on all three endings: final, failed terminal, no terminal listener
(3 failures at the weak-reference assertion on the unchanged production code).
Absorb by freezing final observations and releasing lane preparers after the
last reader; retain final session/history and the shared encoder.

Production gate after release fix: 1923 passed, 2 skipped, 37 subtests passed
(full Python tests, 147.08 s); frontend 264/264, typecheck and build passed.
The earlier subset recorded 87 passed / 2 failed: both failures were imports of
`_browser_workspace_fixtures` from phase2 tests without collecting that test
directory. Full collection resolves the fixture import; both pass. No fixture or
production change was made for those invocation failures. New lifecycle tests
all pass for final, failed terminal and absent terminal reader.

## 2026-09-20 qualification-bundle population prototype

Question: can the short bundle run the established two-session development step
without hiding the required 30-minute confirmation or underfunding either selected
population? The minimum primitives are selected session durations, retained decoder
rate, file windows, browser cases, and headroom. The invariant is admission before
any bundle or decoder startup; the 2x300 and 2x1800 rows are mutually exclusive.

The focused production-path control in `tools/qualify/test_bundle.py` was RED 4/4,
then GREEN 4/4. It measured the short plan as 1,729 live seconds plus 11 file windows
and 16 browser cases: `ceil((1729 * 0.51 + 11 + 16) * 1.25) = 1136`. The long plan
remains 3,068. A bare long run with the short default therefore refuses with a 1,932
request shortfall. A changed population, admitted shortfall, wrong runner duration,
or missing `capacity_2x1800: REQUIRED-NOT-RUN` would falsify the policy.
