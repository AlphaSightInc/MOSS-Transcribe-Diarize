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
remaining witnessed gaps of at least 10 s. Rule H additionally keeps the timed words
actually committed by rolling windows; a later window's straddling word replaces the
earlier truncated copy. Stop-tail recovery and File/URL runs do not supply these words.

After final identity labels (or the chunk stitcher), H finds consecutive live words in
provider holes: at most 0.1 s covered per word, not fully covered, and at least 0.15 s
uncovered across the run. Zero-length words count as 0.1 s. Equal adjacent edge words
(including the same numeral written two ways) are removed. H2 also withholds a whole
candidate run whose comparable units already form the adjacent clean-up suffix or
prefix: clean-up word ends/starts within 1 s of the candidate boundary, at most 12
units on either side, allowing the existing 0.1 s overlap. Chinese word grouping and
numeral spelling do not change equality. This shared discovery check runs before
either lane admits a restore; it never rewrites clean-up words or trims part of a run.
It removes nearby timing-shift duplicates, but can withhold a genuine omitted repetition.
Recorded H100 and 127 engine cells lose no words; four deliberate repetition fixtures
lose 8 candidate words. Shifts beyond the bounds and partly shifted runs remain limits.
See `prototypes/gemini-live/mic-speaker-echo/h2/NOTES.md` for measurements and explicit
stress-export reconstructions (original pre-restore word provenance unavailable).
The existing 10 s fallback
owns its intervals; H skips them. An empty clean-up answer saves the live rows as
committed; rule H's independent admission does not apply to them. On the system lane,
committed witnesses retain their published live identity. Each restored word takes the
nearest kept final word's label among words overlapping witnesses of that same live
identity. A live identity absent from every kept final word gets its own final label;
the existing final-to-live name mapping can preserve its live name. Unassigned witnesses
retain H's nearer-neighbour label. No restored word supplies bridge evidence. This runs
after the stitcher/identity policy and before existing word gates. Clean-up words retain
their text, times and labels. `witness_restored_words` counts inserted words without
adding a provider request; it appears in the numeric operator diagnostics.

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

The microphone gate retains the existing level and two-second anchor rules and adds
measured local-voice evidence (round 5b, `hybrid-w3-mic-short-v9`). `LocalVoiceEvidence`
reads the two lane tapes in 10 ms frames with fresh WebRTC mode-3 detectors per context.
The tab reference is its loudest frame in the preceding 0–100 ms. Echo return is the
median microphone/tab level on tab-voiced frames; with less than one second of tab
speech, the existing fixed −15 dB level test stands in. An unexplained frame is voiced
microphone audio while the tab is silent, or more than 6 dB above its measured echo
return. A sustained stretch lasts at least 0.4 s, bridging holes of at most 50 ms.

A provider-label run joins words across gaps of at most 0.6 s, before the level gate.
It is local if it touches a sustained stretch, at least 80% of its words touch unexplained
audio (word midpoint ±0.2 s), and those words weigh at least 15: three words or five
CJK-like characters. A: local words survive the fixed level gate. C: local words are
removed by the text guard only as part of a two-word echo phrase; the voice guard stays
unchanged. B: without a two-second attributed span, only surviving local runs still
weighing 15 are admitted. `local_speech_seen` retains its two-second meaning, so a short
reply admits only itself. `MicrophoneWordGate(local_voice=None)` preserves prior behavior.
The saved and Stop-tail passes compute the same frame facts in 30 s contexts every
15 s, only computing contexts overlapping the candidate words. Withholding still counts
a Stop tail as covered, rather than failed recovery.

For clean-up witness restoration (WP-C), `LocalVoiceEvidence` judges **one restore
candidate run alone**, after clean-up words were gated. A committed witness carries
two independent authorities: its **source partition** for admission evidence and its
**published live identity** for display/name continuity. Source partitions retain the
provider's request-local grouping, even when the identity registry aliases labels.
Consecutive requests continue a source partition only when they re-hear at least two
distinct committed words, matching at least two distinct new words with the same text
and both endpoints within the provider's 0.1 s step. Occurrences use text/start/end;
duplicate matches to one occurrence do not count twice. A lone common-word coincidence
cannot continue a partition or move an old witness into a new group.
Equal raw labels or published IDs alone never establish continuity.

