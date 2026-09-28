# P52 provisional words: prototype contract

## Structural question

Can a public, real-time audio stream produce prompt provisional words while preserving every spoken passage across normal turns and long-session reconnects? Compare Live transcription with repeated batch tail transcription before choosing the words source.

## Minimum primitives

- **Audio cursor:** cumulative samples accepted from the 16 kHz PCM stream. It is the sole source of audio time and gap accounting.
- **Turn/window:** a bounded portion of that cursor submitted to a model. Live turns and batch windows are alternate ways to make words visible.
- **Word update:** text plus the earliest and latest audio time it may describe, receipt wall time, and finality. This makes latency and replay auditable.
- **Connection epoch:** one Live socket lifetime plus its resumption handle. Reconnect must account for every sample sent during a failed epoch.

Removing any one loses the ability to establish either timeliness, completeness, or continuity. Model configuration and storage are replaceable details.

## Invariants

1. Input is public 16 kHz mono PCM16, paced at 100 ms per push. Sent samples and any unacknowledged/replayed interval are explicit.
2. Each update is attributable to an audio interval; text arrival and audio time share a monotonic clock.
3. A connection failure cannot silently advance the accepted audio cursor. A gap is reported if recovery cannot prove coverage.
4. Scoring uses the same reference and production metric path for all arms; provisional speaker labels are collapsed to one.
5. Real-time latency claims require 1.0× send pacing. Cached or accelerated runs are labelled separately.

## Assumptions and unknowns

- Live SDK event semantics for partial versus final input transcription, manual turn coverage, GoAway, usage, and resumption are **unknown** until observed.
- The audio time represented by an untimed Live text event is an interval bound from the send cursor/turn, not a word timestamp.
- Reference turns may be coarse; any per-second coverage latency derived from lexical matching is approximate.
- The soft $25 lane cap and 2-session simultaneous limit constrain the matrix. Failed arms are parked after the brief's attempt limit.

## Hypotheses and falsifiers

- **H1:** A Live arm yields lower p50 word latency than rolling batch while retaining all reference passages. Falsified if W4 is within 1 s of the best Live arm at no greater cost.
- **H2:** Manual turns bound latency without losing between-turn audio. Falsified by a timed uncovered reference passage or missing sent samples at a turn boundary.
- **H3:** A resumed long Live stream preserves every audio interval. Falsified by an unrecoverable cursor gap, duplicate interval, or passage loss around reconnect.

The winner must have zero dropped passages and WER no more than 0.03 above the best measured arm; then lowest p50 latency wins.

## Tool decisions

- Inspect installed `google-genai` types and existing shared helpers to bind the real SDK calls and billing fields; a mismatch changes the runnable configuration.
- A one-command throwaway runner will print every send interval, model event, usage observation, and scored per-clip outcome. These observations choose the arm; a cached simulation cannot choose latency.
- The production scorer gives comparable WER. A reference-time overlap audit exposes passages WER alone can hide.
- A single full-clip batch word-timestamp pass on the same public clip will anchor the Live lexical first-appearance clock more precisely than uniformly spreading words across broad human reference turns. If it changes the W1/W3 latency order, retain both estimates and investigate; its model-generated offsets are not human ground truth.
- A 30-minute paced run on a surviving arm is necessary to test session expiry, GoAway, and recovery; short clips cannot answer it.
- A two-session paced run tests whether the documented capacity limit throttles provisional words.

## Run and verdict

The one-command probe is `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/words/proto_words.py --arm w1 --clip mono_javier_intro_50s --thinking 0 --max-output 1 --silence-ms 200 --tail-silence 2 --output /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52/w1-javier-cap1.json`. It prints every event and full scored state unless `--quiet` is given. `run_suite.py` runs accept6+alphabet and appends per-clip status.

### Initial one-clip probes (superseded by corpus comparisons below)

| Arm/config | Sent | WER | Word timing | Cost observation | Caveat |
|---|---:|---:|---:|---:|---|
| W1 auto VAD 500 ms, thinking 0, output cap 32 | 50/50 s | .3451 | 5 pause chunks; last 11.4 s unpublished after 8 s drain | no usage event | tail not flushed |
| W1 auto VAD 200 ms, thinking 0, no cap, 2 s silence | 52/52 s | .3805 | lexical first-appearance p50 ~4.77 s | $0.006495 from one usage event | 1,217,764 model audio bytes despite silence prompt; total cost unmeasured |
| W1 auto VAD 200 ms, thinking 0, output cap 1, 2 s silence | 52/52 s | .07965 | uniform-reference first-appearance p50 ~5.08 s | $0.004397 from one usage event after corrected pricing | 0 model audio bytes; selected W1 config |
| W2 manual 2 s | 50/50 s | .4602 | lexical first-appearance p50 ~3.43 s | $0.001086 from one usage event | too many word errors |
| W3 auto VAD 500 ms, no tail flush | 50/50 s | .08850 | interim updates ~0.5 s cadence | no usage event | selected config adds 2 s tail; later Javier run WER .07965 |
| W3 manual 2 s / 5 s | 50/50 s each | .4690 / .4602 | interims present; lexical p50 ~2.94 s at 2 s turns | no usage event | forced turns lose/corrupt words |
| W4 batch 8 s / 2 s, uncached | 50/50 s | .14159 | Gemini word timestamp to arrival p50 2.285 s | $0.00945; $0.6804 per meeting-hour extrapolation | window stitching and timestamp anomalies to audit |
| W4 batch 15 s / 3 s, partly cached | 50/50 s | .14159 | p50 3.532 s (cache-biased) | $0.010982 uncached calls | not a latency selector |

The W1/W3 lexical timing estimate places reference words uniformly inside the corpus's broad reference turns; it is not forced alignment. The first harness latency (`arrival - latest sent audio sample`) is only a lower bound and can be negative, so it cannot select the winner. W4 timing uses the batch model's word offsets and actual response time. W4 runs now disable cache reads.

### Long-session and reconnect evidence so far

W3 unresumed on public `benchmark_30m:acquired_jamie_dimon`: GoAway at audio 540 s with `time_left=50s`; socket aborted with code 1008 at 590.1/1800 s. No resumption handle or usage event appeared. The successful automatic-rotation runs are reported below.

The Developer API refuses `SessionResumptionConfig(transparent=True)` in the installed SDK; its consumed-message index is Enterprise-only. W3 produced no ordinary handle either. A forced 25 s new-session rotation on the public 50 s clip, with buffered 2 s replay, yielded WER .16814 and 0.770 s no-update hole. Buffered 5 s replay yielded WER .10620 and 0.874 s hole. Exact repeated interim events suppressed: 13 versus 19. Both sent 50/50 s and had five final chunks. A model word offset is absent, so the duplicate suppression compares exact text within inferred audio intervals; residual duplicate/loss must be scored from the transcript and the rolling window repairs the provisional path.

