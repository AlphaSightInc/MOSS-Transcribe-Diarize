# R4-5 durable File/URL startup prototype

## Verdict

**SUPPORTED for run B**, prototype only. The existing Meeting can remain the sole
durable owner if valid retained File/URL work is claimed and completed before today's
generic interruption path. The unchanged zero-active assertion then remains true.

No production code changed. No GPU, tunnel, network, or remote decoder request was used.
The local-HF snapshot appeared after the interrupted pane run, so the optional real
runner smoke was run and passed.

Run every deterministic case and print full state:

```sh
prototypes/batch-startup/run.sh all
```

Run one case by replacing `all` with its case name from `--help`. Run the optional
real local-HF smoke:

```sh
prototypes/batch-startup/run-real-smoke.sh
```

Canonical state is in `results.json`; retained copies are under
`evidence/round4/batch/`.

## Structural contract

- **Question:** can one existing File Meeting own retained progress across real app
  restart, with discovery before generic interruption and cleanup?
- **Minimum primitives:** normalized local source; contiguous committed prefix;
  owner `(account, meeting, source, contract)`; pending windows; durable terminal
  transition. A non-blocking OS file lock is transient exclusion, not a durable owner.
- **Invariants:** no received-data loss; no wrong-owner resume; one publication; exact
  reopen; cleanup only after terminal truth; Live recovery unchanged.
- **Assumptions/unknowns:** SQLite 3.50.4 was allowed as a prototype semantic store in
  place of required 3.53.4. The account-scoped method is called directly after resolving
  a session; the base has no login caller for it—its only product caller is account
  revoke at `phase2_lifecycle.py:231-235`.
- **Falsifier:** wrong owner/source/contract decodes; corrupt prefix decodes; any window
  or segment is lost/duplicated; publication repeats; cleanup precedes terminal truth;
  competing startup proceeds; or a Live row resumes.
- **Tool decision:** deterministic 101-window production checkpoint semantics isolate
  lifecycle causality. The real FastAPI lifespan proves ordering. Local HF proves the
  restored model can traverse one actual File path; it does not qualify restart
  acoustics or 200-minute throughput.

## Measured cases

| Case | Verdict | Measured state |
|---|---|---|
| C1 interrupt after 40 | SUPPORTED | 61 calls (`40..100`); 101/101 unique saved segments; publication version 1; exact reopen; cleanup after terminal |
| C2 mid-window crash | SUPPORTED | failed call 40; next startup redid 40 once then `41..100`; 101/101 unique; one publication |
| C3 cancel during resume | SUPPORTED | one call `[40]`; no later calls; durable `status=interrupted, failure_code=cancelled`; cleanup after terminal |
| C4 duplicate startup | SUPPORTED | one OS-lock owner; second lifespan refused; 61 total calls; prefix uncorrupted; one publication |
| C5 wrong owner/source/contract | SUPPORTED | 3/3 refused before decode; 0 publications; each Meeting honestly interrupted; retained source directory preserved |
| C6 damaged prefix | SUPPORTED | missing committed window refused before decode; interrupted; retained source directory preserved |
| C7 URL unavailable | SUPPORTED | retained local copy: 61 calls, 101/101, 0 remote fetches; no local copy: refused, interrupted, 0 fetches |
| C8 account-scoped recovery | SUPPORTED at exact method | session-resolved Account; 61 calls; 101/101; zero active rows. No base login caller exists, so this does not claim a measured login flow |
| C9 non-resumable File | SUPPORTED | current behavior preserved: interrupted; 0 calls; 0 publications |
| C10 D13 Live falsifier | SUPPORTED | Live row interrupted; 0 File calls; unchanged zero-active assertion held |
| C11 local-HF smoke | SUPPORTED | real lifespan; first 10 s of `mono_javier_intro_50s`; completed; 3 segments / 120 text chars; 10.207 s; offline; 0 remote requests |

Deterministic denominator: **10/10 supported**. Base violating controls:
**2/2 strict xfail** (valid retained File and URL prefixes are interrupted on unpatched
`89f833ac`, with zero remaining calls).

