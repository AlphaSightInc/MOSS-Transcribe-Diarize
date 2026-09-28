# Gemini Live hybrid runtime — P63 phase 2

**Decision.** `LiveSession` remains the public transcript and sample-accounting authority. A
session-local Gemini engine writes provisional fast words, commits empty base spans up to the
diarized frontier, then revises them with Gemini speaker rows. Google Transcribe owns
who-spoke-when; the pinned WeSpeaker encoder supplies cross-meeting voiceprints only. The
Account, capture, HTTPS, and browser contracts remain on their existing paths.

## Structural question and primitives

**Question.** How can slow, window-local Gemini output label a continuous 16 kHz stream
without losing accepted audio, duplicating visible words, or changing a meeting speaker ID?

**Minimum primitives.** The accepted sample clock binds every provider word to audio. Account's
complete canonical mixed stage serves the terminal pass. The window scheduler chooses a
monotone rolling frontier. The registry maps window-local labels to meeting IDs. `LiveSession`
owns the displayed prefix, provisional suffix, speaker revisions, and Stop status. The
WeSpeaker observation connects those IDs to Account's existing Voiceprint bank. Remove any
one and coverage, ordering, or identity becomes ambiguous.

**Invariants.** Every accepted sample is on Account's full mixed stage until terminal settlement; the
normal committed prefix advances only to the rolling frontier; provisional text begins at
`committed_samples`; a 45-second lag activates unlabelled base accounting before the
60-second retention limit; each rolling interval has one owner; terminal requests cover the
recording in ≤30-minute chunks; all provider attempts report content-free usage; encoder
identity and dimension match stored Voiceprints. No API key, audio, transcript, or embedding
enters diagnostics.

**Falsifiers.** A 60-minute Account stage loses its head or tail; a slow rolling worker reaches
retention backpressure; a window-local label switch creates a new visible speaker despite
word-time overlap; an invalid provider offset breaks publication; a public paced HTTP run
cannot settle final with exact accepted/accounted samples. These were probed below. Quality
bars across the acceptance population remain unmeasured here.

## End-to-end path

