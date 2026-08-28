# Owner-bound File-Meeting task lifetime

## Structural contract

- **Question:** what is the smallest process-owned structure that lets accepted File work outlive
  the browser without losing Account authority?
- **Minimum primitives:** one owner-bound Meeting handle, one inference coroutine carrying that
  handle, one application-owned strong-reference set, and one exclusively transient `file-work`
  root. A response-attached task is insufficient because response delivery, not Meeting lifecycle,
  owns it. The root is necessary because a killed process cannot run per-task cleanup.
- **Invariants:** browser/cookie disappearance cannot cancel accepted work; shutdown keeps source
  and SQLite alive until synchronous inference quiesces; a canceled result cannot commit; a stale
  authority generation cannot commit; fresh authority still works; completed tasks leave the set;
  restart removes orphaned transient input before admitting requests.
- **Assumptions/unknowns:** the product remains one process. Real model latency is irrelevant to
  this ownership probe and is unmeasured here.
- **Falsifier:** task disappearance after client detach, shutdown returning or deleting input while
  the runner is blocked, any canceled/stale commit, blocked fresh authority, a nonempty task set,
  or a seeded crash orphan surviving pre-admission cleanup.
- **Tool decision:** a deterministic asyncio plus real `to_thread` probe isolates task ownership,
  quiescence, generation fencing, and restart cleanup. Any falsifier rejects the design.

## One command

```bash
uv run --frozen python prototypes/phase2-owner-bound-file-task/prototype.py
```

## Verdict

**Accepted.** Full printed state: 2 Meetings; response accepted; client cookie detached; task
remained live; stale generation committed 0 and was rejected; fresh generation completed 1; normal
task set returned to 0. During shutdown, Stop stayed pending and source remained present while the
synchronous runner blocked; after release the canceled result committed 0, source disappeared, and
the shutdown task set returned to 0. A seeded crash orphan was removed before admission. Retain and
shield the runner task, wait for quiescence, then clean. On restart, clear only children of the
dedicated `file-work` root. No scheduler, resumable job identity, or global Meeting lookup.
