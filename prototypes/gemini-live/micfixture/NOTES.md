# R2-WP2 two-lane microphone fixture

Run from the WP2 worktree root:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/micfixture/build.py
```

## Contract before implementation

- **Structural question:** Can two real mic voices retain separate Local identities while delayed system audio is rejected as echo?
- **Minimum primitives:** two aligned public PCM lanes; timed A/B and C/D reference turns; known echo delay, level, and intervals; the production WeSpeaker encoder; the live word and identity path. Each is needed to distinguish acoustic resemblance, time overlap, and real local speech.
- **Invariants:** system A/B cannot create Local IDs; C/D words remain on the mic lane; overlap alone never proves echo; exactly two local IDs must represent C/D; every scored variant has the same 300 s population.
- **Assumptions / unknowns:** references give turns, not word timestamps; the Gemini word output and the effect of synthetic reverb are unmeasured. The threshold is unmeasured until the sweep. Synthetic echo is not physical speaker leakage.
- **Hypothesis:** a system and mic voice embedding cosine threshold near .60, with ±400 ms word overlap, separates echoed system words from C/D words.
- **Falsifier:** the best threshold cannot reject ≥90% echo while retaining ≥90% of C/D reference words through the real HTTP API, or any A/B voice births a Local ID.
- **Tool decision:** `build.py` freezes the audio population. A throwaway sweep using the production encoder sets the threshold; a paced HTTP replay then measures the user gate. The sweep changes the threshold decision; failed HTTP gates force a policy change or a `PARKED` verdict.

System source: `common/corpus.py` `benchmark_5m:acquired_alphabet` (Ben=A, David=B). Mic source: `benchmark_5m:lex_keyu_jin` (Lex Fridman=C, Keyu Jin=D). Both have complete public references. System turns interleave with and overlap the mic turns. Output WAVs are generated under `out/` and excluded from Git.

## Threshold sweep verdict (2026-09-29)

The production `_OnnxWeSpeakerEmbedder` on the built fixture gave echoed A/B cosine
0.851–0.964 (4/4 echo intervals across both speaker levels) and real C/D-to-A/B
cosine -0.069–0.048 (4/4 cross-voice pairs). At threshold **0.60**, 4/4
echo intervals classify as echo and 0/4 real-local pairs classify as echo.
Use .60 for the bounded voice check with the separate ±400 ms word-overlap
condition. These are interval embeddings, not Gemini-word outcomes or Q-MIC;
the paced HTTP gate remains unmeasured. `out/sweep.json` has every cosine.