1. `phase2_web_cli.py` selects `--live-engine gemini`, loads `.env.local`'s `GEMINI_API_KEY`
   (preferred over the login shell's unrelated value) or `MOSS_GEMINI_API_KEY`, and builds the
   Gemini client. It does not construct the MOSS file runner or a GPU path.
2. `gemini_live_runtime.py` accepts each 16 kHz mixed frame into `LiveSession` and reads
   Account's canonical mixed stage through a session tape view. A Gemini-only descriptor uses
   at least 960,000 retained samples and 115,200,000 stage bytes. The 60-minute synthetic
   probe wrote 360/360 ten-second chunks, 57.6 million samples, and read its first and last
   16,000 samples exactly. Account also owns durable MP3 recovery.
3. `gemini_hybrid_engine.py` keeps a bounded `Lmax + S` live PCM cache. The
   composition root sets growing context to **Lmax=180 s, S=15 s**. At the latest stride tick `t`, the single worker asks for
   `[max(0,t-Lmax),t]` and commits through `t`. If a call is still in flight, newer
   ticks coalesce to the latest one and omitted ticks are counted. The same scheduler
   accepts Lmax up to 300 s. Account's stage supplies
   full audio at Stop. A per-lane `VoicedLiveWords` gate opens W3 only after WebRTC
   voice and closes it after 60 s without voice. W3 `GeminiLiveWordSource` then streams audio to
   `gemini-3.5-transcribe-live` with TEXT, 500 ms automatic silence detection, a 2 s
   Stop flush and 5 s buffered replay on bounded reconnect. It feeds preview only.
   The C4 `ContinuityRegistry` maps window labels to meeting IDs by overlap and
   WeSpeaker evidence, with a 2 s birth rule.
4. `gemini_provider.py` sends verbatim Interactions requests with word timestamps and
   speaker mode for rolling/terminal. It repairs invalid offsets using the observed
   `bc567bb2` rule: end before start or past the audio becomes
   `min(start+1 s, audio_end)`; a word starting beyond the audio tolerance is dropped.
   It sorts overlapping words onto `LiveSession`'s one-owner sample line. The first real
   attempt failed `segments_out_of_order` at 24/60 seconds; the normalized rerun settled.
   A fully overlapping tail with no sample left preserves text in the prior row, so that
   word's distinct speaker attribution is unavailable. Retries cover only 429, 5xx, and
   timeout, at most three attempts with bounded jitter; each attempt updates counters.
5. Normal publication sends an **empty** `GeminiBase` only through the rolling frontier,
   then a `GeminiRolling` revision with canonical speaker IDs. Beyond the frontier, fast
   words occupy one `GeminiPreview` suffix starting at `committed_samples`. If accepted minus
   committed exceeds 45 seconds, a degraded `GeminiBase` commits cached fast words as S00
   rows to stay within retention; later rolling supersedes them. The count is exposed.
   `revise_rolling_interval` remains the narrow later speaker correction operation; it
   preserves exact text while changing speaker boundaries/IDs. A pending rolling unit stays
   visible until a revision covers accepted audio. After 10 s without new frames, one idle
   window commits the accepted suffix before Stop; continuous frames reset that timer.
6. On Stop, the engine requests one final rolling window through accepted audio within the
   5 s configured deadline. If it misses that deadline, the remaining suffix is accounted
   as an empty base span. Terminal Transcribe makes one whole-recording call up to 30 minutes,
   then 30-minute chunks with 20-second overlap beyond that, and maps chunk-local
   labels by overlap word time, and maps final labels to live meeting IDs by sample overlap
   through `terminal_speaker_mapping`. New unmatched labels receive new meeting IDs. A final
   revision owns the whole recording, and the stage view is released. Missing/degraded
   tape becomes `unavailable`; a terminal provider failure becomes visible `failed`.
   Final words follow the measured policy: same-label turns join across gaps up to 1.5 s;
   WeSpeaker embeds eligible attributed spans; centroids merge by descending cosine at
   0.65 unless a 2 s A-B-A turn pattern vetoes a pair. Production WebRTC mode 1, 10 ms
   frames removes words with no voice in a padded 0.2 s interval. Rolling words use the
   same gate. The final label map still uses `terminal_speaker_mapping`.
7. After a rolling speaker row spans at least 2 seconds, the pinned production WeSpeaker
   encoder embeds that exact tape interval. `LiveSpeakerJournalObservation` is available
   through `_identity_observations` and `_identity_match_observations` before settlement.
   Account's existing name/enroll and next-meeting match path consumes it. An offline
   two-meeting test enrolled one voice and auto-matched the same vector in the second.

The preview source is selected in `phase2_web_cli.py` as `GeminiLiveWordSource`; its
implementation is `gemini_live_words.py`. The remaining continuity swap point is
`OverlapRegistry` in `gemini_hybrid_engine.py`. The stable
interfaces are `WordSource.bind(listener)/push_audio(start, pcm16)` and
`SpeakerRegistry.observe_window(window_start_s, words, embeddings|None) ->
(assignments, relabels)`. The current engine computes pinned WeSpeaker vectors from ≥2-second Gemini-local intervals,
passes them into that argument before assignment, and publishes the same vectors under
the assigned meeting IDs for Account. A one-command fake encoder/registry probe confirmed
1/1 vector equality; C3 quality and added embedding latency remain **UNMEASURED**.

## Per-session operational counters

`engine_diagnostics(session_id)` and the additive `engine_diagnostics` snapshot field expose
calls by kind, errors/retries by code, clamped/dropped timing words, audio seconds sent,
USD cost, degraded activations, skipped window ticks, and window/preview lag p50/max. The frontend ignores the
field. All values are operational metadata; no content or credential is serialized.

| Final-path public accept6 `interview_bill_ackman_60s`, 1.0× | Preview | Rolling | Terminal | Total |
| --- | ---: | ---: | ---: | ---: |
| Gemini calls | 14 | 4 | 1 | 19 |
| Clamped words / calls | 0/14 | 0/4 | 0/1 | 0/19 |
| Dropped words / calls | 0/14 | 0/4 | 0/1 | 0/19 |

The Account-stage run sent 340 audio-seconds and cost **$0.017038**. Errors/retries and degraded
activations were 0. Accepted and accounted audio were both 60.0 seconds; terminal status
was `final`, with 194 rows and 2 speaker IDs. Two prior successful runs cost $0.02004 and
$0.017038. The earlier 24-second attempt failed on
word order before HTTP diagnostics existed, so its spend is **UNMEASURED**; total campaign
spend after this 60-second run was at least $0.054116. A final 90-second public run after
the cache correction brought known campaign spend to at least **$0.083668**, under the
$25 pane cap. Receipt:
`/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P63/phase2-public-http.json`.

The paced run's word and label visibility were both p50 **18.264 seconds**, with 39/60
second-buckets observed and 21 unobserved; this misses the 5-second fast-word soft bar.
Window lag was p50 13.5 seconds across 4 applied windows (max 15.5); preview lag p50 1.5
seconds across 13 previews (max 2.5). These are one case's operational observations, not a
population verdict. The pane 6.2 partial `run_quality.py` invocation used the verified H1
#3 accept6 references but does not emit comparable DER/WER for one case. Its MOSS-specific
rolling-window event classifier reported 0/6 because it recognizes MOSS windows; the
terminal range event proved 6/6 planned windows terminal-covered and 0 uncovered. The full
qualification population remains: accept6 primary; gold9 excluding sparse
`benchmark:acquired_jamie_dimon`; the three complete lex 5-minute clips; and complete
`long30m:lex_bill_ackman`. Gold9 acquired NFL and Rolex are usable near-complete references
with small untimed gaps that can slightly inflate miss. Partial `rtfl90` is diagnostic only.

The final 70-second cache path was exercised with public `discussion_rtfl_90s` at 1.0×:
1,439,896/1,439,896 samples accepted/accounted, `final`, 206 rows, 3 speaker IDs. It made
18 preview, 7 rolling, and 1 terminal call; clamped/dropped anomaly rates were 0/18, 0/7,
and 0/1 by kind. Errors, retries, and degraded activations were 0. It sent 589.9935 audio
seconds and cost $0.029552. Word/label p50 visibility was 20.005 seconds over 57/90
observed buckets, again missing the soft 5-second target. This is software integration
evidence, with partial rtfl90 timed reference coverage 60.9/90 seconds; no DER/WER verdict.
Receipt: `/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P63/phase2-public-http-90.json`.

## F3 public replay after W3 and final policy

The paced H1 #3 Javier50 case is software integration evidence, not an accept6 aggregate.
The second replay reported one Live connection, four rolling calls, and one terminal call;
clamped/dropped timing anomalies were **0/1, 0/4, 0/1 calls** respectively. No errors
or retries occurred. It sent 242 audio seconds across overlapping requests and Live
streaming, costing $0.0138433 including a $0.0043333 Live list-price estimate.
Accepted/accounted were **800,000/800,000 samples**. Stop drain
reported `true`; final rendered **one turn** with DER **.019999** and WER **.088496**.
Public-snapshot polling at 250 ms observed preview text in 50/50 one-second buckets;
word p50 was 0.0 s on this coarse bucket metric, while labelled rows appeared in
29/50 buckets at p50 17.263 s. The earlier run's Stop drain missed the deadline,
so this paired replay specifically tests the in-flight promotion. Receipt:
`evidence/P63/h1-fixes-public-javier-after-stop.json`.

That replay preceded D-4: the H1 `settled` capture occurs **before** Stop and had no
idle-ingress drain to wait for. The later D-4 replay below measures settled coverage on
the same public clip without changing the collector.

## D-4: settled work before Stop

A public snapshot now reports **one pending rolling window** while the accepted end exceeds
the successfully revised rolling frontier, including during an in-flight request. Empty
base accounting does not clear that unit. After accepted audio stops advancing for the
rolling stride **S=10 s**, the session's single worker issues a window ending at the accepted
sample and commits its full result. Continuous capture resets the idle clock; Stop still
has its separate deadline-bounded drain.

The paced Javier50 H1 #3 replay proves the collector sees this state: `pre_stop_immediate`
had pending=1 and frontier 30/50 s. It waited **13.374 s** (51 polls) before Stop, then
captured pending=0 and frontier **50/50 s**. Single-case DER changed from **.446 immediate**
to **.063999 settled**; final remained **.019999**. The run made one Live connection, five
rolling calls, and one terminal call, with **0/7 calls** having clamped or dropped timing
words. Cost was $0.0163453, including the Live list-price estimate. Receipt:
`evidence/P63/d4-idle-settle-javier.json`. The 12-pass accept6 result remains pending
pane 6.2; this one case is software integration evidence.

## Decision state

The D-4 pending count and idle drain let H1 measure a genuinely settled pre-Stop surface.
W3 preview, speaker turns, Stop drain, and the selected final identity policy are wired
through Account's public snapshot path. Pane 6.1 still owns the continuity winner; the
current registry is the short-window overlap placeholder. Sparse acquired references
remain diagnostic only.

## Full-suite gate on D-4 commit

On clean `ea2249722422154223970318227ba3377172fc43`, before the growing-window or
voiceprint changes: backend `pytest tests -q` passed **2,460**, skipped 3, xfailed 2,
and passed 37 subtests; frontend `npm test -- --run` passed **313/313** across 28 files;
`npm run typecheck` passed. Existing deprecation warnings only. This is a software
regression gate, not the H1 quality population result.

## L3 capture lanes candidate

The Account mixer still owns one accepted recording clock and canonical mixed stage.
The Gemini engine receives the aligned `system` and `microphone` PCM on that clock.
Separate temporary source tapes supply the per-lane terminal calls and WeSpeaker
voiceprint observations; the mixed stage continues to serve Account audio retention.
The Gemini descriptor raises that stage's bound to 60 minutes, since the old 300 s
manifest bound would make the 302 s E1/M2 terminal passes unavailable.

The system and mic paths each open W3 only on WebRTC-voiced audio and close it
after 60 s quiet. The system keeps growing-context diarized windows, the registry,
and whole-call final policy. The mic transcribes rolling and terminal audio without Gemini
diarization. WebRTC rejects unsupported words; a mic word matching a normalized
system word within ±1.5 s by midpoint is then dropped. Only a surviving mic word
creates the fixed local meeting identity `speaker-microphone`. Several people sharing
the local mic remain one identity. The exact guard applies to timed rolling/terminal
words; W3's untimed provisional text cannot support that exact comparison.

Both lanes have independent provider work and PCM tapes. Rolling keeps one serialized
batch request per meeting; after Stop, up to three final chunks run concurrently.
Their rolling results meet at a synchronized frontier: one
`GeminiRolling` update contains the overlapping source-lane turns and asks
`LiveSession` to advance both `revision_lanes` together. A late independent lane
revision would be refused at `not_at_frontier`. Terminal labels map to live IDs by
sample overlap **within** each lane. The public snapshot retains `source_lane` on
each turn and exposes content-free `engine_diagnostics.lanes` counters.

Offline TDD for aligned PCM, overlapping rows, silent mic call suppression, the
local ID, W3 activation, echo filtering, terminal no-diarization, and lane counters
passed; the full backend gate after L3 passed **2,476**, skipped 3, xfailed 2,
and passed 37 subtests. In paced 302 s HTTPS fixtures, both lanes settled and Stop
finalized. M2 headphones audio produced one mic ID with 21/21 final words inside
operator intervals. E1 speaker audio produced one mic ID but 11/32 final mic words
outside those intervals (34.4%; 21/40 settled, 52.5%). The selected exact echo
guard therefore does not qualify raw speaker echo without browser echo cancellation.
These are two fixtures, not a population estimate; receipts are
`evidence/P63/l3-{e1,m2}-http.json`. For >30-minute recordings, the existing
terminal chunk stitch remains an unqualified candidate: long60 complete truth
falsified POLICY-LONG (DER .328, Bill/Adam false merge, Lex split across three IDs).
Pane 5.3 subsequently revised that policy with a 900 s call cap and timestamp
repair; the new candidate is described below.

## C1+C3 continuity registry candidate

Each system window supplies timed Gemini-local speaker labels. The registry first
groups local labels whose production WeSpeaker vectors agree at cosine ≥0.60 and
whose words do not materially overlap (prototype tolerance 0.15 s). It then maps
those groups one-to-one to existing meeting IDs by maximum word-time overlap with
**committed** prior rows. Where overlap is below 0.6 s, a centroid cosine ≥0.46
can link a returning voice. A wholly unmatched group needs at least 2 s of
Gemini-attributed speech within the window before it gets a displayed ID;
otherwise its words remain unattributed and render as S00. Existing positive
overlap may carry a shorter local label to its known ID. The registry retains
the most recent committed observation and a smoothed centroid per known ID;
it never rewrites a previously committed interval.

The composition root currently sets S=10 s, Lmax=60 s, E=0.46, W=0.60, and H=0.
These are provisional C4 constants until pane 6.1's final verdict. The mic lane
continues to use its one local speaker rule. Deterministic fake windows cover
birth, one-to-one assignment, acoustic return, same-window split, simultaneous
voices, and the committed-frontier boundary. Real paced E1 and Bill receipts
qualify only those public paths; broader C4 quality remains pane 6.1's decision.
The full backend gate on this port passed 2,484 tests, skipped 3, xfailed 2,
and passed 37 subtests.

At 1.0× through Account HTTPS, E1 settled all 302 s with four displayed system
IDs for three true voices; its final pass showed three system IDs and one mic ID.
Its raw speaker echo still caused 14/35 final mic words outside operator intervals.
The 60 s H1 #3 Bill acceptance clip settled and finalized with two system labels:
S01 mostly Bill (52.0 s truth overlap), S02 mostly Lex (3.9 s), and no mic ID
or mic provider call on digital silence. E1 had 1 clamped offset in 64 batch
calls; Bill had 0 anomalies in 7. These are product-path spot checks, not the
six-clip settled-error verdict. Receipts: `evidence/P63/c1c3-{e1,bill}-http.json`.

## POLICY-TIMESTAMPS terminal candidate

Each rolling or terminal batch response first uses the existing parser offset
clamp/drop. The R2 repair keeps Gemini annotation order and every surviving word.
It fixes an interior word longer than 5 s or isolated by >10 s from both valid
neighbours, then shifts a short run after a >10 s jump when an opposite jump
returns near the prior anchor within 30 words. A shift is skipped if it would
leave the call audio or make a word's end precede its start. The adapter counts
repaired words separately from parser clamped/dropped offsets. Rolling and
terminal turn construction preserves annotation order; one-sample projection
keeps the public session's nonoverlapping sample invariant.

The terminal call cap is 900 s. Longer recordings use 30 s adjacent overlaps;
word midpoints assign each final word to one chunk core. Each chunk-local label
gets a production WeSpeaker centroid from eligible attributed spans. Adjacent
labels pair one-to-one by positive word-time co-occurrence, subject to cosine
≥0.65 when both vectors exist and the A-B-A conversational veto. Remaining
eligible label pairs unite by descending cosine with the same veto. The frozen
WebRTC word gate runs after identity; same-speaker words within 1.5 s form turns.
Per-session diagnostics expose `repaired_words` and sticky `chunked=true`, also
broken out by capture lane. The single-call path retains the frozen final
identity policy.

Pane 5.3's **prototype** results on H1 #3 accept6: final DER .104860 unchanged;
complete Lex30m one-call .060764→.038491 after repair, while its T900/O30
stitched candidate measured .032382; complete long60 T900/O30 measured .034568
with five output IDs for five true speakers and no detected false merge. Lex
still occupies two material IDs, so long-form identity remains unqualified.
These are cached-call prototype scores, not fresh product-path quality evidence.
The port passed 81 focused Gemini tests and the full backend gate (2,499 passed,
3 skipped, 2 expected failures, 37 subtests).

## Microphone acoustic echo gate candidate

For each WebRTC-supported microphone word, the gate checks whether the system
lane has any WebRTC mode-1 voiced 10 ms frame in that word span. With no system
voice, it keeps the word. With system voice, it compares microphone RMS with the
loudest equal-duration system RMS at 0–100 ms earlier lags in 10 ms steps and
keeps the word at ≥−15 dB. The existing exact-token ±1.5 s text guard must
also keep it. Both rolling and terminal mic words follow this rule. Public
diagnostics count mic words dropped by the acoustic gate and by the text guard,
per session and microphone lane, without retaining content.

Pane 5.2 measured baseline E1 at **0/19** stray words and M2 at **22/22**
operator words retained with this combined rule on its timed-word bench.
Its harder cases reject a general echo-safe claim: at echo ≥−15 dB, stray words
survive; with operator gain .1, true words are lost. Natural-room performance
is unmeasured.

The real 1.0× E1 Account HTTPS replay on `e7078edc` settled all 302 s and
finalized. The final mic surface had **0/20 stray words** outside the three
operator intervals, with source-phrase recall **7/7, 6/7, 4/5**. The earlier
product run had 14/35 stray final words; its word population differs, so this
is a product-path before/after observation rather than a paired-word test.
The settled mic surface had 0/21 stray words and recall 7/7, 7/7, 4/5.
Diagnostics reported 5,395 acoustic drops and 10 text drops; growing
overlapping windows can evaluate the same word repeatedly, so these are
gate decisions, not unique source words. One offset was clamped and two words
were timestamp-repaired across 64 batch calls; none were dropped by the parser.
Provider errors, retries, and skipped ticks were zero. Reported cost was
$0.251995 including the $0.050667 Live list-price estimate. Receipt:
`evidence/P63/echogate-e1-http.json`.

## Separate short microphone batch windows

The microphone lane now uses its own recent L30/S15 window schedule. Pane 6.1's
C4 verdict sets the system default to growing S15/Lmax180, H0, with the already
selected C3 WeSpeaker thresholds E=.46/W=.60 and the 2 s speaker-birth rule.
Mic windows have diarization off. The engine calls Gemini only when audio newly
covered since the prior mic window contains WebRTC voice. An old utterance in
the 30 s overlap cannot reopen a quiet stride; silent strides still advance
the lane and shared meeting frontier. W3 remains lazy on first voiced audio in both lanes.

Idle and Stop drains send only the unrevised suffix `[rolling frontier,
accepted end]`, matching P61's exact C4 Stop calls rather than repeating the
full 180 s context. The provider-free production-scheduler probe uses E1's
observed batch unit cost and Live list-price estimate. With selected system
S15/L180 and mic L30/S15, a 302 s E1-shaped meeting models
**$2.040 per audio-hour system + $0.832 mic = $2.872 total**. For an hour with
both lanes continuously voiced, the same plan models **$2.598 system + $0.846
mic = $3.444/hour**, including the existing 900 s/30 s terminal chunk cost.
Thus the $3 target passes this short E1 model and fails for continuous
long-form speech. These are modeled dollars, not a new provider bill.
The C4 **offline recorded-response prototype** measured accept6 H1 #3 settled
ruled/raw DER .098518/.108748, E1 first displayed 3 system/4 mixed IDs,
complete Bill30m 2/2 IDs at DER .056321, and complete long60 5/5 IDs at first
DER .048287. Its Bill label lag p50 was 17.845 s and system batch+Live cost
was $2.345/h; that cost excludes the per-meeting terminal and mic costs
included in this model. Product-path qualification remains pane 6.2's run.
One-command state: `python prototypes/gemini-runtime/mic_window_cost.py`.

## Paced long-form lag and provisional echo

The paced long60 receipt on `6c5776e3` exposed rolling work that sometimes
outlasted its 15 s stride. In the first 600 s, 39 windows committed with one
skipped tick; label delay grew while the worker was busy. P61's cached 180 s
provider calls had 10.367 s median latency on 29 full windows there. A
production ONNX probe of two labels with three attributed spans each took
5.574/4.969 s with serial embedding and 2.719/2.645 s with three existing
interval workers, with zero vector difference. The composition root now uses
three workers. A 1.0x HTTP replay of the first 600 s of public long60 then
lowered label p50 from 26.761 to 18.262 s and p90 from 37.508 to 25.015 s;
skipped ticks fell from one to zero. The before run was part of continuous
long60 and labeled 597/600 one-second buckets; the standalone after run
labeled 583/600. The coverage difference and the unmeasured full-meeting lag
remain limits of this latency verdict. P63 retains both receipts.

The E1 browser receipt showed two provisional S00 lines for one 60–70 s phrase.
Both system and microphone W3 streams were open, and the text differed mainly
in capitalization and spacing. The lane composer now removes a temporally
overlapping near-identical preview phrase, preferring the system lane in an
echo tie. Distinct simultaneous microphone speech remains visible. Rolling and
terminal text authority is unchanged; a public LiveSession snapshot regression
checks the two cases.
