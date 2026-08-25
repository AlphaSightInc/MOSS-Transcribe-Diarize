# Live/file roadmap verification

## Question

Does Claude's apparent terminal identity-revision loss occur inside the live runtime, or
only while the HTTP replay client reconstructs the server snapshot?

## One-command reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python prototypes/live-file-roadmap-verification/verify_replay_roundtrip.py
```

The command deliberately exits 1 while the defect exists.

## Verdict — 2026-08-24

**Replay-adapter defect, not runtime finalization defect.** A server-shaped snapshot carrying
`label_revision_version=7` and a non-null `revised_transcript` reconstructs as version `0`
and `None`. `_live_snapshot_from_dict` and `_commit_from_dict` omit those fields. This exactly
explains the baseline trace contradiction: its `identity_finalized` event reports one applied
revision, while its replay-serialized terminal snapshot reports none.

The fix belongs in `moss_transcribe_diarize/live_service_replay.py` plus an HTTP round-trip
regression. Do not tune the identity algorithm from replay traces until this measurement seam
is repaired and the corpus is re-acquired.

## Second-pass cross-verification — 2026-08-24 (Claude)

**Replay-adapter verdict independently confirmed.** Server serialization is
`dataclasses.asdict` (`app/live_service_runtime.py:81,230,253`) and therefore field-complete;
only the two hand-written client reconstructors drop the revision fields. New blast-radius
fact: the 5-minute keyu replay's `identity_finalized` event reports cumulative
`identity_revision_version: 2` — the 60-second cadence sweep fired and applied two label
revisions mid-session at 300 s, so "sweep inertness" is a 60-second-session fact only.

**One-second degradation spot check (independent implementation, no lane_* reuse).**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/live-file-roadmap-verification/spotcheck_1s_vs_25s_spans.py
```

Question: does 1.0 s isolated-span tiling degrade WER vs 2.5 s tiling in the direction and
per-case magnitude the multiview prototype measured? Verdict: **yes** — on lex_bill_ackman
0–30 s, 2.5 s tiling WER `.2264` (1 span discarded-as-empty) vs 1.0 s tiling `.2925`
(0 empty), ratio 1.29×, matching the multiview prototype's Bill ratio (`.261→.330` = 1.26×);
the prototype's larger trio ratio (1.88×) is driven by Milei (3.1×). Incidental observation:
the 1.0 s tiling recovered the words the 2.5 s arm's strict parser discarded at [5.0,7.5] s,
but with heavy fragmentation errors — consistent with "malformed span syntax is a hard-cap
artifact", not a contradiction of it.