A new label matching two earlier partitions gets a fresh partition; the earlier groups
stay separate. Two new labels matching one earlier partition get separate new partitions;
only earlier words positively matching exactly one new label move into that partition.
All raw matches participate in ambiguity checks: a weak competing label or partition
still prevents whole-group continuation. Only qualifying two-word edges authorize
continuation or matched-word transfers; weaker edges stay separate.
Unmatched or ambiguous words stay separate. Thus a corrected seam prefix can accompany
its suffix without pooling two voices. Without correspondence a short reply crossing a
frontier may remain withheld. Published `GeminiRelabel` rows update witness identity,
never the source partition. Different source partitions retain independent local-run
text-weight evidence; two words from each cannot combine to meet the 15-weight bar.
Each partition/run owns its 80% denominator: rejected groups neither lend evidence nor
veto an eligible reply in the same provider hole. Only eligible local words proceed to
the remaining guards and the surviving per-run weight-15 check. A one-word re-heard seam
prefix cannot establish correspondence; each separated piece must qualify on its own.
The measured five-word English control saves its four-word suffix and withholds its
one-word prefix. Two-word-prefix seams remain 5/5 across identity/label changes.
Their samples/text are judged against the lane audio by the same sustained/80%/weight-15 rule,
independently of `local_speech_seen` and neighbouring clean-up words. Only then assign
its speaker. An anchored lane never waives this evidence requirement.
Hole discovery uses the ungated provider timeline: gate removal is not an omission.
Each candidate passes voice activity, independent local-run evidence, and the existing
microphone guards; only surviving local runs still weighing 15 are restored. Microphone
final labeling retains the measured kept-neighbour policy, independent of its source
partition and uncertain published identity. The nearer
kept clean-up neighbour supplies the label (earlier wins a tie); without one, the lane's
local speaker does. Other restored runs never serve as clean-up neighbours. Witness
voice activity is scanned once; saved-pass 30 s local-frame facts and system vectors
are reused. Microphone embeddings read only the candidate's audio span. Re-admission
does not increment provider or local-rescue counters or change the lane anchor.

After the surviving per-run weight check, each admitted source run is compared with
the original clean-up words using H2's same whole-run time-shift rule (1 s, 12
comparable units, existing 0.1 s overlap). A rejected neighbour cannot hide a shifted
reply already beside the hole: the matching source run is withheld before label
assignment and insertion, and adds nothing to `witness_restored_words`. The hole-level
check and remaining admitted words' label/insertion behavior stay unchanged. System
restoration inserts whole checked holes, then assigns labels; it has no separately
admitted source pieces. FIX6 measurements: `mic-speaker-echo/c6/NOTES.md`.

Accepted limit (lead decision, review pass 8, R8-F1): text beside the hole cannot tell a
shifted utterance from a second utterance with the same words. When a local phrase of at
most 12 units is said twice within 1 s and clean-up keeps one copy, the other copy is
treated as the time shift and the phrase is saved once, with or without a rejected
neighbour (before FIX6 the mixed-hole case saved it twice; the isolated case already saved
it once). Chosen over the opposite error, a phrase said once and saved twice (R6-F1).
Constructed cases only; fresh-provider frequency unmeasured.

Measured H prototype: lost name tokens 115 → 4 across 100 pairs; doubled adjacent units
0; 236/250 names retained in 25 system engine cells. BC composition preserves F2's
206/291/310 live/Stop/saved units of 343; omitted five-word replies restored at 10/20 dB
below the tab; zero invented/noise restores on 28 round-4 samples, anchored included.
Sources: `prototypes/gemini-live/mic-speaker-echo/{f3,bc}/NOTES.md`.
Product verification (R5B-C, W off): all 127 recorded engine/level cells reproduce
the composition prototype's text/times; the 100-pair, reply and negative results
above are unchanged. Speaker error remains .0907/.1217 on the two truth controls;
added duplicates, row-ownership failures and counter mismatches are zero. Receipts:
`~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/r5b-c/verdict.json`.
Limits: cannot recover words live never committed or clean-up replaced in time;
microphone replies below weight 15 remain withheld, even on anchored lanes. System
live-only inventions/stutters can return; restored script stays as live supplied it.
Physical echo cancellation, fresh provider behavior and the >900 s chunk plan remain
unmeasured by the recorded prototype.

