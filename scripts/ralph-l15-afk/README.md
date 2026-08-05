# Ralph L1.5 guardrails

Independent L1.5 bundle. It does not source, modify, or share state with any prior
Ralph loop.

Dry-run and preserve evidence:

```bash
scripts/ralph-l15-afk/launch.sh --dry-run \
  --evidence-dir scripts/ralph-l15-afk/evidence
```

Gated work after L1.a freezes the split manifest:

```bash
scripts/ralph-l15-afk/launch.sh --iterations 1 -- <iteration command>
```

Before split freeze, every gated run returns exit 2 with
`split_manifest_unfrozen` and `<promise>BLOCKED</promise>`. Thereafter the
launcher requires exact corpus and split hashes, worktree, branch, keeper
ancestor, plan hash, clean tree, expected previous commit, twelve-iteration cap,
single writer, and allowlisted paths. A `.stop` file requests a graceful stop.

Each candidate-family preregistration must be committed before that family's
first execution. Holdout opens once only, after family and threshold freeze.
