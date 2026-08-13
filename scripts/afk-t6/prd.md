# PRD — Phase 1 ticket #6

**Journal speaker vectors at session end**

Tracker: issue #6 on `aiSight-us/MOSS-Transcribe-Diarize` (private). Read the issue body — its
acceptance criteria are the gate, with no additions or substitutions.

## Goal

When a live session ends, each speaker's album centroid is written to a durable local journal, so
the acoustic identity of that meeting survives the session.

This is deliberately **not** a voice bank: no CRUD, no enrollment, no naming, no matching, no UI.
Those are Phase 2. Read wayfinder T-12's resolution for why.

Why now: nothing in the product writes an embedding to disk today — `live_identity_album.py` is a
277-line pure in-memory structure that dies with the session. The DL2 sprint already lost every
acoustic asset because raw audio hit a TTL before any vector was banked. Writing a few hundred
floats at stop is cheap; re-deriving a voiceprint after the audio is gone is impossible.

Two things that make the journal worthless if you get them wrong:
- **Every row must carry `embedder_id` + `embedder_state_sha`.** Without pinned-encoder identity
  the vectors are uncomparable after any embedder change.
- Rows are **session-keyed, not device-keyed.** T-01's shared-token posture removed per-client
  identity, so there is no `device_id` to key on. Do not invent one.

Journaling defaults **ON**; raw-audio retention stays **OFF** — ADR-0003's opt-in posture governs
raw audio and is deliberately not inherited by a derived centroid. A refused or unusable
observation is declined **by name** and never aborts the session, per the live path's
terminal-failure policy.

This is server-side and independent of the browser, so it is fully verifiable overnight.

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
if ! ( set -o noclobber; echo "$$ ticket-6 $(date -u +%FT%TZ)" > "$LOCK" ) 2>/dev/null; then
  echo "lock held by: $(cat "$LOCK")"        # wait; retry next iteration. DO NOT steal it.
else
  git merge --no-edit dev                    # bring dev into YOUR branch. No rebase.
  #   ... resolve conflicts, then run the FULL validation set on the MERGED result ...
  git push . HEAD:dev                        # fast-forward dev (it is not checked out anywhere)
  git push private HEAD:afk/t6-<slug>       # publish your branch
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
   `evidence/phase1/t6/` — not prose claims.
4. An issue comment links your branch and states, criterion by criterion, what proves it, and
   states plainly what your tests do **not** cover.
5. Branch pushed to `private`.
6. `context.md` and `progress.txt` reflect final state.

**A gate satisfiable by stub evidence is not satisfied.** This project has previously shipped a
rail that passed on stub evidence. Do not repeat it.

Emit `<promise>COMPLETE</promise>` on its own line only when all six hold, or when every remaining
item is blocked on input this loop cannot obtain and that is recorded in `progress.txt`.