The recorded prototype admitted 15/15 short English and 15/15 Mandarin saved units at
−40 dB echo; quiet double-talk 20 dB below the tab retained 27/31 long-turn units.
Across 18 engine cells, live/Stop/saved recall rose from 90/101/157 to 206/291/310 of
343. Five listener/noise engine cells and 28 rebuilt round-4 negative provider answers
(908 voice-gated words) kept zero invented/echoed words; echo-only admission remained
zero at −40/−25/−15 dB. Source: `prototypes/gemini-live/mic-speaker-echo/f2/NOTES.md`.
One/two-word replies without an anchored turn remain withheld; words absent from the
provider answer cannot be admitted; another room voice can qualify from 0.4 s.
Physical echo cancellation and double-talk attenuation remain **unmeasured**, requiring
the plan's attended device check. Grey microphone echo fragments are unchanged.

Per-meeting and per-lane diagnostics add `mic_words_from_provider` (after voice activity),
`mic_words_kept_by_local_voice_level`, `mic_words_kept_unanchored_by_local_voice`,
`mic_echo_return_db` (last measured; null until measured), and `mic_local_voice_seconds`
(union of sustained spans observed so far, avoiding double-counting overlapping windows).
At final release, after clean-up or at live-only close, the shared operator journal
emits one `moss-operator-event.v1` event, code `meeting_engine_diagnostics`, containing
meeting id and numeric diagnostics only. Engine settings, strings, nulls and booleans
are omitted. No transcript, audio, credentials, new storage, or provider requests.

W3's provisional text lacks reliable word timing, so the lane
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
visible text in the same lane: committed speech followed by preview rows already kept.
Comparable units are individual CJK, kana or Hangul characters and whole other letter/digit
runs; number words and digits align. The tail holds at least 60 units, growing with the
lane's preview (1.25 × its units + 8). A repeated head needs evidence equal to five words
or nine CJK characters (weights 5 and 3, minimum 25), at least 60 % matched, with the
existing bounded gaps. The cut uses original-string spans and drops leading Western
and CJK punctuation. Rolling and saved rows are untouched.
Measured arm C removes repeats on all ten recorded cells and preserves the 302 s English
stream byte-for-byte (`prototypes/gemini-live/mic-speaker-echo/f1/NOTES.md`). A traditional
commit under a simplified preview can leave 1–4 solid characters; no script folding is
applied. Heads shorter than nine characters or five words stay. A genuinely repeated
phrase at or above that minimum may be hidden in grey until committed. Japanese and
Korean evidence is synthetic; real provider output and other unspaced scripts are unmeasured.
Mixed scripts and doubled characters in committed rows are separate defects.

The publisher also remembers a proven cut for the currently published rows. It retains
that cut only in the same lane, with overlapping audio extent, a nondecreasing preview
end, and identical comparable units through the cut. Rewritten prefixes and new turns
discard it; an empty preview clears it. Memory holds only the current rows' removed
prefixes and observed ends, not meeting history. It applies the remembered cut after
the original alignment, never aligning the shortened suffix: that would hide a fresh
second occurrence of a phrase (six recorded English publications in the rejected arm).
After a successful rolling update, a remembered cut is forgotten if that lane loses
a visible base row starting before the cut's observed end. Earlier rolling rows remain
visible, so normal rolling appends retain their cuts across later divergence. The next
preview realigns against current solid text. This restores all 61 words hidden by the
81-word degraded paragraph → 20-word rolling replacement; an empty replacement restores
all 81. Other-lane and retained-base proofs survive. Stop clears cuts after tail drain;
new meetings start empty. `prototypes/gemini-live/mic-speaker-echo/a5/NOTES.md` records
the replacement/lifecycle controls and unchanged 2,749-call F1/A2 replay.
Degraded bases use the same trim before committing preview words. Their clock is clipped
at the fallback frontier, so a prior observed preview extent can carry the full prefix
just committed, including a one-word reply. The c5b timeout replay commits "right" once
instead of five times and adds paragraph suffixes instead of whole growing paragraphs.
This is a measured partial repair, not a new frontier estimator: long-turn mismatches
without a previously witnessed cut can still repeat. Local-tail and time-proportional
cuts remain unqualified for preserving fresh speech. See
`prototypes/gemini-live/mic-speaker-echo/a2/NOTES.md` for gates and replay limits.

The user chose the T4 time-ownership trade (D15, 2026-10-01): grey should show
only what arrived after that lane's confirmed point. Older grey words may disappear
when that stretch is confirmed even if the solid model omitted them; the saved
transcript is unchanged. A3 measured 22-word, 11-word and 169-character omissions
that this decision now accepts (`prototypes/gemini-live/mic-speaker-echo/a3/NOTES.md`).

