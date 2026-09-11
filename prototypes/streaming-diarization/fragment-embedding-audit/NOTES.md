# Short-fragment WeSpeaker measurement

**Real embeddings reproduce a split at 1 second; longer cuts are much more stable.**
No policy or production change. This establishes the mechanism for the corpus voice,
not the cause of the operator's particular microphone recording.

## Contract and method

Question: does shortening the same voice's evidence cross the unchanged 0.35 match
floor while 10-second evidence remains above it? Minimum primitives: fixed audio
interval, production embedding, cosine score, chronological reference state. Duration
cannot replace measured similarity; pairwise similarity cannot replace a sequential
birth decision. Invariants: same source/model, all full fixed cuts, unchanged 2.0 s
album / 1.0 s birth / 0.35 score / 0.1 margin. Falsifier: short speech cuts consistently
clear 0.35, or sequential replay never splits. Tools: pinned production ONNX adapter
tests acoustics; unchanged provider/preparer/album tests consequences. No decoder,
reference labels, host operations, or remote inference. Measurement only; no fix phase.

Source: `evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav`,
50 seconds, mono PCM16, 16 kHz. Corpus reference identifies one speaker, Lex Fridman
(introducing Javier Milei). Reference is not read by either script. Cuts start at zero,
are nonoverlapping within each group, and have lengths 1, 1.5, 2 and 10 seconds.
All full cuts are embedded: 50/33/25/5; only the 1.5 s group omits a 0.5 s tail.
Groups share source audio; pairs share observations, so these are descriptive fractions,
not independent trials or population-level estimates. No alternate offsets searched.

`WeSpeakerResNet152LmAdapter` loads the local pinned 75 MB ONNX; normal preflight
verifies its existing asset pin. Descriptor and path retained in results.json.
ONNX Runtime 1.23.2, CPU. Each cut is one embedding interval, using the production
frontend and normalization. Cosine uses the production [0,1] clamp; zeros can include
negative raw cosine. Pair counts exclude self and count unordered pairs once.

Sequential replay supplies these measured vectors to the unchanged production
provider, preparer and album. Each cut is explicitly one local-speaker interval,
with 0.6 s gaps on the simulated timeline. No silence is inserted into embedding
intervals; isolated cuts in a pause-separated WAV would supply the same samples.
This is controlled segmentation, not a transcription/endpoint/capture replay, and
not proof of microphone acoustic equivalence. No retrospective sweep is included;
reported counts are causal identity counts, not final post-sweep counts. Ten-second
windows are an acoustic control exceeding the live span cap, not a deployed mode.

## F1 — All fixed cuts (natural pauses included)

| Cut | Windows | Pairs | Min | P05 | Median | P95 | Max | Below 0.35 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 s | 50 | 1,225 | 0.000 | 0.000 | 0.399 | 0.574 | 0.889 | 474/1,225 = 38.69% |
| 1.5 s | 33 | 528 | 0.000 | 0.042 | 0.524 | 0.668 | 0.747 | 111/528 = 21.02% |
| 2 s | 25 | 300 | 0.000 | 0.015 | 0.585 | 0.711 | 0.767 | 25/300 = 8.33% |
| 10 s | 5 | 10 | 0.779 | 0.805 | 0.860 | 0.898 | 0.900 | 0/10 = 0% |

These are source-window failures, NOT all speech-only failures. In particular the
first second contains only 0.36 seconds classified as speech. Treating that entire
second as a decoded speech interval overstates real birth eligibility if a decoder
would exclude its silence. Do not use the six unfiltered 1 s identities as a faithful
live replay claim.

## F2 — Speech-activity sensitivity check

After observing low scores, checked silence as a competing explanation, without
re-embedding or changing the primary selection. WebRTC VAD 2.0.14, mode 1, 10 ms
frames, scans the original source continuously. Settings match the available local
manifest; host configuration not inspected. Keep cuts for which EVERY frame is
classified as speech. VAD has hangover and errors: this is speech-activity evidence,
not human-verified pure speech. All raw results remain retained, including exclusions.

