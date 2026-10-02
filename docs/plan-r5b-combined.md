# Round 5b — combined plan: live/clean-up text defects, small fixes, rule W (2026-10-01)

Status: **PLAN v2 — LAUNCHED 2026-10-01 (user go)**. v1 was reviewed with `/codex:adversarial-review` (verdict
needs-attention, findings R-F1…R-F3); §12 maps each finding to its change. Stress cap §7 approved with the launch.
Base: `gemini/r4-ui` @ `193d3fc3` (code = `9a1ca171`, what the MacStudio pilot runs). Lead: Claude (MOSS:5.1).

## 1. What the user reported and what was measured

Setup: MacBook Pro, built-in speakers playing the shared tab, built-in microphone, Chrome, pilot at :18600.
The user spoke into the microphone, saw the words in a grey "Speaker TBD" row, and the row vanished without
becoming solid; the grey text under a Chinese row repeated the solid text; after Stop the microphone speech was
absent. Diagnosis (R5-D, `prototypes/gemini-live/mic-speaker-echo/NOTES.md` on `gemini/r5-d`, evidence
`~/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/`) found three independent defects, all reproduced on public
audio, plus two small user requests and one earlier planned change:

| Code | Defect / request | Root cause (measured) | Fix prototype (branch, verdict) |
|---|---|---|---|
| F1 | Grey preview repeats solid text for Chinese | `_trim_committed_preview` compares whitespace tokens; a Chinese clause is one token (75 of 115 units already solid, 0 trimmed; English 52 of 54) | `gemini/r5-f1` — works (arm C) |
| F2 | Local speech shown grey, never solid, absent after Stop | Microphone words need (a) ≤ 15 dB under the tab level and (b) a continuous ≥ 2 s span of provider word times; real phrases measure 0.8–1.7 s, and a voice ≥ 16 dB under the tab loses every word | `gemini/r5-f2` — works on fixtures for phrases of ≥ 3 words; real echo cancellation UNMEASURED |
| F3 | Clean-up loses words the live transcript had | The provider's whole-recording answer omits words (8 of 10 requests lost a name); clean-up replaces the live rows wholesale; only a ≥ 10 s wordless gap is checked | `gemini/r5-f3` — works (rule H); no request-side fix exists |
| M1 | Renamed speaker keeps old name in the summary | Summary is prose written once with the names of that moment; Markdown export dropped the summary after any rename | `gemini/r5-m` — implemented, tested |
| M2 | Label "System sound" → "System Sound Output" | — | `gemini/r5-m` — implemented, tested |
| W | One person shown as two speakers in long meetings | A counterfeit alternation veto (docs/plan-r5-label-purity.md §12) | prototype `ccafb41d`; Stage 3 (§13 there) not yet run |

## 2. Structural view (why these are three fixes, not one)

Each lane (tab, microphone) has three text authorities: instant preview (grey), 15-second window commit (solid),
whole-recording clean-up (saved). Defects sit where two authorities are compared or one replaces another:

- **F1** preview vs commit, same lane: the comparison unit was wrong for unspaced scripts.
- **F2** admission of microphone words: the evidence was wrong (tab loudness and provider clock instead of "is there
  sustained microphone speech the tab cannot explain").
- **F3** clean-up vs commit: replacement had no witness, so an omission was invisible.
- **W** speaker assignment after clean-up; text untouched.

Invariants the combined change must hold (each is a gate in §6):
- I1 A lane's grey preview does not repeat that lane's solid text; fresh speech is never trimmed.
- I2 A microphone that only listens commits and saves 0 invented or echoed words (round-4 result 104/73 → 0).
- I3 Local speech of ≥ 3 words that the provider returned is committed live and saved.
- I4 The saved transcript never loses speech the live transcript had; no speech appears twice.
- I5 English behaviour of F1's rule is byte-identical to today.
- I6 Rule W changes speaker labels only; rule H copies final labels and never changes them.

## 3. Work packages

Design source for each package is the prototype's `NOTES.md` (binding: rule in full, parameters with measured
margins, regression test list). The implementer lifts the measured rule; any deviation is reported, not improvised.

