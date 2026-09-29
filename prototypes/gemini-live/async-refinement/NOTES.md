# Async refinement Stop probe

Structural question: can Stop save the complete live transcript as a durable completed Meeting while a whole-recording Gemini pass is still running, then replace that transcript once without losing a rename?

Minimum primitives: the stopped live snapshot; the Meeting's durable transcript version; a running refinement marker; the terminal task; current speaker labels. The marker gates export/correction and projects a failure notice after restart. The terminal task waits for the version-N commit before it can publish version N+1.

Invariants: all accepted audio is drained or explicitly marked incomplete before version N; cleanup OFF and the MOSS engine retain their behavior; failure leaves N intact; a successful replacement changes only text and version, and reads labels at its commit.

Unknown: real provider latency for the background pass on longer meetings. Falsifier: Stop waits for a held terminal pass, version N is absent while it runs, an allowed rename is lost, or a timeout/restart removes the live transcript.

Tool decision: the held terminal owner-bound HTTP test reaches the durability race and rename seam without a provider charge; the public 60-second 1.0x HTTP smoke checks the packaged server path and actual provider latency/cost. Run:

`PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python -m pytest -q -p no:cacheprovider tests/phase2/test_owner_bound_live_meeting.py -k gemini_cleanup_stop_saves_completed_live_version`

Threshold arithmetic: the supported 60-minute mono PCM tape is 115,200,000 bytes. With 900-second chunks and 30-second overlap, a full lane has five chunks, processed in two batches of up to three. Each chunk decode has a 240-second deadline and at most one coverage retry: a sequential two-lane pessimistic bound is `2 lanes × 2 batches × 2 attempts × 240 s = 1920 s`, before local stitching and scheduling. A 3600-second refinement timeout leaves 1680 seconds for that overhead while ensuring a stalled task eventually becomes a visible failure. This is a bound from configured limits, not a measured latency guarantee.

Verdict: the focused held-terminal test confirms immediate durable N, then atomic N+1 on success or retained N on failure/restart; the forced timeout test confirms retained live text. The public Bill 60-second replay through the packaged HTTPS server at 1.0x accepted/accounted 960,000/960,000 samples, finished `completed/done` at transcript version 6, and metered $0.015676667. The Stop HTTP call took 15.48 seconds; in this small replay the terminal pass finished before the client observed Stop, so it does not itself prove an observable `running` interval. The held-terminal HTTP test supplies that evidence. Full receipt: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp1/async-refinement-smoke/`.

Review-2 summary race: a held version-N provider response was released after a durable N+1 refinement. Before the fix, HTTP returned generic 409 and left the N summary `generating`. The production-path red/green test now observes HTTP 409 `summary_source_changed`, a durable `failed/source_changed` N attempt, and a successful N+1 summary without cancellation. A second held-call variant starts N+1 before N returns; the older in-flight call is superseded. Run: `PYTHONDONTWRITEBYTECODE=1 MOSS_TEST_REAL_SQLITE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python -m pytest -q -p no:cacheprovider tests/phase2/test_server_summary.py -k refinement_supersedes_held_summary`. Both variants pass; no provider send.
