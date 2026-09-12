# Mixer repair: two proposed shortcuts fail their necessary tests

**The corrected behavioral candidate is implemented; [six-case measurement](mixer-repair-differential-20260911.md) is complete and does not meet the full target.** Real-encoder measurement
shows original PCM on the existing short windows still creates speaker 3. A
terminal-style flush at canonical freeze changes already-committed audio under
supported timestamp drift. Only an independently reproduced whole-frame-accounting
bug is fixed. Identity policy and QUALITY_BOUNDS remain untouched.

## F1 — Original level does not restore the missing context

The prior .5925/.1954 comparison changed both PCM level AND endpoint windows.
The narrowed experiment restores original PCM for all embeddings and album evidence
while keeping the account path's actual intervals. It reproduces the mixed baseline
exactly, then gives:

| Path | Evidence seconds | Best existing match | Speakers after turn |
|---|---:|---:|---:|
| Mixed PCM, mixed windows | 1.22 | .1954222813 | 3 |
| Original PCM, same windows | 1.22 | .2401655907 | 3 |
| Original PCM, mono windows | 2.34 | .5925375250 | 2 |

Thus retaining raw source PCM solely for the existing identity preparation does
not fix this defect. Raw-level endpointing must also change, or identity needs a
separate windowing design. The latter is substantially larger and cannot simply
extend a window across an unknown speaker boundary. No such extension is proposed.

The current canonical boundaries also define ASR requests. Restoring mono boundaries
therefore changes decoder input windows even if ASR PCM gain stays the same. An
identical-WER promise cannot accompany this repair without measurement; more
complete pre-Stop coverage also necessarily can change immediate WER.

## F2 — A future clock boundary cannot be flushed early without a new contract

The production mixer uses the successor capture timestamp to seal each ordinary
frame. In a six-frame replay, nominal frame end 2.5 s and actual successor 2.5005 s
are both valid under the current contract. Early terminal-style flush at 2.5 s
produces 7,024 changed samples and an 8-sample invented gap, despite equal total
sample counts (48,008). Normal timestamp-sealed mixing has zero artificial samples.

A safe producer can provide an explicit observed frame-end timestamp. That would
let the mixer seal without waiting for a successor; the browser already knows its
audio-clock frame positions. This must be represented and validated in the lane
contract and sent by the acceptance client too, rather than guessed inside the
mixer. Stop already performs final sealing and full draining; it is not missing
that operation. The candidate now accepts observed frame-end timestamps from browser/replay producers. Older frames keep successor-based sealing.

## F3 — Independent bookkeeping defect fixed

With an 8,000-sample output cap and an 8,008-sample timestamp-stretched interval,
the first output chunk consumes neither whole source frame. The mixer nevertheless
called account_through with empty watermarks, raising LiveV2AccountingError after
the runtime had admitted the chunk. It now retains both source frames until the
8-sample remainder consumes them fully. No gain, interpolation, storage bound or
identity behavior changes. The regression tests sequence continuity and final flush.

## D1 — Corrected candidate to measure

Recommended next implementation: raw-level **endpointing and identity evidence**
for the source audio, with measured ASR regression checks, plus **explicit frame-end
timestamps** for early sealing. Preserve existing numeric policy and quality gates.
Do not implement embedding-only normalization or reuse terminal flush during capture.

The corrected raw-analysis prototype completed Adam before implementation: settled DER .097222, versus account .119889 and mono .091167; two speakers, two births, two admitted, no provisional-only identities. Final WER .133710 equals account; immediate .145009 differs by one error from account .143126.

The implementation carries bounded analysis PCM alongside existing decoder PCM until canonical commitment. A sole audible lane retains original level; two audible lanes retain their existing coherent mix. Analysis drives speech detection and identity; decoder, draft, rolling, recording and terminal audio keep existing PCM. Explicit observed frame ends remove the successor hold without terminal-style flush. Ingress rejects overlap with a previously sealed end, even after source frames are released. A skewed arrival test also fences the newest explicit frame start before treating a missing peer as a gap.
ASR retains its PCM gain and decoder; changed endpoint windows can nevertheless
change WER. Any difference will be reported explicitly, not called unchanged.
The six-case candidate restores reference speaker counts in all cases, but worsens Jamie/RTFL settled DER versus account before and changes immediate WER in Adam/Jamie. The operator subsequently approved round 11 host measurement under the existing 5% band; see the completed differential report.

## Evidence

[Prototype, commands and exact numerical results](../../prototypes/streaming-diarization/mixer-repair-feasibility/NOTES.md).
The original feasibility tests used only the local encoder. The corrected Adam prototype used the existing decoder tunnel; no host operations or 17861 access.
The six-case before results remain in the accepted account-path differential report.
Accounting-fix validation: 1,436 Python tests and 37 subtests passed, 2 existing
skips. All 16 mixer tests pass. No frontend changes in this checkpoint.
