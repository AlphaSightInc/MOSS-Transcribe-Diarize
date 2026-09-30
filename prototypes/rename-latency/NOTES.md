# Issue #15 — slow speaker rename after Stop

Question: where does a post-Stop rename spend its time, and what else waits for it?

Primitives: the durable display name (must be saved before the answer); the voiceprint
fingerprint (derived from the saved audio, needed only by future recognition); the
Account-wide identity lock (serializes bank writes with every Live publication).

Invariant: the name is durable when the request answers; the voiceprint vector and the
2 s floor are unchanged; a voiceprint is written only for the name current at commit, and
never after "no voiceprint" or a delete of the linked voiceprint.

Falsifier: a rename with `save_voiceprint=false` is also slow (then the fingerprint is not
the cause), or the time is ffmpeg decode rather than embedding (then decoding is the fix).

Run (worktree root, $0, public long60 audio tiled, rows split to <=5 s like live rows):
`PYTHONDONTWRITEBYTECODE=1 MOSS_TEST_REAL_SQLITE=1 <venv python> prototypes/rename-latency/measure.py --minutes 13.5 60 150`
Real paths: archive mp3 publish, SQLite store, `AccountSpeakerIdentity.name_speaker`,
`AlbumIdentityResolver.enrollment_observation`, pinned WeSpeaker ONNX, 3 interval workers.
Machine: Apple M3 Ultra. The ga0-rog-laptop (Ryzen 9 6900HS) is unmeasured; its journal has
no access log, so no production rename timings exist.

## Before (base 3d7b1742)

| meeting | speaker speech | rename, save voiceprint | ffmpeg | WeSpeaker | other meeting's rename / Live publication waited |
|---|---|---|---|---|---|
| 13.5 min | 9.9 min, 125 rows | 40.0 s, 38.1 s | 0.4 s | 39.5 s | 37.6 s / 39.5 s |
| 60 min | 35.2 min, 451 rows | 130.1 s, 129.4 s | 1.3 s | 128.8 s | 128.9 s |
| 150 min | 83.4 min, 1068 rows | 278.0 s | 3.4 s | 274.2 s | — |

Rename with `save_voiceprint=false`: 0.00–0.01 s. Every rename re-fingerprints (default is
save). Peak RSS on macOS grew to 5.1 GB (13.5 min) and 14.5 GB (60 min) — unmeasured on Linux.

Verdict: falsifier failed; the cause is the synchronous fingerprint (99% WeSpeaker, ~3.3–4 s
per minute of the speaker's speech) inside the request while holding the identity lock. Decode
is ≤ 1.3%. Nothing re-transcribes audio. Separate frontend effect: the rename bumps the
transcript version, and on a refined meeting `SummaryPane` then regenerates the Gemini summary
(blank until done; a second rename fails the first attempt with "the transcript changed").

## After (fingerprint after the answer, one at a time, outside the identity lock)

| meeting | rename answers in | background fingerprint | other meeting's rename / Live publication waited |
|---|---|---|---|
| 13.5 min | 0.01 s, 0.03 s | 37.6 s, 37.7 s | 0.0 s / 0.0 s |
| 60 min | 0.05 s, 0.10 s | 130.6 s, 130.4 s | 0.0 s / 0.0 s |
| 150 min | 0.29 s | 271.1 s | — / 0.0 s |

The CPU work is unchanged (same vector, same encoder); it no longer blocks the answer or the
identity lock. Fingerprints stay one at a time (as the lock made them before); a second rename
of the same speaker while one runs reuses it and the latest name is written.

Voiceprint outcome identical (one sample, latest name). Tests:
`tests/phase2/test_live_after_stop_voiceprints.py` (3 new, fail on base).

## Decision evidence only: bounded speech (not implemented)

`prototypes/rename-latency/cap.py --minutes 13.5` (2 speakers, one fixture): a vector from
~2 min of evenly spread speech has cosine 0.983 / 0.973 to today's all-speech vector; ~1 min
gives 0.983 / 0.941; the two speakers' full vectors are 0.080 apart; ADR-0009 match floor 0.46.
A 2 min cap would cut after-Stop fingerprint CPU 5–40x on long speakers, but it changes the
stored voiceprint and needs recognition measurement on the real corpora before adoption.
Note: `_unoverlapped_speaker_rows` merges touching rows, so a monologue becomes one long
interval (the 9.9 min speaker is 13 intervals); a likely but unmeasured cause of the GB RSS.