**WP-A — F1 preview trim in comparable units** (`gemini/r5-f1`, `…/mic-speaker-echo/f1/NOTES.md`)
- `gemini_live_runtime.py`: `_trim_committed_preview` and `_repeated_head` compare lane-composer units (one per CJK /
  kana / Hangul character, other runs whole) with evidence weight ≥ 25 (word 5, character 3: five words or nine
  characters). `_preview_units`/`_CJK` move here from `gemini_lane_engine.py` (which imports them back; no behaviour
  change there). CJK punctuation added to the post-cut strip.
- Tests: 14 in `tests/gemini/test_gemini_preview_duplication.py` (list in NOTES).
- Not included: script folding (traditional vs simplified leaves 1–4 characters at such a frontier).

**WP-B — F2 local-voice evidence for microphone admission** (`gemini/r5-f2`, `…/f2/NOTES.md`)
- `gemini_lane_engine.py`: new evidence class (per 10 ms frame: microphone speech by the production detector mode 3;
  echo return = median microphone/tab level over tab-voiced frames, fixed −15 dB when < 1 s of tab speech;
  unexplained frame = microphone speech while the tab is silent or > echo return + 6 dB; sustained stretch ≥ 0.4 s).
  A provider run is local when it touches a sustained stretch, ≥ 80 % of its words lie on unexplained audio and its
  text weighs ≥ 15. Used at three sites: (A) the level gate keeps local words it would drop; (B) a window or lane
  without a 2 s span keeps local runs — a short phrase admits only itself; (C) the text echo guard drops a local word
  only as part of a two-word echo phrase. `MicrophoneWordGate(local_voice=None)` = today's behaviour.
- Counters added to `engine_diagnostics`: `mic_words_from_provider`, `mic_words_kept_by_local_voice_level`,
  `mic_words_kept_unanchored_by_local_voice`, `mic_echo_return_db`, `mic_local_voice_seconds`.
- `provider_revision` → `-v9`; `docs/design-gemini-live.md` microphone section updated.
- Tests: 13 specified in NOTES.
- Known limits (stated to the user): one- and two-word replies with no long turn nearby stay withheld; a phrase the
  provider never returns cannot be admitted; another person in the room is admitted from 0.4 s.

**WP-C — F3 rule H: clean-up keeps live words it offers no replacement for** (`gemini/r5-f3`, `…/f3/NOTES.md`)
- Witness list: `gemini_hybrid_engine.py` keeps the words each rolling window committed (a later window's straddling
  word replaces the earlier truncated copy) and hands them to the terminal in `finish()`;
  `gemini_lane_engine.ConditionalMicrophoneTerminal` passes them through; `gemini_coverage.py` gets the rule. A live
  run with ≥ 0.15 s not covered by any clean-up word (provider time step 0.1 s) is a restore candidate; an edge word
  equal to the adjacent clean-up word is dropped. Intervals owned by the existing 10 s fallback are skipped. File/URL
  runner and Stop-tail recovery unchanged. Counter `witness_restored_words`.
- **System lane (as prototyped):** `gemini_provider.TerminalTranscriber.transcribe` restores after labels are final
  (stitcher / identity policy — therefore after rule W) and before the word gates; a restored run takes the nearer
  neighbour's speaker.
