# Handoff — chart the next-stage multi-user MOSS product with Wayfinder

Written 2026-08-25 EDT. This is a **planning handoff**. The next session charts a fresh
Wayfinder map; it does not implement the destination.

## Launch contract

From the product repo:

```text
Read docs/handoffs/handoff-XXXXXX.md, then invoke $wayfinder in chart-the-map mode.
Use $grilling and $domain-modeling first, one question at a time, because the operator has
explicitly said more requirements will be provided. Do not infer those answers. Chart a fresh
Phase-2 map, create and wire decision tickets, launch its research tickets in parallel, then stop.
Do not write product code, deploy, commit, merge, or push.
```

## Destination to name with the operator

Draft orientation only — the operator must confirm the destination before charting:

> A decision-complete next-stage specification for turning the server-hosted MOSS Chrome client
> into a multi-user product with strict transcript isolation, account identity, durable named
> voiceprints, retained post-Stop audio, and local-LLM features, grounded in current MOSS evidence
> and a read-only audit of LiveTranscribe.

The key phrase is **decision-complete specification**. Wayfinder plans; a later implementation
handoff builds. Ask whether the destination is an MVP spec, a production architecture spec, or a
phased roadmap before fixing scope.

## Operator requirements already stated

1. **Multi-user isolation.** A Chrome client needs a unique identity and the server must route
   transcript text only to the correct client. Cross-user transcript disclosure is disastrous.
   Research the simplest sound design, including browser/session/account identity, server-side
   persistence, SQLite versus PostgreSQL, and whether Google OpenID Connect can supply account
   authentication without this server storing user passwords.
2. **Named voice bank.** A user can edit a speaker name, persist that name with a voiceprint, and
   have later matching speech automatically display the saved name. Decide server versus client
   storage (or a justified hybrid), ownership, cross-device behavior, matching/abstention,
   embedder-version compatibility, deletion, and biometric/privacy boundaries.
3. **Audio retention.** Save meeting audio after Stop. Decide WAV, MP3, or both; mixed versus
   separate capture lanes; storage owner/location; download/history behavior; lifecycle, quota,
   deletion, and failure semantics.
4. **Local LLM support.** Determine what LiveTranscribe actually implements, then decide which
   live formatting, summary, title, or other functions belong in MOSS; where the model runs; how
   it competes with speech inference; and which user/session artifacts it may read and persist.
5. **Reference implementation.** All four feature families exist in the single-machine project
   at `ga0@m4mbp:~/Desktop/AI_Projects/LiveTranscribe`. Audit it extensively over read-only SSH.
   Its single-host assumptions are evidence, not a client/server design to copy blindly.

## Current product state — preserve it

- Authoritative checkout:
  `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize`.
- Current branch/HEAD: `ralph/live-convergence-0824` /
  `7608c91ce36441d9075fbba41e18c5fae8f464ac`.
- The worktree is deliberately dirty with Goal-1 production edits, tests, plans, prototypes, and
  evidence. They are user-owned. **Do not clean, stash, reset, switch branches, or overwrite.**
- Goal 1 fixed rolling overlap refusal. Across 12 actual-live sessions, 122/122 windows applied;
  macro settled pre-Stop WER `.140442`; first-publication p95 `3.652696 s`; changed-region
  correction p95 `10.471099 s`; final WER `.095074`. Source:
  `evidence/live-g4-recovery-20260825/REPORT.md`.
- Goal 2's 15/10 lexical candidate was **rejected at the causal prototype gate**: 0/12 case-runs
  could publish the frozen batch rule monotonically. No 15/10 production code or deployment was
  made. Sources: `evidence/live-15-10-lexical-20260825/ADOPTION.md` and
  `causal-prototype.json` beside it.
- No promotion, merge, commit, or push occurred in the Goal-2 session.
- Prior live PID/listener state is time-sensitive. Recheck it if relevant; do not treat this
  handoff as current runtime proof.

## Existing planning authority — reconcile, do not duplicate

### Closed Phase-1 Chrome map

Branch `dev` contains the completed local-markdown map
`.wayfinder/map-001-phase1-chrome-client.md`; all 12 decision tickets are closed and its binding
implementation contract is `docs/phase1-afk-charter.md`. Read both without checking out `dev`:

```bash
git show dev:.wayfinder/map-001-phase1-chrome-client.md
git show dev:.wayfinder/README.md
git show dev:docs/phase1-afk-charter.md
```

That map explicitly says Phase 2 requires a **fresh map**. Relevant settled context includes:

- server-hosted, zero-install Chrome UI;
- polling-based session snapshots/events;
- Phase-1 target of 2–4 concurrent live sessions;
- Phase-1 shared bearer token and single trust domain — inadequate for this new multi-user scope;
- durable accounts/SSO, voice-bank CRUD, speaker rename, history, and the LLM layer deferred to
  Phase 2;
- session-end vector journaling specified, but no durable named voice bank implemented.

Treat `dev` as planning evidence, not proof of what this current branch deploys. Do not switch the
dirty checkout to inspect it.

### Older server/helper Wayfinder

Also inspect the completed planning corpus at
`/Users/gao/Desktop/AI_Projects/AAgent/260724-moss-capture-wayfinder/` (`map.md`,
`FRONTIER.md`, `DEPENDENCIES.md`, research, and resolutions). It established a server-owned portal
and a capture-only native helper. Some old scope exclusions conflict with today's explicit request
to use Chrome and LiveTranscribe; the new operator request wins. Preserve still-valid reasoning,
but do not silently inherit obsolete exclusions.

