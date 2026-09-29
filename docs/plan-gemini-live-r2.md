# Gemini live — round 2 plan v2 (grilled 2026-09-29; revised after Codex adversarial review)

Base: `gemini/live-hybrid` (worktree `MOSS-Transcribe-Diarize-wt-gemini-live`, which also serves the pilot on :18600 — never
switch its branch). Lead: Claude in MOSS:5.1 (integration worktree `…-wt-r2-int`, branch `gemini/r2-integration`).
Workers: Codex gpt-6-sol high in MOSS:5.2, 5.3, 6.1, 6.2, 6.3, 6.4 (G12 O2), one worktree + branch each. Local commits
only; no push/merge/PR. Briefs: `~/Documents/Codex/2026-09-28/moss-gemini/briefs/R2-*.md`; evidence `…/evidence/P66/`.
Prototype evidence behind each item: `prototypes/gemini-live/{schedule,guard,tentative}/NOTES.md`, `evidence/P65/p2-cleanup-skip.md`.

## 1. Decisions carried into this plan

| Code | Decision |
|---|---|
| D17 O2 | Naming a speaker after Stop also saves a voiceprint (fingerprint that speaker's non-overlapping rows in the saved recording). |
| D19 | Self-hosted MOSS stays in code, hidden; `--live-engine moss` still works and ignores the new options; its tests keep running; no MOSS wording in the UI. |
| G1 O2 | The mic lane may hold several local people: diarize its 30 s windows (stride 15 s), link across windows by overlap + fingerprints (+ veto). |
| G8 O3 | Local people default to "Local 01", "Local 02", … |
| F12 | Mic and meeting-audio lanes call Gemini in parallel (remove the shared batch lock). |
| F13 | Rows committed with no speaker are re-labelled by later windows instead of staying "Speaker TBD". |
| G10 O1 + P4 + P5 | Speaker-window presets: **Balanced 15 s / 90 s (default)**, Economy 30 s / 90 s, Max context 15 s / 3 min; 60 s rejected (P5). P4 fingerprint veto (T .46, margin .20) in the continuity registry. |
| G2 O3 + G9 O1 | Local fingerprint guesses on preview words (1.0 s snippet, T .40, EMA centroids, every 0.5 s per voiced lane, single-thread ONNX per the embedder invariant), shown greyed "Ben?"; display-only, never saved or exported. On confirmation, consecutive same-speaker text on the same lane with no other speaker between renders as ONE block. |
| P2 | After-Stop clean-up is a setting, **default OFF** for Gemini (user decision; see R-A1 for the evidence gate). |
| G3 O3 | All settings live in the browser and are sent with each meeting start / summary request; the server stores none. |
| G4 O1 | Summaries use the server's Gemini key by default, model `gemini-3.5-flash-lite` (dev/test). |
| G5 O1 | "Transcript | Summary" tab in the centre card; rolling summary every 60 s while live, final at Stop, Refresh; the finished meeting is auto-selected. |
| G6 O1 | Left Controls panel like LiveTranscribe (Mode Live|File|URL → Start/Stop → mode section → Export dropdown + Save); Settings gear top-right opens a Settings pop-up; History right with Sessions|Voiceprints. |
| G7 O1 | File and URL work on the Gemini engine via the after-Stop pipeline. |
| G11 | Future only: per-account server-side settings with CRE Studio single sign-on. Not built now. |

## 2. Changes after the adversarial review (R-A = review finding, R-L = lead's own review)

- **R-A1 Clean-up OFF vs ADR-0002.** Keep the user's default OFF, but (a) add **ADR-0017** "Gemini engine: live result is the saved
  transcript by default" that scopes ADR-0002's retrospective-sweep requirement to the MOSS engine and records the evidence;
  (b) add gate **Q-IND**: live-only vs clean-up-ON on every independent complete-reference meeting we have (accept6 ×6, bench5m
  lex ×3, Bill30m, long60, gold9 calibration clips with complete references). Pass = on every meeting live-only IDs ≤ true+1 and
  DER ≤ clean-up-ON DER + 0.03. On failure the lead escalates to the user with the table; the default is not flipped silently.
- **R-A2 Summary ownership.** Amend **ADR-0011** (server may generate summaries with its own Gemini key; rolling summaries over
  the live transcript are allowed and ephemeral) and **ADR-0013** (server-held Gemini key exception now covers summaries).
  Routes are owner-bound through the existing Account workspace (ADR-0006): see §4.
- **R-A3 Echo fixture.** WP2 builds a two-lane public fixture: system lane = public voices A+B; mic lane = two other public voices
  C+D plus an echo of the system lane at −20 dB and −10 dB, 40 ms delay, light synthetic reverb; also a headphones variant (no
  echo). Gate Q-MIC scores echo rejection AND local-voice retention (§5).
- **R-L1 File ownership** per WP (§3) to limit merge conflicts; shared-file edits are small and named.
- **R-L2 Stop with clean-up OFF**: drain the tail, run the F13 relabel over the whole meeting, mark final; voiceprints (D17) and
  summaries work the same as with clean-up ON.
- **R-L3 MOSS stays recoverable**: every new behaviour lives in the Gemini composition; the descriptor tells the UI which options
  exist, so a MOSS server hides the transcription settings.
- **R-L4 Cost meter** records metered input and a Google-rate output estimate ($0.002/min Transcribe, $0.004/min Live) until
  A5 (billing check) settles which is real.

## 3. Work packages (worktree `…-wt-r2-wpN`, branch `gemini/r2-wpN`, all from the same base commit)

| WP | Pane | Scope | Owns | Shared edits |
|---|---|---|---|---|
| WP1 Engine core | 6.3 | F12; presets per meeting; P4 veto; registry `id_prefix` for lane namespaces; F13 relabel; clean-up flag + Stop path (R-L2); descriptor `engine_options`; cost meter (R-L4); ADR-0017 draft. | `gemini_hybrid_engine.py`, `gemini_continuity_registry.py`, `gemini_live_runtime.py`, `gemini_provider.py` | `phase2_web_cli.py` (composition), `phase2_live.py` (payload pass-through) |
| WP2 Mic lane | 6.1 | G1 O2 diarized mic windows with registry `id_prefix="local"` (+veto); "Local NN" default label (server side); diarized mic clean-up pass when ON; cross-lane voice echo check; fixture + scorer (R-A3). | `gemini_lane_engine.py`, fixture/scorer under `prototypes/gemini-live/micfixture/` | `phase2_web_cli.py` (mic factory), `phase2.py` default label |
| WP3 File engine + voiceprints | 5.3 | G7 Gemini file runner for `FileMeetingTasks`; voiceprint evidence for File meetings; D17 O2 after-Stop enrollment for Live meetings. | new `gemini_file_runner.py`, `phase2_speaker_identity.py` | `phase2_web_cli.py` (file runner wiring), `phase2.py` (file_evidence wiring) |
| WP4 Fast guesses | 5.2 | G2 O3 tentative spans on the provisional snapshot; per-lane EMA centroids; abstain rule; G9 one-block rendering rule. | new `gemini_tentative.py`, `live_session.py` provisional field, `frontend/src/lib/transcriptCards.ts` + preview rendering | `gemini_live_runtime.py` (one hook in preview publish) |
| WP5 UI | 6.4 | G6 layout; Settings pop-up (Transcription: clean-up toggle, preset — shown only if the descriptor offers them; Summary: Built-in Gemini (default) / External / Off, model, prompt, language, interval 60 s, timeout; stored in `localStorage` `moss.settings.v1`); G5 tab; export md (default, includes summary) / txt / srt / vtt / json / audio mp3; greyed guesses; "Local NN"; remove the File/URL strip and duplicate export menu; auto-select finished meeting; strip MOSS wording; headless filmstrip + screenshots. | `frontend/src/**` except files WP4 owns | `phase2.py` `_workspace_html` (remove strip) |
| WP6 Summary + qualification | 6.2 | Server summary routes (§4) with `gemini-3.5-flash-lite`; ADR-0011/0013 amendments; harness updates (engine_settings, tentative coverage, Q-IND, Q-MIC); final qualification runs (§5) and cost ledger. | `phase2_summary.py`, `phase2_llm.py`, `prototypes/gemini-live/harness/**` | `phase2.py` route registration |
| Lead | 5.1 | Contract (§4), worktrees, merges in order WP1 → WP2 → WP4 → WP3 → WP6 → WP5 with the full-suite gate after each, code review + fixes, ADR-0017 final, design doc + report, pilot readiness. | `docs/**` | — |

WP2 and WP4 start immediately on their own files and rebase onto WP1 once WP1's registry/runtime commit lands (lead signals).
WP5 builds against §4 with mocked responses and integrates last.

## 4. Interfaces (frozen before workers start; changes only through the lead)

- **Start a live meeting** `POST /api/live/sessions`: optional `engine_settings: {"speaker_window": "balanced"|"economy"|"max",
  "cleanup_after_stop": bool}`; unknown keys/values → 422; defaults balanced / false. MOSS engine ignores the field.
- **Descriptor** `GET /api/live/descriptor` adds `engine_options: {"speaker_windows": ["balanced","economy","max"],
  "default_speaker_window": "balanced", "cleanup_after_stop": {"available": true, "default": false}}` (Gemini only; absent on MOSS).
- **Preset table**: balanced S15/L90, economy S30/L90, max S15/L180 (growing window, H0). Mic lane always 30 s window / 15 s stride.
- **Guesses**: snapshot `session.provisional.tentative_spans: [{start_sample, end_sample, source_lane, speaker}]` where
  `speaker` is a canonical meeting speaker ID; display-only; never in saved transcripts, exports, or events that persist.
- **Local IDs**: mic-lane canonical IDs `local-0001`, …; default display label "Local 01", … (server default label and frontend map).
- **Summaries** (owner-bound: `require_account` → Account workspace `open meeting` handle; wrong owner → 404; no `account_id`):
  - `POST /api/meetings/{meeting_id}/summary/live` body `{model?, language?, prompt?}` → current live effective transcript of an
    active meeting → `{summary, source: {committed_samples, text_revision_version}, generated_at_ms}`; not persisted;
    409 if under 40 words.
  - `POST /api/meetings/{meeting_id}/summary/server` body `{source_version, model?, language?, prompt?}` → completed meeting's
    authoritative transcript at that version (409 on mismatch) → existing 5-key validation → persisted as `final_summary`
    exactly like today's browser path (same artifact, same automatic title rule).
  - Model allow-list `gemini-3.5-flash-lite` (default), `gemini-3.5-flash`, `gemini-3.8-flash`; key from the server's `.env.local`.
  - The existing browser-owned External path stays unchanged.
- **Diagnostics** (`engine_diagnostics`, content-free): add `veto_fired`, `f13_relabels`, `tentative_shown_s`, `tentative_abstained_s`,
  `mic_echo_dropped_by_voice`, `output_cost_estimate_usd`.

## 5. Acceptance gates (integration head, real HTTP API, public audio only)

1. Backend + frontend suites, typecheck, build green; MOSS-engine tests green (D19).
2. **Q-LIVE** (clean-up OFF, Balanced): accept6 ×2 settled DER ≤ .110; E1 two-lane labels at Stop ≤ 4; long60 IDs ≤ 6 and
   DER ≤ .08; 0 dropped passages; speaker-less speech at Stop ≤ 0.5 % of speech time and no single speaker-less run > 2 s (F13;
   a voice with < 2 s in the whole meeting may legitimately stay "Speaker TBD").
3. **Q-IND** (R-A1) as defined in §2.
4. **Q-SPEED**: words p50 ≤ 1 s; speaker names p50 ≤ 15 s; guesses on long60: coverage ≥ 70 % of Speaker-TBD time, accuracy ≥ 95 %.
5. **Q-MIC** (R-A3): speakers variant — 0 local IDs born from system voices, ≥ 90 % of echoed system words dropped from the mic
   lane, C and D kept as exactly 2 Local IDs with ≥ 90 % of their reference words retained; headphones variant — same retention.
6. **Q-FILE**: accept6 files final DER ≤ .110; long60 file DER ≤ .06; voiceprint saved when naming after Stop (Live and File).
7. **Q-SUM**: valid 5-key summaries for E1 and long60; live rolling updates every ~60 s; wrong-owner request → 404.
8. **Q-UI**: filmstrip E2E passes; screenshots of Controls (3 modes), Settings, Summary tab, greyed guesses, one-block merge.
9. Cost per meeting-hour reported metered and with output estimate; total round-2 Gemini spend ≤ $50 (dev ≤ $5/pane, qualification ≤ $20).
10. Then the user's attended review (checklist in the handback).

## 6. Risks

- R1 The veto was proven on one voice pair (Q-IND widens this).
- R2 Guesses unmeasured on compressed conference audio, similar voices, echo, several local people (Q-MIC covers echo only synthetically).
- R3 No public multi-person single-mic corpus; the fixture is synthetic.
- R4 Codex weekly quota may run out mid-round → lead reassigns the package to a Claude agent.
- R5 Output-token billing unconfirmed (A5): Balanced is $1.36/h metered or $2.31/h if output is billed.

## 7. Out of scope

CRE Studio sign-in and server-side settings (G11), removing MOSS code, push/merge/PR, private or operator audio.
