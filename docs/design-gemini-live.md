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
| System rolling | Per-meeting seconds (round 3, J2): growing context `[max(0,t-C),t]` every R s, **Refresh** R 5–60 s (default 15) and **Context** C 90–300 s (default 90); holdback H=0; at most one batch call in flight **per lane** (lanes run in parallel); a late call coalesces ticks and increments `skipped_window_ticks` |
| Microphone rolling | Fixed recent 30 s window every 15 s, **Gemini diarization on** (round 2); its own continuity registry with IDs `local-NNNN` shown as `Local NN`; open batch windows only for newly covered WebRTC-voiced audio |
| W3 preview | `gemini-3.5-transcribe-live`, TEXT transcription, automatic VAD silence 500 ms, 2 s tail flush, 5 s replay after bounded GoAway reconnect; each lane opens only on WebRTC voice and closes after 60 s quiet |
| Continuity | One-to-one Hungarian word-time overlap with committed rows, minimum 0.3 s; cross-window WeSpeaker cosine E=0.46; within-window local-label merge W=0.60 when words overlap by no more than 0.15 s; an unmatched label needs 2 s Gemini-attributed speech before a displayed ID is born |
| Embeddings | Up to three continuous attributed spans of 2–10 s per local label, joined across gaps ≤0.6 s; production pinned WeSpeaker, three interval workers; measured vectors unchanged from serial encoding |
| Retention and idle | 60 s retained-sample bound; at >45 s accepted-minus-committed lag, publish a degraded base that **carries both lanes' preview words as unlabelled rows** (round 2 S2); after 15 s without ingress, drain the unrevised accepted suffix; Stop returns within the browser's deadline while the server keeps draining up to 60 s, then decodes any still-uncovered tail with the terminal transcriber, else saves with an `unavailable` (needs-review) outcome — never a silent `final` (round 2 F1) |
| Batch requests | `gemini-3.5-transcribe` verbatim word timestamps and speaker labels for system; app retries 429, 5xx, timeout up to three attempts with bounded backoff; SDK internal retry disabled so physical attempts match counters |
| Terminal | **Default on, in the background** (`cleanup_after_stop`, ADR-0017, D20): the live transcript is saved at Stop and the terminal pass commits an improved version later; export and passage corrections wait for it. One call through 900 s; above 900 s, 900 s chunks with 30 s overlap, at most three concurrent final calls, midpoint word-core ownership and seam/cosine stitch; skip any WebRTC-unvoiced final chunk. The same pipeline serves File and URL meetings (`app/gemini_file_runner.py`) |

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
and final mic words. A live (rolling) mic window publishes words only when its gated
words hold a continuous attributed span of at least 2 s (0.6 s joins, the same evidence a
voiceprint needs); otherwise its words are counted as `mic_words_dropped_unanchored` and the
terminal pass decides the saved text (round 4, issue #3: noise and echo-residue windows
produced 165 → 3 invented, often foreign-language, words with unchanged non-backchannel
retention; `prototypes/gemini-live/mic-hallucination/NOTES.md`). The saved (terminal and
Stop-tail) mic words are withheld only when the meeting's microphone never showed such a span,
in any live window or in the saved words themselves; they are counted as
`mic_words_withheld_unanchored_lane`, and a Stop tail withheld this way counts as covered, not
as a failed recovery (listen-only speaker lanes 104/73 → 0/0 saved invented words; saved
retention unchanged on six lanes with local speech; margin 1.9 s vs 2 s). W3's provisional text lacks reliable word timing, so the lane
composer removes from a mic preview row every run of at least three words (five CJK
characters) that occurs anywhere in the system words it could echo: committed system rows
and the system preview ending within n/1.5 + 5 s of the row (n = its units). Each run is
matched on its own, since the far end repeats itself and one in-order alignment anchored on
the wrong copy left 102 echoed characters in a Mandarin replay. Leftover runs
under four units are dropped, and so are leftovers of an echo row that repeat the lane's own
committed words; a row with nothing left is not shown (round 4: under speaker echo one W3
mic turn grew to ~400 words while the old preview-only 60% test saw only the uncommitted
suffix; recorded streams 244/423 → 13/10 echoed units per poll, local sentences unchanged,
short replies inside an echo row wait for their commit;
`prototypes/gemini-live/mic-preview-echo/NOTES.md`). A short mic preview row (no script with
four words or seven CJK characters in it) also loses its words in a script the meeting has
not used: a script counts once that much of it was committed on either lane or stood in one
preview row of either lane. Noise and echo residue otherwise show isolated kana, Devanagari
or Hangul words in a Mandarin or English meeting (243 → 0 word-polls); a genuine first short
reply in a new language waits ≈13 s for its commit, a sentence ≤0.6 s
(`prototypes/gemini-live/preview-script/NOTES.md`). System text wins an echo tie; a later
overlapping row in the same lane replaces the earlier one.
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
- **Clean-up after Stop, in the background** (ADR-0017, D20): the drained live surface is saved as the final transcript at Stop;
  the whole-recording pass then commits an improved version (`refinement_state` none/running/done/failed on meeting detail and
  History; 409 `refinement_running` for passage corrections and audio download meanwhile). Q-IND showed live-only materially worse on
  3 of 12 independent meetings (`evidence/P66/qual-f962d97d/qind.json`), so the default is on.
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
  `prototypes/gemini-live/wp3-overlap/NOTES.md`). The fingerprint runs after the name is saved (answer `pending`), one at a
  time and outside the identity lock: it costs ~3.3–4 s per minute of the speaker's speech on an M3 Ultra (99% WeSpeaker,
  ≤ 1% ffmpeg decode), which inside the request made a rename take 40 s (13.5 min meeting) to 278 s (150 min) and stalled
  every Live publication meanwhile (issue #15, `prototypes/rename-latency/NOTES.md`).
  Known limit (round-4 review): the pending fingerprint lives in memory only, like the Live "saved when recording
  finishes" path — a restart or fingerprint error in that window leaves the name without a voiceprint; renaming retries.
- **Server summaries** (ADR-0011/0013 amendments): `POST /api/meetings/{id}/summary/live` (ephemeral, owner-bound live transcript)
  and `/summary/server` (completed transcript at `source_version`, stored as `final_summary`), default `gemini-3.5-flash-lite`,
  content-free `usage` in both responses. A meeting records the version its post-Stop clean-up produced (`refined_version`);
  only a summary older than that is regenerated automatically or failed as `source_changed`. Speaker renames and passage
  corrections bump the version but do neither; Refresh stays the user's choice (D1, issue #15).
- **Cost meter**: usage reports metered input, `metered_output_usd`, and a Google-rate output estimate ($0.002/min Transcribe,
  $0.004/min Live) separately; File/URL cost is an estimate from the terminal chunk plan (`prototypes/gemini-live/qfile/NOTES.md`;
  retries unmeasured). Whether Google bills Transcribe output tokens (usage reports 0) is unconfirmed (A5).
- **Fixed (S1):** a paced long60 run stopped labelling at 750 s while all 173 system windows decoded. Cause: `ordered_segments`
  dropped `source_lane` when merging a fully-overlapped tail word, and the two-lane combiner raised on every later publication
  (reproduced $0 with cached real responses, `prototypes/gemini-live/s1-cached/NOTES.md`; fixed replay labels through 2579.9 s).
  Engine worker exceptions are now counted as `errors_by_code["worker_<Exception>"]` instead of staying silent.
  The fixed paced long60 run (WP4) published labels through the whole meeting and settled all 2,586 s.

## Round 3: per-user providers (2026-09-29, plan `docs/plan-r3-ui.md` I-2/I-3, Q4)

- **No server key.** The server starts without any provider key; `.env.local` is never read by the app. Each Live create,
  File/URL upload, server summary and `POST /api/providers/test` carries the user's own key; a missing Gemini key is
  400 `{"detail": {"code": "api_key_required"}}`. Clients are built per meeting/job/request from that key.
- **Engine settings v3** (`validate_engine_settings`): `{"transcription": {"vendor", "url", "model", "api_key"},
  "refresh_seconds", "context_seconds", "cleanup_after_stop"}`; presets removed; unknown keys and out-of-range values are
  400 with a human `detail`. Rolling and clean-up use the settings model (default `gemini-3.5-transcribe`); instant words
  stay `gemini-3.5-transcribe-live`. The microphone lane keeps 30 s context / 15 s refresh.
- **OpenAI-compatible transcription** uses `OpenAICompatibleDiarizer` (`app/openai_compatible_provider.py`) for both lanes
  and File jobs, with no instant words; clean-up after Stop is forced off. Real-model quality is unmeasured.
- **Custody.** The key exists only in memory for the meeting, job or request: `engine_diagnostics.engine_settings` shows
  `"api_key": "[redacted]"`, and nothing durable (SQLite, notices, failure reasons, logs, work directories) holds it
  (`tests/phase2/test_user_provider_keys.py` sentinel test). A server restart cannot resume an in-flight clean-up (the live
  version is kept) or File job (it fails), since the key is gone.

## Round 3 addition: OpenAI-compatible transcription (WP-F, plan `docs/plan-r3-ui.md` J1/I-5)

- **Adapter** `app/openai_compatible_provider.py`: `OpenAICompatibleDiarizer(url, model, api_key, report_usage)` has
  `WindowDiarizer`'s surface (`diarize(pcm16, *, deadline, kind, diarize) -> GeminiWords`) over
  `POST {url}/audio/transcriptions`. Format rule: model name containing `diarize` → `diarized_json` + `chunking_strategy=auto`;
  otherwise `verbose_json` with word + segment timestamps; a 400 naming the format falls back once to `json`, sticky per meeting.
  Labels: the model's speaker when returned, else one label per returned segment (J1). Text without word times is spread over
  mode-1 WebRTC voiced frames, so placed words survive the word gates. Requests over 600 s (25 MB upload limit) split into
  prefixed pieces. It owns retries (429/5xx/timeout, per attempt ≤ 120 s inside the caller deadline); usage rows are
  content-free, `cost_usd` 0 (price unknown). No preview words (`NoPreviewWords`); `probe()` backs the Settings Test.
- **Measured through the production identity paths** (golden lines as provider stand-in,
  `prototypes/streaming-diarization/openai-segment-labels/NOTES.md`): per-segment labels give live accuracy .836 (+1.1 extra
  speakers, 8.5% speaker-less before Stop) and File .867 with **+3.9 extra speakers** (rtfl: 22 for 4) — File has no orphan step.
  json-only models (e.g. `gpt-4o-transcribe`) give one speaker per request and lose/duplicate up to 11%/13% of words at live
  refresh boundaries. A short-segment attach rule was rejected (≤ +1 point). Real model quality is unmeasured.

## Round 4 addition: rolling summaries (#6, #10)

- Live (`/summary/live`) and final (`/summary/server`) summaries share one generator, prompt, model and schema. The
  rolling pane now renders the whole five-section document like the final pane (its Theme line alone carried 28/54 of
  the facts the document carried 50/54 of; `prototypes/gemini-live/live-summary/NOTES.md`).
- Language = Auto now asks for "the transcript's dominant language": gemini-3.8-flash answered English for 3/12 Chinese
  snapshots before (all ≤ 50 s), 0/12 after. gemini-3.5-flash-lite stays unreliable under Auto (3/6); an explicit
  Language works on it. A browser still holding the untouched old default `gemini-3.5-flash-lite` (saved before
  round 4, or a v1 record) moves to `gemini-3.8-flash`; flash-lite chosen since is kept (saves record the defaults
  they were made under). The transcription model is untouched.
- The 40-word minimum counts each CJK ideograph as a word (a 5-minute Chinese transcript was 13 "words").
- Default wait after each summary 20 s (was 60; a browser still holding the untouched 60 moves to 20): ≈ $1.73 per
  meeting-hour with gemini-3.8-flash vs $0.70 at 60 s (measured usage, English). Previous-summary carry-forward
  (LiveTranscribe) was measured unnecessary: facts lost between refreshes 1/26.

## Round 4: long meetings and transient disconnects (issue #1, 2026-09-30)

- **Incident.** Three back-to-back meetings on ga0-rog-laptop ran 45.5, 55.2 and 45.5 min and each ended
  `helper_lease_expired lanes=none`: frames and heartbeats stopped at the same instant, the server interrupted 30 s
  later. No server bound, runtime failure or host Wi-Fi event coincided; the browser-side trigger is unmeasured.
- **Saved audio 1 h → 12 h** (`GEMINI_MAX_TAPE_BYTES`, disk-bound; Account's stage is a file). Time-compressed through the
  real phase-2 stack, a 200-min meeting saved only 60 min (`audio.partial.mp3`) and skipped the post-Stop pass
  (`complete_tape_unavailable`); with the fix it saves all 200 min.
- **Post-Stop pass ≤ 4 h** (`GEMINI_MAX_REFINEMENT_SECONDS`, RAM-bound). Real composition + WeSpeaker ONNX, instant fake
  provider: 35.6 s / +1.6 GB peak RSS at 1 h, 113.5 s / +2.6 GB at 3 h (provider latency excluded). Longer meetings keep
  the live transcript (`meeting_exceeds_refinement_bound`).
- **Transport.** Capture POSTs are abandoned after 10 s and replayed, so a hung request no longer pins a lane and the
  heartbeat; the Gemini launch scripts' helper lease is 120 s (was 30 s); a lease expiry's journal line names the last
  heartbeat (`last=<state> last.<lane>=<code>`, or `last=none`).
- **Growth, not a limit.** Snapshot GET grows linearly (766 KB, 29 ms at 200 min / 1,200 rows); frame POST cost is flat.
- **Finished meetings in memory.** `_sessions` is never pruned; each finished meeting also kept its engine (~8.5 MB at
  1 h: rolling caches, provider client and key) and, on endings without the final pass, open lane tapes and Live
  sockets. The engine is now closed and dropped on every ending (`_release_tape`). Process RSS is the final pass's
  high-water, not per-meeting growth: 448 MB → 1,960 MB after one 1 h meeting, then +25/+1/+4 MB for three more
  (retained state per finished meeting 8.5 → 0.9 MB, engines alive 4 → 0).
- **Preview backlog sheds chunks** instead of closing the socket: a 60 s catch-up during a reconnect overflowed the 64-chunk
  backlog and preview stayed off while people kept talking (0/60 chunks sent in the next 30 s; 60/60 after the fix).

## Round 4: joining words into text (F1, 2026-10-01)

- **Defect.** Gemini returns one "word" per Chinese character and every join wrote a space, so committed, saved and
  exported Chinese read "大 家 好， 今 天" (572 spaces in the 574-word saved transcript of r4 run (c)). The grey preview
  was clean only because it is the provider's own unspaced string.
- **One rule, both runtimes** (`join_text` in `transcript_text.py`, `joinText` in `frontend/src/lib/text.ts`, one shared
  test table): no space when the character on either side of the join is from a script written without spaces (Han,
  kana, bopomofo, CJK punctuation, full-width forms); otherwise exactly one, never two. Hangul keeps its spaces
  (Korean separates words). Only the joined string changes; words, times, speakers and segments are untouched.
- **Mixed text** reads "我们用API做测试" and "大概30万". Gemini's own Chinese strings in run (c) (preview, summaries)
  write "30万" unspaced every time (13/13 phrases) and disagree on English words (5 spaced both sides, 3 unspaced,
  3 half-spaced), so the single either-side rule was taken over "space between Chinese and Latin letters, not digits".
- **Measured** by re-joining the saved words of the three r4 runs: English 55/55 segments byte-identical (1,787 words);
  Chinese 572 → 0 spaces, no character lost.
- **Join sites.** Server: `speaker_turns` (rolling commits, mic lane, tail recovery, clean-up, File/URL, the
  OpenAI-compatible path), `ordered_segments` (overlapping tail word), Live model-turn parts. Browser: same-speaker rows
  (`mergeTranscript.ts`, which exports and Copy read), preview rows (`tentative.ts`), the history card. Summaries read
  the stored text.
- **Meetings saved before the fix read clean; their rows are not rewritten** (user decision D3). Where a saved
  transcript is served (`Meeting.to_dict`: opened meeting, History, exports) or handed to the server summary,
  `without_join_spaces` drops a single space that stands between two unspaced-script characters, nothing else. A space
  beside a Latin letter, digit or Hangul stays as stored, because the saved string does not say whether it was a
  join: old meetings read "大概 30 万左右" and "用 API 做测试", new ones "大概30万". On the recorded runs: Chinese
  572 → 6 spaces (the six beside "30" and one Cyrillic token); English 55/55 segments returned as the same string;
  a 3-hour-sized Chinese transcript (86,760 characters) takes 4 ms. Renames and passage corrections address rows by
  speaker id and segment id and rewrite the row with its text as saved.
- **Not changed.** The MOSS-engine seam merge (`resolve_segment_overlaps`) keeps its measured single-space join.
- **Preview "Yeah.researching" / "AndYou" is the provider's string, not a join of ours.** Gemini Live glues sentences
  inside one transcription update. In 13,103 recorded update strings (551k words) the shapes are `x.Y` 750,
  `x.y` 1,296 (about 500 of them real addresses such as acquired.fm) and `xY` 657 (about 300 real names: McDonald's, YouTube,
  PayPal); an `x.Y` glue point sits at the end of an earlier update in only 30 of 72 first sightings, so the update
  sequence does not locate it. Only `x.Y` is safe to repair (0 in 38.7k committed words) and it would not fix the two
  reported examples, so nothing was added; the committed text replaces the preview within seconds.
- **Unmeasured.** How Gemini splits Japanese and Korean into words.

## Round 4: the conversation veto and reused labels (P69 F3, 2026-10-01) — measured, unchanged

In a 65.5-minute meeting the saved transcript named one host twice (long60-part DER .165; .052 for the same
audio without the extra 22 minutes). The provider had reused the host's two chunk-local labels for two new
voices at the end of one 900 s chunk; their single A–B–A alternation vetoed six correct merges (cosine .74–.81).
Relaxing the veto to two alternations repairs that meeting (.049) but lets two different speakers merge on the
recorded synthetic K4 meeting (DER .221 → .330) and on an overlapped-speech replay (3 → 2 speakers), so the
shipped rule stays. A voice-checked veto (an alternation counts only if its turns match their labels) passed
every replay but is unmeasured on raw provider labels. Numbers, gates and what the next step needs:
`prototypes/gemini-live/aba-veto/NOTES.md`.

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
activations, preview/window lag, microphone acoustic/text/unanchored drop and saved-lane withhold decisions, preview
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
