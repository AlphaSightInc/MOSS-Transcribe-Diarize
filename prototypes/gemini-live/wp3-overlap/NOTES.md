# WP3 completed Live enrollment interval prototype

Question: how much of a named speaker's saved row time remains after every other speaker's rows, on either lane, is excluded?

Primitives: half-open time intervals; canonical speaker ID; union of other-speaker intervals. Each is required to avoid counting another voice as sole evidence.

Invariant: selected intervals are within named rows and disjoint from all other-speaker rows. Their union duration determines the existing 2 s enrollment floor.

Assumptions: transcript row times align with the saved mixed recording; this prototype does not measure acoustic separation or diarization quality.

Falsifier: a crossing or contained other-speaker row leaves any overlapping time selected, or duplicate named rows inflate eligible duration.

Tool decision: deterministic interval script prints the full selected state; a failure changes the subtraction algorithm before product code. Production integration test then checks the saved-audio path.

Run: `PYTHONDONTWRITEBYTECODE=1 python prototypes/gemini-live/wp3-overlap/check.py`

Verdict: 3/3 deterministic cases passed. One cross-lane overlap left 3.0 of 4.0 s eligible; a contained overlap left 1.0 of 2.0 s and must refuse; duplicate owned rows with two competing spans left 1.5 s after union. Product checks are in `tests/phase2/test_live_after_stop_voiceprints.py`; the throwaway script can be removed. Saved mixed-audio timing and acoustic identity remain to be measured in HTTP smoke.