**Reconnect boundary audit contract.** The structural question is whether the 30-minute stream's three rotations visibly lose or repeat speech despite complete audio send accounting. Minimum primitives: the audio-time reconnect boundary, a local timestamped batch transcription of retained audio, and the Live final text spanning that boundary. Invariant: compare the same public audio seconds and preserve the raw hypothesis. Unknown: batch transcription itself can err, and Live words have no timestamps. Falsifier: missing batch words near a reconnect, or repeated Live phrases, would refute clean provisional continuity. Tool decision: transcribe a short retained-audio context at each boundary and align its central words to nearby Live final text; three small batch calls give a boundary-specific proxy that the sparse 30-minute human reference cannot provide. The result will not certify D6, which is owned by rolling and terminal passes.

The first 30-minute public acquired-Jamie run sent all 1,800 s, rotated after GoAway at audio 540.0/1080.2/1620.6 s, and replayed the preceding 2 s. No resumption handle or consumed index appeared. Connection pauses were .196/.360/.414 s; the wall-clock holes between visible updates were 1.396/1.322/.905 s. Across all 3,173 emitted updates, 397 exact duplicate interim events were suppressed. The local 30 s batch context audit found 27/43, 29/41, and 20/27 central ±5 s model words matched to nearby Live finals; longest contiguous missing runs were 2.7, 3.0, and 1.8 s respectively. No adjacent final-chunk phrase repeated at the three boundaries. This is a model-to-model proxy, and the acquired-Jamie 30-minute human reference covers only 374/1,800 s. The forced Javier50 pair is a stronger direct mitigation comparison: 2 s replay omitted eight consecutive words that 5 s replay retained; their WERs were .168142 and .106195, respectively, with .770/.874 s on-screen holes and no repeated final phrase.

The second 30-minute public lex-Bill run has a **complete 1,800/1,800 s human reference**. With 5 s replay it sent 1,800/1,800 s and scored WER `.163589`; 3,144 visible updates, 144 finals, and 529 exact interim duplicates suppressed. GoAway rotations at audio 540.0/1080.3/1620.7 s had no handle; connection pauses were .248/.365/.213 s and on-screen no-update holes were .929/1.183/1.240 s. The local batch boundary proxy matched 39/41, 34/34, and 32/32 central ±5 s words. At the first boundary, two isolated function words were unmatched (model spans .2/.1 s); at the third, an adjacent final phrase repeated two words (`people start`). All three 30 s audit calls had zero timing anomalies. The exact consumed-audio boundary remains unknown, so the 5 s replay interval is an explicit uncertainty record, not a proof of zero loss. The paired forced Javier test and this long result support **5 s as the provisional replay default**. The rolling diarized windows and terminal pass, which read the retained tape, own completeness in the hybrid design.

The measured **on-screen no-update hole** is the wall time from the last visible provisional update before each reconnect to the first afterward; its worst observed value with 5 s replay was 1.240 s. A missing provisional word may remain absent until a rolling committed row replaces it. P52 did not measure that end-to-end correction delay; the separate window pane's L30/S10/H5 candidate is a schedule, not an observed repair-time guarantee.

`WordStream` records replay uncertainty before reopening a failed socket, includes a failed-send chunk in the replay interval, and retries a failed final stream-end send. Injected send-failure checks covered both audio and stream-end sends with one 100 ms chunk. Exact-text suppression requires **strictly overlapping** inferred audio intervals: a repeated word at the next turn boundary is retained, while a repeat in the same interval is suppressed. These are local prototype checks; the long lex run started before these edits and tests the prior ordinary GoAway path.

The initial probes led to paced accept6, extended, manual-turn, L/S, and long-session measurements below.

### W4 stitching falsification probe (pre-registered after 5-minute receipt)

**Structural question:** does W4's 0.5729 WER on `acquired_alphabet` reflect batch transcription quality or repeated words admitted when overlapping windows disagree slightly on offsets? **Minimum primitives:** an absolute word interval and an ordered publication frontier; no model-specific labels. **Invariants:** one audio-time occurrence is published once, real-time arrival cannot be moved earlier, and every alternative uses the exact same saved 150 window responses. **Unknown:** the reference may omit words; word-offset jitter may exceed 0.5 s. **Falsifier:** if near-time duplicate suppression or a 2 s maturity delay does not materially reduce WER without creating uncovered speech seconds, the W4 quality loss is not this stitching policy. **Tool decision:** replay saved public-window receipts with these two single-variable alternatives; no new provider call, and the W4 selection/cost decision changes only if WER improves enough to enter the 0.03 quality band.

**Result and reference correction:** baseline 872 words/.5729 WER; near-time dedupe 849/.5330; 2 s maturity 863/.5469 and p50 latency 3.035→5.117 s. The full 300 s Gemini batch pass has 808 words/.4514 WER against the same human file. That file holds only 45 selected transcript lines and 78.9 s summed segment duration (122 occupied one-second buckets), with line indices 2, 25, 37, 38, and 44 missing. Thus its full-clip WER is **not a valid 300 s quality metric**. Use the clip for paced longevity and latency, and show any lexical score as a sparse-reference diagnostic. The W4 stitch alternatives stay prototype-only; neither resolves the mismatch.

### Reference custody correction (lead common/corpus.py a9634449)

H1 #3 scored accept6 against manifest sha `80fc15bd…`; the current worktree had later-corrected Bill Ackman and Keyu Jin references. The shared corpus now points all six cases at manifest-matching H1 files materialized from git `966d250b^`; all six hashes were verified by the lead. I re-scored saved W1/W4 hypotheses without provider calls. On the **H1 truth set**, accept6 macro WER is W1 `.150109` (was `.141402` against the later references) and W4 `.160538` (was `.147370`). Bill changed W1 `.178161→.193182`, W4 `.218391→.255682`; Keyu changed W1 `.034722→.071942`, W4 `.159722→.201439`; the other four were unchanged. `suite-comparison.json` retains receipt WER and current re-scored WER per clip. All subsequent verdicts use the H1 truth set.

Reference timing coverage is not a quality gate by itself: `benchmark:acquired_nfl` has a 16.9 s music interval represented by an empty-text reference segment, so its roughly 40 occupied speech seconds in a 60 s clip are expected. The scorer's explicit sparse-reference exclusions are only the lead-confirmed `benchmark_5m:acquired_alphabet` and `benchmark:acquired_jamie_dimon`; timing fraction remains a diagnostic. This avoids discarding clips because they contain silence or music.

Lead corpus ruling: gold9 `benchmark:acquired_jamie_dimon` 12.3/60 s is diagnostic only; `acquired_nfl` 52.9/60 and `acquired_rolex` 51.1/60 are near-complete and usable, with small untimed gaps that can inflate miss. Gold9 lex clips are complete; 3-minute calibration Jamie 179/180 and Adam 180/180 are complete, Shapiro 152.5/181 mostly complete. The `discussion_rtfl_90s` acceptance fixture has only 60.9/90 s timed reference and is partial, but remains in the fixed H1 #3 accept6 primary macro for comparison to that benchmark. Qualification aggregates use accept6 primary, gold9 minus only 1-minute acquired Jamie, the three complete lex 5-minute clips, and complete 30-minute lex Bill Ackman.