## Reconciliation proved

```text
real lifespan opens store
→ File owner claims and validates retained source + prefix
→ valid work reaches completed/cancelled terminal truth
→ current generic File recovery interrupts every remaining File row
→ current Live recovery interrupts Live rows
→ unchanged _assert_no_active_meetings sees zero
→ transient-only cleanup runs
```

Cancellation uses the existing durable vocabulary: Meeting `interrupted` plus outcome
`failure_code=cancelled`. A fourth Meeting status is unnecessary.

## Minimal production seams for run B

- `phase2_file.py:105-141,162-211,332-417`: deepen `FileMeetingTasks`; move the
  normalized local source and checkpoint into a Meeting-keyed durable directory after
  Meeting creation; retain URL acquisition locally; validate owner/source/checkpoint;
  pass that checkpoint at `:417`; remove only after durable terminal truth. Keep
  `file-work` transient and separate.
- `phase2.py:1927-1941`: invoke File retained-work claim/resume before
  `recover_active_meetings`; keep `clear_transient_work()` after recovery.
- `phase2.py:716-749`: keep as the fallback for all unclaimed, invalid, and
  non-resumable File rows. No skip list is needed if claimed rows become terminal first.
- `phase2.py:751-763`: **no weakening**. The assertion must remain unchanged.
- `phase2_lifecycle.py:215-236`: apply the same File claim before the existing
  account-scoped recovery caller. Do not call it “after login” without adding/measuring
  a real login caller.
- `windowed_transcription.py:197-255`: existing checkpoint validation/wiring is
  sufficient; no new checkpoint framework or threshold is needed.

## Controls run B must carry

- **Healthy H1:** C1 plus exact reopen, one publication, and terminal-before-cleanup.
- **Healthy H2:** C9 and existing startup cleanup tests remain unchanged.
- **Healthy H3:** C10 plus existing Live recovery tests keep D13 and the zero-active
  assertion.
- **Violating V1:** un-xfail
  `test_r4_5_base_lifespan_resumes_valid_retained_prefix[file]`.
- **Violating V2:** un-xfail the same control for `[url]`.
- **Violating V3:** wrong owner/source/contract, corrupt prefix, and competing startup
  must make zero delegate calls and zero publications.
- **Violating V4:** a Live row offered retained File artifacts must still interrupt and
  must never enter the File runner.

## Boundaries

- The deterministic runner proves lifecycle/window ownership, not acoustic quality.
- The local-HF smoke proves one short current-host path only; it does not prove resume
  quality, 200-minute runtime, or resource bounds.
- SQLite 3.50.4 substitution is prototype-only and cannot qualify production runtime.
- The P2 SQLite semantic-store allowance remains explicit; no product bypass was made.

## C12 — background retained resume (Run C C2)

**Question.** Can a valid retained File Meeting continue as the existing owner after
lifespan starts, while generic recovery terminalizes only an unclaimed File row and a
resume failure remains visible on its Meeting?

**Hypothesis.** Claiming a valid owner before fallback recovery, preserving that active
row, and running its existing windowed work in the background is sufficient. No new job
identity, status, threshold, or scheduler is required.

**Falsifier.** Lifespan waits for the held resume; the unclaimed row remains active;
the claimed row is interrupted by fallback; or a controlled mid-window failure lacks a
durable `failed/resume_failed` outcome.

**Command.**

```sh
MOSS_R4_NO_WRITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/batch-startup/prototype.py --case background-resume
```

**Verdict. SUPPORTED.** The 2026-09-21 C12 run entered real lifespan while the claimed
resume remained active; its one released window completed with one publication. The
simultaneous unclaimed File row became `interrupted`. A separate controlled failure
became durable `failed/resume_failed`. Both owner directories were removed only after
terminal truth. The deterministic runner used zero decoder, network, tunnel, or GPU
requests; it measures lifecycle composition, not acoustic quality. The one-second wait
is a prototype liveness falsifier, not a product timeout or policy.