The T4 time cut carries original source turns beside the rendered rows, before their
starts are clipped. Each lane keeps its own publication clock; an update from the other
lane cannot re-date cached text. For each active original turn, the latest publication
at or before that lane's confirmed point supplies a snapshot. Confirmation follows the
end of currently visible solid rows in that lane, including degraded fallback rows; it
cannot advance on an empty base/window clock alone. If replacement makes that extent
retreat, snapshot history is discarded. The unchanged comparable-unit prefix of the
snapshot is removed only when it extends beyond the existing text cut. A unit is hidden
by the time rule only if it proves publication at or before confirmation. Text-rule
cuts remain unchanged; C1's count floor below is a separate user-authorized trade.
The existing genuine-repeat limit above remains; the lead explicitly amended A4's
freshness gate to judge time additions only.

Different original starts never borrow snapshots. Duplicate source keys, joined rows,
ambiguous origins and text changed by lane filtering abstain. Prefix rewrites shorten
the exact snapshot proof; a count alone does not establish word timing. Pending history
holds at most 64 publications per active turn plus one snapshot. If a stalled frontier
needs history discarded at that bound, the time rule abstains until retained history is
eligible; a dropped newer publication cannot leave an older snapshot in force. Once
a retained eligible publication supersedes the dropped history, its cut remains valid.
Source/socket restart clears that lane's snapshots and keeps its clock
watermark against stale cached rows. Finals clear their turn, even when already covered
and therefore forwarded only as metadata; Stop and meeting release clear all snapshot
text. The text rules' separate remembered cuts and their invalidation stay unchanged.
The time rule is optional: a fault in preview snapshot processing publishes the
already-computed text-rule rows, clears snapshot state and increments numeric
`preview_snapshot_errors`. Snapshot advance faults after base/rolling commits likewise
clear/count/continue. The meeting remains active; later previews can publish normally.

**D16 O2 (2026-10-02): enable C1, then measure real-world effectiveness.** Each
unambiguous original turn keeps a cut count N with its snapshot state. Shown cut is
`max(today's cut, N)`, even after a text rewrite; today's cut is the larger of the
text-rule and exact-snapshot cuts. Seed N from today's cut and retain each new
maximum. Keep it only in the same lane and original
turn while the visible-solid confirmed point does not retreat and current units are
at least N. A shrink below N discards the old count; today's cut can seed it anew.
Final, turn removal, source reopen, Stop and new meeting clear it at the existing
snapshot lifecycle boundaries. Ambiguous origins abstain. Floor computation shares
the optional snapshot fault boundary: on error, show text-rule rows, clear state,
increment `preview_snapshot_errors`, and keep the meeting active.

**Accepted limit:** if a rewrite deletes head units and appends fresh speech, C1 can
hide that many fresh units in grey until they become solid. The known-clock control
deletes 15 of 60 old units and appends 20 fresh units: today's cut45 becomes60,
hiding15 fresh units. D16 supersedes the no-additional-fresh-loss invariant for C1
only; the measured loss is retained as an accepted-limit test, not a passing freshness
claim. Solid and saved transcript processing are unchanged.

**Second accepted limit (lead disposition of review pass 9 F1, same class):** the floor
trusts today's cut. When today's rule hides a whole short interim that repeats an earlier
solid line (13 of 13 units) and the provider then inserts fresh words before that line's
end, today's rule alone would self-correct (13 -> 7) but the floor holds 13 and hides 6
fresh units for the rest of that turn. Constructed control; on the recorded streams the
cut of a non-shrinking turn decreased once in 3,974 comparisons and the higher cut was
right. The effect is grey-only, confined to that turn, and ends when the words become
solid; the user's stated tolerance (2026-10-02) is exactly this: temporary, never carried
into later turns. A text-anchor refinement that can re-place the cut is being measured
(a7); until then the per-meeting `floor_hidden_units` counter reports how much the rule hid.