### Accept6 primary result (H1 #3 truth set, paced 1×)

| Arm | 6-clip macro WER | Uncovered reference seconds | Word arrival | Observed cost | Timestamp anomalies |
|---|---:|---:|---|---|---|
| W1 3.8 Live AUDIO, auto VAD 200 ms, thinking 0, cap 1 | .150109 | 0/608 by ±3 s proxy | batch-oracle anchored per-clip p50 1.586–5.734 s | $0.005381 over 7 base clips; only 1/7 complete usage | n/a |
| W3 3.5 Transcribe Live TEXT, auto VAD 500 ms | **.135347** | 0/608 by ±3 s proxy | batch-oracle anchored per-clip p50 .648–.752 s | $0 observed; 0/7 complete usage, true cost **UNMEASURED** | n/a |
| W4 batch tail 8 s every 2 s | .160538 | 0/608 by ±3 s proxy | batch word-offset to arrival per-clip p50 2.336–3.098 s | $0.180720 for 920 s of source audio = $0.707/meeting-hour | 49/460 calls; 49 clamped, 1 dropped-offset word; 0 call errors |

The sparse acquired-alphabet 5-minute clip was also sent at 1× for each arm; its WER is diagnostic: W1 .486111, W3 .501736, W4 .572917. All accept6 paths in `suite-comparison.json` are `.cache/h1-references/...` from the H1 #3 manifest. The ±3 s uncovered-seconds check uses inferred Live event intervals and broad human turns, so it is a passage-presence proxy, not proof of D6 completeness. The W3/W1 first-appearance clock uses batch model word offsets aligned to reference tokens; W4 uses its own batch word offsets. The observed Live usage metadata does not qualify cost/min or the $3/hour soft bar.

The W3 base receipts expose 1,681 `interim_input_transcription` updates and 79 final `input_transcription` chunks across 920 s of source audio. WER uses the finals; on-screen latency uses first appearance in the interim stream. There were no resumption handles and no Live errors on these seven short/medium clips.

On Javier50, four uncached W4 grids gave: 8/2 WER .141593 and p50 2.285 s ($.6804/hr), 8/3 .132743 and 3.182 s ($.4668/hr), 15/2 .159292 and 2.856 s ($1.1772/hr), 15/3 .141593 and 3.125 s ($.8124/hr). Anomalous calls were 3/25 (8/2 base receipt), 3/17, 1/25, and 0/17 respectively. The fastest W4 variant trails W3 by more than 1 s, so the stated falsifier for needing Live is not met on this clip even before cost comparison.

### Extended quality evidence

The W4 8/2 extended paced suite completed 12/12 gold9 plus complete lex5m clips. Its qualified macro WER is `.179901` over 11 clips; the sparse 1-minute acquired Jamie diagnostic is `.906780` and excluded. The three complete 300 s lex cases score Bill `.163420`, Keyu `.109439`, Javier `.150628`. All 901 window calls returned successfully; 98/901 calls had invalid word offsets, with 99 clamped words and three dropped-offset words. The measured bill is `$0.355002` for 1,800 s of source audio, or `$0.710/meeting-hour`. Per-clip anomaly rates and reference paths are in `suite-comparison-extended.json`.

W1 extended completed 12/12: qualified 11-clip macro WER `.133788`, versus W4 `.179901`. On the complete 300 s lex clips W1 scored Bill `.089827`, Keyu `.079343`, Javier `.087866`; zero model-audio bytes across all 12 and no Live errors. Its qualified per-clip batch-oracle anchored first-appearance p50 ranges from 1.926 to 5.771 s (median of clip medians 4.195 s). Observed usage metadata totals `$0.010245` but 0/12 clips have a complete usage receipt; true W1 cost is unmeasured.

W3 gold9 completed 9/9. Excluding only sparse 1-minute acquired Jamie, the eight-clip WER macro is W3 `.135191`, W1 `.151828`, W4 `.194427` on identical references. Median of the eight per-clip word-arrival p50 values is W3 `.686 s` and W1 `4.451 s` using batch-derived word anchors; W4's own word offsets give `2.563 s`. All W3 gold9 sends completed without Live errors or model audio, but usage remained absent.

## Final words-source verdict

**Select W3 `gemini-3.5-transcribe-live` TEXT, auto VAD 500 ms, 2 s tail flush, and 5 s buffered replay on reconnect** for provisional unlabelled words. It has the lowest measured first-word latency and the lowest macro WER on both the H1 #3 accept6 primary set and the 11 usable extended clips. The reusable prototype interface is `words_stream.py`; the retained audio tape and rolling/terminal Transcribe passes own committed completeness. This is a words-source prototype result, not an end-to-end hybrid or cost qualification.

| Arm | H1 #3 accept6 macro WER, 6 clips | Extended macro WER, 11 usable clips | Median of extended per-clip p50 word arrival | 300 s lex macro WER, 3 clips | Cost evidence | Offset anomaly calls |
|---|---:|---:|---:|---:|---|---|
| W1 3.8 Live AUDIO, cap 1 | .150109 | .133788 | 4.195 s (batch word anchor; 4,407/4,764 human words) | .085679 | $0.010245 observed, 0/12 clips usage-complete | n/a |
| **W3 3.5 Transcribe Live TEXT** | **.135347** | **.126486** | **.692 s** (batch word anchor; 4,429/4,764 human words) | .103273 | $0 observed, 0/12 clips usage-complete; **true cost unmeasured** | n/a |
| W4 batch 8 s every 2 s | .160538 | .179901 | 2.827 s (own word offsets) | .141162 | $0.355002/1,800 s = **$0.710/meeting-hour** | accept6+alphabet 49/460; extended **98/901** (99 clamped, 3 dropped-offset words) |

The extended set is eight gold9 clips plus three complete lex5m clips. `benchmark:acquired_jamie_dimon` is sparse and excluded; the fixed accept6 macro retains its partial rtfl90 fixture. Each arm had 0/1,691 uncovered usable-reference speech seconds under the ±3 s interval proxy, which cannot prove word-by-word completeness. W4 had 0/901 extended call errors. W1 and W3 had no Live errors or model-audio output on the extended set, and two simultaneous Live sessions showed no throttling in these runs. W3's extended per-clip anchored p50 ranges `.658–.747 s`, with median of per-clip p90 `.965 s`; the anchor is a separate batch model's word timestamps aligned to human text, not human forced alignment.

The winner rule's 0.03 WER band is satisfied by W3 and W1 on the primary and extended sets. W4 is `.0534` above W3 on the extended set, outside the band. On the paired paced Javier50 latency comparison, fastest W4 8/2 p50 `2.285 s` trails W3 `.714–.752 s` by more than the 1 s falsifier threshold; thus the stated falsifier for needing Live was **not met**, regardless of the unmeasured Live price. The W3 30-minute complete lex-Bill run scored `.163589` WER with three recovered GoAway rotations and at most a 1.240 s on-screen no-update hole, but exact provider-consumed audio and time until rolling correction remain unmeasured. Live cost/min and the `$3/meeting-hour` soft gate are unqualified because Live usage metadata was absent or incomplete.

