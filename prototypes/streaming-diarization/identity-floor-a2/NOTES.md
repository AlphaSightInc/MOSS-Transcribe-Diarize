# A2: identity birth floor, evidence only

Question: does suppressing short-observation births reduce false splits at the cost of missing a briefly contributing real person?

Primitives: a source interval has a real speaker and PCM; an observation has one production-selected embedding; a canonical identity can be born, matched, or revised. Source identity cannot be inferred from the number of output IDs.

Invariants: within each scenario, exactly the same intervals, embeddings, ordering, transcript markers, 2 s album admission, 0.35 score, 0.10 margin, 60 s sweep and final sweep across floors 1/1.5/2 s. No production policy changes. Nine adopted clips remain a separate regression denominator. The marker transcript assumes correct within-span diarization; no decoder is called.

Unknown: actual AirPods performance, microphone channel causality, wall-clock correction latency. Hypothesis: a higher birth floor can suppress both false identities and real brief speakers. Falsifier of “fewer identities is better”: brief B has no distinct identity despite fewer false splits.

Tool: local pinned WeSpeaker ONNX embeds each source unit once; the existing production replay consumes identical cached vectors for all arms. Trace-only instrumentation records labels after commit and sweep. PCM is genuine existing corpus speech; controlled fixtures concatenate source intervals with 0.6 s gaps (no synthesized voice). No host or remote model calls.

Preselected cases: Lex intro fully voiced 1 s units from the peer's existing activity inventory; the same units with an initial contiguous 2 s Lex seed; genuine Bill Ackman at source 1 s for a 1 s or 1.5 s brief contribution, inserted after five Lex units (both unseeded and seeded variants); optional Bill return at source 10–12 s. Source intervals are selected before model scoring, never by desired match outcome. Floor arms never change observation lengths.

Metrics: every label is owned by the true speaker with greatest duration assigned to it (ties lowest truth ID). False splits = extra IDs owned by a person. Missed people = people owning no ID. Misassigned seconds are separate, so a false merge cannot masquerade as a detected person. Unnamed seconds include ALL truth speech, even units too short to embed. Report causal and final separately. Correction delay measures audio-time from unit end to the last transition into a correct identity (using final duration-majority ownership), provided it stays correct; unresolved units are censored, not zero. Initial correct assignments are excluded from correction delay. All subsequent label changes also retain their revision delay, including repairs of duplicate IDs belonging to the same person. This metric does not measure decoder, network or display delay. Full state retained in results.json.

Run (existing local assets only):

```sh
.venv/bin/python prototypes/streaming-diarization/identity-floor-a2/run.py --data-root /path/to/standing-bench/data --intro-wav /path/to/mono_javier_intro_50s/audio.wav
```

The user explicitly requested a retained, repeatable batch bench; it replaces the prototype skill's interactive TUI. Fresh embedding is default; `--reuse` replays available retained vectors; missing caches are freshly embedded locally. Verdict and measured results: `docs/audits/identity-floor-a2-bench-20260911.md`.