### Tracker choice

The current branch has no configured Wayfinder tracker. The closed Phase-1 effort used the
local-markdown conventions in `dev:.wayfinder/README.md`. GitHub issue discovery currently resolves
the upstream `OpenMOSS/MOSS-Transcribe-Diarize`, which has no Wayfinder labels/map; **do not create
planning issues upstream**. Unless the operator explicitly selects the private `aiSight-us`
tracker, use a fresh local-markdown map in this product repo, following the existing conventions.

## Research the map must expose

These are domains to cover breadth-first, not pre-decided answers or implementation tickets:

- **Identity and isolation:** account, browser/device, session, capture stream, event cursor,
  transcript, audio, voiceprint, and LLM artifact identities; server-generated versus
  client-asserted identifiers; end-to-end authorization at create/read/stream/download/delete.
- **Authentication:** Google OpenID Connect/OAuth flow and maintained framework integrations;
  session-cookie/token lifecycle, logout/revocation, deployment origin/TLS, and a minimal local or
  non-Google fallback if the operator requires one. Use current official sources.
- **Persistence:** data ownership and relational schema boundaries; SQLite versus PostgreSQL based
  on measured concurrency, deployment topology, backups, and failure recovery — do not select a
  database from familiarity alone.
- **Voice bank:** inspect LiveTranscribe's embedding production, storage schema, rename flow,
  matching thresholds, relabel behavior, model identity, and deletion. Separate within-session
  diarization from cross-session person recognition.
- **Audio archive:** inspect how LiveTranscribe writes audio and how MOSS's retained mixed tape and
  two capture lanes differ. Decide canonical archival form before transcoding convenience copies.
- **Local LLM:** inventory exact LiveTranscribe prompts, runtime, endpoints, UI states, persistence,
  cancellation, and resource use. Decide whether “local” means server-local or user-device-local.
- **Capacity and deployment:** expected users, simultaneous meetings, trust boundary, network
  exposure, single server versus future scale, ASR/LLM GPU contention, storage growth, and operator
  observability.
- **Acceptance:** deliberate cross-user routing/adversarial-isolation tests, account/session
  revocation, concurrent capture, voice false-match/abstention, audio durability, LLM privacy, and
  reproducible measured gates. Wrong-user delivery must be structurally unrepresentable, not a UI
  convention.

Multi-user isolation is genuine security scope because the operator explicitly named its failure
as disastrous. Stay surgical: secure the reachable product paths; do not add generic enterprise
scaffolding without a requirement.

## LiveTranscribe audit contract

Start read-only and preserve its dirty worktree if any:

```bash
ssh ga0@m4mbp '
  cd ~/Desktop/AI_Projects/LiveTranscribe &&
  git status --short --branch &&
  git rev-parse HEAD &&
  git remote -v
'
```

Inspect committed content with `git show HEAD:<path>` where local edits overlap. Do not edit,
clean, stash, reset, launch destructive migrations, or treat launcher success as architecture
proof. The known day-to-day launcher is `scripts/run_app.sh` (`run_app_bundle.sh` is a wrapper),
but the next session's purpose is source/data-flow research, not running the app unless a ticket
requires an attended prototype.

For external packages and Google authentication, browse current **official documentation and
primary sources**. Record exact versions, licensing/deployment constraints, and what remains
unmeasured. Prefer multiple parallel research tickets after the map is charted.

## Wayfinder execution rules

1. Read this handoff, `AGENTS.md`, the closed Phase-1 map, the Phase-1 charter, and the older
   capture map.
2. Invoke `$wayfinder` **chart mode**. Use `$grilling` + `$domain-modeling` to name the destination,
   then grill breadth-first. Ask one question at a time; never answer the operator's side.
3. Create one canonical map and only the decisions sharp enough to ticket now. Put dependent fog
   under **Not yet specified**. Put conscious exclusions under **Out of scope**.
4. Create tickets first, then wire blocking relationships. Refer to every map/ticket by name, not
   bare IDs.
5. Launch every research ticket in parallel research subagents; each records sources/findings in
   its own ticket/context pointer. Charting may resolve research tickets, but hand-resolve no other
   decision in this session.
6. Stop after charting. Return the map path/URL, named frontier tickets, blocked tickets, research
   sessions launched, unresolved fog, and the exact next-session command.

## Suggested skills

- `$wayfinder` — controlling planning workflow.
- `$grilling` and `$domain-modeling` — required to name the destination and resolve human choices.
- `$codebase-design` — interfaces and server/client seams after terms are stable.
- `$prototype` — only for later tickets requiring measured behavior or a concrete UI/data-flow
  reaction; follow this repo's prototype-before-production rule.
- `/research` subagents — Wayfinder's required vehicle for external/repository research, if
  available in that session.
- `$tmux-peer` only if relevant work is actively occurring in another named pane.

## Hard stops

- Planning only unless the new map's Notes explicitly expands scope.
- Do not implement while charting.
- Do not resurrect or deploy 15/10 lexical.
- Do not claim Google authentication, SQLite/PostgreSQL suitability, voiceprint privacy, or local
  LLM capacity from generic knowledge; research the current product/deployment and measure where
  the decision changes behavior.
- Do not use a scorecard instead of judgment. Make one recommendation per resolved decision with
  its evidence and trade-off.
- Do not call historical, shadow, launched, or queued work complete/deployed.
