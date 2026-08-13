# PRD — Phase 1 ticket #1

**Gate 2 canary: real Chrome audio to diarized transcript in the browser**

Tracker: issue #1 on `aiSight-us/MOSS-Transcribe-Diarize` (private). Read the issue body — its
acceptance criteria are the gate, with no additions or substitutions.

## Goal

Prove the one thing this project has never proved: real Chrome audio reaching the model and
coming back as a diarized transcript rendered in that same browser.

Upgrade the kept harness at `prototypes/browser-capture-feasibility/` from talking to a local stub
into talking to a real service. It currently hardcodes 8000/16000 and posts prototype extras —
both must go.

**Because display capture cannot be automated, your real end-to-end proof is the MICROPHONE lane.**
Launch Chrome with `--use-fake-device-for-media-stream --use-file-for-fake-audio-capture=<wav>`
feeding a known **two-speaker** WAV. That failure mode on 2026-08-03 was display-specific; the mic
path is automatable. Exercise the `system` lane with **synthetic frames** through the same
production routes, and record explicitly that this does not prove real display capture.

This ticket is the keystone: #5, #6 and #7 build on its client. Land something mergeable early
rather than perfecting it.

Charter gates that bind you: **G1** (mic lane e2e, ≥2 distinct speaker ids, zero sequence gaps,
exact `frame_samples`), **G2** (system lane synthetic, honestly labelled), **G7** (backgrounded tab
sustains cadence and does not trip the helper lease). Read charter §4 for the capture spec —
mic-first activation ordering, the nine v2 keys, worklet-driven POSTs, the error taxonomy.

## Non-negotiable constraints

**Read `docs/phase1-afk-charter.md` in full before your first change. It is binding.**
Design decisions come from `.wayfinder/map-001-phase1-chrome-client.md` (premises C1-C11) and the
closed decision tickets under `.wayfinder/tickets/`. All twelve are closed. **Do not re-litigate
any of them.** If you believe one is wrong, record it in `context.md` and comment on your issue —
do not act against it.

- Remote host `ga0-alienware-rtx4070ti` is **READ-ONLY**. Never restart, deploy to, reconfigure,
  or send a mutating request to `moss-live-web`, `moss-vllm`, or `moss-web`. Verify against a
  **locally-run** service you start yourself on a port you own.
- **Automated display capture is forbidden.** The display chooser needs a fresh user gesture per
  capture and permits no persistent grant; the 2026-08-03 CDP-flag attempt failed with
  `NotReadableError`. Do not use automation source-selection flags. Two-lane display verification
  is deferred to the operator's attended checklist (charter §7).
- Push **only your own branch** to remote `private`. Never force-push. Never push `dev` or `main`.
- **You may not close GitHub issues.** Comment evidence; the supervisor verifies and closes.
- Never commit tokens, `.pem`, `.p12`, pairing payloads, or `ops/moss-live.env`.
- **Your ticket only.** Defects found elsewhere go in `context.md` and an issue comment. Do not fix
  them.
- Never hardcode frame geometry. `frame_samples` / `sample_rate` come from
  `/api/live/descriptor` — they are deploy-manifest values.
- Do **not** add Uvicorn workers. Device state, session ownership, runtime objects, mixers, event
  queues and view grants are process-local; two workers can route unsafely.
- `AGENTS.md` requires measuring on the production code path before writing production code for
  any new algorithm, threshold or policy. Extend `prototypes/streaming-diarization/` rather than
  rebuilding measurement scaffolding.

## Merge protocol — serialized self-merge, MERGE not rebase

`prompt.md` forbids rebasing and that rule stands. Integrate with **merges only**.

You MUST hold the merge lock for the whole operation:

```bash
LOCK="$(git rev-parse --git-common-dir)/afk-merge.lock"
if ! ( set -o noclobber; echo "$$ ticket-1 $(date -u +%FT%TZ)" > "$LOCK" ) 2>/dev/null; then
  echo "lock held by: $(cat "$LOCK")"        # wait; retry next iteration. DO NOT steal it.
else
  git merge --no-edit dev                    # bring dev into YOUR branch. No rebase.
  #   ... resolve conflicts, then run the FULL validation set on the MERGED result ...
  git push . HEAD:dev                        # fast-forward dev (it is not checked out anywhere)
  git push private HEAD:afk/t1-<slug>       # publish your branch
  rm -f "$LOCK"                              # ALWAYS release, including on failure
fi
```

- `dev` is intentionally **not checked out** in any worktree, which is what makes
  `git push . HEAD:dev` work. Do not check `dev` out.
- Validation must pass on the **merged** result, not just on your branch before the merge.
- Never steal a lock. If one looks stale (>30 min), comment on your issue and let the supervisor
  break it.
- If your merge breaks `dev`, revert the merge commit immediately. Do not forward-fix while
  holding the lock.
- Safety tag: `pre-afk-20260813`. Backup branch: `dev-backup-20260812`.

## Definition of done

1. Every acceptance criterion on your GitHub issue is satisfied.
2. Validation passes on your branch **after merging current `dev` into it**.
3. Evidence exists as **raw artifacts** (command output, logs, measurement files) committed under
   `evidence/phase1/t1/` — not prose claims.
4. An issue comment links your branch and states, criterion by criterion, what proves it, and
   states plainly what your tests do **not** cover.
5. Branch pushed to `private`.
6. `context.md` and `progress.txt` reflect final state.

**A gate satisfiable by stub evidence is not satisfied.** This project has previously shipped a
rail that passed on stub evidence. Do not repeat it.

Emit `<promise>COMPLETE</promise>` on its own line only when all six hold, or when every remaining
item is blocked on input this loop cannot obtain and that is recorded in `progress.txt`.
