# Wave-1 qualification policy probe

## Question and hypothesis

Can one immutable candidate manifest and one write-once attempt bundle prove or refuse the
cumulative Wave-1 core without manufacturing deployed or G7 evidence? The measured design needs
seven irreducible primitives: immutable candidate identity, a write-once attempt bundle, pure gate
predicates, collection only through already-authorized adapters, machine test denominators,
distinct content boundaries, and the production archive oracle.

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

**PASS, 18/18 derived policy assertions plus the isolated Linux runtime falsifier.** The full printed state proves:

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
