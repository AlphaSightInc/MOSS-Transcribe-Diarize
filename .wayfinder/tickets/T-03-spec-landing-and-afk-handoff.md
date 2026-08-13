---
id: T-03
map: map-001-phase1-chrome-client
title: Where the Phase 1 spec lands and how the AFK loop consumes it
type: grilling
status: closed
assignee: operator+claude
blocked_by: []
---

## Question

C1 makes the destination a locked spec handed to the existing AFK builder loop. What is the
spec's physical form, and what does "decision-complete" mean concretely enough that a
Horizon/Builder role can act without asking a design question?

**Partially pre-answered (operator, 2026-08-12):** the map and its tickets were moved into the
**target repo** at `.wayfinder/`, and sessions run from there. So planning artifacts for this
effort live with the code, not in the control plane. Take that as given and resolve the rest —
in particular whether `.wayfinder/` is committed, gitignored, or kept untracked (see question 7).

Resolve:

1. **Artifact split.** Which parts belong in the target repo as ADR/design doc (durable,
   versioned with the code, reviewable by the loop's Reviewer role) versus the control plane
   as PRD/plan (process state)? The repo already has `docs/adr/0001..0003` and
   `docs/design-streaming-diarization.md` as precedent; the control plane has
   `plans/`, `context/`, and `scripts/ralph-afk/prd.md` as the loop's WHAT.
2. **ADR count and boundaries.** Is Phase 1 one ADR ("browser capture client and polled
   session delivery") or several (auth posture; transport/poll contract; UI fidelity rule)?
   Each ADR should be independently reviewable and independently revisable.
3. **PRD conformance.** `scripts/check-prd-conformance.py` exists. What must the Phase 1 PRD
   contain to pass it, and how are the map's tickets ordered into PRD task sequence?
4. **Idea/attempt registration.** This is a large multi-subsystem change. Does it enter the
   loop as one IDEA or several, given `max_active_attempts` and the promote-keeper gate?
   Note the loop's existing state files (`IDEA_BACKLOG`, `HORIZON_PLAN`) are stale
   (last verified 2026-07-27) and reference a different in-flight effort.
5. **How the decision record survives.** Per operator practice, rulings are archived at
   ruling time. Where do this map's charting decisions (C1–C10) and each ticket resolution
   land in the control plane's ledgers so the AFK roles read them as binding?
6. **What "no open questions" is tested against.** Define the check a session runs before
   declaring the map done — e.g. every reference component has a Phase 1 disposition, every
   `WsEvent` member has a source or an explicit unreachable ruling, every new endpoint has a
   request/response shape and an error taxonomy.
7. **Is `.wayfinder/` committed?** It is untracked in the target repo today, which mutates
   `git status --porcelain` and therefore the control plane's `target_status_digest` /
   `target_dirty` fields — an AFK role comparing against `PROJECT_BRIEF` will read it as drift.
   Rule one of: commit it, add it to `.gitignore`, or accept the digest change and refresh the
   brief. Also note the repo is currently on branch `fix/stop-route-bounded-drain`, not `main`.

Ground truth: this repo's `MISSION.md`, `POLICY.md`, `OPERATOR_GUIDE.md`, `roles/`,
`scripts/check-prd-conformance.py`; target repo `docs/adr/`, `AGENTS.md`.

## Resolution

**Several ADRs under `docs/adr/`; `.wayfinder/` committed and git-tracked (operator, 2026-08-13).**

- **Artifact form:** the spec lands as **multiple ADRs** in the target repo's existing
  `docs/adr/` sequence (continuing after 0001/0002/0003), not one monolith. Each ADR is
  independently reviewable and independently revisable.
- **`.wayfinder/` is committed and tracked**, so the map and its tickets version with the code.
  This settles question 7: it is neither gitignored nor untracked drift. The control plane's
  `target_status_digest` / `target_dirty` fields should be refreshed from this commit rather
  than read as drift.
- Planning artifacts for this effort live **with the code**, not in the control plane. The
  control plane keeps loop state, ledgers, evidence, and review decisions.

**Still to be settled by the ADR-writing session** (mechanical, no further operator input needed):
the exact ADR boundaries and numbering, PRD conformance shape, and how many IDEAs this enters
the loop as. Proposed split, one ADR each: browser capture client; polled session delivery;
Phase 1 auth posture; frontend serving/fidelity rule.
