---
id: T-07
map: map-001-phase1-chrome-client
title: File-mode adapter over the certified /api/jobs pipeline
type: grilling
status: closed
assignee: claude
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

## Resolution (2026-08-13) — ruled by the supervisor on the operator's behalf

1. **The adapter is CLIENT-side. No new server endpoints.** T-02 already builds a poller that
   synthesizes reference-shaped events from MOSS's native surfaces; file mode reuses that seam by
   speaking `/api/jobs` directly and synthesizing the same `session_state` / `transcript_update`
   events. Adding server-side session-shaped wrappers around jobs would duplicate a translation
   layer that already has to exist.
2. **State mapping:** job state → `SessionLifecycle` (`queued`→`starting`, `running`→`recording`,
   `done`→`completed`, `failed`→`failed`). Job progress drives `progress_pct`. Job states with no
   reference equivalent collapse to the nearest; none are invented.
3. **Segments → `TranscriptItem`** using the identical shape T-02 fixed, so one `TranscriptPane`
   renders live and file output. `state` is always `final` for file mode — there is no provisional
   tail. `segment_id` is the job's segment index.
4. **Upload:** existing multipart `POST /api/jobs`. `_admit_upload_request`, the 408 receive-idle
   timeout, and chunked `_read_upload_chunk` already exist and are kept. Client shows byte
   progress. **No resume in Phase 1** — a failed upload retries whole; state that limit in the UI.
   Respect the `runs_dir` admission bound; surface "server busy" rather than queueing client-side.
5. **Lifetime:** artifacts persist until explicitly deleted via the existing
   `DELETE /api/jobs/{id}`. Phase 1 adds no TTL and no auto-cleanup.
6. **Studio handoff:** none built, but a file uploaded through the new UI lands in the same
   `runs_dir` and is therefore already visible in `/studio` for subtitle editing and burn-in. Note
   this as a free benefit; do not build a bridge.
7. **Auth — job routes get the shared token.** They are unauthenticated today. T-01's single trust
   domain accepted shared *reads*; it did not accept unauthenticated *writes*. Upload consumes
   disk and GPU, so an open upload endpoint on the tailnet is a materially worse exposure than
   shared transcript reads. Apply the same shared bearer to the job routes.
