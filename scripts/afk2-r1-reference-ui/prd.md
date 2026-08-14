# PRD — r1-reference-ui

**Port the reference frontend for real**

## Goal

The previous attempt hand-wrote a **74-line `App.tsx` stub** where the reference has **1773
lines**, then marked the criterion done. Its 5-file `frontend/src/` stands against the
reference's ~68 files. That stub is what currently deploys, and it is why "pixel by pixel
exactly" — the operator's most emphatic requirement — is not met.

**Your job is a faithful port, not an approximation.**

Source of truth: `/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src/`. Port its
components, state, and lib modules. The build config, `styles/index.css` and the four bundled
font families are already lifted verbatim and verified — do not re-derive them.

Apply the closed rulings in `.wayfinder/tickets/T-05-reference-ui-control-triage.md`:

- **Layout: invent no geometry.** `.main` stays a three-column grid. The `HistoryPanel` column
  becomes the reference's own **permanently-collapsed 48 px rail**, non-interactive
  (`data-right-collapsed="true"`). The stub set it to `"false"` and rendered a full panel, which
  makes the centre transcript pane **232 px too narrow** — and charter §5 exempts the rail from
  the pixel diff, so that error would pass unnoticed. Get this right.
- Mode control reduces to **`Live | File`**. Keep transcript pane, transcript search, generic
  speaker labels, toasts, segmented control, and local mic mute (`track.enabled = false`).
- Drop: mic picker, server-side device enumeration, output volume, native pickers,
  export-to-folder, both server-side mute paths, `HistoryPanel` contents, `SummaryView`,
  `LlmSettingsModal`. Remove shortcuts whose targets are gone rather than leaving no-ops.
- Replace `api/ws.ts` with a poller feeding the **identical** `dispatchWsEvent()` seam; leave
  `state/`, `components/`, `lib/` otherwise untouched. Contract: T-02's resolution.

**Gate (executable):**
```bash
npm --prefix frontend run typecheck && npm --prefix frontend test
python3 scripts/afk-guardrails/preflight.py r1-reference-ui
```
Plus, recorded as artifacts: a file-count and line-count comparison against the reference, and
proof that `data-right-collapsed="true"` is what renders.

**Port the reference's component tests too.** The previous attempt transferred zero and passed a
tautological 22-line file. `--passWithNoTests` has been removed, so an empty suite now fails.

You are the critical path — r2 waits on you. Land a faithful shell early.


## Guardrails — enforced, not advisory

`RALPH_PREFLIGHT_CMD` runs `scripts/afk-guardrails/preflight.py r1-reference-ui` before **every**
iteration with `RALPH_PREFLIGHT_REQUIRED=1`. If it fails, **the loop stops.** It checks:

- **Prerequisites.** If what you need does not exist, you stop at iteration 0 and escalate on
  the issue. You do **not** build scaffolding for a run you cannot perform. The previous fleet
  burned eight iterations doing exactly that.
- **File ownership.** You may only modify the paths this ticket owns (see
  `scripts/afk-guardrails/ownership.json`), plus your own loop dir, `evidence/phase1/`, `docs/`,
  `tests/`, `.wayfinder/`. Touching another ticket's files stops the loop. Two agents previously
  built the same feature with incompatible APIs because nothing declared ownership.
- **Banned patterns.** `--passWithNoTests`; and any evidence artifact citing a probe script that
  is not in the tree. A gate whose probe was deleted cannot be re-run by anyone.

## What went wrong last time — do not repeat it

Six agents ran this repo on 2026-08-13. All six wrote `COMPLETE`. Independent adversarial review
returned **four FAIL and one PASS-WITH-DEFECTS**. The failure modes, verbatim:

1. **Self-certification.** Agents declared done against criteria they had not met. **You may not
   write your own verdict.** A separate reviewer reads your raw artifacts. Emit
   `<promise>COMPLETE</promise>` only when the executable gate passes and every criterion has a
   raw artifact behind it.
2. **Stub-satisfiable gates.** A test asserting `code in FROZEN_SET` where the parametrize list
   *is* that set. A fairness "measurement" that restated a deque's behaviour with zero decode
   cost. A hardcoded fixture string standing in for model output. **If your test would pass with
   the feature deleted, it is not a test.**
3. **Building the evidence instead of the thing.** One ticket shipped a status projection with no
   client; another shipped measurement scaffolding and no dispatcher. **Build the deliverable
   first, then measure it.**
4. **Deleting the probe.** A gate's only proof was a JSON blob whose generator had been removed.
   **Every artifact must name a committed, re-runnable probe.**
5. **Overstating scope.** A criterion said "two-speaker fixture in the selected tab"; what ran was
   a three-speaker fixture through the microphone. Say exactly what you ran.

## Definition of done

1. Your ticket's executable gate passes (see the ticket section below).
2. Validation passes after merging current `dev` into your branch.
3. Every criterion has a **raw artifact** under `evidence/phase1/r1-reference-ui/` — command output, logs,
   measurements — plus the committed probe that produced it.
4. An issue comment states, criterion by criterion, what proves it **and what your tests do not
   cover**.
5. `context.md` and `progress.txt` reflect real state.

**State plainly what you did not prove.** An honest blocked stop is a good iteration; a false
completion is the failure this fleet exists to correct.

## Merge protocol — YOU DO NOT MERGE

**Changed by the orchestrator, 2026-08-14. This supersedes any merge instruction above.**

Do **not** merge to `dev`. Do **not** `git push . HEAD:dev`. Do not take the merge lock.

Work only on your own branch and commit there. When your gate passes, stop and say so on the
issue. The orchestrator then runs an adversarial review of your branch, sends you any defects it
finds, and only reconciles branches into `dev` after those are fixed.

This order is not bureaucracy. The previous fleet merged first and reviewed second; four of six
branches were later found to have failed their acceptance criteria, and two P0 regressions --
a total live-capture outage and ordinary overload converting into dead sessions -- reached `dev`
and had to be repaired by hand. Review before reconcile is the fix.

You may still `git merge --no-edit dev` **into your branch** to stay current, and you must
validate on that merged result. That direction is safe; the reverse is not.
