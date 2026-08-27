# Handoff — finish the Phase-2 multi-user Wayfinder map

Updated 2026-08-27 EDT. This is a **planning handoff**. Continue the existing map; do not chart a
new one and do not implement product code.

## Launch contract

From the product repo:

```text
Read AGENTS.md, docs/handoffs/handoff-phase2-XXXXXX.md,
.wayfinder/README.md, and .wayfinder/map-002-phase2-multiuser.md. Invoke $wayfinder in
work-through mode. Run `python3 .wayfinder/frontier.py --all`, respect every live claim, and
resolve exactly one open ticket. Use $grilling + $domain-modeling for operator decisions and
$prototype only when the ticket requires new measured behavior. Planning only: do not write or
deploy product code; do not commit, merge, push, clean, stash, reset, or switch the dirty checkout.
```

## Authority and destination

- Canonical map: `.wayfinder/map-002-phase2-multiuser.md`.
- Tracker: local Markdown under `.wayfinder/tickets/`; never create planning issues upstream.
- Destination: a decision-complete Phase-2 MVP specification for a known 2–10-person tailnet
  team, shipped in waves: Accounts/isolation/live MP3 first, then private voice bank and
  client-configured language-model assistance.
- Current checkout: `ralph/live-convergence-0824` at charting base `7608c91`; deliberately dirty
  with user-owned production, evidence, prototype, and planning work. Preserve it exactly.
- The map is planning authority. Closed ticket resolutions are settled evidence; do not repeat
  their research or reopen their decisions without contradictory measurements.

## Outstanding dependency graph

Seventeen of 21 Phase-2 tickets are closed. Four remain:

1. **Client-configured LLM — functions, browser ownership, artifact access, and UI contract
   (T-25): claimed by `codex-20260827`.** All prerequisites are closed: the LLM inventory,
   identity/isolation, browser-path prototype, and revised final-summary prototype. Skip it while
   claimed. Its resolution must consume the settled one-post-Stop V15 summary contract; it must
   not resurrect rolling or repair calls.
2. **Operator observability — metadata-only multi-user health and capacity (T-29): blocked only
   by the LLM contract.** It becomes frontier when that ticket closes.
3. **Post-Wave-1 sequencing — private voice bank or client-configured LLM next (T-32): blocked
   only by the LLM contract.** The Wave-1 boundary is already closed. It becomes frontier beside
   operator observability; resolve it in its own Wayfinder session.
4. **Phase-2 acceptance gates — adversarial isolation, revocation, voice, audio, LLM privacy
   (T-28): final by design.** It now depends on both operator observability and post-Wave-1
   sequencing, plus the already closed architecture/design tickets. Run it only after both close.

```text
Client-configured LLM contract (claimed)
  ├─> Operator observability ───────────┐
  └─> Post-Wave-1 sequencing ──────────┴─> Phase-2 acceptance gates ─> map closure
```

There is **no frontier ticket at handoff time**: the sole unblocked open ticket is claimed. Rerun
the frontier query; do not clear another session's claim based on this document.

## Freshly closed evidence already incorporated

- **Client-configured LLM browser path and hybrid-summary policy (T-31):** browser-owned
  provider/controller path measured; the original summary prompt was rejected.
- **Revised summary prompt and deterministic output contract (T-33):** V15 accepted for exactly
  one post-Stop call over the finalized transcript; no rolling or repair calls; exact five-field
  JSON shape; 7/7 valid visible non-holdout outputs, 2.207 s median / 3.360 s maximum. Broader
  quality and blind holdouts remain unmeasured.
- The canonical map now contains the missing T-33 decision pointer. The final-gates ticket now
  depends on sequencing and no longer contradicts the audio design by demanding in-product quota
  deletion.

## One-session procedure

1. Run `python3 .wayfinder/frontier.py --all` and choose one unclaimed frontier ticket by name.
2. Claim it in frontmatter before work. Read its full question and every blocking resolution.
3. Resolve only that decision with the operator; do not infer the operator's side.
4. Append `## Resolution`, set `status: closed`, add one concise pointer under the map's
   **Decisions so far**, then rerun the frontier query.
5. Report the new frontier and blockers by ticket name. Stop.

After the final acceptance-gates ticket closes, follow **Where the Phase-2 spec lands and how the
AFK loop consumes it (T-27)**: ADR per family plus `docs/phase2-afk-charter.md`, then private
`aiSight-us` implementation tickets. This handoff does not authorize those writes, any product
implementation, or any Git/deployment action.
