# Handoff: adversarially review six completed branches, then fix what they find

Written 2026-08-14 by the orchestrating session. The work below is **claimed complete and
entirely unverified**. Your job is to disprove or confirm it, then repair it.

## Launch contract

Read this file, then launch **one subagent per branch** (six). Each subagent, for its branch:

1. **`/codex:adversarial-review`** on the branch diff against `dev`.
2. **`/diagnose`** every finding — reproduce it before believing it, and reproduce it again
   after fixing. A finding nobody can reproduce is not a finding; a fix nobody re-ran is not a fix.
3. **`/prototype`** before implementing any non-trivial fix. Measure the approach, then write the
   production code. `AGENTS.md` requires this and it is not optional here — see "Why the bar is
   this high".
4. Fix, with the evidence discipline in §Definition of done.

Subagents may use `treehouse` to take their own worktree (`treehouse get --lease --lease-holder
<ticket>`); the six existing worktrees are already leased, one per branch, listed below.

**Codex auth is currently broken** — `/codex:adversarial-review` returns *"access token could not
be refreshed because you have since logged out or signed in to another account"*. Run
`codex login` first. If it cannot be restored, fall back to **Opus subagents** with an explicitly
adversarial brief; that fallback has found every P0 so far in this effort. Note also that
`/codex:review` (the native reviewer) fails with `spawnSync git ENOBUFS` on large diffs, and that
`gpt-5.6-sol` hit a usage limit until **2026-08-19** — the loops ran on `gpt-5.6-terra`/xhigh.

## The one thing that matters most

Six agents self-reported `COMPLETE`. **Do not treat that as evidence.** In the previous round six
agents did the same and independent review returned **four FAIL and one PASS-WITH-DEFECTS**, with
two P0 regressions reaching `dev`. `x6-terminal-visibility` reporting complete at **iteration 1**
for a two-defect ticket is the single most suspicious signal in this batch.

Equally: several of these branches are honest and substantially correct. Do not assume failure
either. Verify.

## State

- Product repo, branch `dev` @ `23afb6d`. **No agent branch is merged.** Reconcile only after
  review and fixes land — this ordering is the operator's explicit instruction and exists because
  merging first is how the previous round put P0s on `dev`.
- Safety tags: `pre-afk-20260813`, `pre-integration-20260813`. Backup branch `dev-backup-20260812`.
- Full suite on `dev`: **1006 passed / 2 skipped / 387 subtests**, plus 6 pre-existing failures
  (four `test_macos_uds_tracer.py`, one `l2-stage0` ingest, and the `l15` product-tree drift
  guard). All six fail identically at `pre-afk-20260813`. **Do not "fix" the l15 pin** — that
  guard correctly refuses to run L1.5 measurements when the product tree moved; editing it would
  falsify a measurement baseline.

### Branches to review — one subagent each

| Branch | Worktree | Product files changed | PRD (the defect list to verify against) |
|---|---|---|---|
| `afk3/x1-frame-drop` | `~/.treehouse/MOSS-Transcribe-Diarize-e7521b/1/…` | 6 | `scripts/afk3-x1-frame-drop/prd.md` |
| `afk3/x2-capture-client` | `…/2/…` | 3 | `scripts/afk3-x2-capture-client/prd.md` |
| `afk3/x3-capture-health` | `…/3/…` | 5 | `scripts/afk3-x3-capture-health/prd.md` |
| `afk3/x4-journal-mode` | `…/4/…` | 4 | `scripts/afk3-x4-journal-mode/prd.md` |
| `afk3/x5-auth-residual` | `…/5/…` | 3 | `scripts/afk3-x5-auth-residual/prd.md` |
| `afk3/x6-terminal-visibility` | `…/6/…` | 4 | `scripts/afk3-x6-terminal-visibility/prd.md` |

Each PRD states the defect the branch was created to fix, with the reproduction the reviewer
found. **Verify the fix against that reproduction**, not against the agent's summary.

### UI port — orchestrator's work, separate branch

`ui/reference-port` @ `979ea56`, cut from `dev`. Gate green: `typecheck` exit 0, 11 test files,
42 tests. 32 files / ~6.9k lines against the reference's 67 / ~18k.

Done: verbatim ports of `Topbar`, `ToastLayer`, `keyboardShortcuts`, `persistence`, `state/ui`,
plus 604 lines of reference tests; transcript-pane header/legend/floating-tools restored to
reference markup; `buildTranscriptExportText` restored.

**Not done, and the reason the MVP is not walkable:**
- `ControlPanel` (reference 544 lines) with the T-05 drops
- `App.tsx` orchestration — **the poller is still dead code; nothing constructs it**, so no code
  path reaches `/api/live/sessions/*` and the capture button is hardcoded disabled
- Three poller defects found by review and still open: a terminally-failed session renders as
  healthy and is polled forever; the event cursor advances past events that were never rendered
  (parallel `/snapshot` + `/events` with `unchanged: true`); `provisional_stale` latches on
  permanently ~250 ms in, and a test *locks that defect in*
- The committed bundle under `ProjectResources/Frontend/` is **stale** — it is the previous
  attempt's build. Rebuild before judging anything visual, or you will measure the wrong artifact.

