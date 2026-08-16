# Handoff: resume after the MacStudio reboot

Written 2026-08-16 by the orchestrating session, immediately before a planned reboot.
**The AFK3 cycle is COMPLETE and reconciled.** This document exists so the next session knows the
mission, what landed, what is genuinely open, and which environmental lies to disregard.

## Mission

MOSS-Transcribe-Diarize Phase 1: ship a **browser-based (Chrome) live capture MVP** — two audio
lanes (microphone + shared/system) captured in the browser, streamed to a local service, transcribed
and diarized live in a faithful port of the LiveTranscribe reference UI. Binding authority is
`docs/phase1-afk-charter.md` (authority §1, capture spec §4, fidelity method §5, acceptance gates
§6, attended checklist §7). Premises: `.wayfinder/map-001-phase1-chrome-client.md`; 12 closed
decisions in `.wayfinder/tickets/` — **settled, do not re-litigate**.

## Where the roadmap stands

| Stage | State |
|---|---|
| Six fix branches (`afk3/x1`…`x6`) reviewed + repaired | ✅ done |
| Reconciliation into `dev` | ✅ done — all six tips are ancestors |
| UI port + App.tsx capture wiring | ✅ done (`ec7cdcb`) |
| Weighted canonical admission / bounded shutdown | ✅ done (`1db447c`) |
| G7 background-tab evidence | ❌ **blocked on Chrome** |
| G3 two-lane display capture | ❌ **operator's attended checklist, charter §7** |
| Push / deploy | ❌ not done, deliberately |

`dev` = `4e8cae5`, **local only** (`private/dev` = `8fec841`). Nothing pushed, `main` untouched, no
issues closed, no deployment.

## Read these, do not re-derive

1. **`docs/handoffs/handback-afk3-20260815.md`** — Codex's own close-out. Merge SHAs in order,
   weighted-admission semantics, acceptance evidence, and its four "human gates". Authoritative for
   what it did.
2. **`/Users/gao/.claude/reboot-checkpoints/moss-20260814-174105/`** — the pre-reboot forensic
   checkpoint (1218 files, SHA-256 manifest). Contains the six per-branch verdicts, every reviewer's
   findings, evidence audits, the guardrail defects, and the environment diagnosis. Read
   `POST_CHECKPOINT_UPDATE.md` first; it supersedes the rest.
3. `docs/handoffs/handoff-afk3-XXXXXX.md` — the plan Codex executed. Historical now.

## My independent verification (do not take Codex's numbers on trust — I didn't)

Verified with TCC up, Codex idle, no concurrent runs:

- All seven tips (`afk3/x1`…`x6` + `ui/reference-port`) are **ancestors of `dev`** ✅
- Commits `1db447c`, `4e8cae5` exist on `dev` ✅
- Working tree clean ✅ · not pushed ✅
- Frontend: typecheck clean, **99/99**, 13 files ✅

**One number does not reproduce.** Codex reported `2 failed / 1063 passed` with "macOS tracer 6/6
passed". My run:

```
6 failed, 1059 passed, 2 skipped, 394 subtests
```

The delta is exactly the 4 macOS tracer tests (1059 + 4 = 1063), failing with `-6` SIGABRT and
Launch Services errors — the code-signing fault. They fail consistently for me and passed once for
Codex; treat them as **flaky-under-degradation, unresolved**, not green.

**What matters — no regression:**

| | `dev` @ `f6353eb` (pre-merge) | `dev` @ `4e8cae5` (now) |
|---|---|---|
| failed | 6 | **6 — the same 6** |
| passed | 1006 | **1059** (+53) |
| subtests | 387 | **394** (+7) |

Same failures as before any of this work started: l15 product-tree drift, l2-stage0 `55 != 92`, and
the 4 environmental tracer tests.

## FIRST ACTION AFTER REBOOT — validate the host

The reboot exists to clear a wedged-daemon fault. Run in order, stop at the first failure:

```bash
whoami                                                    # MUST print "gao", not "501"
dscl . -read /Users/gao RecordName                        # MUST succeed (was: eServerError)
codesign -v --strict /System/Applications/Calculator.app  # MUST be silent (was: CSSMERR_TP_NOT_TRUSTED)
spctl -a -vv /System/Applications/Calculator.app          # MUST NOT say "internal error in Code Signing subsystem"
curl -sS -o /dev/null -w '%{http_code}\n' https://chatgpt.com   # MUST NOT be 000 (DNS was dead)
pgrep -l trustd                                           # MUST NOT say "sysmond service not found"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --dump-dom about:blank >/dev/null; echo $?   # want 0, was 134
```

Then re-measure the baseline — **do not reuse the 6-failure number**:

```bash
cd /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize
.venv/bin/python -m pytest -q -p no:randomly | tail -12
```

