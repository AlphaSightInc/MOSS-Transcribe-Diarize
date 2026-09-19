# Round 2 implementation and qualification

**NOT production-ready.** The candidate improves scheduling, File speaker attribution, storage scaling and saved-result trust. It still fails the required brief-participant and ordinary same-stream interruption behavior. Do not promote honest uncertainty or successful capacity as recognition success.

## Implemented

- **F1:** Two Live recordings; at most two decoder calls and one background call. Live priority over File/URL/finalization. A third actual recording is refused before durable creation. A stopped, raw-closed meeting no longer consumes a recording slot during background settlement. Raw drain still does; owner cleanup and background limits remain intact.
- **F2:** File speaker rematching reuses per-passage vectors before mixed decoder labels are averaged. Existing thresholds/encoder unchanged. Retained30-minute comparison cut confused time92.01→45.63s; fresh30-minute validation below confirms similar behavior.
- **F3:** Disk-backed complete audio, streaming final WAV, explicit storage failures, checkpoint-prefix evidence reconstruction, cached committed parsing and whole-range terminal authority. File/URL has no200-minute duration test; transfer/storage bounds remain finite. Checkpoints are transient job work, not cross-process File resumption.
- **F4:** Last-reader cleanup; explicit final unknown; separate uncertain passage targets; settled exact-passage correction to existing/new recording-local people; durable reopen/export; no implicit voiceprint enrollment.

## Measured

The full short bundle ran on `1fa1c8b4`:2004Python tests+37subtests passed,5skipped;285frontend tests. Final frontend integration passed288tests/typecheck/build. The later Stop-slot repair passed137relevant backend tests. Corrected rename/export oracle controls passed96tests.

Paired30-minute Live on `203b7f04`:

|Metric|Monologue|Panel|
|---|---:|---:|
|First API text|1.539s|2.043s|
|Pre-Stop processing-frontier lag p95|2.729s|2.673s|
|Stop-to-final|146.524s|185.418s|
|Ordered word error|10.20%|7.11%|
|Source-turn speaker error|0.69%|6.96%|
|First→last-third median lag|1.155→1.233s|1.303→1.512s|

Both accounted for all28,800,000samples and reopened completed; final text tails1799.94/1799.92s.2002decoder calls, peak1 in this trial, no detected foreign load. App resident memory~647MBinitial/~1050MBcapture/~1180MBsettlement peak/~1051MBend. Repeated sources test load, not acoustic diversity. Panel correct attribution:Ben97.40%,David84.07%,**Jamie0% across42.21reference seconds**. The monologue word error also exceeds the retained9.5074% final-word comparator.

Five-minute mixed workload:240/300s Live plus150s File and URL each; all completed. Processing lag p952.483/2.180s; Stop10.401/16.767s. File/URL completed~18.29s after acceptance.306calls, peak2, no detected foreign load.

Fresh File measurements:3-minute WAV/MP3/M4A~18.2s, word error12.63/12.83/12.42%, speaker error9.39/10.50/10.51%. Six-minute WAV34.285s, word error10.69%, speaker error10.13%. Fresh30-minute WAV on `be2dd06d` completed174.785s,464segments, tail1799.85s, word error10.77% on4725words, speaker error10.32%; Bill91.35%,Keyu87.87%,Lex89.29%. All3people represented;24.75s explicitly unknown. Five exports/reopen/audio download passed. Raw four-speaker count includes unknown, not a fourth person.

Speaker metrics use coarse source-time turns with no collar/offset fitting. They are comparative evidence, not fine acoustic DER or held-out population estimates. Internal frontier lag is not word-on-screen delay. The short browser fixture measured3.33s Start→first visible text; sustained visible-word latency remains unmeasured.

201-minute deterministic controls prove full File tail through new-app reopen, bounded tape lifecycle and repaired publication scaling.5/30/201-minute feed cost0.064/0.381/3.105s; traced Python peaks0.684/1.227/4.420MB. Tuple append still copies; arbitrary-length strict linearity is unproved. Actual built saved-desktop UI rendered4824passages/2.03MB at201represented minutes:tail visible1.258s, search71.27ms. No200-minute acoustic run or continuous-live-rendering qualification.

## Remaining blockers / scope

- **R1:** Brief participant not identified. Repeated-identical-utterance pooling was falsified by independent utterances. Terminal-only novel birth remains provisional below the unchanged admission floor;0/4false-birth controls do not establish population safety.
- **R2:** Same-stream brief interruption omitted by decoder in all−3/0/+3dB mixtures. Generic overlap prompt recovered0/2. Sequential controls recognized both. Downstream overlap preservation alone cannot restore absent words.
- **R3:** Existing synthetic dual-lane word bars and identity-gap case still fail. Gain0.03(−30.46dB) is adversarial injected input, not physical microphone evidence. Browser true-hidden cases remained untestable; summary provider skipped; physical microphone/echo testing deferred.

Empty rolling recognition disables further rolling attempts; deterministic Stop/base/terminal preservation passed. Retry benefit and hallucination cost remain acoustically unmeasured, so no retry policy was introduced. Early final decoding remains optional; there is no product Stop deadline.

## Follow-up and custody

Keep the measured low-hanging fixes. Next quality experiment must recover source-adjudicated short/overlapping speech with correct negative controls before adding identity ownership or concurrent-publication machinery. Measure actual visible-word delay and live snapshot/render cost before incremental-transfer work. Do not lower thresholds or set bars from achieved scores.

Fresh targeted rename passed. Fresh browser cases1/8/10 passed, with exact Live/File export bytes retained. Old failures remain unchanged;20retained short-file exports also pass corrected semantic checks. Wrong-speaker/dropped-word/changed-time/missing-review mutations fail.

Full report/receipts and plain human guide:
`/Users/gao/Documents/Codex/2026-09-19/moss-round2/assessment.md`
and `human-microphone-test.md`. Detailed attended protocol:
`docs/handoffs/round2-publication-attended-microphone-guide.md`.

Global campaign3326decoder requests, peak2, zero budget refusals. Own services/tunnel closed; no physical microphone or unmute, no push/deployment/shared-service restart. Shared host manifest remains9600000bytes(5min); isolated tests provisioned460800000bytes(240min). Code support does not upgrade that deployment configuration. Private test launcher bypasses the host SQLite version pin; deployment parity is unqualified.

Four tmux agents usedgpt-5.6-sol/high. Production revision for final File/UI checks:`be2dd06d45cca24ce3e56eff843a4d245f168c09`; later documentation/evidence commit does not change product code. Preserve performance receipts against their actual revisions.
