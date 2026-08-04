# Ralph L2 Stage-0 guardrails

Independent Campaign-A bundle. It does not source, modify, or reuse
`scripts/ralph-afk/` or that loop's state.

Dry-run and preserve evidence:

```bash
scripts/ralph-l2-afk/launch.sh --dry-run \
  --evidence-dir scripts/ralph-l2-afk/evidence
```

Gated run after A1 freezes the corpus manifest:

```bash
scripts/ralph-l2-afk/launch.sh --iterations 1 -- <iteration command>
```

Before A1, every gated run returns exit 2 with
`corpus_manifest_unfrozen` and `<promise>BLOCKED</promise>`. The launcher then
requires the exact worktree, branch, keeper ancestor, plan hash, clean tree, exact
previous commit, frozen corpus hash, ten-iteration cap, single writer, and path
scope. A `.stop` file requests a graceful stop before the next iteration.

Future candidate campaigns must commit each family preregistration before executing
that family's first run. A NOTES timestamp or a preregistration/result co-commit is
not independently sealed proof of ordering.