Manual turns are parked: on the same Javier50 public clip, W2 N=2/3/5 s scored `.460/.549/.478` WER and W3 N=2/3/5 s `.469/.522/.460`, versus W3 auto `.080`; all sent 50/50 s, but W2 N=5 also had one uncovered second and emitted 99,844 model-audio bytes. W4 overlap-stitch alternatives were only useful on the sparse acquired-alphabet diagnostic and did not change the winner.

## F0 — Robustness follow-up: measurement contract (2026-09-28)

**Structural question:** When the provisional W3 Live words stream receives non-speech, an echoed microphone mix, or two simultaneous speakers, which visible words reflect real speech and which failure persists until the rolling diarized pass corrects it?

**Minimum primitives:** the retained mono audio tape with known sample time; an input condition (generated non-speech, public single-speaker reference, E1 synthetic microphone mix, or two public references); the W3 visible interim and final text events; and, for overlap, a batch transcript of the identical mix. Audio time separates genuine signal from quiet intervals; references provide a denominator where they exist; final text and first appearance distinguish provisional display from committed words. None supplies word-accurate timing for Live, so event-time claims remain bounds.

**Invariants:** send PCM16 mono at 16 kHz in 100 ms chunks paced 1.0×; hold model, auto-VAD 500 ms, and tail flush fixed while changing only language hint or input condition; compare overlap arms on byte-identical mixtures; count false words only where the audio truth is known silent/non-speech; call E1 words descriptive because there is no transcript reference. The H1 #3 accept6 reference set is primary.

**Assumptions and unknowns:** synthetic white/pink noise and chord/rhythm are controlled falsifiers, not field music; the E1 operator lane is a synthetic corpus voice; Live has no word offsets and still lacks complete usage metadata, so true cost and exact word onset remain unmeasured. An `en-US` hint could suppress foreign-script errors or could damage legitimate words. A VAD gate is a candidate policy only after measured false-positive removal and real-speech retention.

**Falsifiers:** a language hint fails if it leaves hallucinations or materially worsens H1 accept6 WER; a gate fails if it cuts real words; W3 overlap fails if it loses the quiet reference words at −10 dB while batch retains them; echo tolerance fails if the E1 mix adds repeated phrases or suppresses the three known utterances. A bounded provisional error is tolerable only with a measured correction path and duration.

**Tool decisions:** use the existing `proto_words.run_live` production-path configuration and shared corpus/score helpers for paired Live calls, the shared `diarize_window` for the identical overlap mix, and deterministic local PCM generation for non-speech. These calls change whether to recommend a language hint, VAD gate, or overlap caveat. Limit this follow-up to $3; absent complete Live usage, also bound the number and duration of calls and report cost as unmeasured.

After the baseline batch −10 dB mixture retained 0 distinctive Keyu bigrams, two one-variable batch probes were registered: an `en-US` hint with diarization unchanged, and diarization off with language auto. If either recovers quiet words, that simple configuration could mitigate overlap; otherwise the mono mixture remains an unresolved source-separation problem. Each is one 60 s public batch call.

The actual rolling-window candidate from P53 is 30 s length / 10 s stride. Before claiming the quiet voice cannot be filled by rolling correction, probe those four windows on the same mixture and count a quiet reference bigram as present if it appears in any window. This is an optimistic union bound rather than stitched output; zero recall would falsify rolling recovery on this example, while positive recall would require a stitching test.

### F1 — Non-speech and inserted gap (paired paced W3 Live)

Eight 60 s non-speech signals—digital zero; white and pink noise each at full-scale RMS `.0003`, `.0010`, `.0030`; and a synthetic chord/rhythm at RMS `.018`—were each sent with auto language and `en-US`, 100 ms PCM chunks at 1.0× plus a 2 s tail. **All 16 calls emitted 0 interim words and 0 final words: 0 hallucinated visible/final words per minute.** No foreign-script output appeared. This differs from the separate batch model's `2`/`好的。` generated-signal hallucinations; it does not prove immunity to real music or other noise.

A public Javier 50 s clip with 20 s of digital zero inserted at audio 25–45 s also had **0 updates in the central 29–42 s gap** in both language modes. The last pre-gap final appeared at audio 25.9 s; new speech first appeared at 46.3 s (auto) or 45.8 s (`en-US`). Both produced 108 final token units and `.079646` WER against the H1 #3 Javier reference with times shifted after the inserted gap. The original W3 `en` Javier50 receipt scored about `.080`; this gap did not create a dropped passage or measurable quality loss. Exact Live word onset is unavailable.

**Verdict:** no VAD gate or language hint is justified by these controlled non-speech results alone. The two modes are identical on this cohort; accept6 determines whether `en-US` affects real speech. Receipts: `evidence/P52/robust-live-{case}-{auto,en-US}.json` and `robust-manifest.json`.

### F2 — Language hint on H1 #3 accept6

Six public acceptance clips were rerun at 1.0×, with only `language_codes` changed between omitted (auto) and `["en-US"]`; model W3, 500 ms auto VAD, and 2 s tail were identical. References are the manifest-matching H1 #3 set in `common/corpus.py` (the 90 s rtfl fixture remains partial but is part of this fixed primary population).

| Clip | Auto WER | `en-US` WER |
|---|---:|---:|
| Jamie 180 s | .085366 | .081882 |
| rtfl 90 s | .160194 | .165049 |
| Adam 180 s | .143126 | .143126 |
| Bill 60 s | .227273 | .227273 |
| Keyu 60 s | .122302 | .115108 |
| Javier 50 s | .061947 | .079646 |
| **Macro, six clips** | **.133368** | **.135347** |

All 12 sends completed, no Live errors or model audio; none had a complete usage receipt. The prior selected W3 `en` baseline is also `.135347` on the same H1 population, from earlier calls. The `en-US` hint neither suppressed a hallucination in this test (auto already had zero on its eight non-speech minutes) nor improved macro WER. Its +`.001979` WER over auto is small, with one larger Javier regression and modest Jamie/Keyu gains. **Verdict:** keep the existing W3 configuration; no evidence supports adding an `en-US` hint as a robustness policy. Actual Live spend remains unmeasured.

### F3 — Simultaneous public voices; rolling correction falsifier

The complete gold9 60 s Bill and Keyu clips were RMS-matched, summed to mono, and sent at equal level or with Keyu 10 dB quieter. W3 Live used `en-US` in both cases; batch Gemini 3.5 Transcribe saw the byte-identical whole 60 s mixtures with diarization and word offsets. Each human reference is complete. **Word fraction** below is the longest common subsequence (LCS) count over each voice's ordered reference words and the combined output. It is optimistic because shared words such as “the” can be credited to both voices. The **distinctive two-word phrase** fraction excludes phrases occurring in the other reference and is the stronger voice-presence check.

