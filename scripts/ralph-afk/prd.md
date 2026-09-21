# PRD - MOSS round 4, ralph run D: close the revocation retention leak

An adversarial acceptance review of run C confirmed C2–C7 and every run-B regression check, and confirmed that the
revoke resume/unfence hole (C1's first half) is genuinely shut. It then found that **C1's second half was not done and
its control was deleted rather than corrected**: a revoked account's retained input is now kept forever. Run D closes
exactly that, plus four small disclosures the review named. Nothing runs C or B achieved may regress.

## Goal

> When an account is revoked, the raw media and checkpoint it left behind must stop being held. Revocation is the
> moment a person expects their data to be released, so the retained owner directory must not survive it — and the
> control that proves so must exist, not have been deleted.

## Acceptance bar

Every point below, with evidence (commands, exact counts, before/after) in progress.txt:

- **D1 — revocation releases the retained input.** Reproduce the leak first and record it: after `_revoke_account`,
  `retained_root/<account>/<meeting>` still contains `owner.json`, `input.wav` and `checkpoint`, and survives a later
  boot because `active_file_meetings` joins `a.enabled = 1` (`phase2.py:637`), so the row is never claimed, refused or
  reclaimed, and `clear_transient_work` only touches `_work_root` (`phase2_file.py:159-179`). Then make revocation
  release it **after** the Meeting's durable terminal truth, never before, and never beyond that Meeting's own
  directory (`_remove_retained_work_dir`'s `parent.parent != retained_root` guard must still hold). A disabled
  account's already-terminal leftovers from an earlier boot must also be reclaimed — decide where that belongs and say
  why.
- **D2 — the deleted control is restored, corrected, not dropped.** Run B asserted `assert not owner_dir.exists()`
  after revoke; run C removed it with no successor. Restore an equivalent assertion in the C1 healthy control
  (`tests/phase2/test_retained_file_claim.py`), alongside the existing `decoder.calls == []`, `("interrupted", None)`
  and still-fenced assertions. Prove it RED on the current tree first. A sibling account's and a sibling meeting's
  retained directories must be proven to survive.
- **D3 — no dead revocation-adjacent entry points.** `release_settled_account_fence` (`phase2_file.py:356-361`) now has
  zero non-prototype callers, and `resume_retained_work`'s `account=` parameter (`phase2_file.py:205`) is only ever
  called with the default. Remove them, or keep them with a one-line comment stating who is expected to call them and
  why an unreachable fence-release on the class that enforces revocation is safe. Removal is preferred.
- **D4 — disclose the non-resumed failure-signal change.** `_complete`'s commit and publication failure arms changed
  `raise` → `return` for **both** modes (`phase2_file.py:772-784`, `807-819`); previously a normal upload whose commit
  failed ended its task with an exception that `_settle_entries` turned into `RuntimeError("File Meeting could not be
  quiesced.")` and `_task_done` logged. Durable truth is unaffected, but C2 asked only for the *resumed* path. Either
  restore the signal for the non-resumed path or record the change and its rationale in
  `docs/verify/round4-run-c/VERIFY.md` and the run-D verifier. State which you chose and why.
- **D5 — the last-resort outcome write is guarded.** `_run`'s resumed handler calls `_mark_failed`
  (`phase2_file.py:668-673`), which swallows `AccountRevoked` (`:603-606`) and does not guard other exceptions from
  `handle.finish`. If that write fails the row stays `active` with only a log line. Make the failure path leave a
  durable, operator-visible outcome or, if that is genuinely impossible, record precisely what state results and why it
  is acceptable. The claim "each failure is a durable, operator-visible Meeting outcome" must be true for this arm too,
  or be narrowed in the verifier to the arms actually proven.
- **D6 — correct the journal's wrong evidence pointer.** `progress.txt` iteration 4's Evidence line cites
  `tests/phase2/test_batch_startup_prototype_controls.py` for post-boot task joining that lives in
  `prototypes/batch-startup/prototype.py`; run C never touched that test file. The journal is append-only, so add a
  correction entry rather than editing history.
- Everything runs B and C achieved still holds: `_assert_no_active_meetings` byte-identical and still used when nothing
  is claimed; no Live row can enter `claimed_file_meetings`; D13 preserved; deletion only after durable terminal truth
  and only within the owning Meeting's directory; the gap remedy partition-scoped with both branches asserted; no
  constant, gate bar, `QUALITY_BOUNDS` or `DEFAULT_MIC_GAIN` change; the two Jamie controls still `xfail(strict=True)`
  and nothing else xfailed; S17 UNMEASURED and `capacity_2x1800` REQUIRED-NOT-RUN.
- Full backend suite ≥ **2,158 passed / 0 failed / 5 skipped / 2 xfailed**, frontend ≥ 312/312, typecheck clean;
  rebuild + empty `git status` if any frontend source changes. `docs/verify/round4-run-d/VERIFY.md`.

## Constraints

- Python `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`,
  always `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`; frontend via the symlinked `frontend/node_modules`.
- **Offline: 0 decoder requests, no tunnel, no proxy, no GPU, no external provider, no network.**
- **Never delete or weaken a control to make a bar pass.** If a control asserts the wrong thing, correct it and say so
  explicitly in progress.txt. Run C deleted one silently; that is the specific failure this run exists to repair.
- Never change `QUALITY_BOUNDS`, gate bars, identity constants, `DEFAULT_MIC_GAIN`, sentinels, poll delays,
  `LIVE_MEETING_LIMIT`, or the definition of `_assert_no_active_meetings`. No duration floor, no new constant.
- Deepen `FileMeetingTasks` and the lifecycle seam; no new framework, no feature flag.
- Live capture keeps D13: no live resume across a restart, ever.
- Never `git push`, merge or rebase; commit only on branch `round4/ralph-b`. Historical `evidence/` is read-only.
- Never read or print `~/.config/moss/openrouter.env` or any `OPENROUTER_API_KEY`.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- Stop early only via the completion contract: acceptance bar met with evidence, or every remaining item blocked on
  input the loop cannot obtain, recorded in progress.txt.
- A blocker ends the iteration, not the loop: record it, commit anything useful, and let the next iteration attack it.
