# Side preflight prototype

Structural question: can a staged Account release run three production acceptance
predicates on an isolated HTTPS side origin, with content-free evidence and no
Phase-1 mutation?

Minimum primitives: staged release; disposable app state; trusted side origin;
normal HTTP workspace bootstrap; production `FixedAccountCampaign`; decoder
counter; cleanup. Each binds a different authority or observation.

Invariants: only port 7863 on the host, no Phase-1 unit operation, zero local
real decoder requests, frozen acceptance bounds, unchanged campaign methods,
content-free retained receipts. Quality runs both frozen passes; G9's nested
600-second capacity is part of G9. No skipping either.

Assumptions/unknowns: host profile assets and side-port TLS must work; staging
must retain the required model and corpus; local Mac has no staged host runtime,
trusted tailnet cert, model directory, quality corpus, Linux systemd journal, or
`/proc` metrics surface. G9 needs a completed and named production Live meeting
before invocation. The capacity code hardcodes `moss-web.service` and journal
units, so a side-process substitution would be required and is **not** yet
validated as qualification-equivalent.

Falsifier: any selected predicate reads Phase-1 identity/state/logs, lacks its
prerequisite, cannot finish on a local stub through the same driver, or emits
content-bearing retained output. A stub pass would prove orchestration only,
not quality or host qualification.

Tool decision: inspect production seams to identify hidden prerequisites;
run a local loopback stub to prove zero-real-request boundary and count calls;
run the exact driver only if its dependency and identity checks succeed.
Host execution belongs to the lead and requires a staged runtime/cert/profile.

Verdict on ec54ddb0: falsified. The production load method binds telemetry to
the Phase-1 units; a side run would observe the wrong process/journal. The
guard exits before any app starts. Stub HTTP smoke was 200 with 0 requests,
but the full selected-predicate run is unmeasured.

Command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python prototypes/round6-side-preflight/run.py --help`

Step 2 structural question: can the existing `web_unit` config bind PID and
journal telemetry to one side user service while the default still binds to
`moss-web.service`? Minimum new primitive: one validated web unit name. The
decoder remains the one canonical vLLM unit. Invariants: default H1 commands
and units stay identical, unsafe/unloaded names fail before measurement,
and no `crash_recovery` runs. Unknown: real host transient unit lifecycle and
trusted TLS are host-only. Falsifier: a side-configured load opens a Phase-1
journal or PID, or the journal reports a different unit than requested.
Tool decision: a focused fake-systemd RED test exercises the production load
call site and reader; full backend/bundle detects default-path drift; local
stub checks only HTTP orchestration. Hypotheses: fixed journal literal;
restricted PID allowlist; restricted journal allowlist; later host asset/TLS
prerequisites. The first three are independently testable here.
