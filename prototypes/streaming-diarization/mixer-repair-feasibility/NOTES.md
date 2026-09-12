# Mixer repair feasibility — 2026-09-11

**Verdict:** restoring PCM level only is insufficient. Reusing terminal flush at a
canonical boundary violates the current timestamp authority. Do not promote either
shortcut into the product.

Structural question: which stage must change to undo the measured extra identity
without changing causal ownership or clock alignment?

Minimum primitives: source PCM level, endpoint/ASR span boundaries, identity
intervals within those spans, and capture-clock interval endpoints. They are
independent: level cannot reconstruct a different window; a sample count does not
reveal an unknown successor clock timestamp.

Invariants: unchanged policy values and QUALITY_BOUNDS; no future evidence; no
joining distinct voices; complete final audio; source frames accounted only after
consumption. Unknown: six-case WER after an endpoint change. No after scores are
claimed for an unimplemented behavioral change.

Falsifiers/experiments:
1. Real pinned encoder and current identity preparer; replay the retained Adam
   provider intervals through the birth with mixed PCM, then original source PCM.
   Restore mono windows separately. The mixed baseline must reproduce the prior
   .1954222813 score, or the probe is not authoritative.
2. Production mixer with six 0.5-second frames, a successor at 2.5005 seconds, and
   an early terminal-style flush at the 2.5-second canonical boundary. Compare
   samples with normal timestamp-sealed mixing. A changed committed prefix or
   invented gap rejects early flushing as an alignment-preserving fix.

Run from repository root:

```sh
.venv/bin/python prototypes/streaming-diarization/mixer-repair-feasibility/probe.py --out /tmp/moss-mixer-feasibility-new
.venv/bin/python prototypes/streaming-diarization/mixer-repair-feasibility/tail.py
```

The first command needs the installed identity manifest/ONNX only, not a decoder,
server, database or tunnel. It reuses actual decoder-derived intervals from the
prior differential, with placeholder text; reference speaker labels never enter
preparation. PCM remains in the external scratch directory. Retained results
contain counts/scores/timing only. The baseline and mono control exactly reproduce
the previously measured match scores, validating this narrowed loop.

| PCM / frozen identity windows | Best match at disputed turn | Identities after turn |
|---|---:|---:|
| Mixed / mixed windows | .1954222813044011 | 3 |
| Original / same mixed windows | .24016559066910273 | 3 |
| Original / mono windows | .5925375249553347 | 2 |

Fixed short-window raw/mixed cosine: .9823770645768589. WeSpeaker already subtracts
feature means, but quantization/frontend effects prevent perfect gain invariance.
That residual level effect is not enough to explain away the short-window failure:
restoring the original PCM throughout the causal reference history still births 3.

Early-flush control: same 48,008 output samples, but 7,024 values differ and 8
artificial zero samples appear at the canonical boundary. Normal mixing has none.
The future timestamp was not available when the early flush committed those bytes.
Stop already seals and drains the complete tail using the existing terminal rule.

The probe also exposed a separate real accounting failure: a bounded mixed output
chunk can consume only part of each stretched source frame, giving no whole-frame
watermarks. Calling account_through({}) raised after runtime admission. The product
fix simply waits to account until a whole source frame has been consumed. Its
regression fails before the fix and passes after, including the 8-sample remainder
and final flush. This does not change PCM, endpointing, identity or clock policy.
