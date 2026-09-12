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
consumption. Unknown: six-case WER after an endpoint change. Six-case after scoring is required before claiming the target met.

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


Corrected prototypes and custody checks:

```sh
.venv/bin/python prototypes/streaming-diarization/mixer-repair-feasibility/observed_end.py
.venv/bin/python prototypes/streaming-diarization/mixer-repair-feasibility/input_proof.py
```

The observed-end prototype has two audible lanes and an 8-sample clock stretch:
zero changed output bytes, 40,008 samples admitted by the fifth frame instead of
32,000. Its product regression additionally interleaves lane arrival and draining.
The six-case input proof finds byte-exact source analysis and byte-exact prior
headroom decoder PCM; all received samples are admitted before Stop. Largest
analysis frame is 16,000 bytes. The coordinator regression fills its existing
8,000-sample admission bound, rejects an extra frame without growing analysis
retention, then releases/reuses capacity on commitment. No raw analysis tape.

`raw-analysis-adam.json` retains the corrected real-decoder prototype: settled
DER .097222, two speakers vs account .119889/three; mono .091167/two. Final WER
.133710 equals account; immediate .145009 vs .143126 differs by one error.
The live six-case after measurement is retained separately as it completes.


Completed six-case result: `differential-results.json`. Settled DER macro improves
.182603→.162036 (mono .156766), all six emitted counts equal reference. Per-case
parity is NOT established: Jamie and RTFL DER worsen versus account before;
Adam/Jamie immediate WER add two/one errors. Hold behavioral candidate from cutover.
Full findings: `docs/audits/mixer-repair-differential-20260911.md`.

To reproduce on an already running **own** stack (fresh output directory required):

```sh
.venv/bin/python prototypes/streaming-diarization/mixer-repair-feasibility/measure_account.py --cert /tmp/own-stack/cert.pem --out /tmp/moss-mixer-replay-new
```

Start that stack with the existing account-path-differential/run_stack.py recipe,
its own state directory and port 17862. Do not restart or access the operator's
17861 database. This replay invokes the decoder; do not confuse it with the
network-free byte/encoder probes above. Raw captures and a mode-0600 cookie stay
in the scratch output; results are written after each case.
