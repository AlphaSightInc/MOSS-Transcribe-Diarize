# Gemini live runtime — final design and measured envelope

**Decision.** The Account application, HTTP API, browser transcript contract, audio retention,
and speaker naming remain in place. The selected live engine uses Gemini Live for fast
unlabelled words, Gemini 3.5 Transcribe for speaker-attributed rolling and final text, and
the pinned local WeSpeaker encoder for speaker continuity and cross-meeting voiceprints.
`LiveSession` remains the authority for accepted samples and every public transcript row.
The production selection is `--live-engine gemini`; the default remains `moss`.

## Structural contract

**Question.** How can window-local speaker labels become stable meeting identities on a
continuous audio clock while slow provider calls, reconnects, and Stop never lose accepted
audio or publish the same text twice?

**Minimum primitives.** One accepted 16 kHz sample clock and complete Account tape locate
all words; two capture lanes preserve the system/microphone distinction; a fast provisional
source gives immediate text; a monotone rolling frontier bounds revisions; a continuity
registry maps Gemini-local labels to meeting IDs; `LiveSession` owns the visible surface;
a terminal pass corrects the whole tape; WeSpeaker observations connect meeting IDs to
the existing Voiceprint bank. Removing one loses a required boundary or identity fact.

**Invariants.** Each accepted sample remains on the tape until final settlement. The
provisional suffix starts at `committed_samples`. A rolling interval has one text owner;
completed words belong to the frontier by **word end**. Only a terminal revision can
replace the complete recording. A later rolling identity correction uses the narrow
`revise_rolling_interval` path. Diagnostics carry operational metadata only: no audio,
transcript, embedding, or API key. Every physical batch attempt has one counted retry owner.

**Assumptions and falsifiers.** Gemini timestamps and local labels can drift; WebRTC can
misclassify speech or music; one physical microphone may contain more than one person. A
paced run with unexplained missing accepted audio, a public duplicate provisional phrase,
identity count beyond the E1 bound, or a provider attempt absent from counters falsifies
this design. Full-meeting quality after the final lag change and natural-room echo behavior
remain unmeasured here.

## Public data flow

| Input or event | Runtime action | `LiveSession` and browser effect |
| --- | --- | --- |
| Aligned system and microphone PCM | Account accepts one clock; Gemini keeps bounded per-lane caches and temporary lane tapes | Existing session/tape/MP3 paths retain the recording |
| W3 Live text | `GeminiPreview` from the voiced lane; the lane composer removes overlapping near-identical echo phrases | One S00 provisional suffix from `committed_samples`; distinct simultaneous mic text remains visible |
| Rolling Gemini window | Empty `GeminiBase` through the frontier, then `GeminiRolling` speaker turns | Revised, labeled prefix with stable canonical meeting IDs |
| Later speaker correction | `GeminiRelabel` / `revise_rolling_interval` | Existing row text keeps its place while a displayed speaker ID changes |
| Idle ingress or Stop | Decode only `[rolling frontier, accepted end]` when needed | Settled prefix covers received audio; pending work stays visible until covered |
| Terminal Gemini pass | Timestamp repair, speaker stitch, word gate, final label map, terminal revision | Whole-recording final surface and `finalization_status=final`; failures show `failed` or `unavailable` |

The public snapshot and event routes, frontend parser, naming route, export, and final
summary remain the existing Account interfaces. The frontend ignores the additive
`engine_diagnostics` field. The engine protocol and deterministic scripted engine are in
`app/gemini_live_runtime.py`; the session worker is in `app/gemini_hybrid_engine.py`;
source-lane composition is in `app/gemini_lane_engine.py`.

## Selected composition and constants

All product defaults live in `app/phase2_web_cli.py`; the selected word source is
`GeminiLiveWordSource` in `app/gemini_live_words.py`, and the selected registry is
`ContinuityRegistry` in `app/gemini_continuity_registry.py`.