**Prediction to test:** if code signing is repaired, the 4 macOS tracer failures should clear and
the baseline should drop to **2** (l15 + l2-stage0). If they persist, they are a real defect, not
environmental — that would overturn a standing assumption.

**Do not** change FDA/TCC settings and **do not** reinstall Chrome. The fault was never a permission
or a corrupt app; full diagnosis in the checkpoint's `FDA_DIAGNOSIS.md`.

## Environmental lies — recognise, do not debug

These wasted hours this cycle:

- `git` says **`fatal: not a git repository`** / `Unable to read current working directory` when it
  merely cannot read `.git` under `~/Desktop`. Looks exactly like corruption. It is not.
- `pytest` dies inside `<frozen site>` on `.venv/pyvenv.cfg`, or Python fails with
  **`failed to make path absolute`** — a suite that never started, easily misread as a failing suite.
- A contaminated run is identifiable by `AssertionError: 128 != 0`, `ops/moss-live.env is not
  gitignored`, or those tracebacks. **Discard such runs.**
- **Never run `pytest` or `swift build` concurrently with another agent's suite.** Two `swift build`
  invocations collide on `.build`; I misdiagnosed that as a real failure and had to retract it.

## Human decisions waiting (nothing proceeds without these)

1. **Reboot + recheck host**, then redo the macOS tracer and Chrome/G7 evidence.
2. **Minimum canonical queue-depth policy.** Codex's weighted admission means a frame or Stop tail
   whose predicted span weight alone exceeds `max_queue_depth` **can never be admitted**. Decide:
   enforce a deployment-configured minimum derived from endpoint/frame geometry, or accept
   retry/timeout as product policy. (Codex's handback §"Deliberately open".)
3. **The 1-second browser terminal-request bound** is now explicit policy — change only deliberately.
4. **L15 pin and the archived 92-unit L2 corpus** — update, restore, or accept as permanent baselines.
   Note: `l2-stage0` failure count varies per worktree because the corpus is **untracked**; that is
   environmental, not a defect. Never "fix" the l15 pin — it correctly refuses to run L1.5
   measurements when the product tree moved.
5. **Review two design calls Codex made on the operator's behalf** (both flagged as human-gated in the
   prior handoff; both look correct to me): threading `terminal_session_status` into
   `live_capture_status.py`, and adding a distinct `"stopped"` → *"Audio capture stopped."* capture
   phase so a clean stop no longer reports `failed`.
6. **Whether to push `dev`.** It is 1 commit ahead of `private/dev` and has never been pushed.

## Known-open, unowned (from the review cycle — details in the checkpoint)

- Two `scripts/afk-guardrails/preflight.py` blind spots: probe-citation is enforced only for
  filenames matching `*probe*.py`/`*proto*.py`, and only **existence** is checked, so a probe that
  crashes on re-run still passes. Both were exploited this cycle.
- Two tautological G7 assertions remain in `probe_g7_hidden_tab.py` (`:250`, `:263`).
- `VIEWABLE_SESSION_STATUSES` excludes terminal statuses, so a viewer still cannot learn *why* its
  session died.
- No post-`1db447c` adversarial review was run, per the stop order. New findings are follow-up work,
  **not** a reason to reopen AFK3.

## Traps specific to this repo

- **Wrong repo.** The shell's default cwd `…/0.AISIGHT_LOOP/moss-transcribe-diarize` is a *different,
  unrelated* repo. Product repo is `…/Github_Projects/MOSS-Transcribe-Diarize`. Codex's tmux pane
  (`MOSS:1.2`) is also cwd'd there while editing the correct repo — do not be misled.
- `npm` works only via `/opt/homebrew/bin/npm`; `npm ci` genuinely fails. `log` is shadowed — use
  `/usr/bin/log`. zsh: `$var` followed by `:` is a history modifier.
- Seven worktrees exist under `~/.treehouse/MOSS-Transcribe-Diarize-e7521b/{1..6}/` plus
  `…-wt-ui-port`. All were clean at handoff.

## Do not

Push `main` · close GitHub issues (comment evidence; the orchestrator closes) ·
restart/redeploy/mutate `moss-live-web`, `moss-vllm`, `moss-web` on the GPU host (different machine;
the reboot does not affect it) · add Uvicorn workers · automate the display-capture picker ·
weaken a test to make a gate pass · reopen AFK3 reconciliation.

## Suggested skills for the next session

- **`/codex:adversarial-review`** — now finally runnable once DNS returns. Best first use: the
  post-`1db447c` review that was deliberately deferred, scoped as new follow-up work.
- **`/diagnose`** — for anything that does not reproduce first try; every real defect this cycle was
  found that way.
- **`/tmux-peer 1.2`** — Codex's session (`%167`) still holds the full AFK3 reasoning if more detail
  is needed than the handback carries.
- Skip `/grilling` and `/domain-modeling` unless a genuinely new decision opens.
