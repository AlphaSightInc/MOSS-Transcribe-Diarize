---
id: T-08
map: map-001-phase1-chrome-client
title: Live-to-file transcript export
type: grilling
status: closed
assignee: claude
blocked_by: [T-02]
---

## Question

The goal statement names "transcribe live mode to file mode". C2 removed the reference's
`export-to-folder` endpoints (they wrote to the *server host's* filesystem). What replaces them?

Resolve:

1. **Client-side or server-side?** The browser already holds every transcript item the poller
   delivered, and the reference ships `lib/transcriptExport.ts` (`buildTranscriptExportText`,
   formats `md | txt | json`). A pure client-side `Blob` download is nearly free and needs no
   server change. A server-side artifact is durable and survives the tab — but Phase 1 has no
   session history to hang it on. Decide, and say what is lost either way.
2. **Completeness.** A client-side export captures only what the client received. The
   retrospective identity sweep relabels spans *after* stop (see T-02 question 5), so an
   export taken too early is subtly wrong — different speaker attribution than the final
   truth. Define when export is offered, or how the user is told the transcript is not final.
3. **Audio export.** The reference also exported session audio. ADR-0003 makes retained audio
   **opt-in** and the store arrives declared or not at all; retained-tape work also carries a
   BLOCKED Stage-0 verdict. Is live audio export in Phase 1 at all? Recommend no unless the
   deployment already declares a tape store.
4. **Formats and naming.** Which of `md | txt | json` ship; file naming with no session titles
   (titles are Phase 2).
5. **Does "live to file mode" mean something more than export** — e.g. re-running a completed
   live session through the higher-quality file-mode pipeline for a better transcript? That is
   a materially different and more valuable feature. Rule it in or out explicitly; if in, it
   needs its own ticket and probably its own phase.

Ground truth: reference `frontend/src/lib/transcriptExport.ts`, `wavEncode.ts`;
target `docs/adr/0003-live-session-audio-retention.md`;
`moss_transcribe_diarize/app/live_tape.py`;
control plane `docs/l2-retained-tape-feasibility-diagnosis-20260803.md`.

## Resolution (2026-08-13) — ruled by the supervisor on the operator's behalf

1. **Client-side `Blob` download. No server change.** The browser already holds every transcript
   item the poller delivered, and the reference ships `lib/transcriptExport.ts`
   (`buildTranscriptExportText`, formats `md | txt | json`). A server-side artifact would need
   session history to hang on, which Phase 1 does not have.
2. **Completeness:** export is available at all times and is marked *provisional attribution*
   until finalization lands, per T-02's finalization ruling. The retrospective sweep can relabel
   speakers after stop, so an early export is honestly labelled rather than blocked.
3. **Audio export: NOT in Phase 1.** ADR-0003 retention is opt-in and production deprovisioned it
   on 2026-08-09; with no retained raw there is nothing to export. The vector journal (T-12) is
   not audio and is not user-exportable.
4. **Formats** `md | txt | json`, all three. Naming `transcript-<session_id>-<iso8601>.<ext>` —
   session titles are Phase 2, so the id carries identity.
5. **"Live to file mode" does NOT mean re-running a completed live session through the
   higher-quality file pipeline.** That would require retained audio, which is off. Ruled **out of
   Phase 1** and recorded as a Phase 2 idea worth more than plain export, since it would buy a
   genuinely better transcript rather than a different file format.
