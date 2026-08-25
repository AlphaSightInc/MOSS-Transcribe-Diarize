# M0a — replay reconstructors are field-complete (2026-08-25)

**Question.** Does the shipped replay client reconstruct exactly what the service
serialized, so every campaign metric is computed on the transcript the session actually
published?

**Answer: no, until this change.** Three fields were dropped on the way back in.

| Field | Owner | What the dropped value made a reader believe |
|---|---|---|
| `CanonicalCommit.revised_transcript` | `_commit_from_dict` | every replayed span read as never corrected — retrospective sweep results invisible to scoring |
| `LiveSnapshot.label_revision_version` | `_live_snapshot_from_dict` | every replayed session read as "settled, zero revisions" |
| `LiveServiceDescriptor.live_protocol` | `_descriptor_from_dict` | replayed descriptor reported default v2 capabilities regardless of what the service advertised |

The first two are the M0(a) targets named in the PRD; the third is the same defect class
in the same three-function seam and was found by making the round-trip check field-complete.

## Evidence

- `reproducer-before.json` / `reproducer-after.json` —
  `prototypes/live-file-roadmap-verification/verify_replay_roundtrip.py`, exit 1 → exit 0.
- `mutation-check.txt` — deleting each of the three restored lines individually makes
  `ReplayReconstructorRoundTripTest` fail (`CAUGHT` x3). The test is a real tripwire, not a
  restatement of the fix.
- `pytest-replay.txt` — `tests/test_live_service_replay.py` green.
- Full suite: `.venv/bin/python -m pytest tests/ -q` → 978 passed, 2 skipped, 386 subtests.

## Why the test is shaped this way

Equality after a JSON round-trip only bites when the fixture varies the field, so a new
defaulted field would sail through an equality-only test exactly as these three did.
`_assert_varies_from_defaults` walks the dataclass tree and fails on any defaulted field
still holding its default, which forces every new field into the fixture and therefore into
the equality check. The nine fields the runtime pins to one legal value in `__post_init__`
(schema versions, protocol identity, sample rate, `feature_enabled`) are listed as
`_PINNED_FIELDS`: a fixture cannot vary them, and a reconstructor that read the wrong one
would raise rather than mis-measure.

## Consequence for prior evidence

Unchanged from the campaign's opening assessment: revision fields in replay traces recorded
before this fix are untrustworthy (they read as zero/None regardless of truth);
`identity_finalized` events are unaffected because they never went through these
reconstructors. The M0(d) re-acquisition is what re-establishes trustworthy snapshots — in
particular the 5-minute case must now show the 2 label revisions its `identity_finalized`
event reports.
