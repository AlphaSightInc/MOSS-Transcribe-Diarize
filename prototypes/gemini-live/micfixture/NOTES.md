# R2-WP2 two-lane microphone fixture

Run from the WP2 worktree root:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/micfixture/build.py
```

With a local Gemini HTTPS stack on WP2 port 18720, pace one variant and score it:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/micfixture/run_http.py --base-url https://127.0.0.1:18720 --variant speakers--10 --out prototypes/gemini-live/micfixture/out/runs/speakers--10
```

Repeat for `headphones` and `speakers--20`. `score.py <snapshot.json> --variant
<name>` re-scores a saved public HTTP snapshot. `qmic.json` reports Local IDs,
C/D reference-token retention, and residual echoed A/B reference tokens. The
scorer assigns reference words evenly within each referenced turn (word
timestamps are unavailable), removes one-to-one C/D longest-common-subsequence
matches, then finds residual mic/system token matches within ±2 s. This timing
approximation is a scoring limitation, not measured word-level ground truth.

## Contract before implementation

- **Structural question:** Can two real mic voices retain separate Local identities while delayed system audio is rejected as echo?
- **Minimum primitives:** two aligned public PCM lanes; timed A/B and C/D reference turns; known echo delay, level, and intervals; the production WeSpeaker encoder; the live word and identity path. Each is needed to distinguish acoustic resemblance, time overlap, and real local speech.
- **Invariants:** system A/B cannot create Local IDs; C/D words remain on the mic lane; overlap alone never proves echo; exactly two local IDs must represent C/D; every scored variant has the same 300 s population.
- **Assumptions / unknowns:** references give turns, not word timestamps; the Gemini word output and the effect of synthetic reverb are unmeasured. The threshold is unmeasured until the sweep. Synthetic echo is not physical speaker leakage.
- **Hypothesis:** a system and mic voice embedding cosine threshold near .60, with ±400 ms word overlap, separates echoed system words from C/D words.
- **Falsifier:** the best threshold cannot reject ≥90% echo while retaining ≥90% of C/D reference words through the real HTTP API, or any A/B voice births a Local ID.
- **Tool decision:** `build.py` freezes the audio population. A throwaway sweep using the production encoder sets the threshold; a paced HTTP replay then measures the user gate. The sweep changes the threshold decision; failed HTTP gates force a policy change or a `PARKED` verdict.

System source: `common/corpus.py` `benchmark_5m:acquired_alphabet` (Ben=A, David=B). Mic source: `benchmark_5m:lex_keyu_jin` (Lex Fridman=C, Keyu Jin=D). Both have complete public references. Five C/D turns are retained with quiet spans between them; system turns interleave with and overlap the mic turns. Output WAVs are generated under `out/` and excluded from Git.

## Threshold sweep verdict (2026-09-29)

The production `_OnnxWeSpeakerEmbedder` on the built fixture gave echoed A/B cosine
0.851–0.964 (4/4 echo intervals across both speaker levels) and real C/D-to-A/B
cosine -0.069–0.048 (4/4 cross-voice pairs). At threshold **0.60**, 4/4
echo intervals classify as echo and 0/4 real-local pairs classify as echo.
Use .60 for the bounded voice check with the separate ±400 ms word-overlap
condition. These are interval embeddings, not Gemini-word outcomes or Q-MIC;
the paced HTTP gate remains unmeasured. `out/sweep.json` has every cosine.

## Text echo policy prototype verdict (2026-09-29)

Question: Does exact single-token text matching discard real local words that
share ordinary words with system speech? Hypothesis: apply voice+time first,
then reject adjacent two-token echo phrases; reject isolated text matches only
when the mic speaker has no usable voice vector. Falsifiers: either echo
variant drops under 90% or retains under 90% C/D words; E1 gains stray mic
words outside its three local speech windows. The throwaway prototype used
cached 300 s Gemini word results and the production WebRTC, acoustic, voice,
and embedding paths. Reference-token timing is interpolated within turns.

| Variant | Old local words | Proposed local words | Old echo rejected | Proposed echo rejected |
| --- | ---: | ---: | ---: | ---: |
| Headphones | 296/336 (88.1%) | 319/336 (94.9%) | n/a | n/a |
| Speakers −20 dB | 294/336 (87.5%) | 317/336 (94.3%) | 576/576 | 576/576 |
| Speakers −10 dB | 298/336 (88.7%) | 319/336 (94.9%) | 573/576 | 575/576 |

E1 public 302 s fixture: existing and proposed both leave 20 final mic words,
all within ±2 s of its three known local speech windows; **stray 0 → 0**.
No E1 increase. The direct probe does not establish real HTTP Stop behavior,
identity count, or rolling-window behavior. Its full results are retained in
`evidence/P66/wp2/echo-gate-ablation.json` and `e1-gate-ablation.json`.
The accepted policy is now in the live gate. This prototype consumed one new
E1 Gemini call ($0.015102); prior variant probes consumed $0.045006.
