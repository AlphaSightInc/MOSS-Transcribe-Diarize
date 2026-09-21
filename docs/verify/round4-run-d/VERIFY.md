# Round 4 run D — offline verification

**PASS — offline scope.** Run D closes the revoked-owner retention leak without
reopening revoked work or weakening the durable-terminal deletion boundary.

## D4 — ordinary task failures re-signal after durable truth

A File Meeting has two separate facts: its durable operator-visible outcome and
its background task result. A resumed task must return after recording failure
because it runs behind startup. An ordinary upload is not a startup dependency,
so it keeps the prior task failure signal after the same durable outcome and
owner-local cleanup.

Run D chose **restore**, not merely disclose. In
`FileMeetingTasks._complete`, commit and audio-publication exceptions now
re-raise only when `resumed` is false. Both branches first write `failed` and
remove only that Meeting's retained owner directory. The resumed controls still
return after durable `resume_failed`, preserving non-blocking startup.

`test_unresumed_failure_is_durable_and_resignals_task` was RED before the
restoration: the Meeting was `storage_failed` but its task had no exception.
It covers both ordinary failure arms. Together with the retained commit and
publication controls, the focused result is **4 passed**. No decoder, network,
GPU, tunnel, proxy, or provider request was made.

The directly affected ordinary-File and retained-resume modules are also
**39 passed**; `py_compile` and `git diff --check` are clean.

Falsifier: a normal commit/publication failure either lacks its durable failed
Meeting outcome or ends its task successfully; a resumed failure aborts
lifespan.

## D1/D2 — revocation releases only terminal retained owners

`Phase2Store.terminal_file_meeting_owners()` supplies durable terminal File
owners. `FileMeetingTasks.reclaim_terminal_retained_work()` removes their exact
directories only when `parent.parent == retained_root`. Account revoke calls it
after account-scoped fallback has terminalized the revoked Meeting; lifespan
calls it after global recovery, so terminal leftovers under accounts disabled by
an earlier boot are also reclaimed. It neither scans nor deletes an account
directory.

The restored healthy control was RED on the prior tree: revoke and a later boot
both left `owner.json`, `input.wav`, and `checkpoint`. It is green after the
change: `test_account_revocation_does_not_resume_retained_file_work` proves
durable `interrupted`, no decoder dispatch, the retained fence, no owner
directory, and survival of same-account and sibling-account markers.
`test_lifespan_reclaims_disabled_account_terminal_retained_work` proves later
boot reclamation while sibling owners survive. The focused controls were **2
passed** and the retained module was **18 passed**.

Falsifier: a revoked terminal owner remains after revoke or later boot; cleanup
precedes terminal truth; or either sibling owner is removed.

## D3 — remove unreachable retained-recovery surfaces

`release_settled_account_fence` and the unused `account=` parameter on
`resume_retained_work` are removed. The production inventory has one retained
resume call: the unfiltered lifespan owner. There is no account-scoped path
that can revive retained work or release a revoked account's fence. The retained
module was **19 passed** after removal.

Falsifier: a production caller can request account-scoped retained resume or
invoke the deleted fence-release operation.

## D5 — retained last-resort write failure

For resumed work, `_mark_failed` retries one unexpected non-revocation
`MeetingHandle.finish` failure through the same atomic, owner-bound mutation.
It reports whether terminal truth exists; the outer handler removes retained
input only on that truth. `AccountRevoked` reports no truth and preserves the
owner. A permanently unavailable SQLite write still cannot produce a durable
outcome: the task raises and preserves its retained owner for a later boot.

`test_lifespan_retries_a_failed_last_resort_retained_outcome_write` was RED
before the retry with an `active` Meeting. It is green with durable
`failed`/`resume_failed` and exact-owner cleanup.

Falsifier: one transient terminal-write failure leaves the Meeting active, or
cleanup occurs without a durable terminal outcome.

## D6 — historical evidence correction

The append-only Run-D iteration-5 journal entry corrects Run-C iteration 4's
post-boot joining pointer: the actual `await entry.task` evidence is
`prototypes/batch-startup/prototype.py:1148`; commit `9d839bf2` did not touch
the previously cited product-test file. The historical entry itself is intact.

## Required final gates

Run on 2026-09-21 with the pinned Python, `PYTHONDONTWRITEBYTECODE=1`, and
`PYTHONPATH=.`:

```text
$PY -m pytest -q -p no:cacheprovider tests
2162 passed, 0 failed, 5 skipped, 2 xfailed, 37 subtests passed in 168.03s

npm --prefix frontend test -- --run
28 files passed; 312 passed

npm --prefix frontend run typecheck
clean
```

`git diff --name-only round4/integration...HEAD -- frontend` was empty before
the gates. Therefore the PRD's conditional frontend rebuild and asset-parity
gate does not apply. The full backend result exceeds the required 2,158-pass
floor. The checks were offline: no decoder, network, tunnel, proxy, GPU, or
provider request. `_assert_no_active_meetings` remains byte-identical; D13,
the gap remedy, strict Jamie xfails, S17 UNMEASURED, and
`capacity_2x1800` REQUIRED-NOT-RUN retain their stated boundaries.
