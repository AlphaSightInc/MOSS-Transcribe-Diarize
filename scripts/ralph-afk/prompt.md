# Iteration Procedure

<!-- Per-iteration instructions for the loop agent. The engine prepends run
     facts (repo, iteration counter, preflight status), appends the completion
     contract, and substitutes the double-brace ITERATION/BUDGET/DIR tokens at
     launch. Keep this file project-agnostic: WHAT to achieve belongs in
     prd.md, current state belongs in context.md. Most projects never need to
     edit this file. -->

Read, in order:

1. Repo agent instructions if present (`AGENTS.md`, `CLAUDE.md`, or equivalents).
2. `{{DIR}}/prd.md` — the goal, acceptance bar, and hard constraints.
3. `{{DIR}}/context.md` — current evidence and the ranked candidate work list.
4. `{{DIR}}/progress.txt` — enough recent entries to avoid repeating or undoing prior work.

Then perform exactly one iteration:

1. **Choose.** Pick the highest-leverage open candidate from context.md. Go
   off-list only when evidence demands it, and record the justification. If
   context.md is stale, empty, or contradicts observed reality, repairing
   context.md from evidence is itself a valid iteration.
2. **Change.** Make one logical change: a fix, a test or probe, a
   simplification, a documentation repair, or an evidence-backed revert of a
   prior `ralph:` commit. Prefer the smallest change that moves the goal;
   reducing code or complexity is a valid outcome.
3. **Validate.** Run the smallest command that produces real evidence for your
   change; widen scope only when the focused result justifies it.
4. **Update working memory.** Edit context.md so it matches reality after your
   change: record the chosen candidate's outcome, add or remove candidates
   based on what you learned, prune stale evidence. Keep the whole file
   readable in one sitting — history belongs in progress.txt, not here.
5. **Record.** Append one concise entry to progress.txt: iteration
   {{ITERATION}}, target, files touched, validation command and result,
   evidence paths, what you learned, recommended next step.
6. **Commit.** `git commit` your own work with subject
   `ralph: iteration {{ITERATION}} - <short focus>` and a body carrying the
   target, validation result, and any blocker. The launcher checkpoints
   whatever you leave uncommitted, but your own commit message is preferred.

Rules:

- One logical change per iteration; no drive-by edits to unrelated systems.
- Respect the phase gates in context.md. Do not start production-reliability
  work until the IDEA-044 compatibility checkpoint is recorded green. Do not
  checkout, merge, push, deploy, restart a service, install an app, or mutate a
  remote host unless the selected candidate explicitly authorizes that action.
- Generalize. Never hard-code instance-specific values — identifiers, proper
  names, labels, thresholds, or locale/language-specific strings — into
  general logic. Implement the general rule that makes the instance behave,
  unless prd.md declares that value part of the domain contract.
- Never weaken validation, tests, or safety gates to make results look better.
- Respect history: no `reset --hard`, no rebase, no `--amend` of published
  commits, no force-push, no `git clean`, `git stash`, or `git restore`.
- Do not delete files outside artifacts you created this iteration.
- If blocked, record the blocker and the best next probe in progress.txt; a
  well-documented dead end is a useful iteration.
- Do not add orchestration (task trackers, containers, services) unless prd.md
  requires it.