| Mix / method | Bill words | Keyu words | Bill distinctive phrases | Keyu distinctive phrases |
|---|---:|---:|---:|---:|
| Equal / W3 Live | 59/176 (33.5%) | 75/139 (54.0%) | 39/168 (23.2%) | 51/131 (38.9%) |
| Equal / whole-clip batch | 113/176 (64.2%) | 72/139 (51.8%) | 83/168 (49.4%) | 51/131 (38.9%) |
| −10 dB / W3 Live | 124/176 (70.5%) | 39/139 (28.1%) | 103/168 (61.3%) | **17/131 (13.0%)** |
| −10 dB / whole-clip batch | 159/176 (90.3%) | 23/139 (16.5%) | 139/168 (82.7%) | **0/131** |

At −10 dB, the default batch call, an `en-US`-hinted batch call, and a no-diarization batch call each found **0/131** distinctive Keyu phrases. The actual P53 rolling candidate (30 s window, 10 s stride) was also probed at ends 30/40/50/60 s: an optimistic union of all four transcripts found Keyu **0/131** at −10 dB (Bill 138/168); at equal level it found Keyu 87/131 and Bill 104/168. That optimistic union overstates any stitcher's output, so zero is a strong failure signal for the rolling correction path on this mixture. The whole-clip batch call is also a terminal-pass proxy and did not recover Keyu. One of 12 batch overlap calls had a timestamp anomaly (one clamped word in equal-level whole-clip batch); none dropped a word by invalid offset. All Live sends and batch calls completed without reported errors.

**Verdict:** W3 displays a short Keyu fragment at −10 dB, but the proposed same-mono rolling and terminal Gemini passes cannot be credited with filling this quiet voice on the measured example. The independent Keyu 60 s W3 gold9 receipt scored `.129496` WER, showing the source is transcribable when separate. The smallest supported recovery is to **preserve and transcribe physically separate input lanes before summing, wherever lanes exist**; that does not solve two voices already mixed on one lane. For that case, mark quiet-overlap completeness **UNRESOLVED** and retain the audio for review; source separation or another overlap-specific method needs its own measured prototype. Do not claim D6 no-dropped-passages from the rolling/terminal path on this condition.

### F4 — E1 delayed echo and three synthetic operator utterances

The public E1 fixture's 302 s `system.wav` and `E1-microphone.wav` were summed sample-for-sample at their fixture gains into one PCM16 mono stream (0 clipped samples). The microphone contains −25 dB delayed system echo, noise, and three 3 s corpus utterances at 30/135/248 s. System-only and mixed W3 Live calls used `en-US`, 500 ms auto VAD, 1.0× pacing, and 2 s tail. E1 has no human system transcript, so **no WER is asserted**.

| Stream | Final words / 302 s | Words/min | Nearby repeated four-word phrases / opportunities |
|---|---:|---:|---:|
| System only | 808 | 160.53 | 1/805 (0.124%) |
| System + E1 mic | 833 | 165.50 | 1/830 (0.120%) |

The one repeated phrase, “so we want to,” occurs in both outputs. Thus the echo did **not** measurably double phrases under this local definition (same four-word phrase repeated within 20 tokens), despite 25 more total words in the mix. Different ordinary transcript wording accounts for some total-word difference; the 25 cannot all be assigned to the mic.

The synthetic mic voice is drawn from the public Keyu clip. Its complete human transcript contains these phrases; the fixture gives utterance start/duration, not human word offsets. Counts below are distinctive phrase bigrams in the final transcript, compared with the system-only control:

| Mic at | Human source phrase | System only | Mixed | Assessment |
|---|---|---:|---:|---|
| 30 s | “they think that they're responsible for you” | 0/6 | 0/6 | Not recovered |
| 135 s | “deference to authority is not blind submission” | 1/6 | 1/6 | No mic-specific gain; shared incidental phrase |
| 248 s | “in exchange for some deference” | 0/4 | 3/4 | Partially recovered as “An exchange for some deference” |

The third phrase appeared only in a final chunk ending at sent-audio 272.5 s, roughly 24.5 s after utterance onset, and did not appear in the nearby interim updates. The first two source phrases were not detected in mixed output. The separate 3 s echo-free mic batch probes returned 8/7/6 words and 0 timing anomalies in all three calls; they are a model cross-check, not an independent human timed reference. **Operator outcome: two lost, one partial and late.** This is a provisional mono-stream failure, not an echo-doubling failure.

There is no long natural E1 silence: WebRTC VAD mode 1 on 10 ms frames found 0 stretches ≥2 s in both tracks (longest unvoiced run 0.84 s system, 0.73 s mixed). To make the requested silence test measurable, a derived 60 s E1 excerpt inserted 20 s of digital zero between its first and second 20 s of speech. It produced **0 interim/final updates in the central audio 24–36 s gap**; last pre-gap final ended at audio 21.0 s and next speech appeared at 41.3 s. This supports no hallucination on the controlled E1 gap, while natural E1 silent-stretch hallucination remains unmeasured because that condition did not occur.

**Verdict:** do not rely on one mixed mono W3 stream to expose brief overlapping microphone speech; two of three known utterances were absent. Where separate system/mic lanes already exist, retaining and transcribing them before mixing is the smallest supported candidate; the measured echo-only duplication rate gives no reason for an echo-specific dedupe rule. All three E1 Live sends completed without reported errors; actual Live cost remains unmeasured. Receipts and exact text are in `evidence/P52/robust-analysis.json` and `robust-live-e1_*.json`.

### F5 — Follow-up decision and limits

**Keep W3 for provisional single-stream words, with its existing language setting.** The controlled silence/noise/music cohort and both inserted gaps produced no visible hallucinations, so a VAD gate and `en-US` hint have no measured benefit. The earlier W3 WER/latency selection stands for its qualified corpora.

**Mixed concurrent speech is a qualification gap, not a cosmetic transcript issue.** On E1, two of three known mic utterances disappeared from the mono mix; on public same-lane −10 dB overlap, rolling 30 s windows and a whole-clip terminal proxy recovered 0/131 quiet-voice distinctive phrases. The minimal supported candidate is to retain separate capture lanes when they exist and transcribe them before mixing. For already mixed single-lane overlap, no tested config fixes the loss; preserve the audio, mark completeness unresolved, and prototype a recovery method before asserting D6. This follow-up makes no product-code change.

Receipt audit: **35/35 Live calls and 15/15 batch calls completed**, all audio sent, zero call errors; batch timing anomalies **1/15 calls, one clamped and zero dropped-offset words**. P52 ledger grew from about `$0.753` before this follow-up to `$0.7775` observed, mainly the 15 batch calls. **0/35 Live calls had complete usage metadata**, so actual Live spend and independent reconciliation against the follow-up `$3` cap remain **UNMEASURED**. The experiment bounded Live audio to these 35 public/generated calls and stopped. Evidence is `evidence/P52/robust-analysis.json`, `robust-manifest.json`, and individual retained receipts. One E1 fixture and one two-voice overlap pair cannot establish general overlap failure rates; the demonstrated missed passages are enough to falsify an unconditional completeness claim.

