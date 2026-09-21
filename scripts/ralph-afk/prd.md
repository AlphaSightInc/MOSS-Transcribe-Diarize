# PRD - MOSS round 4, ralph run C: close the acceptance review's findings on run B

Run B implemented all three mandated behaviours correctly — an adversarial acceptance review verified byte-identical
`_assert_no_active_meetings`, no live-resume path (D13), partition-scoped-once identity with both branches asserted,
untouched constants/bars/gain, and an exactly-audited fixture correction. It then found **three consequences run B did
not surface**, plus smaller gaps. This run closes them. Nothing run B achieved may regress.

## Goal

> Make the durable File/URL ownership introduced in run B safe in the three ways the review showed it is not: account
> revocation must not resurrect work or unfence late results; a retained resume must never take down or stall
> application startup; and retained work that is refused or cancelled must not be kept forever.

## Acceptance bar

Every point below, with evidence (commands, exact counts, before/after) in progress.txt:

- **C1 — revocation does not resume, and does not unfence.** `_revoke_account` (`phase2_lifecycle.py:231-233`) must not
  call `resume_retained_work`, and must not call `release_settled_account_fence` merely to allow one. Revoking an
  account must leave its retained File work unresumed and its late results still rejected by the fence
  (`phase2_file.py:302`, guard `:349-354`). A revoked account must never gain a newly published transcript. Controls:
  (a) healthy — revoke with a retained prefix present ⇒ the Meeting is terminal, `decoder.calls == []`, no new
  transcript version, retained dir handled per C3; (b) violating — a test that fails on the current tree by showing a
  revoked account publishing a transcript (`tests/phase2/test_retained_file_claim.py:362-375` asserts exactly that
  today and must be corrected, not deleted). The account-scoped claim, if it is kept at all, must run only where a
  legitimate account-scoped startup caller exists — and if none exists, say so and remove the call rather than inventing
  one.
- **C2 — startup is never blocked or aborted by retained work.** A failure in any retained resume (commit,
  publication, or post-terminal cleanup) must not propagate out of `lifespan` (`phase2.py:1960`): startup completes,
  the failure is recorded on the Meeting and visible to the operator, and the app serves. Startup must also not await a
  full re-decode: the resume runs as a background task under the existing scheduler, not inline at boot. Controls:
  healthy — an app whose retained resume raises still starts and serves its descriptor, with the Meeting's failure
  durably visible; violating — a test that fails on the current tree because a raising resume aborts startup. Add a
  control proving boot does not wait for a long resume (use the existing deterministic runner; assert the app serves
  while the resume is still pending).
- **C3 — refused or cancelled retained work is reclaimed.** When `_verified_retained_input` refuses work
  (`phase2_file.py:510-545`) or a URL Meeting is cancelled mid-download, the owner directory must not survive the
  Meeting's durable terminal transition. Removal happens **after** terminal truth, never before, and never for work
  still owned by an active Meeting. `tests/phase2/test_retained_file_claim.py:316` currently asserts
  `owner_dir.exists()` after `interrupted` — correct that assertion to the intended behaviour. Controls: healthy — a
  refused prefix leaves no owner directory once the Meeting is `interrupted`; violating — the current
  retain-forever behaviour. Bound the blast radius: only this Meeting's own directory may be removed.
- **C4 — the URL acquisition failure window is closed.** `_record_retained_source` (`phase2_file.py:619`) must not be
  able to leave a URL Meeting `active` with no task after a successful download: a failure there ends the Meeting
  durably (`failed`, with the reason visible) instead of waiting for the next restart. Control proves it.
- **C5 — honest documentation of what the ladder reference does.** `SYSTEM_LADDER_REFERENCE`
  (`tests/e2e/verify_demo_lanes.py:27`) has exactly one consumer (`tests/test_round4_overlap_diagnosis.py:28`); the
  deployed ladder scores solo-lane vocabulary retention and reads no reference row. Correct
  `docs/verify/round4-run-b/VERIFY.md` so it no longer claims the ladder is scored against that population, and reword
  its falsifier 3 to something actually testable (or delete it and say why).
- **C6 — product-level assertion of the batch invariant.** The "101/101 unique saved segments, no duplicate after the
  replayed window" property currently lives only inside `prototypes/batch-startup/prototype.py`, which pytest never
  runs. Assert uniqueness and no-duplication at product level in `tests/phase2/test_retained_file_claim.py` for the
  resume and the mid-window-crash cases.
- **C7 — corpus internal consistency.** The corrected Bill row `[0.0, 29.25]` now overlaps the following row
  `[29.0, 33.0]` in the same file. Either adjust the neighbouring row's start so the file is internally consistent
  (audited: it must still describe the same audio), or record in the corpus README why the overlap is intentional and
  which consumers read which rows. Do not change any scored text.
- Everything run B achieved still holds: `_assert_no_active_meetings` byte-identical to base; no live resume (D13);
  gap remedy partition-scoped with both branches asserted and no constant moved; fixture correction exactly the audited
  rows with the three class-(a) additions still visible; the two Jamie controls still `xfail(strict=True)`; S17 and
  `capacity_2x1800` still explicitly unmeasured/deferred.
- Full backend suite ≥ **2,152 passed / 0 failed / 5 skipped / 2 xfailed** and frontend ≥ 312/312; typecheck clean; if
  any frontend source changes, rebuild and leave `git status` empty (asset parity). `docs/verify/round4-run-c/VERIFY.md`.

## Constraints

- Python `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python`,
  always `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.`; frontend via the symlinked `frontend/node_modules`.
- **Offline: 0 decoder requests, no tunnel, no proxy, no GPU, no external provider, no network.**
- Never change `QUALITY_BOUNDS`, any gate bar, identity constants (`ALBUM_*`, `min_segment_samples`),
  `DEFAULT_MIC_GAIN`, the live frame protocol, sentinels, poll delays, `LIVE_MEETING_LIMIT`, or
  `_assert_no_active_meetings`. No duration floor. No new hand-tuned constant.
- Do not weaken, narrow or delete any control. Where a control asserts the wrong behaviour (C1's revoke publish, C3's
  retain-forever), correct the assertion and say so explicitly in progress.txt — never silently.
- Deepen `FileMeetingTasks` and the lifecycle seam; no new framework, no second job system, no feature flag.
- Live capture keeps D13: no live resume across a restart, ever.
- Never `git push`, merge or rebase; commit only on branch `round4/ralph-b`. Historical `evidence/` is read-only.
- Never read or print `~/.config/moss/openrouter.env` or any `OPENROUTER_API_KEY`.

## Budget and stop

- The launcher argument sets the iteration budget; one logical change per iteration.
- Stop early only via the completion contract: acceptance bar met with evidence, or every remaining item blocked on
  input the loop cannot obtain, recorded in progress.txt.
- A blocker ends the iteration, not the loop: record it, commit anything useful, and let the next iteration attack it.
