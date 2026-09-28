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
3. `gemini_hybrid_engine.py` keeps a bounded 70-second, 2.24 MB live PCM cache for window
   requests: a 60-second window can end up to 10 seconds behind current capture because
   windows end on stride boundaries. The Account stage supplies full audio at Stop. Its measured W3 `GeminiLiveWordSource` streams accepted audio to
   `gemini-3.5-transcribe-live` with TEXT, 500 ms automatic silence detection,
   a 2 s Stop flush and 5 s buffered replay on bounded reconnect. It feeds preview
   only. The legacy batch source remains available for isolated tests. Its
   `FixedWindowScheduler` asks for up to 60 seconds every 10 seconds, with a 10-second
   holdback. Warm-up windows start at 20 seconds. Its `OverlapRegistry` uses a Hungarian
   word-time co-occurrence assignment to keep IDs stable as Gemini changes local labels.
   Unmatched voices get new `speaker-NNNN` IDs. The registry interface accepts
   `embeddings` so the measured C3 policy can consume the same WeSpeaker vectors.
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
USD cost, degraded activations, and window/preview lag p50/max. The frontend ignores the
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
