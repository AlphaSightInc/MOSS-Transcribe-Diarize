---
id: T-07
map: map-001-phase1-chrome-client
title: File-mode adapter over the certified /api/jobs pipeline
type: grilling
status: open
assignee:
blocked_by: [T-02]
---

## Question

C7 runs Phase 1 file mode through a thin adapter over `/api/jobs`. What is that adapter's
contract, and how does remote upload behave?

MOSS's file mode is a **job** pipeline: `POST /api/jobs` (multipart) → `GET /api/jobs/{id}` →
`GET /api/jobs/{id}/segments` → `PUT .../segments` → `POST .../render` →
`GET .../download?kind=`. The reference frontend instead expects a **session**:
`POST /api/sessions/start-file` → status polling → transcript items → the same
`TranscriptPane` that live mode renders into.

Resolve:

1. **Which way the adapter points.** Add session-shaped endpoints that wrap jobs, or teach the
   frontend to speak jobs directly and synthesize session-shaped events in the poller? T-02's
   poller already synthesizes events for live; reusing that seam may be cheaper than new
   server endpoints — decide on evidence, not taste.
2. **State mapping.** Job states → reference `SessionLifecycle` / `describeBatchStatus`
   vocabulary. Which job states have no reference equivalent, and vice versa?
3. **Segments → `TranscriptItem`.** Must agree with T-02's shape so one `TranscriptPane`
   renders both live and file output. Diarization labels included.
4. **Remote upload.** The reference picked local files via a native host dialog; a remote
   client uploads over the network instead. `_admit_upload_request`, the receive-idle timeout
   (408), and chunked `_read_upload_chunk` already exist — confirm they hold for large files
   over a tailnet, and define the client's progress/retry/resume behaviour. Note `runs_dir`
   admission bounds concurrent uploads; state the limit the UI must respect.
5. **Where the file lands and for how long.** Phase 1 has no history, so what happens to
   uploaded media and job output after the tab closes? Note `DELETE /api/jobs/{id}` exists.
6. **Does the Subtitle Studio's editing/render/burn-in path stay reachable** for a file
   uploaded through the new app — i.e. is there a handoff to `/studio`, or are the two
   pipelines deliberately separate in Phase 1?
7. **Auth.** Batch/job routes are currently **unauthenticated** while live routes are not.
   Under C5's shared token, does file mode become authenticated too? Rule this explicitly —
   an unauthenticated upload endpoint reachable from the tailnet is a decision, not an oversight.

Ground truth: `moss_transcribe_diarize/app/server.py` lines ~163–365;
`moss_transcribe_diarize/app/jobs.py`; reference `frontend/src/api/rest.ts`
(`startFileSession`, `getBatchStatus`) and `frontend/src/api/types.ts`.