| Cut | Retained windows | Pairs | Min | P05 | Median | P95 | Max | Below 0.35 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 s | 39 | 741 | 0.169 | 0.298 | 0.465 | 0.586 | 0.696 | 91/741 = 12.28% |
| 1.5 s | 23 | 253 | 0.267 | 0.413 | 0.583 | 0.690 | 0.747 | 3/253 = 1.19% |
| 2 s | 16 | 120 | 0.481 | 0.528 | 0.644 | 0.729 | 0.767 | 0/120 = 0% |

No 10 s window is entirely VAD-positive. The original five controls contain
8.85/8.94/9.38/9.71/9.95 VAD-positive seconds and still all match comfortably.
The 1 s effect therefore survives removing all cuts with detected non-speech;
silence alone does not explain the short-duration failures in this experiment.

## F3 — Births and the 0.1 margin

Margin is a difference between best and competing scores, not a pairwise threshold.
Treating two examples of the same voice as two true identities would manufacture a
margin problem. Instead, evaluate the actual competing references created by the
chronological production matcher. With one existing reference, runner-up is zero.

| Input | Causal identities | Margin refusals / match-floor-eligible turns | Margin min / median / max, all non-cold turns |
|---|---:|---:|---|
| All cuts, 1 s | 6 | 9/44 | 0.000 / 0.189 / 0.611 |
| All cuts, 1.5 s | 4 | 8/29 | 0.004 / 0.183 / 0.592 |
| All cuts, 2 s | 2 | 0/23 | 0.028 / 0.723 / 0.814 |
| All cuts, 10 s | 1 | 0/4 | 0.887 / 0.892 / 0.903 |
| VAD-positive cuts, 1 s | 2 | 6/37 | 0.002 / 0.299 / 0.611 |
| VAD-positive cuts, 1.5 s | 1 | 0/22 | 0.521 / 0.645 / 0.747 |
| VAD-positive cuts, 2 s | 1 | 0/15 | 0.679 / 0.755 / 0.825 |

Decisive speech-filtered trace: source [1,2) s births speaker-0001; its 1-second
reference remains provisional. Source [25,26) s scores **0.289004** against it and
births speaker-0002. Subsequent similar competing references produce six abstentions
at the unchanged margin. Both identities finish provisional, zero admitted exemplars.
The same filtered 1.5 s sequence stays single despite three below-floor PAIRS:
not every low-scoring pair is encountered against the chronological reference.
Pair failure fraction is therefore not a birth probability.

## F4 — Decision boundary and correction

This demonstrates real same-voice acoustic variation sufficient for within-session
births under short controlled intervals. It supports the operator's proposed
mechanism, but does not establish their three identities end to end: their audio,
decoder-local intervals and live assignment history remain unmeasured. The corpus
is a single recording/channel; phonetic content and boundaries vary with cut length.
This experiment does not calibrate an alternative threshold or justify changing one.

Provisional-only identities are NOT permanently trapped. Later matching >=2 s
observations can admit exemplars; once both have admitted banks they may meet the
existing merge rule. Sweeps can also relabel historical units without merging IDs.
Persistent sub-2 s evidence lacks accumulation and merge eligibility, but 'no path
back even with more evidence later' overstates that limitation.

Keep policy unchanged. Present these distributions and the observed 1 s split to
the operator; choosing any policy change requires a separate measured decision.

## Reproduce / retained evidence

From worktree root:

```sh
.venv/bin/python prototypes/streaming-diarization/fragment-embedding-audit/probe.py --model /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx
.venv/bin/python prototypes/streaming-diarization/fragment-embedding-audit/speech_check.py
```

`vectors-*.json`: all 113 fresh embeddings with source intervals, written after each
observation. `pairs-*.json`: all 2,063 within-group pair scores. `results.json`:
descriptor, quantiles (including quartiles), denominators and complete sequential
scores/assignments. `speech-results.json`: VAD coverage for every cut, selected-pair
scores and filtered sequential traces. No corpus audio/model duplicated into git.