## LANES — separate microphone transcription prototype (2026-09-28)

### Measurement contract, frozen before lane calls

**Structural question:** Can a physical microphone lane preserve local speech that the mono system+mic mix loses, while excluding echoed system words and noise before those words create a speaker?

**Minimum primitives:** independent system and mic PCM tapes on the same sample clock; known local-utterance intervals and source words; timed mic and system batch words; one provisional W3 mic text stream; an independent WebRTC voiced-frame mask. Physical lane provenance identifies the local participant without Gemini speaker IDs. Audio time is necessary for echo comparison; lexical agreement without time would suppress unrelated speech.

**Invariants:** feed public E1 and echo-free M2 mic tapes unmodified at 16 kHz PCM16, W3 at 100 ms/1.0× with the selected `en` configuration; compare the same three source utterances at 30/135/248 s, each 3 s. Only a mic word that passes both the WebRTC speech gate and the echo guard can produce a local-speaker word. The guard drops a normalized mic token only when an identical system token is within ±1.5 s; it does not delete unrelated tokens because a neighboring word matches. Preserve the raw mic output and count every suppressed word. The prior F4 mono mixed result is the baseline.

**Assumptions and unknowns:** W3 Live events have no word timestamps, so an exact ±1.5 s per-word guard is testable on batch windows, while provisional W3 guard timing is only an inferred interval. The round-6 fixture builder file named in the brief is absent from this worktree; `fixture.json` gives source offsets, and each 3 s M2 operator waveform correlates with the public gold9 Keyu audio at source 2/9/17 s at `.999582/.999455/.999528` (mic/source gain ≈`.300`). The complete Keyu human transcript contains the source phrases. Exact word onset inside those 3 s slices is not human-aligned. Live usage completeness and hence incremental Live cost remain unmeasured unless metadata appears.

**Frozen operator reference phrases and denominators:** 30 s: “they think that they're responsible for you” (7 words); 135 s: “deference to authority is not blind submission” (7); 248 s: “in exchange for some deference” (5). They occur in the complete public Keyu human transcript; the earlier three isolated-M2 batch calls returned 8/7/6 words and 0 offset anomalies, serving as a lexical cross-check. Score matched ordered words in the corresponding local-utterance interval, and report both raw and guarded recall; success requires at least 5/7, 5/7, and 4/5.

**Falsifiers:** E1 fails if >5% of guarded mic words are system echoes or any operator phrase has <70% word recall. M2 fails if any non-utterance mic word survives. Concurrent system speech fails if it suppresses the local phrase. An echo guard that removes a reference operator word fails even if its echo rate improves.

**Independent echo outcome:** the guard's own exact-text match rate after filtering is zero by construction, so it cannot be the success metric. On E1, all mic words outside the three known 3 s operator windows are false background/echo observations; count those before and after each gate as a fraction of retained mic words. On M2, the same outside-window count measures noise hallucinations without system echo. This fixture-truth denominator makes the >5% E1 criterion falsifiable.

**Tool decisions:** reuse the production-path `run_live` W3 probe for paced mic sessions, `common.diarize_window` for L30/S10 timed batch windows, and WebRTC mode1/10 ms with ±.2 s word support as the existing speech gate. Compare raw, VAD-only, echo-only, and combined words to attribute any improvement or harm. System words come from the same public system tape; use cached identical windows where available. One local `lane_proto.py` command will print full state and retain JSON receipts. No product implementation is authorized. This follow-up is capped at $3; number/duration of calls and ledger spend are bounded and reported even if Live usage is absent.

**Two bounded guard diagnostics, registered after baseline E1 failed at 17/36 outside-utterance words:** A1 doubles the identical-token time tolerance from ±1.5 to ±3 s; A2 keeps ±1.5 s but accepts one character edit between tokens of length ≥4, a narrow model-wording repair. Each uses the same saved batch words, with no provider call. An alternative earns a recommendation only if outside-utterance words fall to ≤5% while all three operator recalls stay ≥70%; otherwise stop and report the structural echo problem.

### LANES result — physical separation recovers speech; word echo guard fails E1

Two 302 s public mic tapes were fed to **independent paced W3 streams** with the selected `en` config. A second pass used 30 s Gemini 3.5 Transcribe windows every 10 s on each mic tape without diarization; the system tape used the same diarized rolling windows as the existing pipeline. For each 10 s strip, one batch window owned its timestamped words. The measured guard retained a mic word only when WebRTC mode1/10 ms reported speech within ±0.2 s and no same normalized system word fell within ±1.5 s. This is a batch-word guard; W3 itself exposes no word offsets for an exact provisional version.

| Fixture / batch state | Mic words | Words outside three 3 s operator windows | Operator recall at 30 / 135 / 248 s |
|---|---:|---:|---|
| E1 raw | 815 | 796/815 (97.7%) | 7/7, 7/7, 4/5 |
| E1 VAD only | 815 | 796/815 (97.7%) | 7/7, 7/7, 4/5 |
| E1 exact-text echo guard + VAD | 36 | **17/36 (47.2%)** | **7/7, 7/7, 4/5** |
| M2 raw / guarded | 22 / 22 | **0/22 / 0/22** | **7/7, 7/7, 4/5** |

The echo guard classed 779/815 E1 raw mic words (95.6%) as same-token system matches within ±1.5 s, and by definition leaves zero such matches after filtering. **That zero is not echo control evidence.** The independent fixture truth says 17 surviving words are outside all operator speech. Giving word times a ±0.2 s boundary tolerance still leaves 17. E1's echo/noise lane is WebRTC-voiced on 25,460/29,300 ten-ms frames outside operator speech (86.9%); M2 is voiced on only 47/29,300 (0.16%). VAD removed zero Gemini words in both calls. The two frozen word-guard adjustments also fail: A1 exact token ±3 s leaves 15/34 outside (44.1%); A2 one-character edit ±1.5 s leaves 17/36 (47.2%). Neither harms the 7/7,7/7,4/5 operator recall, but neither meets the ≤5% false-background requirement. Stop threshold tweaks.

**Concurrent-speech recovery is real on this fixture.** System VAD marks 300/300, 300/300, and 278/300 frames voiced during the 30/135/248 s mic utterances. The separate mic batch output keeps 7/7,7/7,4/5 source words even after the guard, meeting the brief's ≥70% per-utterance bar. The prior mono-mix F4 baseline recovered 0/6, no mic-specific gain on the second phrase, and 3/4 bigrams on the third only late. The physically separate lane therefore solves the *operator omission* seen in mono, while leaving echo false words unresolved.

