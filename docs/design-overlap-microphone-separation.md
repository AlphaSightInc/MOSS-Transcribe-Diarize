# Recovering overlapping microphone speech

**Status:** design checkpoint; no implementation selected or authorized by this note.

## Conclusion

The capture client already supplies the only lossless separator available to this system: aligned
`system` and `microphone` lanes. The live path destroys that separation when it adds both lanes into
one mono waveform. A decoder that receives only that sum cannot reliably recover a microphone voice
roughly 30.5 dB below the tab voice.

The smallest sufficient repair is to keep the owner mono recording unchanged while making transcript
production lane-local from capture through terminal finalization:

1. retain the two aligned source lanes beside each mixed frame;
2. decode each non-silent lane in an **independent** ASR request over the same time interval;
3. preserve each result's source lane and original timestamps, including cross-lane overlap;
4. assign canonical identities from the PCM lane that produced each word; and
5. prevent rolling or terminal mono decoding from replacing the lane-derived transcript.

This is a design hypothesis until a production-path prototype recovers the known microphone words in
the measured quiet-microphone overlap case. Identity counts are excluded from the success decision.

## Structural contract

### Question

What information must survive the live path so two simultaneous source-lane voices can both become
committed words with distinct canonical speakers?

### Minimum primitives

| Primitive | Responsibility | Why it cannot be removed |
| --- | --- | --- |
| **Aligned lane PCM** | The system and microphone samples for the same meeting interval. | These are the last point where the voices are physically separated. |
| **Lane-local decode** | One ASR inference context for one source lane. | Joining lanes by addition or concatenation preserves a level relationship inside one model context. |
| **Source transcript segment** | Text, source lane, local speaker, and original start/end samples. | Text without source loses the evidence needed for overlap and identity ownership. |
| **Canonical identity mapping** | Maps each source-local speaker to a meeting speaker using that source's PCM. | ASR-local labels are not stable identities. |
| **Transcript authority** | Carries lane-derived segments through rolling and terminal publication. | A later mono revision can otherwise erase recovered microphone words. |

### Invariants

- The successful overlap output contains words from both known voices, attributed to two distinct
  canonical speakers.
- The non-overlapping tab-then-microphone path remains successful at microphone gain `0.03`.
- Parity overlap remains successful.
- A lane whose frame contract says `silent` produces no words, speaker evidence, or identity.
- The mixed PCM bytes remain the owner recording and keep the existing minus-6-decibel sum and limiter.
- Existing `QUALITY_BOUNDS`, identity policy, acoustic echo cancellation defaults, readiness
  thresholds, queue ownership, and file-mode behavior remain unchanged.
- `identities_born_count` is telemetry only. It never establishes word recovery.

### Assumptions and unknowns

- **Established:** parity overlap produces both voices; quiet-microphone overlap produces only the tab
  voice; gain-only raises the noise floor; the lane-preserving branch changed identity count without
  changing committed text.
- **Established from code:** the base canonical decoder receives the mono sum; rolling and terminal
  decoders also receive mixed PCM; a terminal revision replaces the visible surface.
- **Established from the rejected branch:** `7e5a2ad2` retained lane PCM but concatenated system bytes
  followed by microphone bytes into one longer ASR request. It did not perform independent lane
  inference.
- **Unknown:** whether independent live-span requests recover the measured `0.03` microphone words at
  every endpoint boundary. Historical whole-clip lane decoding passed content gates, while the older
  fragmented live prototype did not.
- **Unknown:** whether two serial requests fit the current stop and queue budgets on the target stack.
  This must be measured; it must not be answered by weakening the lifecycle checks.
- **Unknown:** whether every terminal lane has enough complete retained PCM for the existing whole-
  meeting finalizer. A missing lane tape must leave the already-committed lane transcript intact.

### Falsifier

Reject this design if two independent production ASR requests over the measured aligned overlap still
produce a committed transcript without the known microphone words, or if the final surface loses
words that were present before terminal finalization. Also reject it if the non-overlap, parity,
lifecycle, reshare, or frontend gates regress.

## Why the mono sum loses the microphone

For aligned source samples `s[n]` and `m[n]`, the mixer publishes:

```text
y[n] = 0.501187 * s[n] + 0.501187 * m[n]
```

At microphone scale `0.03`, its contribution is `20 log10(0.03) = -30.46 dB` relative to the tab
before the common headroom factor. The sum is many-to-one: many pairs of source signals produce the
same `y[n]`. Once only `y[n]` remains, neither diarization nor identity matching can reconstruct words
the ASR did not emit.

Pre-sum gain does not add separation. It raises microphone speech, room noise, and acoustic bleed
together. The rejected gain branch therefore changed level while preserving the ambiguity.

The rejected lane-preserving branch also left both lanes inside one acoustic inference context. It
constructed one waveform as `system_pcm + microphone_pcm`, where `+` was byte concatenation, decoded
that longer waveform once, then assigned the first and second halves back to lanes. The model still
saw the loud and quiet inputs together. Its lane-specific identity embeddings explain why an identity
could be born even when no microphone text was recovered, including from digital silence.

## Required transcript path

### D1. Preserve source PCM beside the owner mix

`LiveCompatibilityMixer` continues to calculate and publish the current mono `AudioFrame.pcm` for
endpointing, recording, replay, and compatibility. The same staged interval also carries exact PCM16
for `system` and `microphone`, plus whether each lane was entirely marked `silent` by the input frame
contract. No gain, normalization, denoising, or new energy threshold is introduced.

