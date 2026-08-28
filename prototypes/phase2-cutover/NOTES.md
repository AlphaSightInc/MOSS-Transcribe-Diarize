# Phase-2 attended cutover prototype

## Question and hypothesis

Can one forward cutover plus one incomplete-attempt restore make every reachable crash boundary
truthful without admitting an Account? The hypothesis is that eight primitives suffice: one fixed
host cutover lock, an append-and-fsync phase journal, the existing Phase-1 marker plus both runtime
drain views, one complete snapshot, one immutable release pointer, three exact terminal outcomes,
an explicit `restored|preadmission` target that cannot admit an Account, and one candidate-owned
attended browser observation that cannot be replaced by a profile-authored report.

## One command

```bash
PYTHONDONTWRITEBYTECODE=1 bash prototypes/phase2-cutover/run.sh
```

The probe prints its full structural contract, every durable event, the full simulated host state,
and a derived assertion denominator. It exits nonzero if any assertion fails.

## Falsifier

Reject the design if a crash after any durable mutation cannot restore the original tree exactly;
if two cutovers mutate one host concurrently; if the snapshot roles are missing or extra; if an
attempt overlaps candidate state; if a corrupt archive reopens either product; if the vLLM process
identity changes; if candidate state is discarded instead of quarantined; if a wrong origin passes
G7; or if a pre-admission terminal state has admitted an Account.

## Verdict

The first adversarial extension measured **RED, 60/66 assertions** against the original model.
It exposed six reachable states: two attempts held different attempt-local locks; an attempt nested
inside candidate state was accepted; a tenth unruled snapshot root passed the subset check; a
crash after `restore_started` became non-replayable `SAFE_STOPPED`; `restored` required an absent
attended browser and therefore never recorded `planned_restore`; and an arbitrary HTTPS host/port
was labeled production. These failures select one fixed host lock, exact root equality and
pre-effect overlap rejection, idempotent restore replay, the Wave-1-to-planned-restore branch, and
one committed production origin. No retry framework or second cutover state machine is needed.

The restore-ownership extension then measured **RED, 78/80 assertions**. A normal planned restore
removed and copied all nine explicit old roots even though forward cutover never mutated them. A
crash after both old web units restarted but before the `phase1_started` journal append caused the
next restore to rewrite all nine roots while `moss-web` and `moss-live-web` were running. The vLLM
process remained live in both states, making GPU-runtime/model replacement specifically unsafe.
This rejects unconditional whole-root extraction: existing explicit roots are preservation truth,
automatic unit/profile/pointer targets are restore-owned, and every restore replay must stop both
web units before inspecting or applying snapshot bytes.

The consolidated failure-boundary extension measured **RED, 83/86 assertions**. With the journal
persistently unwritable after `candidate_started`, rollback performed zero effects and left the
candidate running. `SAFE_STOPPED` was published with the marker absent and `moss-live-web` still
active. Restoring a deliberately missing model root reconstructed the right bytes but fsynced no
restored file or directory. These states select best-effort journal recording around independently
owned rollback effects, verified block/listener state before `SAFE_STOPPED`, and recursive fsync of
newly restored regular files and directories before their parent rename and terminal publication.

**PASS, 86/86 assertions.** The corrected probe measured one fixed host lock rejecting a second
attempt, exact nine-role equality, attempt/candidate-state nonoverlap, replay to exact old state
after each of five restore effects, Wave-1 followed by planned restore without G7, exact
production-origin rejection, and nine explicit nonoverlapping old-image roots
(checkout including both runs trees, provider manifest, auth state, shared token, TLS pair, vector
journal, cold GPU runtime, and model), a successful pre-admission state, a successful
canary followed by a deliberate whole restore, a known canary
failure with exact whole restore and candidate-state quarantine, exact restore after each of seven
durable mutation boundaries, unchanged vLLM process identity, and `SAFE_STOPPED` after archive
corruption. A crash before snapshot needs only marker removal and old-process restart; after
snapshot, restore is admitted only when the one archive digest matches its manifested value.
Normal restore wrote zero existing explicit roots. A deliberately missing model root alone was
reconstructed and its regular file plus directory were fsynced. Replay after the unjournaled web
start effect wrote no roots while either web unit was live. Persistent journal failure left its last
durable phase at `candidate_started` but still completed exact physical rollback. When marker
creation failed and one web listener remained active, the model returned
`RESTORATION_UNCERTAIN` and published no `SAFE_STOPPED` terminal.

Wave-1 success with absent attended evidence and a deterministic-rehearsal observation both restore
the old image. Only the production-browser observation reaches `preadmission/G7 PASS`; a planned
`restored` rehearsal remains `G7 UNCLAIMED` even when its deterministic adapter exercises the full
forward sequence.

Real OAuth, trusted TLS, Chrome microphone/tab/screen, and the remote host are deliberately
unmeasured here and cannot close G7.
