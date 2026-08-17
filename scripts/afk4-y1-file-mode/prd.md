# PRD — y1-file-mode

## Goal

**Gate G9 says "Live mode and file mode both work through the one UI." Live mode works. File mode
is a cosmetic stub and G9 cannot pass.**

`frontend/src/App.tsx:68-96` renders a file picker whose entire behaviour is:

```tsx
onChange={(event) => setSelectedFileName(event.currentTarget.files?.[0]?.name ?? "")}
```

It sets a string. Nothing is uploaded, nothing is transcribed, nothing renders.
`grep -rn "api/jobs" frontend/src/` returns **nothing**.

Make file mode actually work, as a **thin client-side adapter over the existing certified
`/api/jobs` pipeline** (map-001 C7). You are not building a transcription backend — `/api/jobs`
already exists and `/studio` already drives it. Read `moss_transcribe_diarize/app/jobs.py` and the
Studio page before writing anything; this is reintegration, not new capability.

**Bar:**

1. Selecting an audio file and confirming submits it to `/api/jobs` and surfaces real progress.
2. The resulting transcript renders in the **same `TranscriptPane`** the live path uses, through
   the same state seam — not a second renderer. Diarized turns with speaker ids, as in live mode.
3. Switching Live ↔ File does not corrupt or leak either mode's state.
4. Failure paths produce a server-authored message and no crash: unsupported file type, a job that
   fails server-side, and a file chosen then cleared.
5. `frontend` vitest and typecheck stay green; you add tests for the adapter and the mode switch.

**Do not** invent a new event vocabulary. `frontend/src/api/mossPoller.ts` already maps MOSS
cursors onto the reference event model (ticket T-02); reuse that seam or state plainly why it does
not fit.

## Evidence

Commit raw artifacts under `evidence/phase1/y1-file-mode/`: the adapter exercised against a
locally-run service with a real audio file, showing the request, the job lifecycle, and the
rendered transcript text. A screenshot or DOM dump proving it rendered in `TranscriptPane` — a
passing unit test alone does not prove the pane rendered.

State plainly in your evidence what the run does **not** cover.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y1-file-mode` before every
iteration: prerequisites, file ownership, banned patterns, and evidence artifacts citing runners
not in the tree. You own `frontend/src/App.tsx`, `frontend/src/api/jobs.ts`,
`frontend/src/components/FilePanel.tsx`, plus your own loop dir, `evidence/phase1/`, `docs/`,
`tests/`. **`frontend/src/components/TranscriptPane.tsx` belongs to y2 and
`frontend/src/state/session.ts` to y3** — read them, do not edit them. If you need a change there,
record it in `context.md` and say so on the issue.

## Hard constraints

- The GPU host `ga0-alienware-rtx4070ti` is **READ-ONLY**. Verify against a locally-run service you
  start yourself, on a port you own.
- Never hardcode frame geometry or job parameters; they are deploy-manifest values.
- Push **your own branch only**, to remote `private`. Never push `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- Do not weaken a test to make a gate pass.
- Binding authority: `docs/phase1-afk-charter.md`, `.wayfinder/map-001-phase1-chrome-client.md`,
  `docs/phase1-gate-status.md` (current gate truth), `AGENTS.md`.