W3 preview on the mic alone showed all three source phrases in both fixtures: the first update containing ≥70% of a phrase arrived at median **2.674 s from utterance onset** on E1 and **2.844 s** on M2 (3/3 denominators; not per-word latency). E1 produced **798 final words** over 302 s, mostly echoed system speech; M2 produced **19 final words**, exactly its three operator phrases, with no other final text. Thus an ungated E1 W3 mic preview would visibly echo the system even though the later batch guard removes most words. W3's broad untimed final chunks cannot implement the exact ±1.5 s word guard as specified; a provisional alignment/gating method remains unmeasured.

All **93/93 batch calls** completed with **0/31 anomaly calls on each lane**, zero clamped or dropped-offset words. System calls were 31/31 cache hits. The **added mic batch cost** was `$0.045062` per 302 s fixture, or **$0.537/meeting-hour** at the tested 30 s/10 s cadence; the same cost applied to E1 and M2. Both W3 mic sessions sent 304/304 s without errors, but **0/2 had complete usage metadata**, so W3 and total added cost per hour remain **UNMEASURED**. P52 observed ledger increased from `$0.7775` to `$0.8676` across this follow-up; that increase is the two uncached mic batch suites, not a complete bill. Raw, filtered, per-call, latency, and cost state: `evidence/P52/lane-analysis.json`; prototype: `words/lane_proto.py` (one command in its header).

**Verdict against brief falsifiers:** E1 fails (a) because 47.2% guarded words are false background, despite 3/3 operator phrases passing; echo-free M2 passes (b) with 0/22 non-utterance words; and (c) is not triggered because all three utterances were recovered during system speech. **Do not adopt the proposed exact-word echo guard as a general mic-lane policy.** Keeping physical lanes is supported for operator recovery, but E1 needs a separately measured acoustic echo suppression or equivalent before mic words can create settled local-speaker rows. The selected W3 system pipeline stays unchanged. No product code was written.
## VOICEPRINT — cross-meeting D3 qualification contract

**Structural question:** Does naming a meeting speaker enroll a durable voice identity that correctly names that same voice in later meetings, while leaving other voices unnamed?

**Minimum primitives:** a timed public audio tape and reference speaker turns establish which voice spoke; a meeting-local speaker ID is the naming target; a persisted voiceprint carries identity between meetings; live snapshots expose speaker labels. Each is needed to distinguish correct reuse from a same-meeting label or a wrong-speaker match.

**Invariants:** name Lex only after matching its local speaker ID to Lex reference speech; an enrolled voiceprint must be visible as enrolled, not pending; later labels must attach to Lex, not Keyu or Jamie; the negative control stays unnamed; all meetings use the same local HTTP routes as the UI, isolated state, and 1.0× paced public audio.

**Assumptions and unknowns:** the runtime under test may differ from this worktree; voiceprint eligibility, enrollment delay, and UI observation timing are unknown until measured. Missing or ambiguous local speaker identification is a failed observation, not permission to guess. Provider cost from live usage may be unmeasured.

**Falsifier:** no enrolled Lex print after naming, wrong-speaker auto-name, missing Lex auto-name in B/D, Keyu named before enrollment, any auto-name in no-Lex C, or no HTTP observation path for these outcomes.

**Tool decisions:** use the runtime tree through its actual local HTTPS stack and `AccountCookieLiveReplayService` with the public corpus tapes, because mocked identities cannot establish D3. Save route responses and timed snapshots as P52 JSON receipts. The shared launcher rejects the brief's 18530–18539 assignment; a pane-local copy changing only that port check permits the mandated isolated port without editing product or shared tooling. Spend ceiling is $2.

### VOICEPRINT result — both enrolled voices transfer; Bill stays unnamed

The lead narrowed P52 to Keyu enrollment, the two-name Keyu five-minute clip, and the Bill five-minute negative. P63's already committed A/B/C trio is not repeated as qualification. One Bill60 Lex seeding replay was separately authorized because the P52 DB was fresh. Runtime `c58595dadc111998d5cce9fc25e193b9fe2729e2`, Gemini engine, local HTTPS 18530, one isolated Account owner and DB. All four clips were public, 1.0× paced, and accepted in full; naming used the same active-meeting `PUT` route as the UI, enrollment used `GET /api/voiceprints`, and labels came from the **outer** live snapshot HTTP envelope, not the nested `snapshot` object. Final speaker IDs were mapped to complete timed references by overlap, only in the measurement client.

| Step | HTTP outcome and timed reference check | First visible auto-name after reference first words | Calls preview/rolling/terminal | Offset anomaly words / calls | Reported cost |
|---|---|---:|---:|---:|---:|
| A Lex seed (Bill60) | **PASS**; active PUT at audio 50.0 s returned `enrolled`; bank has one compatible Lex print, one sample; Lex ID overlaps Lex 3.8 s, Bill .7 s final | manual | 1/6/1 | clamped 0/8; dropped 0/8 | $0.015681 |
| B Keyu enrollment (Keyu60) | **PASS**; Keyu ID overlaps Keyu 43.0 s, Lex 0; active PUT at 45.0 s returned `enrolled`; bank has Lex and Keyu, both compatible, one sample each | Lex 8.5 s (first words 25.0, label 33.5) | 1/6/1 | clamped 0/8; dropped 0/8 | $0.015681 |
| D `benchmark_5m:lex_keyu_jin` | **PASS**; primary Lex ID overlaps Lex 85.1/88 s, Keyu 1.6 s; primary Keyu ID overlaps Keyu 207.4/212 s, Lex 0; both final labels correct | Lex 12.5 s (0→12.5); Keyu 12.5 s (52→64.5) | 1/30/1 | clamped 0/32; dropped 0/32 | $0.083729 |
| E `benchmark_5m:lex_bill_ackman` | **PASS**; primary Lex ID overlaps Lex 70.3 s, Bill 1.0 s and is named; primary Bill ID overlaps Bill 221.7 s, Lex .9 s and stays unnamed. All 524 Bill-dominant timed snapshot observations have no name; no Keyu label anywhere in final map | Lex 6.5 s (6→12.5); Bill never named | 1/30/1 | clamped 2/32; dropped 0/32 | $0.083729 |

**Verdict:** D3's cross-meeting path passes both positive and negative follow-ups on these two complete 300 s references. Reported runtime cost totals **$0.198819 / $2 cap**; it includes a Live list-price estimate, so it is not a provider invoice. Across 80 calls, two word offsets were clamped and zero dropped. The public HTTP counter gives anomaly *words per call cohort*, not which call was anomalous; E's anomalous-call incidence is therefore unmeasured (one or two calls). All four final sessions were `closed/final`, with zero provider errors/retries, zero skipped window ticks, and zero voiceprint encoder errors. D's label map retained three short Lex-labeled IDs beyond the final primary ID, although those IDs had no final reference-overlap rows; this is visible identity fragmentation, not a wrong Keyu label. Population false-match/miss rates remain unmeasured.