| Component | Selected behavior |
| --- | --- |
| System rolling | Per-meeting preset (round 2): **Balanced** growing context `[max(0,t-90 s),t]` every 15 s (default), Economy 90 s every 30 s, Max context 180 s every 15 s; holdback H=0; at most one batch call in flight **per lane** (lanes run in parallel); a late call coalesces ticks and increments `skipped_window_ticks` |
| Microphone rolling | Fixed recent 30 s window every 15 s, **Gemini diarization on** (round 2); its own continuity registry with IDs `local-NNNN` shown as `Local NN`; open batch windows only for newly covered WebRTC-voiced audio |
| W3 preview | `gemini-3.5-transcribe-live`, TEXT transcription, automatic VAD silence 500 ms, 2 s tail flush, 5 s replay after bounded GoAway reconnect; each lane opens only on WebRTC voice and closes after 60 s quiet |
| Continuity | One-to-one Hungarian word-time overlap with committed rows, minimum 0.3 s; cross-window WeSpeaker cosine E=0.46; within-window local-label merge W=0.60 when words overlap by no more than 0.15 s; an unmatched label needs 2 s Gemini-attributed speech before a displayed ID is born |
| Embeddings | Up to three continuous attributed spans of 2–10 s per local label, joined across gaps ≤0.6 s; production pinned WeSpeaker, three interval workers; measured vectors unchanged from serial encoding |
| Retention and idle | 60 s retained-sample bound; at >45 s accepted-minus-committed lag, publish a degraded base that **carries both lanes' preview words as unlabelled rows** (round 2 S2); after 15 s without ingress, drain the unrevised accepted suffix; Stop returns within the browser's deadline while the server keeps draining up to 60 s, then decodes any still-uncovered tail with the terminal transcriber, else saves with an `unavailable` (needs-review) outcome — never a silent `final` (round 2 F1) |
| Batch requests | `gemini-3.5-transcribe` verbatim word timestamps and speaker labels for system; app retries 429, 5xx, timeout up to three attempts with bounded backoff; SDK internal retry disabled so physical attempts match counters |
| Terminal | **Optional per meeting** (`cleanup_after_stop`, default off for Gemini — ADR-0017). One call through 900 s; above 900 s, 900 s chunks with 30 s overlap, at most three concurrent final calls, midpoint word-core ownership and seam/cosine stitch; skip any WebRTC-unvoiced final chunk. The same pipeline serves File and URL meetings (`app/gemini_file_runner.py`) |

Pilot guards use cross-pass transcript witnesses, since WebRTC can mark music
as voiced. W3 rotates with its existing 5 s replay only after batch words cover
at least 10 s since the last preview text. Rolling windows have no coverage
retry: on the real E1 run the preview witness (which also hears speaker echo on
the microphone lane) fired 12 times on normal audio and re-inserted echo text,
and a missed live window only affects the live view. A final chunk uses
committed live rows as its witness, retries once, then carries live rows across
any remaining missing interval, so the saved transcript never loses live speech.

The provider parser clamps a word end before its start or beyond the call audio to
`min(start+1 s, audio end)` and drops a word starting past the audio tolerance. The
rolling and final timestamp repair retains Gemini annotation order, fixes isolated
>5 s durations or >10 s jumps between valid anchors, and counts repaired words. The
final identity policy embeds eligible attributed spans, forms per-label centroids,
excludes A-B-A/B-A-B conversational pairs with both gaps ≤2 s, then greedily unions
by descending cosine at ≥0.65 without crossing an excluded pair. Words map to turns
when successive same-speaker gaps are ≤1.5 s. Production WebRTC mode 1, 10 ms drops
a rolling or final word only when no voiced frame lies in its ±0.2 s padded span.
Final labels map back to live meeting IDs by sample overlap (ADR-0005 D8).

The microphone gate also requires either no system WebRTC voice over a word or
microphone RMS at least −15 dB relative to the best system RMS at a 0–100 ms lag.
The existing normalized-token echo guard must also pass. Both filters run on rolling
and final mic words. W3's provisional text lacks reliable word timing, so the lane
composer drops a mic preview row when at least 60% of its normalized tokens occur
in the union of system preview rows overlapping it within ±2 s. System text wins
an echo tie; a later overlapping row in the same lane replaces the earlier one.
At the commit frontier, the public publisher aligns each preview chunk's head to
the last 60 tokens of committed effective speech in the same lane. A match of at
least five tokens trims the repeated prefix; number words and digits align.
A truly identical simultaneous phrase can be hidden in preview.

The pinned WeSpeaker observations for Gemini-attributed meeting IDs flow through
`_identity_observations` and `_identity_match_observations` to Account's existing
name/enroll route and Voiceprint bank. Compatible encoder identity and vector
dimension are required; Gemini never assigns cross-meeting names by itself.

## Round 2 additions (2026-09-29, plan `docs/plan-gemini-live-r2.md`)

- **Fingerprint veto** (`ContinuityRegistry.observe_window`): after overlap-first Hungarian matching, a label is contested when
  another meeting ID's centroid cosine is ≥ .46 and beats the assigned ID by ≥ .20; a contested window is re-solved with
  fingerprint weights. Measured: fixes 6/6 cached identity collapses (e.g. S30/L90 Bill30m DER .487 → .051, long60 .350 → .046)
  with no passing-case regression beyond +1 ID (`prototypes/gemini-live/guard/NOTES.md`). Evidence covers one voice pair.
- **Schedule presets** (`prototypes/gemini-live/schedule/NOTES.md`): S15/L90 halves re-sent audio (11.6× → 5.9×) and lowers label
  lag (p50 17.5 → 13.3 s on long60) at equal long-form DER; 60 s context is rejected (P5: over-splitting even with the veto).