**D17 O2 (2026-10-02, user): solid-tail anchor together with the cut floor.** The head-to-
frontier text match needs an unbroken chain over the whole turn; the anchor needs agreement
only at the confirmed frontier. Anchor = the closing units of the lane's latest-ENDING solid
row with weight >= 25 (five words / nine CJK characters; a shorter row gives no anchor). It
is searched in the turn's units at or after the retained count with the existing
`_repeated_head` tolerance; the first hit moves the cut to its end, a miss leaves the floor
in force. Same turn identity, lane isolation, lifecycle and fault boundary as the floor.
Counters `preview.<lane>.anchor_hidden_units` / `anchor_publications` (numbers only);
`floor_hidden_units` counts floor and anchor together.

Measured (prototype a7, candidate C4; product functions equal the prototype on all 2,255
grey rows of the two recorded long-turn episodes): repeat residue c6s 18,868 -> 314 and
c6 73,989 -> 11,852 unit-seconds (floor alone 1,730 / 73,989); complete Mandarin, English
and R5-D streams unchanged apart from the one floor change.
**Accepted limit (user-informed):** when solid's ending is absent from grey at its own
place and the same five words occur later in fresh speech, the cut lands after the later
copy and 20-29 fresh units (constructed controls) stay out of grey until solid. ALREADY-
SATISFIED and once-per-tail guards were measured and changed nothing. Cost at two hours on
a 900-unit turn: +0 to +0.75 ms per publication over the floor step. Live provider and
physical-device behaviour unmeasured; the user's meetings and the counters are the test.

C1 product matches the frozen A5 prototype on all 1,005 complete A4 publications.
The only difference from C0 is Mandarin publication137 at69s, cut144->145; English575
and R5-D64 are unchanged. Conditional c6s published-row repair: 478 observations,
repeat18868.27->1730.19 unit-seconds,36 changed observations; old c6:868 observations,
repeat73988.68 unchanged,0 changes. Original stress keys, raw prefixes and provider
final flags were not captured: these are overlap-conditioned repair measurements,
not complete raw service/lifecycle parity or acoustic fresh-loss qualification.
Physical-device effectiveness and future provider variance remain UNMEASURED.

