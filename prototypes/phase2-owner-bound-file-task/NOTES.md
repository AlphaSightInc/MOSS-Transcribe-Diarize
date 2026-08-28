# Owner-bound File-Meeting task lifetime

## Structural contract

- **Question:** what is the smallest process-owned structure that lets accepted File work outlive
  the browser without losing Account authority?
- **Minimum primitives:** one owner-bound Meeting handle, one inference coroutine carrying that
  handle, and one application-owned strong-reference set. A response-attached task is insufficient
  because response delivery, not Meeting lifecycle, owns it.
- **Invariants:** browser/cookie disappearance cannot cancel accepted work; a stale authority
  generation cannot commit; fresh authority still works; completed tasks leave the set.
- **Assumptions/unknowns:** the product remains one process. Real model latency is irrelevant to
  this ownership probe and is unmeasured here.
- **Falsifier:** task disappearance after client detach, a stale commit, blocked fresh authority,
  or a nonempty set after both tasks finish.
- **Tool decision:** a deterministic asyncio probe isolates task ownership and generation fencing.
  Any falsifier would reject the task set before production integration.

## One command

```bash
uv run --frozen python prototypes/phase2-owner-bound-file-task/prototype.py
```

## Verdict

**Accepted.** 2 Meetings; response accepted; client cookie detached; task remained live; the stale
generation committed 0 times and was rejected; fresh generation completed once; task set returned
to 0. Use only the strong-reference set—no generic scheduler, job identity, or Meeting lookup.