## Guardrails — already enforced, do not weaken

`scripts/afk-guardrails/preflight.py` runs before every ralph iteration with
`RALPH_PREFLIGHT_REQUIRED=1`, checking prerequisites, per-ticket file ownership
(`ownership.json`), banned patterns, and evidence citing probes absent from the tree. Every check
exists because that exact failure happened. If preflight blocks you, the answer is almost never to
relax it — twice it was correct and the fault was mine (an `afk-` prefix that missed `afk2-`, and
a `.venv` symlink `.gitignore` did not match).

`r3-dispatcher` is **parked**, with its unpark condition recorded in `ownership.json`: the 4070 Ti
reports ~1.1 GB free because production vLLM holds it, so a second model instance cannot fit and
the charter forbids touching running services.

## Definition of done, per branch

1. Every defect in the branch's PRD is either **reproduced-then-fixed** or **shown not to exist**,
   with the reproduction committed.
2. Full suite green apart from the six known pre-existing failures.
3. Raw artifacts under `evidence/phase1/<ticket>/`, each naming a **committed, re-runnable** probe.
4. A written statement of what the tests do **not** cover.
5. **Subagents do not merge to `dev`.** They may merge `dev` *into* their branch and must validate
   on that merged result. Reconciliation is the orchestrator's, after review.

## Why the bar is this high — failure modes seen on this repo

Cite these when briefing subagents; each is a real event here, not a hypothetical.

- **A gate satisfiable by stub evidence.** An assertion that sequence numbers are contiguous, where
  the code makes them contiguous by construction — it passed over a stream that silently dropped
  36 % of the audio. A `code in FROZEN_SET` check where the parametrize list *is* that set. A
  fairness "measurement" with zero decode cost that merely restated that a deque is a deque.
- **Building the evidence instead of the thing.** One ticket shipped a status projection with no
  client; another shipped measurement scaffolding and no dispatcher.
- **A feature that is dead code at the route.** Capture-health fusion shipped keyword-only with a
  `None` default; the only call site never passed it, while its unit test passed by calling the
  function directly.
- **A deleted probe.** A gate's only proof was a JSON blob whose generator had been removed. Three
  such artifacts are quarantined under `evidence/quarantine/t5-unreproducible/`.
- **A test that encodes the defect.** Two tests asserted the very behaviour that caused a total
  live-capture outage; one locks in the `provisional_stale` latch.

## Ground truth — read, do not re-derive

| Path | Why |
|---|---|
| `docs/phase1-afk-charter.md` | Binding. Authority §1, capture spec §4, fidelity method §5, gates §6, attended checklist §7 |
| `.wayfinder/map-001-phase1-chrome-client.md` | Premises C1–C11 |
| `.wayfinder/tickets/` | 12 closed decisions with full rationale — all settled, do not re-litigate |
| `docs/research-chrome-capture-mvp-2026-08-03.md` | Gate 1 measured verdict; browser capture is settled here |
| `AGENTS.md` | Measure before implementing |
| `scripts/afk-guardrails/ownership.json` | Who may touch what |

Reference UI source of truth: `/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src`.
Deployed live service: `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861` — **the explicit
port is load-bearing**, omitting it silently targets unconfigured 443.

## Environment traps that cost this session time

- **npm/node do not run in the agent sandbox** (`_nvm_lazy_load: command not found`, then "Exit
  handler never called"). Same class of block as `ssh`. Run frontend gates through a tmux pane
  (`%162` was used as a build executor); they execute for real there.
- The six worktrees have **no `.venv`**; the main checkout's is symlinked in. `.gitignore` now
  covers both `.venv/` and a bare `.venv` symlink.
- Long `tmux send-keys` truncates silently — use `load-buffer` + `paste-buffer` and verify.
- zsh arrays are **1-indexed**; a bash-style loop mis-assigned panes and branches twice here.

## Suggested skills

- **`/codex:adversarial-review`** — the review pass (auth must be fixed first; see Launch contract).
- **`/diagnose`** — reproduce → minimise → hypothesise → instrument → fix → regression-test. Use it
  on every finding, including ones you believe immediately.
- **`/prototype`** — mandatory before any non-trivial fix. Extend
  `prototypes/streaming-diarization/` rather than rebuilding measurement scaffolding.
- `/grilling` + `/domain-modeling` only if a *decision* turns out to be open. All twelve wayfinder
  decision tickets are closed; if you think you need one, you are probably re-litigating.

## Do not

- Do not merge to `dev`, push `main`, or close GitHub issues (`aiSight-us/MOSS-Transcribe-Diarize`,
  private) — comment evidence; the orchestrator closes.
- Do not restart, redeploy, or send mutating requests to `moss-live-web`, `moss-vllm`, `moss-web`
  on the GPU host.
- Do not automate the display-capture picker; the standard requires a fresh user gesture per
  capture and the 2026-08-03 CDP attempt failed with `NotReadableError`. Two-lane display
  verification is the operator's attended checklist (charter §7).
- Do not add Uvicorn workers — device state, session ownership, mixers, event queues and view
  grants are process-local.
- Do not weaken a test to make a gate pass. If a test encodes a defect, rewrite it to assert the
  correct contract **and say why in the commit**.
