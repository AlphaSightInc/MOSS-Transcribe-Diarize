# Wave-1 qualification policy probe

## Question and hypothesis

Can one immutable candidate manifest and one write-once attempt bundle prove or refuse the
cumulative Wave-1 core without manufacturing deployed or G7 evidence? The measured design needs
thirteen irreducible primitives: immutable candidate identity, a write-once attempt bundle, pure
gate predicates, collection only through already-authorized adapters, machine test denominators,
distinct content boundaries, the production archive oracle, canonical output identity, measured
fairness, one disposable revoked session, campaign-unit denominators, mechanical cutover rehearsal,
and the installed operator CLI projection.

### Review-falsifier experiment contract

- **Structural question:** can the exact accepted command, G4 fairness, G5 revoked boundary,
  external denominators, cutover rehearsal, and G6 operator surfaces pass only when their underlying
  product state was exercised?
- **Minimum primitives:** `git_sha` at the output boundary; queued/started/processed lifecycle
  evidence during joint readiness; one already-revoked disposable session; 15/4/8/12/122 raw
  campaign units; actual isolated block/drain/archive/release/restore operations; and installed
  `mtd-admin status` human plus JSON output through the one status allowlist. Each primitive has one
  boundary and removing any one recreates its corresponding false pass.
- **Invariants:** the valid candidate path reaches an exclusive attempt; absent contention is not
  fairness; G5 does not revoke G2's future peer; terminal evidence exposes raw unit denominators; a
  missing release cannot install; exact old bytes return after forced failure; direct UDS success
  cannot stand in for the required human and JSON CLI surfaces.
- **Assumptions and unknowns:** real OAuth, deployed speech campaigns, production TLS, and attended
  cutover remain externally unmeasured. The isolated rehearsal proves mechanics only and never G7.
- **Falsifier:** `git_sha` raises before the bundle; no queued/started events pass G4; the G5 401
  probe is still valid; 15/4/8/12/122 are absent; a dangling release passes rehearsal; or operator
  raw state passes without both CLI surfaces.
- **Tool decision:** call the production entrypoint and reducers because a model cannot establish a
  reachable false pass; use a temporary isolated host because filesystem install/restore truth
  cannot be measured in memory. Any observed falsifier rejects the production candidate.

### Crash-prefix oracle experiment contract

- **Structural question:** can recovery prove the maximal accepted Live prefix without inventing an
  MP3 duration tolerance?
- **Minimum primitives:** the exact accepted PCM prefix, plus the existing
  `MeetingAudioArchive.publish_live_prefix` encoder. PCM is the only accepted-audio truth before a
  crash; the production archive is the only component that defines retained MP3 bytes and metadata.
- **Invariants:** the same PCM, ffmpeg, and archive policy produce identical MP3 bytes and metadata;
  no threshold, alternate encoder, or transcript content enters the comparison.
- **Assumptions and unknowns:** production ffmpeg determinism for identical raw PCM was unmeasured
  before this experiment.
- **Falsifier:** two independent archive publications of the same exact PCM differ in bytes or
  metadata. That result rejects byte equality as the recovery oracle.
- **Tool decision:** run the production archive twice in separate Meeting directories because only
  that experiment can distinguish exact determinism from an unsupported duration tolerance. A
  mismatch changes the design; no provider, browser, or deployment tool is needed.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 bash prototypes/phase2-wave1-qualification/run.sh
```

## Measured verdict

**RED before correction: 18/25 derived assertions passed.** Exact production paths measured:

- valid `git_sha` output raised `KeyError` before `AttemptBundle`;
- four-session evidence with all queued/started lifecycle removed, `fairness_measured=false`, and
  reported skew zero still passed;
- G5 selected the still-valid `b_peer` and therefore observed `200`, not the required revoked `401`;
- no terminal production projection exposed the 15 actions, 4/8 capacity sessions, or 12
  sessions/122 windows;
- a manifest naming a missing candidate release still reported a passing cutover rehearsal; and
- G6 passed without exercising installed `mtd-admin status` human or JSON output.

The prior **PASS, 18/18** base policy and isolated Linux runtime falsifier remain valid for the
previously measured primitives. The full printed state also proves:

- exact SQLite 3.53.4 plus clean/same-SHA/all-layer evidence can pass the cumulative core while G7
  remains explicitly unclaimed;
- SQLite 3.50.4, a dirty candidate, a different evidence SHA, a missing deployed layer, and one raw
  false predicate each refuse qualification;
- an existing candidate manifest cannot be overwritten; and
- a failed attempt remains a failed artifact rather than becoming a retry target;
- machine-reported test denominators reject a decreased suite, a skipped required case, and a
  missing required file rather than trusting a command exit code;
- privacy scanning cannot qualify with missing, empty, or duplicate Account sentinel/session
  boundaries; and
- the exact cross-owner action set rejects a missing action or a before/after mutation.
- two production `MeetingAudioArchive` publications of the same 50,731-sample PCM prefix were
  byte-identical (19,917 bytes each) with identical 3,171 ms metadata. Exact recovered bytes and
  metadata therefore replace the rejected 100 ms duration tolerance.

**GREEN after correction: 25/25 derived assertions passed.** The exact command now reaches the
exclusive attempt claim using `git_sha`; capacity rejects missing contended lifecycle events; G5
uses its disposable revoked session; terminal evidence exposes 15/4/8/12/122 raw units; the
isolated rehearsal verifies manifested release/launcher/unit bytes, executes a forced-failure
restore, directly compares the whole old tree, and observes unchanged vLLM runtime bytes; and G6
requires both installed `mtd-admin status` surfaces through the shared allowlist. Candidate staging
executes SQLite construction and installs launchers from the detached candidate checkout. The
running Account process must resolve through the manifested immutable release and active pointer.

The available development runtimes are not qualification candidates: CPython 3.10.19 and 3.12.12
both report SQLite 3.50.4; CPython 3.14 reports 3.53.0; `pysqlite3==0.6.0` reports 3.51.1. The
production driver must refuse all of them because ADR-0008 requires exactly 3.53.4. APSW was not
substituted: it would replace the settled `aiosqlite==0.22.1` persistence implementation rather than
package the accepted runtime.

An isolated Ubuntu 24.04 production-semantics build then established the smaller positive seam.
Stock dynamically-linked `/usr/bin/python3.12` reported SQLite 3.45.1. The official
`sqlite-autoconf-3530400.tar.gz`, pinned to its published SHA3-256, built one shared library under an
additive private prefix. Applying that prefix only through `LD_LIBRARY_PATH` made the same Python
and a clean candidate wheel report SQLite 3.53.4 with `aiosqlite==0.22.1`, WAL, foreign keys on,
`synchronous=FULL`, schema v1, and the same truth after close/reopen. Without the prefix, store open
failed before creating a database parent. Therefore a full CPython rebuild is unnecessary: one
private SQLite library plus a separate Account web virtual environment is the minimum packaging
primitive. The GPU/vLLM environment never loads it.

The production driver now owns the write-once attempt, machine-reported Python and frontend
denominators, exact external predicate reduction, candidate wheel/installed RECORD projection,
Account-cookie replay adapter, and isolated whole-restore rehearsal. Its candidate staging path
strong-constructs the SQLite prefix and an immutable clean-wheel Account runtime beside the live
Phase-1 deployment; it does not activate either. Real Google OAuth, deployed four-session and
quality campaigns, production TLS, installed-host identity, and the production-origin canary remain
**unmeasured**. The prototype uses complete synthetic observations only to falsify the reducer; they
are not release evidence and cannot claim G7.