The exact observation path is `GET /api/live/sessions/{id}/snapshot` outer `speaker_labels` (`app/phase2_live.py:1233`, then `app/live_transport.py` snapshot envelope), while the nested `snapshot.session.effective_transcript` supplies timed canonical speaker IDs. Manual enrollment is `app/phase2.py:2459` and the bank is `app/phase2.py:2519`. No missing observation path or product edit was needed. P52 receipts: `evidence/P52/voiceprint-A.json`, `voiceprint-B.json`, `voiceprint-D.json`, `voiceprint-E.json`, and `voiceprint-analysis.json`; replay prototype `words/voiceprint_proto.py`. The helper launcher differs from the shared script only in its accepted port range.
## ECHOGATE — acoustic mic echo decision contract

**Structural question:** Can relative lane loudness distinguish mic echo from local speech when a text match misses echoed words, while preserving every known operator utterance?

**Minimum primitives:** sample-aligned system and mic PCM give independent source levels; a timed mic word defines the decision span; system WebRTC voice activity decides whether a competing source is present; a bounded 0–100 ms lag search covers fixture echo delay; fixture operator intervals and human phrases supply truth. The existing text guard is a separate comparison, not acoustic evidence.

**Invariants:** every arm filters the same timed words within a fixture; the system-unvoiced bypass keeps a local word; the ratio compares RMS on the same duration and tests lag only in the declared range; score operator recall by each of the three utterances and false background independently of whether a word matches text. No product code changes.

**Assumptions and unknowns:** E1's no-AEC echo uses the known public fixture; a louder echo and a quieter local voice are constructed only from those fixture parts. A word's timestamp may include silence or another talker. The current product's 14/35 false-background result and the earlier offline batch bench's 17/36 have different word populations; retain both denominators. Performance on natural unseen acoustic environments is unmeasured.

**Falsifier:** any E1 utterance loses >30% of human source words, any M2 operator word is dropped, or false-background words exceed 5% of retained final mic words. The −15/−10 dB echoes and 0.1-gain talker bound the operating envelope rather than justify a new threshold after seeing failures.

**Tool decisions:** extend `lane_proto.py`'s public-fixture, timestamped-word and WebRTC path; compare acoustic-only, text-only and combined arms for D ∈ {6,10,15,20} dB. Reuse existing Gemini word receipts where the audio is unchanged. Re-synthesize fixture variants and obtain new words only if necessary to measure the harder-case false-word denominator, within the $1 cap. A one-command prototype prints full state and retains P52 JSON receipts; its result decides whether pane 6.3 has an implementable rule.

### ECHOGATE result — baseline rescue, no stable acoustic threshold

The rule compares each timed mic word's root-mean-square (RMS) amplitude with the loudest equal-duration system span at lags 0–100 ms in 10 ms steps; a word bypasses the ratio only when system WebRTC mode 1 is entirely unvoiced across it. A candidate keeps the word when mic level is within D dB below the system. Every arm also retains the existing mic WebRTC gate; text-only uses the current exact-token ±1.5 s echo guard, and combined requires both text and acoustic admission. E1's actual 30 ms echo, 0.3-gain public Keyu phrases, and noise were verified by subtracting the known delayed system and source slices: outside-utterance residual RMS 32.55 PCM units versus M2 background 32.36. No synthesized variant clipped (largest absolute PCM sample 7,425/32,767).

All cells below are **stray words / retained words**, where stray means word midpoint outside the three known 3 s operator intervals. D columns are ordered **6 / 10 / 15 / 20 dB**. Each variant received its own Gemini 30 s/10 s timed-word windows; unchanged E1/M2 words reused prior receipts.

| Public fixture condition | Raw | Text only | Acoustic only D6 / D10 / D15 / D20 | Text + acoustic D6 / D10 / D15 / D20 |
|---|---:|---:|---|---|
| E1 echo −25 dB, operator gain .3 | 796/815 | 17/36 | 0/14 · 0/17 · 0/19 · 0/19 | 0/14 · 0/17 · **0/19** · **0/19** |
| M2 no echo, operator gain .3 | 0/22 | 0/22 | 0/15 · 0/19 · 0/22 · 0/22 | 0/15 · 0/19 · **0/22** · **0/22** |
| Echo −15 dB, operator gain .3 | 821/847 | 16/32 | 0/17 · 0/19 · 112/135 · 792/816 | 0/13 · 0/15 · 4/19 · 16/31 |
| Echo −10 dB, operator gain .3 | 851/881 | 39/58 | 0/18 · 64/92 · 820/849 · 840/870 | 0/14 · 4/23 · 39/58 · 39/58 |
| Echo −25 dB, operator gain .1 | 818/849 | 18/38 | 0/0 · 0/1 · 0/16 · 0/22 | 0/0 · 0/1 · 0/13 · 0/18 |

**Operator retention:** E1 raw and D15/D20 combined recall the human source phrases at 7/7, 7/7, 4/5 words; M2 D15/D20 retain all **22/22 raw operator word rows**, while D10 drops 3/22 and D6 drops 7/22. E1 D6 cuts the first phrase to 3/7, exceeding the allowed 30% loss. At −15 dB, raw Gemini already finds only **3/7** of the second source phrase, so even the less aggressive gates cannot meet the source-word falsifier. At −10 dB, D10 combined keeps source phrase recall 7/7, 5/7, 4/5 but leaves **4/23 stray (17.4%)**; D6 suppresses all stray words but cuts phrase two to 4/7. At gain .1, D15 combined leaves 0/13 stray but cuts phrase one to **3/7**; D20 restores 7/7, 6/7, 4/5 yet lets −15 dB echo produce 16/31 stray. Zero retained words is a loss, not a clean pass.

**Operating envelope:** on this fixture, E1 stray-word mic/system ratio has median −25.0 dB and operator words median −4.7 dB (10th percentile −9.1). D15–D20 separate these and pass baseline E1+M2. At −15 dB echo, stray median rises to −15.4 dB and transcription itself loses source words. At −10 dB echo, stray median −10.4 dB overlaps normal operator's quieter words. At gain .1, operator median falls to −15.0 dB. **No tested D passes the full requested envelope**; the acoustic level comparison is not ready for pane 6.3 to implement. There is no six-line implementation rule to hand off. Keep the product text guard's E1 failure visible and use capture echo cancellation or a separately measured source-specific method before claiming echo-safe mic attribution.

**Custody and cost:** P52 exact-word bench has 17/36 E1 text-guard strays; the separately observed product final surface has 14/35, and its durable transcript stores grouped segments rather than per-word offsets. These are distinct denominators; this prototype does not certify an improvement on the product's 14/35 population. The three hard variants made 93 window calls, 21 provider cache hits and 72 new calls for **$0.105144 / $1 cap**. All 93/93 hard-variant calls and 62/62 reused E1/M2 calls have zero timing anomalies (0 clamped, 0 dropped); there were no reported call errors. Per-case hard-variant anomaly incidence is 0/31 each. Full words, level ratios, arms, source recall and per-call receipts are in `evidence/P52/echogate-analysis.json` and `echogate-batch-*.json`; one-command prototype `words/echogate_proto.py`. No product code was changed.
