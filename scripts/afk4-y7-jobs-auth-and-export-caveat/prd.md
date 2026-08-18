# PRD — y7-jobs-auth-and-export-caveat

## Goal

Two acceptance criteria that shipped unmet while the gate above them was recorded as PASS. Both were
found by reading the issues criterion-by-criterion rather than trusting the gate rollup.

### 1. `/api/jobs` is unauthenticated (issue #8, security)

Verified 2026-08-18: `POST /api/jobs` in `moss_transcribe_diarize/app/server.py:198` takes no auth
dependency, there is no auth middleware, and **no test asserts any of this**. Issue #8 states the
criterion in as many words:

> **Job routes require the shared bearer token.** They are unauthenticated today; T-01 accepted
> shared *reads*, not unauthenticated *writes*, and upload consumes disk and GPU.

So today anyone who can reach the host can spend its disk and its GPU without presenting anything.
T-01 accepted a single trust domain for *reading transcripts*; it did not accept anonymous writes.

**Bar:** all four job routes (`GET /api/jobs`, `POST /api/jobs`, `GET /api/jobs/{id}`,
`DELETE /api/jobs/{id}`) require the shared bearer, reusing the **existing** auth seam in
`live_auth.py` — do not build a second auth mechanism. Tests must prove: no bearer → rejected;
wrong bearer → rejected; correct bearer → admitted; and the existing pairing flow still works when
no shared token is configured. `_admit_upload_request`, the 408 receive-idle timeout and chunked
reads must all survive unchanged.

The frontend file-mode client must send the bearer it already holds in memory. It must not put the
token in a query parameter or in `localStorage` (issue #2's criterion, still binding).

### 2. An exported transcript must carry its own provisional caveat (issue #9)

`frontend/src/lib/transcriptExport.ts` records `provisional_stale` as a boolean in the **json**
export only. The criterion is about the file a human opens:

> An export taken before finalization is marked **provisional attribution** inside the exported file
> itself, not only in the UI — the retrospective sweep can relabel speakers after stop, so a file
> that outlives the tab must carry its own caveat.

A boolean in a machine format does not warn the person reading the markdown.

**Bar:** an export taken before finalization carries a human-readable caveat in **every** format —
markdown, text, and json — stating that speaker attribution is provisional and may be revised by the
retrospective sweep after the session ends. An export taken after finalization must **not** carry it,
or the warning becomes noise everyone learns to ignore. Test both directions.

Keep the filename contract intact: `transcript-<session_id>-<iso8601>.<ext>`.

## Evidence

Raw artifacts under `evidence/phase1/y7-jobs-auth-and-export-caveat/`. For the auth work, show the
rejected and admitted requests against a locally-run service — a unit test alone does not prove a
route is guarded. Include a before/after of an export taken mid-session.

## Guardrails (enforced — the loop stops on violation)

`RALPH_PREFLIGHT_REQUIRED=1` runs `scripts/afk-guardrails/preflight.py y7-jobs-auth-and-export-caveat`
before every iteration. You own `moss_transcribe_diarize/app/server.py`,
`frontend/src/api/jobs.ts`, `frontend/src/api/jobs.test.ts`,
`frontend/src/lib/transcriptExport.ts`, `frontend/src/lib/transcriptExport.test.ts`,
`evidence/phase1/y7-jobs-auth-and-export-caveat/`, plus your own loop dir, `docs/`, `tests/`.

`moss_transcribe_diarize/app/live_auth.py` is **read-only** — reuse its seam, do not modify it. If it
genuinely cannot be reused, stop and escalate rather than forking a second auth path.

## Hard constraints

- Auth is a security seam. Do not weaken bearer comparison or revocation to make a route pass.
- The GPU host is **READ-ONLY**. Verify against a locally-run service on a port you own.
- Push **your own branch only**, to `private`. Never `dev` or `main`. Never force-push.
- You may not close GitHub issues. Comment evidence; the orchestrator closes.
- Do not weaken a test to make a gate pass.
- Binding authority: `docs/phase1-afk-charter.md`, `.wayfinder/tickets/T-01-shared-token-trust-posture.md`,
  `docs/phase1-gate-status.md`, `AGENTS.md`.