- **Speaker-less rows (F13)** are relabelled by later windows; at Stop a remaining row takes the best same-lane fingerprint at
  cosine ≥ .46, else stays Speaker TBD. Refused relabels are counted (`f13_relabel_refused`), never fatal; speaker-less turns are
  never bridged. **Orphans:** an ID with < 2 s total committed speech (not user-named) is absorbed the same way at Stop
  (`orphan_speakers_absorbed`).
- **Clean-up after Stop off by default** (ADR-0017): the drained live surface is saved as final; P2 evidence
  (`evidence/P65/p2-cleanup-skip.md`) and the Q-IND gate.
- **Microphone lane** (G1 O2): diarized 30 s windows; cross-lane voice echo guard drops a mic word whose voice matches overlapping
  (±0.4 s) system speech at cosine ≥ .60; the token echo guard keeps multi-token matches and requires voice corroboration for single
  tokens (measured: headphones retention 320/336, speakers −20/−10 dB echo rejected 575/576 and 574/576, 2 Local IDs, 0
  system-born; `prototypes/gemini-live/micfixture/NOTES.md`).
- **Tentative names** (`app/gemini_tentative.py`): per-lane EMA centroids of settled canonical speakers; every 0.5 s of voiced
  audio the trailing 1.0 s is embedded (single-thread pinned encoder) and assigned at cosine ≥ .40, else abstain; display-only
  `provisional.segments[].tentative_speaker`, never saved or exported (`prototypes/gemini-live/tentative/NOTES.md`).
  The S1-fixed, paced public long60 product run showed 96.36% first-visible guess coverage but only 91.89% accuracy
  (≥95% gate failed), despite full audio settlement; embed p95 was 213 ms. The final settled transcript conflated Javier
  with Lex under one canonical ID and split Bill/Lex across IDs. The earlier 98.98% five-clean-ID offline result was
  conditional and does not establish product acceptance. See the WP4 NOTES verdict and P66/wp4/long60-fixed receipt.
  A zero-send shared-encoder falsifier found identical serial/concurrent WeSpeaker vectors on ten fixed public clips
  (20 overlapping call pairs, max component delta 0, min cosine 1); this tested concurrency path does not explain the
  collapse (`prototypes/streaming-diarization/shared-encoder-concurrency/NOTES.md`). Fresh provider output remains unmeasured.
- **After-Stop voiceprints** (D17): naming a completed Live meeting's speaker fingerprints that speaker's rows in the saved
  recording minus intervals overlapped by any other row (either lane), ≥ 2 s (3/3 cases: 3.0 s eligible, 1.0 s refused;
  `prototypes/gemini-live/wp3-overlap/NOTES.md`).
- **Server summaries** (ADR-0011/0013 amendments): `POST /api/meetings/{id}/summary/live` (ephemeral, owner-bound live transcript)
  and `/summary/server` (completed transcript at `source_version`, stored as `final_summary`), default `gemini-3.5-flash-lite`,
  content-free `usage` in both responses.
- **Cost meter**: usage reports metered input, `metered_output_usd`, and a Google-rate output estimate ($0.002/min Transcribe,
  $0.004/min Live) separately; File/URL cost is an estimate from the terminal chunk plan (`prototypes/gemini-live/qfile/NOTES.md`;
  retries unmeasured). Whether Google bills Transcribe output tokens (usage reports 0) is unconfirmed (A5).
- **S1 label stall resolved:** a fully overlapped tail word lost `source_lane` during `ordered_segments` reconstruction,
  causing the two-lane publisher to raise after 750 s (`prototypes/gemini-live/s1-cached/NOTES.md`). The fixed paced
  long60 run published labels through the final meeting and settled all 2,586 s. Identity quality remains open as noted above.

## Measured envelope and custody

Figures below name their code/fixture population. They do not combine different
qualification SHAs into one aggregate. H1 uses the six accept6 clips twice and the
verified H1 #3 reference set. The five acquired 5-minute references, acquired
Jamie 30-minute reference, gold9 acquired Jamie 60 s, and rtfl90 are too sparse
for binding DER aggregates. Complete lex 5-minute references and lex Bill30m
are supporting populations.

