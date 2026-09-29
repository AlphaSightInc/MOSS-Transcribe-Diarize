# Stop orphan prototype — public E1

Structural question: can a 0.2 s canonical stray be mapped to a same-lane established
speaker using the production pinned WeSpeaker encoder and the settled cosine threshold
of .46? If its vector is unavailable or below threshold, the Stop policy leaves its
words and timing intact but changes its label to Speaker TBD.

Primitives: final committed row durations, lane, saved-audio row embedding, established
speaker centroid. Invariants: only IDs below 2 s total are candidates; manual names and
cleanup-ON are untouched; no row text or time changes. Unknown: short-span embeddings
may be unstable. Falsifier: the E1 0.2 s span cannot embed, or its best cosine is below
.46; then the measured result supports abstention, not a claimed absorption.

Run from the WP1 worktree root with the shared Python:

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/streaming-diarization/orphan-stop/probe_e1.py --snapshot /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r2-wp2/prototypes/gemini-live/micfixture/out/runs/e1-r3/stop_snapshot.json --audio /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/system.wav --model /Users/gao/.local/share/moss-transcribe-diarize/live/voxceleb_resnet152_LM.onnx
```

This is a local encoder probe on public audio, with no Gemini send. It uses three
up-to-2 s established samples per speaker as centroid witnesses. These are not the
unavailable in-meeting centroids from the saved E1 session, so the cosine is a viability
probe, not a replay of the product's exact matching decision.

## Result and verdict (2026-09-29)

The saved E1 final surface has system speech totals of 187.3 s, 27.5 s, 0.2 s,
and 44.9 s for speakers 0001–0004 respectively. The production encoder returned
a vector for the 0.2 s row. Its cosines to witness centroids for 0001, 0002, and
0004 were .0665, .0552, and .3083. All are below .46. The measured E1 choice is
**Speaker TBD**, preserving the 0.2 s word and removing the orphan ID. A different
meeting row may exceed .46 and be absorbed, which needs a runtime unit test.

This result does not establish the exact E1 product outcome because the live centroids
were not retained in that snapshot. It falsifies any assumption that a short-row
fingerprint must find a valid speaker match. The policy must abstain when it does not.
