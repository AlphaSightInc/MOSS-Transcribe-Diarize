# Phase-2 attended cutover prototype

## Question and hypothesis

Can one forward cutover plus one incomplete-attempt restore make every reachable crash boundary
truthful without admitting an Account? The hypothesis is that seven primitives suffice: an
append-and-fsync phase journal, the existing Phase-1 marker plus both runtime drain views, one
complete snapshot, one immutable release pointer, three exact terminal outcomes, and an explicit
`restored|preadmission` target that cannot admit an Account, plus one candidate-owned attended
browser observation that cannot be replaced by a profile-authored report.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 bash prototypes/phase2-cutover/run.sh
```

The probe prints its full structural contract, every durable event, the full simulated host state,
and a derived assertion denominator. It exits nonzero if any assertion fails.

## Falsifier

Reject the design if a crash after any durable mutation cannot restore the original tree exactly;
if a corrupt archive reopens either product; if the vLLM process identity changes; if candidate
state is discarded instead of quarantined; or if a pre-admission terminal state has admitted an
Account.

## Verdict

**PASS, 61/61 assertions.** The probe measured nine explicit nonoverlapping old-image roots
(checkout including both runs trees, provider manifest, auth state, shared token, TLS pair, vector
journal, cold GPU runtime, and model), a successful pre-admission state, a successful
canary followed by a deliberate whole restore, a known canary
failure with exact whole restore and candidate-state quarantine, exact restore after each of seven
durable mutation boundaries, unchanged vLLM process identity, and `SAFE_STOPPED` after archive
corruption. A crash before snapshot needs only marker removal and old-process restart; after
snapshot, restore is admitted only when the one archive digest matches its manifested value.

Wave-1 success with absent attended evidence and a deterministic-rehearsal observation both restore
the old image. Only the production-browser observation reaches `preadmission/G7 PASS`; a planned
`restored` rehearsal remains `G7 UNCLAIMED` even when its deterministic adapter exercises the full
forward sequence.

Real OAuth, trusted TLS, Chrome microphone/tab/screen, and the remote host are deliberately
unmeasured here and cannot close G7.
