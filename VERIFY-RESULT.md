# WP6 verification result — 2026-09-18, Fable (MOSS:2.1)

**Evidence integrity: PASS with explicit collector omissions. Capacity: NOT ACCEPTED.**
Fresh continuation started clean at 57907d76ce07e121eabffa8921b50650f9dfd574 on
mvpfix/wp6-capacity-baseline. Import resolved inside the assigned worktree. Part 0
remains accepted. Starting artifacts were verified in this fresh context; new
harness/evidence edits were checked in this same continuation, not another `/new`.

## Executed

- Original VERIFY.md reductions matched before the extra authorized run: four
  historical attempts, 1,612 calls. Original raw run directories remain unchanged.
- Updated VERIFY.md executed after the rerun. All three `cmp` reductions match:
  current SUMMARY.json, original recovered.json, new recovered.json.
- Retention suites: **42 passed, 19 subtests passed, 1 existing warning**, 3.55s
  (initial fresh execution also 42/19, 3.43s). Six Python files compile.
- Full Python, initial repository-local TMPDIR: **4 failed, 1698 passed, 2 skipped,
  21 warnings, 37 subtests**, 161.06s. One long Unix socket path; two staging dry-run
  fixtures inside protected checkout; one known WP4 fixture mismatch. All are
  adjudicated file-by-file in prototypes/capacity-campaign/NOTES.md.
- Full Python, isolated short TMPDIR: **1 failed, 1701 passed, 2 skipped,
  21 warnings, 37 subtests**, 158.38s. Sole failure is the explicitly tolerated
  `tests/phase2/test_voiceprint_latency_measurement.py::test_name_latency_is_independent_of_observer_polling_delay`.
  No source/test changes were made to obtain this result. Full suite is not called
  all-green; it meets COMMON.md's stated exception rule.
- Frontend: **24 files, 206 tests passed**, 2.41s. Initial vitest-not-found attempt
  retained; prescribed node_modules symlink resolved it without installing packages.
- No production diff from 37979e53; `git diff --check` passes. Owned ports 18106/17866
  have no listeners. lsof exit 1 is expected and recorded, not a check failure.

## Independent retained-record checks

Five attempts, thirteen sessions: nine completed, four interrupted (two intentional).
Exactly **2,887 decoder starts and finishes**, maximum own concurrency 2. New run
20260918-002944-4x600: **1,275 starts/finishes**, ordinals 1..1275 match exactly;
4×2,400 acknowledged lane frames; 0/9,600 wrong-owner probe failures.

All four saved MP3 files independently probe **600.000 s**, 16 kHz mono, 3,600,765 bytes.
Two available/completed/final, two partial/interrupted/helper-lease expiry. Stop→final
39.686738/29.489338s for 1/2. Persisted final text equals final API text for those two.
Birth counters 2/2/unknown/unknown; named saved speakers 2/2/1/3. The missing counters,
HTTP status/body and final snapshots for 3/4 remain unmeasured. Accepted/accounted
API counters are exact for 1/2 only; 3/4 audio-sample totals derive from acknowledgments.
The earlier run's speaker overcounts included the unassigned bucket; WP12.md corrects
that interpretation while retaining Jamie's original four-named/three-reference finding.

12/32 foreign-load samples; 3 pauses totaling 269.986569s. Capacity clean=false;
no eight-session run exists. Inference RTF unavailable because interrupted collectors
left incomplete rolling events. No production root cause or repair is claimed.

Shared local manifest matches its retained original bytes and mtime 1787665017563735525.
The actual consumed descriptor states max_tape_bytes=57600000. Exact current staged/
deployed bound remains not recorded; no host inspection was used to infer it.
Original manifest source revision 29681e04 is not claimed as executing code provenance.

## Artifacts and deviations

`evidence/mvpfix/wp6/verify-execution.txt` records literal verification commands/results;
full test logs retain both attempts. `runner-used.py` freezes the actual live collector;
subsequent metadata-only repairs (last-observed counters, HTTP code, speaker category
count) have offline/compile verification, not another live run. No extra decoder calls.
A shell wrapper used zsh's read-only status variable after suites finished; test output
was retained and later wrappers corrected. No test result is inferred from that error.

Only harness/evidence changed. No identity/quality/readiness/mixer/decoder policy
change, shared-manifest edit, push, merge, deployment, shared service restart or peer
message. Exact births and terminal states for failed collectors cannot be supplied
from retained evidence; this limitation is reported instead of retried away.

Committed test logs normalize trailing whitespace only; original stdout retained
in ignored .wp6-tmp/raw-*.txt. Live actions/result/decoder records are unchanged.