| Evidence | Measured result | Boundary |
| --- | --- | --- |
| H1 12 passes, `6c5776e3` | Settled ruled/raw diarization error rate (DER) .092089/.101115; final DER .104860; 0/1216 dropped reference seconds; 1 clamped word/108 calls, 0 dropped words, 0 errors/retries | Full 0b9deed5 H1 qualification is pending pane 6.2 |
| E1 302 s, `6c5776e3` | 4 labels at Stop for 4 true speakers; fast text p50 0.0 s on 302/302 audio-second buckets; labeled rows p50 22.634 s on 254/302; $2.791/audio-hour | The ≤20 s label soft bar failed on this pre-L1 run |
| Long60 2586 s, `6c5776e3` | 5/5 IDs; settled/final raw DER .043404/.034375; Lex retained one dominant ID; cost $2.461/audio-hour | Label p50 26.517 s first 5 min, 29.519 s last 5 min before L1 |
| Public long60 first 600 s, `0b9deed5` candidate | Label p50/p90 18.262/25.015 s, 583/600 labeled buckets, 0 skipped ticks, two IDs at Stop; before 26.761/37.508 s, 597/600 buckets, one skip | Standalone after run ends at 600 s; full-meeting lag and the 14-bucket coverage difference remain open |
| Real cross-meeting public voiceprints, `c58595da` | Lex named from Bill60, auto-named on Keyu60; Lex and Keyu both auto-named on Keyu5m; Bill remained unnamed on Bill5m (0/524 Bill-dominant observations named) | Earlier code path, same naming seam; natural-room recordings unmeasured |
| E1 microphone acoustic gate, `e7078edc` | 0/20 stray final mic words outside operator intervals; phrase recall 7/7, 6/7, 4/5 | Echo ≥−15 dB and quiet operator gain 0.1 defeat this rule in bench tests |
| Stress on `56513e30` | 600 s digital silence finalized 2.621 s after Stop with no batch calls; 604 s many-speaker fixture finalized in 68.397 s; injected 503 physical attempts matched error/retry counters | Silence still opened system W3 on that SHA; `130f3d39` adds voiced-only system W3; final-SHA real stress rerun pending pane 6.4 |

The E1 cost model for a 302 s meeting with its observed lane activity is
$2.872/audio-hour including final calls; the product E1 measurement was
$2.791/audio-hour. A continuously voiced two-lane hour models $3.444/hour,
above the $3 soft target. W3 usage lacks provider usage metadata; its counter
uses the list-price estimate of $0.005 per streamed minute. Final chunks on
recordings above 900 s are a measured candidate, with long60 product accuracy
shown above; wider long-form identity and late-call behavior are not qualified.
Synthetic music can pass WebRTC and yielded one unsupported final token (`2`)
in the P64 music fixture. A single microphone lane always has one local speaker
ID. The 600 s silence fix and reconnect/echo preview fixes need their final-SHA
real stress or browser checks; deterministic regressions cover the code paths.

`engine_diagnostics` exposes per-session, per-lane calls by kind, errors and
retries by code, audio seconds sent, provider cost, W3 list-price estimate,
clamped/dropped/repaired word counts, chunked status, skipped ticks, degraded
activations, preview/window lag, microphone acoustic/text drop decisions, preview
stall restarts, coverage retries, rolling preview fallbacks, and terminal
coverage fallbacks.
Counters contain no meeting content. The SDK retry proxy test verifies physical
attempt accounting; Stop failures produce visible `failed`/`unavailable` state.

## Evidence and verification

- Product H1/E1/long60 scorecard: `evidence/P62/gemini-c4-6c57-scorecard-1032/scorecard.json` and `evidence/P62/gemini-c4-6c57-long60-0953/summary.json` in the campaign evidence root.
- L1 first-600 comparison: `evidence/P63/l1-before-first600.json` and `evidence/P63/l1-paced-10min-130f3d39-candidate/result.json`; one-command encoder and paced probes are in `prototypes/gemini-live/runtime-lag/`.
- L2 public provisional regression: `tests/gemini/test_gemini_live_runtime.py::test_public_provisional_suffix_collapses_overlapping_echo_preview`; E1 observed preview pair is retained in `evidence/P61/uimerge-e1-browser/service-snapshots.jsonl`.
- L4 commit-frontier preview regression: `tests/gemini/test_gemini_live_runtime.py::test_public_preview_trims_committed_speech_in_same_lane`; E1 observed overlap is retained in `evidence/P64/lead-final-merged-E1-L3/service-snapshots.jsonl`.
- Voiceprint: `evidence/P52/voiceprint-{A,B,D,E}.json`; echo gate: `evidence/P63/echogate-e1-http.json`; stress: `evidence/P64/runtime-s12-{faults-http-503,silence10,manyspk}-full1/summary.json`.

All campaign evidence paths in this section resolve under
`/Users/gao/Documents/Codex/2026-09-28/moss-gemini/`. On exact clean code SHA
`0b9deed5`, full backend `pytest tests` passed **2,523**, skipped 3, xfailed 2,
and passed 37 subtests (27 warnings); frontend Vitest passed **313/313** across
28 files; frontend TypeScript typecheck passed. The three command logs are
`evidence/P63/final-{backend,frontend,typecheck}-0b9deed5.log`.
