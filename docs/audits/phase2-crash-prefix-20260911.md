# Crash recovery: wrong revision field, not a layer-dependent recovery failure

Starting revision: f484c635. Verified the same defect and layer selection in round-5
candidate 513c9d5f using local Git objects. No host operations.

**F1 — A durable prefix is already-persisted speech.** Live publication builds a
transcript document containing `segments` (`app/phase2_live.py::_transcript_document`).
`Phase2Store` writes this document into `meeting_transcripts`, advancing its separate
SQLite `version` column. `_meeting_from_row` and `Meeting.to_dict` expose that durable
revision as top-level `transcript_version`; it is not inside the transcript document.
A positive revision plus nonempty segments establishes the transcript prerequisite.
Accepted PCM alone or an in-memory transcript is insufficient.

**F2 — The probe read the wrong field.** `FixedAccountCampaign.crash_recovery` creates
a live session and streams the first corpus case in descriptor-sized frames,
paced at the sample rate. At the normal 8,000-sample frame size it tries 120 frames,
i.e. 60 seconds of audio (plus request latency). After each frame it GETs the owner
meeting and tests for nonempty segments and a positive revision. It incorrectly read
`transcript.version`; a real response has `transcript_version` and
`transcript: {segments: [...]}`. The missing nested field defaulted to zero on every
iteration, regardless of whether speech had been persisted. The exception is thrown
before `systemctl kill` is reached. It therefore establishes neither a persistence
failure nor a recovery failure. The actual round-5 transcript content is uninspected.

Once the prerequisite succeeds, the probe records accepted PCM, kills/restarts the
web service, requires a changed process ID, compares the saved transcript document,
compares recovered partial MP3 bytes and metadata against the production archive
oracle, checks interrupted status, and requires rejection of capture reattachment.
Those checks, timings, and audio requirements are unchanged.

**F3 — Pre-admission did not pass this probe; it never runs it.**
`phase2_acceptance.py::EXTERNAL_REQUIREMENTS` includes crash_recovery only under
`deployed.G3`. `pre_admission.G3` contains only meeting_modes_history_restart.
`measure_layer` iterates that layer's requirements. This explains the asymmetry
without positing any runtime/configuration difference. Confirmed in both 513c9d5f
and the current source; no denominator or scheduling change is made.

The unambiguous fix is a one-line lookup of `before['transcript_version']` (with the
existing missing-value default). A regression test now constructs its response with
the production `Meeting.to_dict`, instead of inventing a nested version. Before the
fix, valid API-shaped data fails and a nested-only version incorrectly succeeds.
After the fix, the valid case reaches the recovery checks; zero revision, empty
segments, and nested-only revision all fail before restarting. Initial run: two
failed, two passed. Corrected run: four passed.

Also corrected the observer diagnostic: it now reports
`expected 1 interactive history card; observed N`, distinguishing absence from
ambiguity. The scoped locator from f484c635 remains unchanged.

Verification:

    .venv/bin/python -m pytest tests/phase2/test_wave1_qualification.py -k real_crash_producer -q
    .venv/bin/python -m pytest tests -q
    npm --prefix frontend test

Results: 1,234 Python passed, 2 skipped, 37 subtests passed; 155 frontend passed.
No quality bounds,
quality validator, identity policy, or host state changed. Round 6 is on 9fa8ee85
and does not contain this fix. Recovery remains unqualified until a subsequent
host-owned run executes the corrected probe.
