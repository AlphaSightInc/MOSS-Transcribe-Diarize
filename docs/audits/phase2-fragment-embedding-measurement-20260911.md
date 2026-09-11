# Fresh short-fragment embedding experiment

Pinned local WeSpeaker measurement completed; no decoder, host operations or policy
changes. Full reproducible report and raw evidence:
[bench NOTES](../../prototypes/streaming-diarization/fragment-embedding-audit/NOTES.md).

- F1: Fixed 1/1.5/2/10 s cuts: below-0.35 pair fractions 38.69/21.02/8.33/0%.
  Natural silence inflates short-window failures; these are not pure speech results.
- F2: Restricting to entirely WebRTC-VAD-positive cuts: 91/741 (12.28%) at 1 s,
  3/253 (1.19%) at 1.5 s, 0/120 at 2 s. Ten-second controls all exceed 0.779.
- F3: Unchanged sequential matcher on filtered 1 s embeddings creates two IDs;
  second birth at source [25,26) scores 0.289004 against the first provisional
  reference. Six subsequent margin abstentions. Filtered 1.5/2 s stay single.
- F4: Real corpus mechanism reproduced, operator's microphone cause not proven.
  Provisional identities can later admit >=2 s evidence and become mergeable;
  no accumulation of short fragments does not mean permanent irrecoverability.

113 real embeddings; all 2,063 unfiltered pair scores retained. Reference labels are
not inputs. Controlled single-local-speaker segmentation, no decoder or endpoint
replay; 10 s windows are an acoustic control beyond the live span cap. Policy intact.