Numeric `preview.<lane>.floor_hidden_units` accumulates units hidden beyond today's
text/snapshot cut; `floor_publications` counts publications where that extra cut acts.
Both follow existing time-cut accounting, including cached-row republications.
`time_hidden_units` still measures only the snapshot addition. The existing per-meeting
content-free operator diagnostics line carries these counters; no new event/storage.
Evidence and reproducible commands: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/R5B-A6/`;
regressions: `tests/gemini/test_gemini_preview_floor.py`.
On the same fixed two-hour solid population below, C1's added runtime work including
snapshot/floor processing and diagnostics is0.880ms mean (0.975ms p95), within the
1ms mean gate; current C0 bench0.667ms. Retained F1/A2 calls2749/2749, A5 transitions
5/5, degraded controls and FIX7 overflow/fault probes remain unchanged.

The earlier A4-only product replay matched its prototype on 366 Mandarin, 575 English and 64 R5-D
publications. Mandarin changes 23 calls, removing 46 additional old unit-publications;
English and R5-D output are unchanged. All six divergence injections remove the repeat
and keep their fresh suffix; time additions outside the exact snapshot prefix are zero.
The 61-word degraded-replacement control remains visible. Added source-to-publication
mean work is 0.34/0.70/0.19 ms, respectively; pending peaks are 35/28 for the long streams.
Numeric-only `engine_diagnostics.preview` exposes per-lane raw/shown units, text
and additional time removal, maximum grey units, source clock, confirmed point and
publication totals; history maxima/overflows are separate numeric fields. Diagnostics
count only current preview text; saved-text unit totals are omitted without a cache.
A fixed two-hour synthetic solid transcript (1440 rows, 720 per lane) measures 0.635 ms
mean added runtime work per publication, including snapshot scans and diagnostics;
the removed whole-solid count made the same population cost 97.642 ms.

Combined later-solid-proxy residue reaches 4 Mandarin / 5 English units on non-rewrite
publications, present for 45/41 cumulative publication seconds; rewrite publications
reach 4/3 units. Those are recorded text/clock proxy metrics, not a fresh-provider or
browser qualification. Original rewrite counts are 16/41; raw stress streams, physical
device behavior and live long-run qualification remain unmeasured here. The bench and
exact real-run diagnostics contract are in
`prototypes/gemini-live/mic-speaker-echo/a4/NOTES.md`; A3's raw-publication capture
contract still applies to the lead's future real run.

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
  later. No server bound, runtime failure or host Wi-Fi event coincided; the trigger was unmeasured then. P74 below
  identifies Chrome request exhaustion as the browser-side cause.
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
every replay and caused no wrong merge on a fresh raw-label pass over the 8 synthetic meetings, but its check
drops the veto for 7 of 38 different-speaker pairs there — every time a label mixes two voices — so it is not
shipped either. The open primitive is label purity, not the alternation rule. Numbers and gates:
`prototypes/gemini-live/aba-veto/NOTES.md`.

## Round 5: a renamed speaker in a summary (2026-10-01)

- **Defect.** After a rename the summary still said "Speaker 1". A summary is prose written once by a model that was
  given every transcript row under its speaker's name at that moment (`GeminiSummaryGenerator`: `"speaker": row["speaker"]`).
  A rename rewrites the transcript rows and, by decision D1 (#15), asks the model nothing, so the stored prose kept
  the old name. A second defect hid behind it: the Markdown export kept a summary only when its version equalled the
  transcript's, and a rename raises the transcript version, so after any rename the export dropped the whole summary.
- **Structural question.** Which words of a stored summary mean which speaker, and under what name is that speaker
  shown now?
- **Primitives.** (1) *Given names*: the name each speaker id carried in the transcript handed to the generator, saved
  with the summary (`speaker_names` in the artifact's `provenance_json`; returned by `/summary/live`). (2) *Current
  names*: the name each speaker id shows in the transcript now (`transcriptSpeakerNames`, the transcript's own label
  rule). (3) *Reading*: every whole mention of a given name is shown as that speaker's current name
  (`renameSummarySpeakers`, `frontend/src/lib/summarySpeakers.ts`), in the Summary pane and in the Markdown export.
  The stored document is never rewritten, so a second rename, a swap of two names and a rename back all start from
  the same text. Neither side can be dropped: without (1) a search has only the default label to look for.
- **Why not search for the default label.** "Speaker 1" is what speaker-0001 is called only until someone names it. A
  speaker named Alice before the summary (by a voiceprint, or by hand during the meeting) is "Alice" in the prose;
  renaming her to "Alicia" afterwards leaves a default-label search nothing to find. And before round 4 (F4)
  "Speaker n" was numbered by order of first speech in one transcript version, not read off the id
  (`docs/plan-r3-ui.md` I-4), so in an older summary "Speaker 1" need not be speaker-0001: the search could put one
  person's new name on another person's sentences. How often that would happen is unmeasured.
- **Invariants.** No model call and no summary request on a rename. Only given names are looked for: a default label
  the generator never used is ordinary text. A name must be whole: "Speaker 1" is not in "Speaker 10", nor "Al" in
  "Also"; all given names are matched together, longest first, so "Ann" inside another speaker's "Ann Lee" belongs to
  the longer name. Chinese writes no space between words, so a Chinese neighbour needs no gap ("Speaker 2介绍了…").
  A name is left as written when its speaker is no longer in the transcript, when the transcript shows that speaker
  as unattributed, or when two speakers were given one name and now differ. Timestamps and data values are not prose
  and are not touched.
- **Measured.** On the 84 recorded Gemini summaries under `prototypes/gemini-live/live-summary/` (37 Chinese) the
  model wrote the given label verbatim in 252 of 252 mentions (0 paraphrases such as "the first speaker" or a
  translated label; 49 mentions touch a Chinese character). The reading rule renamed 252/252, changed 0 characters
  outside them, and made 0 false rewrites of the word "You" (the first microphone voice's default name).
- **Summaries saved before this change** carry no given names; they are shown exactly as stored (no guess), in the
  pane and in the export. Refresh regenerates one with the current names.
- **Cannot do.** Tell a name from the same word used otherwise ("You", "Will", "May" in a quoted sentence); follow a
  mention the model paraphrased or lower-cased; split a Chinese name from a longer word that only starts with it
  ("张伟" inside a non-speaker's "张伟明"); follow a passage correction (its rows move to another speaker, the prose
  does not); rename the meeting title the first summary set. How Gemini mentions the microphone voice "You" in a
  two-lane summary is unmeasured (no recorded two-lane summary in the repo).

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
| E1 microphone acoustic gate, `e7078edc` | 0/20 stray final mic words outside operator intervals; phrase recall 7/7, 6/7, 4/5 | Fixed rule alone loses quiet local words; v9 adds measured local-voice evidence (F2 fixtures). Physical echo cancellation remains unmeasured |
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

R5B-C2 measured both authorities independently: unassigned/born/reassigned seam replies
5/5; aliased stray0/reply4/4 and two distinct two-word replies0. Recorded100 pairs and
45 archived cells preserve H text/times/counts and kept labels, with no new restored-only
identity on that population. Truth error .0907/.1217 unchanged; the two truth-verified
restores retain correct labels. An injected entire12-word speaker omission on the930s
chunk schedule restores12/12 under its published live name with unchanged encoder calls.
The indexed identity bridge adds about0.13s on a36,000-word two-hour lane. No new embedding
or provider call. If live identity was wrong, nearest kept final evidence can follow a
clean-up split locally; a completely omitted voice with a wrong live ID remains wrong.
See `prototypes/gemini-live/mic-speaker-echo/c2/NOTES.md` and R5B-C2 evidence for complete
prototype/product gates, ambiguity controls, row-level stress audit and stated limits.

## P74-R: browser resume — measured proposal, not shipped (2026-10-02)

An originating browser page can resume an active meeting within the existing 120 s
lease using an explicit origin-sign-in-authorized handshake. Keep the meeting,
engine, speaker ledger and audio stage; replace only the capture page. The handshake
must return authoritative lane sequence/epoch/end and mixed/capture clock state,
and fence frames, heartbeat, Stop and Abort from the previous page. Heartbeat-only
takeover is rejected: an awakened original still admits audio (200) and causes
new-page overlap refusals. Expired, closing, accepted-Stop and server-restarted
meetings remain non-resumable.

Throwaway code composes real Phase2 routes, the scripted Gemini engine, production
mixer and MP3 archive. With 4 s prefix + gap +4 s continuation, gaps of 5/30/90/119 s
accept 16/16 frames and save one 13/38/98/127 s MP3 with elapsed-time silence and
correct resumed transcript timestamps. Manual speaker name survives. A 125 s gap
refuses with 409 and retains the original 4 s partial archive. The 90 s falsifier
passes. At 119 s gap +45 s continuation, peak lane retention is 29.5/60 s; existing
mixer pacing delays the first resumed live transcript row by 30 s. Real Chrome
reload with fake media, actual CaptureClient/worklet and a throwaway adoption seam
completes one meeting; microphone mute/echo choices, sequences and new epochs survive.
Chrome share track labels change on reacquisition and cannot identify the old tab.

Proposal: one **Resume recording** button, same origin Sign-in session and stored
meeting-specific capture settings; ask the user to select the previous shared tab;
preserve missing time as silence plus a separate interruption notice. Keep 120 s;
view reads do not extend the lease, explicit valid takeover renews normally. Another
Sign-in session stays read-only; same-cookie concurrent tabs give one winner.
Original automatic-summary ownership must follow adoption without duplicate workers.

Physical Bluetooth/device continuity, real browser crash, human picker, exact live
network-clock accuracy, provider recognition/latency and product acceptance remain
unmeasured. No production change or accepted ADR amendment is made here. Full
contract, negative S1 evidence, options O1–O4, required ADR/test amendments, size
estimate and one-command bench: `prototypes/gemini-live/long-meeting/resume/NOTES.md`.
Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume/SUMMARY.json`.