### D2. Decode lanes independently

One canonical arbiter item still owns one frozen span. Inside that item, each non-silent lane is sent
to `BoundedWavInference.transcribe_pcm` as a separate request with the original span sample count and
clock. Requests remain serial so the existing single-worker fairness rule is not bypassed.

An all-`silent` lane is skipped from ASR and identity. A non-silent lane that returns no parsed words
contributes nothing; nonzero PCM alone never creates transcript content.

This differs materially from `7e5a2ad2`: no request contains both lanes, either summed or placed one
after the other.

### D3. Keep simultaneous source segments

Each parsed segment retains `source_lane`, local speaker, and its original time. Local speaker labels
are namespaced by source before identity preparation. Stable ordering is by start sample, lane, end
sample, then local label; ordering does not clip either segment's extent.

Overlap normalization applies **within one source lane** to duplicate window decodes. It must not clip
or drop segments merely because the other source lane speaks over the same samples. The session's
text-revision validation therefore needs source-aware overlap: overlapping intervals are valid only
when their source lanes differ.

### D4. Bind identity to recovered words

Identity preparation receives only speakers present in parsed lane transcripts and embeds each speaker
from its producing lane PCM. A silent or wordless lane has no speaker unit. Existing birth, admission,
match, and margin policy values remain exactly as deployed.

### D5. Preserve lane authority through finalization

The current rolling and terminal listeners decode `CompleteMixedTape`; terminal publication replaces
the full visible transcript. Leaving them mono would reintroduce the information loss after a correct
canonical span decode.

Lane sessions therefore retain complete aligned source tapes through the existing terminal lifetime.
Rolling and terminal transcript producers use the same independent lane decode and source-aware merge
as canonical spans. The mixed tape remains the owner recording and lifecycle/accounting authority.
If lane refinement cannot answer, it publishes no proposal and the already-committed lane-derived
surface remains visible, matching the existing refinement failure rule.

Legacy mono sessions continue through the current mono rolling and terminal path.

## Prototype and implementation order

### P1. Production-path falsifier

Extend the existing lane bench rather than create a second framework. One command must print the full
state for four fixed cases:

1. parity overlap;
2. quiet-microphone overlap at `0.03`;
3. non-overlapping tab then microphone; and
4. tab speech with a microphone lane marked `silent` and containing digital zeros.

Use two distinct, known voice transcripts. Run the production decoder independently per active lane,
merge on the meeting clock, then exercise the real identity preparation and `LiveSession` publication
path. Score the committed/effective transcript text. Do not use identity count as a gate.

The prototype passes only if both known word sets survive overlap under distinct canonical speakers,
the non-overlap and parity cases remain correct, and the silent lane contributes neither words nor a
speaker. If quiet microphone words are still absent, stop: this seam is falsified and a measured
speech-enhancement or reference-conditioned separator would be a different design.

### P2. Minimal production change after P1 passes

1. Add aligned lane PCM and the explicit all-silent fact to `AudioFrame`.
2. Retain source lanes by meeting sample range in `LiveCoordinator` and the complete-tape path.
3. Add one lane-local decoder/merge interface shared by canonical, rolling, and terminal producers.
4. Prepare identity from parsed source segments and their owning PCM.
5. Admit source-aware overlap in text revisions while retaining within-lane normalization.
6. Keep all legacy mono calls on their current path.

No blind source-separation model, automatic gain control, noise gate, new readiness rule, or feature
flag is part of this candidate.

## Verification decisions

| Check | Failure detected | Action if it fails |
| --- | --- | --- |
| Quiet-microphone overlap text oracle | The target defect remains despite lane-local inference. | Reject the implementation; do not infer success from speakers or identity counts. |
| Parity overlap text oracle | Lane merge or identity loses a case already proven. | Fix source merge/identity before any live run. |
| Non-overlap text oracle and `verify_demo_lanes.py` | The demo's working alternation path regressed. | Reject the candidate. |
| Silent-lane text oracle | PCM presence creates words or an identity without speech. | Fix active-lane admission; do not change identity thresholds. |
| `stress_lifecycle.py` | Extra inference violates stop, restart, concurrency, or reattach behavior. | Fix scheduling/retention or reject the candidate. |
| `stress_reshare.py` | Lane state fails across reshare/device epochs. | Fix lane retention lifecycle or reject the candidate. |
| Phase 2 suite | Server/session/publication contracts regressed. | Fix the implementation; only the known `decode_failed` failure remains exempt. |
| Frontend `npm test` | The unchanged capture contract was accidentally broken. | Fix the regression. |

The three end-to-end scripts were added after base `628341fa`; the implementation branch must carry
their existing versions unchanged before candidate verification. Evaluator expectations are evidence,
not implementation knobs.

## Tool decision

- Reading the two rejected diffs locates what each attempt actually changed and prevents relabeling
  identity movement as text recovery.
- Tracing canonical, rolling, terminal, and session publication locates every point that can discard or
  replace lane-derived words.
- The lane bench is necessary because independent-request recovery and latency are unmeasured on the
  exact new case. A passing synthetic stub cannot answer either question.
- The live provider is used only after the local production-path prototype passes. Repeating the
  supplied baseline, gain, concatenation, or identity-count measurements would not change this design.
