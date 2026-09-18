# WP6 capacity prototype — 4x600 not accepted

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

## Verdict and authority

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
  The corrected reporting path was not used to rerun the load to green.
- Paused-run wall-clock lag and decoder elapsed timing include pause/dispatch waits;
  they are not uncontended inference measurements. Words/minute uses audio duration.
- Setup failures and exceptions write failed results, then terminate every owned
  subprocess. No production repair should follow a harness-only failure.

Retain this explicitly provisional harness for the integrated-build rerun, per
WP6 brief (exception to deleting the throwaway prototype). Live results and failed harness attempts are retained under evidence/mvpfix/wp6/.
