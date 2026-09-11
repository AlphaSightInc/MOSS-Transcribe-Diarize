# Job 1: honest settled/final captures

Starting revision: f1f33168. This supersedes the capture-behavior findings in the historical
NOTES.md; the earlier frozen-decode measurements remain historical evidence.

Question: can a quality capture claim convergence while rolling work remains, settling timed
out, or finalization failed? The capture must refuse those claims. Canonical backpressure and
identity behavior stay unchanged.

The minimal evidence is the existing canonical queue count, the lossless rolling admission /
completion event stream, and terminal finalization status. A rolling completion can arrive after
a snapshot was read, so the captured transcript must be refreshed after observing completion.

Changes in the shared SurfaceCaptureService used by Phase-2 quality:

- Track admitted rolling item IDs and their completion events throughout replay and settling.
  Check event continuity; a missing interval fails instead of assuming no rolling work remains.
  Canonical pending_work_items retains its original transport meaning.
- Wait for both canonical and admitted rolling work to drain. Missing snapshots or a settle
  timeout raise ServiceReplayFailure before a settled capture or Stop request is made.
- Fetch the settled snapshot again after observing completion, preserving the completed revision.
- Require finalization_status == final whenever post_stop_final is captured, including the
  collector's terminal-trace fallback. Reject failed, unavailable, and not_started. A running
  terminal pass continues through the existing terminal polling loop.

Tests: tests/phase2/test_quality_surface_capture.py. Before the change, five cases failed and
one passed: rolling work was sampled immediately, timeout did not raise, and failed/unavailable/
not_started were accepted as final. Added coverage also exercises completion arriving after the
first snapshot and unsuccessful terminal states returned directly by Stop.

Commands:

    .venv/bin/python -m pytest tests -q
    npm --prefix frontend test

Results: 1,228 Python tests passed, 2 skipped, 37 subtests passed; 155 frontend tests passed.

QUALITY_BOUNDS, _validate_quality, and identity policy are untouched. No host operations.
Job 2 (fresh identity/provider output on all six cases) is UNSTARTED at this checkpoint.
The previous frozen speaker timeline experiment cannot establish those four speaker metrics.