- **Microphone lane (changed after review, R-F1/R-F2):** a committed live word is not proof of local speech (round 4
  recorded three invented live words beside a real turn), and a restored run must not be judged as part of its
  neighbours. So on the microphone lane: (1) the clean-up words go through the microphone gates (WP-B) first, exactly
  as without rule H; (2) each restore candidate run is then judged **on its own** — never merged with neighbouring
  clean-up words by label — and is restored only if it is a *local run* by WP-B's evidence (touches a sustained
  unexplained stretch, ≥ 80 % of its words on unexplained audio, text weight ≥ 15), **also on a lane that already has
  an anchored turn** (`local_speech_seen` does not waive it); (3) only then does it take a speaker label (the nearer
  kept neighbour on that lane, else the lane's local speaker). Echo words kept by clean-up around it play no part.
- This composition is prototyped and measured BEFORE it is implemented (WP-BC below).
- Tests: 12 rule-level, 3 terminal-level, 3 engine-level (list in NOTES) + the WP-BC cases.
- Known limits: cannot restore what live never had; a word clean-up replaced stays replaced; live fragments
  ("Yeah,") come back on the system lane; restored words keep the live script; on the microphone lane a one- or
  two-word live reply that clean-up omits is not restored.

**WP-BC — composition prototype: microphone admission × witness restore** ($0, before WP-C is implemented)
- Throwaway, in `prototypes/gemini-live/mic-speaker-echo/bc/`, composing `f2/evidence.py` + `f2/candidate.py` with
  `f3/rule.py` on the production engine with recorded answers. Contract in NOTES.md first.
- Must show, with numbers: (a) **omitted short reply amid echo** — clean-up omits a 3–6 word local reply and keeps the
  surrounding echo words; quiet local audio (10 and 20 dB under the tab); with the order above the reply is saved
  (the reviewer's probe: merged with the echo run only 6 of 31 words touch unexplained audio → 0 eligible);
  (b) **invented words beside a real turn** — the round-4 pattern (three invented live words next to a real local
  turn, clean-up omits them): 0 restored, also with `local_speech_seen` true; deterministic live-only noise witnesses
  omitted by clean-up: 0 restored; (c) every F2 and F3 prototype number on the recorded cells is unchanged or better;
  (d) the same with rule W's label step enabled and disabled (W acts before H; microphone admission must not change).
- A failed (a) or (b) changes the design before any production code is written.

**WP-D — operator diagnostics line** (new, small; needed to verify F2 on the user's physical device)
- At the end of a live meeting (after clean-up, or at close when clean-up is off) emit ONE content-free operator
  event (`moss-operator-event.v1`, code `meeting_engine_diagnostics`) with the meeting id and the numeric
  `engine_diagnostics` (calls, counters above, cost; no text, no audio, no key). Today the counters live only in
  memory, so the user's own failing meeting could not be diagnosed. No schema change, no new storage.
- Test: one unit test that the event carries the counters and no transcript text.

**WP-E — merge `gemini/r5-m`** (M1, M2; already implemented: frontend 551 / backend 2713 pass with rebuilt bundle).

**WP-W — rule W** (docs/plan-r5-label-purity.md §12–§14) — **DROPPED 2026-10-01: Stage 3 verdict UNMEASURED** (the
provider did not reproduce the failure on any of three fixtures; W equalled the shipped rule word for word; $0.29
spent). Production keeps the shipped stitch rule; step S4 is skipped. The text below is kept for the record.
- Stage 3 first (user-approved, cap $0.30, evaluator pane 6.4 at "READY v2", gates frozen in §13). Independent of
  WP-A…E: it scores shipped rule A vs frozen W on the same raw provider words of system-lane fixtures; the raw
  responses are saved, so re-scoring after integration costs $0.
- Only if Stage 3 says PASS: production change in `gemini_long_final.py` (and `gemini_final_policy.py` only if the
  same primitive applies and is measured there), lifted from `…-wt-r5-p3/prototypes/gemini-live/label-purity/w/`,
  with regression tests from the recorded 65.5-min pattern and the four protective pairs. FAIL or UNMEASURED: W is
  dropped from this plan and production keeps the shipped rule.

## 4. Who builds what, and in what order

Lead (Claude, MOSS:5.1) owns orchestration, review, merges and steering. Implementers are the Codex agents
(gpt-6.1-sol, high) in tmux panes 6.1–6.4, each started with a fresh context (`/new`) and a written brief
(`~/Documents/Codex/2026-09-28/moss-gemini/briefs/R5B-*.md`, status `status/R5B-*-STATUS.md`). Integration branch
`gemini/r5b-int` in a NEW worktree `…-wt-r5b-int` (from `gemini/r4-ui`), so the pilot's worktree is untouched until
cutover.

| Step | Work | Who | Depends on |
|---|---|---|---|
| S0 | Stage 3 paid run and scorecard (WP-W, cap $0.30) | pane 6.4 (evaluator, keeps its context) | launch |
| S1a | WP-A implemented on `gemini/r5-f1` | pane 6.1 | launch |
| S1b | WP-B + WP-D implemented on `gemini/r5-f2` | pane 6.2 | launch |
| S1c | WP-BC composition prototype on `gemini/r5-f3` ($0) | pane 6.3 | launch |
| S2 | Lead review (own reading + an independent adversarial pass by a fresh-context Codex pane) and merge into `gemini/r5b-int`: WP-E → WP-A → WP-B/D | lead | S1a, S1b |
| S3 | WP-C implemented on a branch cut from `gemini/r5b-int` **after WP-B is merged** (it needs WP-B's evidence class; this also removes the two-file conflict), following WP-BC's measured design; lead review; merge | pane 6.3 | S1c, S2 |
| S4 | If S0 = PASS: WP-W production change on top of `gemini/r5b-int`; verification on HOLD + Stage-3 raw words at $0 | a free pane (fresh context) implements, pane 6.4 verifies | S0, S3 |
| S5 | Integration gates at $0 (§6 G-int), bundle rebuilt once, both full suites | lead | S3 (+S4) |
| S6 | Adversarial review of the whole integration diff by a fresh-context Codex pane; findings fixed by the owning pane; repeated until no blocking finding remains | lead + panes | S5 |
| S7 | Real-provider stress matrix (§7) on the integrated build, own server on ports 18960–18969 | helper with the R5-T harness | S6 |
| S8 | **Candidate server for the user's physical check** — the integrated build served from `…-wt-r5b-int` on port **18620** with its own state, same host names as the pilot. The pilot (:18600) stays on today's code | lead | S7 |
| S9 | Attended check by the user on the MacBook against :18620 (§8); lead reads the diagnostics line. **Blocking**: a required sentence missing, or echo/invented text saved as local speech → no cutover; diagnose from the counters, fix, re-run S5–S9. Incomplete measurement is not a pass | user + lead | S8 |
| S10 | Cutover: `gemini/r4-ui` fast-forwarded to `gemini/r5b-int`, pushed; pilot restarted once (after checking no active meeting); candidate server stopped. Rollback = restart the pilot at `9a1ca171` | lead | S9 pass |
| S11 | After the user's OK: laptop update + trusted certificate (docs/plan-r5-start-flow.md) | lead | S10 |

## 5. Interactions between packages (each is checked at S4)

| Pair | Risk | Check |
|---|---|---|
| WP-B × WP-C | (i) A restored local reply judged together with neighbouring echo words fails admission and is deleted; (ii) an invented live word beside a real turn is restored because the lane is already anchored; (iii) a lane the saved pass withholds deletes live-committed local runs | WP-BC cases (a)–(d) as regression tests on the product code; replay R5-D's 9 two-lane cells + F2's cells: saved microphone units ≥ F2 prototype numbers; 0 invented/echoed |
| WP-A × WP-B | More microphone rows are solid, so the microphone preview is trimmed against them | F1's microphone-lane Mandarin cell and F2's short-phrase cells: 0 repeated units, fresh units not lower |
| WP-C × WP-W | H must run after W's labels and copy them | 65.5-min raw replay: W's result unchanged (host one group, long60 DER ≤ .060); restored words carry the neighbour's final label |
| WP-B × WP-W | If W enters `gemini_final_policy.py` it runs on the microphone lane before the anchor reads labels | Only if W touches that file: F2 cells before/after W, identical admission |
| WP-C × round-4 mic fix | A live-only invented word in a clean-up-silent stretch would be restored | Microphone restores need local-run evidence of their own (WP-C); the round-4 mixed speech/noise lane and a listener lane are replayed at S5 and re-recorded through the whole engine at S7 |

## 6. Gates

Per package (numbers from the prototypes are the bar; "not lower than the prototype on the same recorded cells"):
- **G-A** repeated units → 0 on every recorded unspaced/mixed cell; English/Korean cells byte-identical; fresh units
  not lower; cross-lane trims 0; ≤ 1 ms added per publication.
- **G-B** I2 holds on all nobody-speaking lanes (0 committed, 0 saved); short phrases ≥ 3 words saved in the recorded
  cells (English 15/15, Mandarin 15/15 at −40 dB); long turns not below today; double-talk at 20 dB under the tab:
  long turn ≥ 27/31; echo committed 0 at −40/−25/−15 dB.
- **G-C** name tokens lost ≤ prototype (115 → 4 over the 100 pairs); doubled units 0; frontier duplicates still
  removed; speaker error on truth fixtures not worse by > .005; added provider cost $0.
- **G-BC** WP-BC (a) omitted short reply amid echo saved at 10 and 20 dB under the tab; (b) 0 invented or noise
  witnesses restored, anchored lane included; (c) recorded-cell numbers of F2 and F3 not lower; (d) identical with W's
  label step on and off. Each must be exercised: an unexercised case is UNMEASURED and blocks S3.
- **G-D** the diagnostics event appears once per meeting, numbers only.
- **G-E** `gemini/r5-m` tests pass after the bundle rebuild.
- **G-W** docs/plan-r5-label-purity.md §13 decision rule; after integration the HOLD and Stage-3 raw words give the
  same W result at $0.
- **G-int** (S4): frontend suite, full backend suite (`MOSS_TEST_REAL_SQLITE=1`), the three prototypes' recorded
  matrices re-run against the PRODUCT code (not the patched copies) with results equal to the prototype's, and the
  §5 checks.

## 7. Real-provider stress (S5; needs the user's approval of the cap)

Real Chrome, the real page, public audio only, summaries off, spend ledger before every run.

| Cell | Purpose | Est. cost |
|---|---|---|
| Mandarin + English names on the tab, silent microphone | F1 on the real page; F3 names kept | $0.10 |
| Mandarin tab → English tab, short local replies (English and Mandarin) at −40 dB echo | the user's scenario: F1 + F2 + F3 together | $0.13 |
| English tab, quiet local speech over the tab (20 dB under), −25 dB echo | F2 double-talk; echo never committed | $0.13 |
| English tab, microphone only listening, −25 dB echo and room-noise events | I2 on the whole engine | $0.13 |
| One round-4 listener lane and the round-4 mixed speech/noise lane re-recorded through the whole engine | I2 against the original fixtures; no invented word restored beside real speech | $0.55 |
| Both sources, 16-minute meeting (chunked clean-up, stitcher) with a late joiner | H + W (if shipped) + F2 in a long meeting | $0.95 |
| Rename a speaker → Summary pane + Markdown export, label at 1440 / 400 px | M1/M2 on the real page (summary ON for this cell only) | $0.10 |

Estimated $2.1; **cap $3.00** (retries and one repeated cell). Separate from Stage 3 ($0.30, already approved).

## 8. Attended check by the user (S9, about 5 minutes, against the candidate at :18620 BEFORE cutover; only a physical microphone shows real echo cancellation)

1. The 2.5-minute script in `…/f2/NOTES.md` ("Attended check"): silence → a short question over the tab → a 5–6 s
   sentence over the tab → pause the video, "Okay, sounds good." then "Yes." → noises without words → a quiet
   sentence over the tab → Stop. Expected: the four sentences saved under "You", nothing else; "Yes." may be missing.
2. A Chinese video with English names for 60 s: no grey repetition; after Stop the names are still there.
3. Rename a speaker; the summary shows the new name. The source box reads "System Sound Output".
The lead then reads the meeting's diagnostics line (numbers only): which rule kept or dropped microphone words,
the device's real echo return, and whether the provider heard the speech at all.

**Pass:** the four sentences of step 1 are saved under "You" ("Yes." may be missing), no echo or invented text is
saved as local speech, steps 2–3 as described. **Fail or incomplete:** the pilot stays on today's code; the counters
say which rule acted; fix and repeat.

## 9. Not in this plan (measured or noted, deliberately deferred)

- Chinese script consistency (provider flips simplified/traditional in live windows and clean-up; no request-side
  fix). Needs its own decision and prototype (a conversion must never touch Japanese text).
- Echo fragments in the grey microphone row (never committed; F2 D3). The stale doubled character at a window
  frontier in live text (clean-up removes it). The clean-up coverage retry that re-sends identical audio. A parser
  drop on a garbled provider time (1 word in 62 answers). Punctuation loss after clean-up (not reproduced).
- One- and two-word local replies with no long turn nearby.

## 10. Risks

- R1 Real echo cancellation may attenuate the local voice below what the evidence rule needs (file-backed microphone
  cannot show it). Mitigation: attended check + diagnostics line; today's behaviour is the fallback inside the rule.
- R2 WP-B widens admission (another voice in the room from 0.4 s; voiced non-speech with ≥ 3 provider words).
  Measured heaviest invented run: weight 10 vs bar 15. Watched by I2 cells in S4/S5.
- R3 Rule H can restore a live-only invented word (none in two attack cells; round-4 lanes re-run in S5).
- R4 Two packages edit the same two engine files; the lead merges and the §5 checks run on the merged code.
- R5 Stage 3 may be UNMEASURED (provider does not reproduce the failure): W is then dropped; the rest proceeds.
- R6 The integration replaces the pilot build the user is testing: one restart at S10, only after the physical
  check passed on the candidate server; rollback is a restart at `9a1ca171`.

## 12. Review findings → changes (`/codex:adversarial-review`, 2026-10-01)

| Finding | Change |
|---|---|
| R-F1 a restored local reply inherits an echo label and fails admission | Microphone lane: clean-up words are gated first; each restore candidate is judged alone on its own audio, then labelled (WP-C); WP-BC case (a) with W on and off |
| R-F2 invented words restored beside real speech; listener-only tests miss it | Restores need local-run evidence even on an anchored lane; WP-BC case (b); round-4 mixed lane in S5 and S7 |
| R-F3 physical acceptance after pilot cutover | Candidate server :18620; attended check S9 is blocking and precedes cutover S10; failure disposition and rollback stated |

## 11. Spend so far in this phase

Diagnosis $0.26, prototypes $0.06 + $0.24 + $0.17 = **$0.73 of the $1.00 phase cap**. Stage 3: $0 of $0.30.

## 13. Decisions and scope added after launch (2026-10-01 evening)

- **D15 = O1 (user): grey text is cut by the clock.** Grey shows only what arrived after the lane's confirmed point;
  older grey words disappear at confirmation even when the solid text lacks them (they are never saved either way).
  Fresh speech may never be hidden. Built as R5B-A4 (`briefs/R5B-A4.md`); the text-only attempts A2/A3 are recorded in
  `prototypes/gemini-live/mic-speaker-echo/{a2,a3}/NOTES.md`.
- Added during the round: Reassign-passage dialog as one dropdown (user request); restored runs keep their live
  speaker and microphone restore evidence is grouped by source partition (reviews 3–5); a phrase clean-up already has
  beside a hole is not restored (stress audit); remembered preview cut dropped when its solid support is replaced.
- **Standing instruction (user):** when the lead can confirm the build is ready, host ONLY the fixed build on one port
  (pilot :18600; candidate :18620 stopped) and update `ga0-rog-laptop` to the same build.
- Accepted boundary: an empty clean-up answer for a lane keeps the live rows as committed (pre-existing fallback).