## P74: capture response lifetime (2026-10-02, candidate, not deployed)

A completed POST must release its response stream, even when its acknowledgement is unused. Chrome retains an
unread `no-store` response as an open loader; about 16,384 loaders exhaust every request from that page. Two
frame lanes (4 POSTs/s) plus heartbeats (2/s) reach this at 45m31s. Server health cannot repair that page.

P74-L1's retained bench (`prototypes/gemini-live/long-meeting/L1/NOTES.md`, `FETCH-AUDIT.md`) bundles the real
CaptureClient, supplies synthetic worklet frames, and calls the real Phase2 routes with ScriptedGeminiEngine.
Baseline 54fb5573 dies at capture request ordinal 16,382 in 19.24s; even ordinary GET/POST then fail. Each of C1
(client drain), C2 (empty success), C3 (capture response `no-cache`), and C4 (C1+C3) passes 100,002 requests. Tiny
2-sample frames accelerate request counting; this is 4.63 meeting-hours of request volume, not physical capture
or provider-duration qualification. Native-memory runs disconnect Playwright's Network observer after acquiring
the page: its retained request bookkeeping otherwise adds hundreds of MB. Warm native renderer RSS drifts about
9–11 MB across the last 70,002 requests; JS heap stays roughly flat, unlike the baseline's hundreds of MB of
retained loaders. Full receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/leak-fix/`.

Candidate recommendation: **C1+C3**. `captureFetch` drains the network body at one choke point before returning an
in-memory Response with the original status, headers, and error JSON. Descriptor, create, frame, heartbeat and
Stop all use it. Existing 409 sequence adoption, replay, 429 retry/drop, and terminal handling are unchanged.
The server applies `Cache-Control: no-cache` only to frame/heartbeat POST responses, including errors; other API
responses remain `no-store`. This releases old bundles' loaders while retaining the acknowledgement contract.
C2 works in Chrome but discards acknowledgements other callers use, so it is not the product proposal.

Risk: these two response types no longer prohibit all cache storage; `no-cache` requires revalidation and their
POSTs carry no explicit freshness. The header change cannot rescue a page already exhausted; it must reload.
The page currently keeps its last active status and says “Reconnecting — keep this tab open.” Its pill therefore
keeps counting “Recording” although delivery has stopped; it cannot receive the eventual helper-lease interruption.
The smallest honest copy improvement, proposed only, is: “This page lost its connection — retrying. If it stays
disconnected, reload and start a new recording; check History for the recorded part.” No invented outage classifier
or new timeout is needed. The fetch audit also identifies an inactive SummaryPane error-path leak: one unread HTTP
error every 5s can exhaust a fresh page in 22h45m20s. Healthy summary replies are consumed; this slower residual is
reported separately and is not fixed or qualified by the capture candidate. Real-duration physical capture, other browser versions, and provider throughput remain
unmeasured by this bench.

## P74-RS: same-meeting server resume candidate (2026-10-02)

**U1** browser reload/reopen resumes the same Meeting by an explicit handshake;
automatic requests cannot steal a page whose accepted heartbeat is less than 3 s
old; 409 `capture_page_alive` includes `retry_after_ms`. The browser retries
automatic resume for up to 8 s after load, then becomes a viewer only if the old
writer still heartbeats. User requests may take over immediately. A per-Meeting
guard serializes the
handshake and all capture mutations; compare-and-swap yields one winner. The
response supplies authoritative clocks/cursors. Idempotent retry returns the same
state without renewing twice. **U2** every handoff records mixed-clock interruption
metadata separately from speech; mixer zero-fill preserves elapsed missing time.
Closed `capture_interruptions` plus `sample_rate` persist through
Stop/refinement/reload/History in the snapshot `session` and saved document top
level. Open gaps are not listed. Browser transcript/exports render the exact
`([HH:MM:SS-HH:MM:SS] Recording Interrupted)` line; server metadata only, no
export endpoint or new renderer. Existing Python subtitle exports stay unchanged.
Recognition, speaker statistics and summary input exclude it. **U3** retain the
120 s lease and lifecycle owner; expiry/closing/accepted Stop/server restart never
reopen. **U4** only the origin Sign-in session replaces its page, and the old
writer receives `capture_replaced` on frames/heartbeat/Stop/Abort. Headerless
non-resuming clients retain their existing meeting flow. Browser restoration and
summary-watcher transfer belong to the client package.

Offline product matrix: 4 s prefix + 5/30/90/119 s gap + 4 s continuation produces
one exact 13/38/98/127 s MP3, with zero-amplitude interior gaps and completed status.
125 s refuses with interrupted status. At 119 s +45 s continuation, retained
PCM peaks at 29.5/60 s per lane; the first resumed live row is delayed 30 s by
existing mixer pacing. No larger buffer or new mixer algorithm.
`measure.py --product` under `prototypes/gemini-live/long-meeting/resume/` prints
full state using real routes/mixer/archive with an offline engine. Provider and
physical-device recovery, clock accuracy under real network latency, and browser
product acceptance remain unmeasured. Candidate server build only; no deployment.

P74-RS verification after lead R1–R3: all six offline product cells pass.
Original regressions: 26 red on `c7884d46`, one headerless control green.
Amendments: 11 red / 17 green on `ed89d899`, all 28 green on the final candidate.
Full backend: 2946 passed, 9 skipped, 2 xfailed, 37 subtests passed (420.86 s).
Existing pre-P74 expectations unchanged; server export assertions removed per R3.
Receipts and local commit classification: `status/P74-RS-STATUS.md` under
`~/Documents/Codex/2026-09-28/moss-gemini/`.
