# Round 3 — UI/UX clean-up, per-user providers, preview duplication (2026-09-29)

Base: `gemini/r2-integration` @ `1dee41cb`. Integration branch `gemini/r3-ui`. Lead = Claude session; six helpers
(WP-A … WP-F) each in their own worktree `…-wt-r3-{a..f}` on branch `gemini/r3-{a..f}`. Local commits only.

## 1. Decisions (user, 2026-09-29 grilling)

| Code | Decision |
|---|---|
| Q1/Q2 | Settings = one dialog, three tabs: **Transcription**, **Summary**, **General**. Both model tabs ask Vendor, URL, Model name, API key. MOSS self-hosted stays unplugged (code kept, not offered). |
| Q2 | Transcription vendors: **Gemini (AI Studio)** (URL hidden, model default `gemini-3.5-transcribe`) and **OpenAI-compatible** (URL, model, key optional). |
| Q3/J1 | OpenAI-compatible transcription = small adapter: POST `{url}/audio/transcriptions`; uses the model's speaker labels when returned (`diarized_json`), else one provisional label per returned segment so local WeSpeaker fingerprints (ContinuityRegistry) link voices. No instant grey words for this vendor; clean-up after Stop not offered for it. Tested only against a local fake server; real-model quality UNMEASURED. |
| Q4 | Gemini key is **required** (both tabs). The server key in `.env.local` is never used by the browser app. Start / summary / File / URL are blocked until a key is entered (K9). |
| Q5 | Microphone-lane default names: first local voice **"You"**, then **"User 1"**, **"User 2"** … unless a voiceprint names them. Shared-lane speakers: **"Speaker 1"**, **"Speaker 2"** … everywhere (no raw `S01`, `S01?`, `Speaker TBD?`). Guesses show the plain label (e.g. `You`, `Speaker 2`) with a dotted colour rule instead of the solid one, and a screen-reader-only "(guess)" (issue #7; was a `?` suffix). |
| Q6 | Text rule: a string stays only if it tells the user to do something or explains why a control will not work. Keep list K1–K9 below; everything else removed. States show on the control (Export Save reads "Improving…" and is disabled; top pill "Recording 12:34" / "Stopping"). |
| Q7 | Stress-test budget: real Gemini ≤ **$5** (public audio only). |
| J2 | Speaker window = two integer fields: **Refresh every** 5–60 s (default 15) and **Context** 90–300 s (default 90); refresh ≤ context. Presets removed. The 90 s floor is measured (P5: 60 s merged/split speakers). |
| J3 | Rolling summary: checkbox **Rolling summary** + **Wait after each summary (s)** timed from the END of the previous request; 0 = start the next immediately; requests never overlap. Default 60 (round 4 #10: 20). |
| J4 | Default summary prompt shortened to a few lines, same five JSON sections. |
| J5 | Shared-lane source label from Chrome's share choice (`displaySurface` of the display-media video track): `browser`→**Browser**, `window`→**Window**, `monitor`→**Screen**; microphone lane → **Mic**. Stored per meeting id in browser storage (History is per-browser, ADR-0006). |
| J6 | Transcript rows copy LiveTranscribe: left meta column (speaker name, source, time), text right; speaker colours `--sp-1…8`; floating glass Find / Copy / Auto-scroll toolbar and glass find bar. Fonts and tokens from LiveTranscribe. |
| J7 | Product name **"aiSight - LiveTranscribe"** in the top bar and the browser tab title (replaces "MOSS"). |
| J8 | Preview duplication fix = diagnosed trim rewrite + lane tag on degraded (preview-fallback) commits. |

### Keep list (Q6) — the only status/hint text allowed

- K1 No microphone sound — check the input in Chrome site settings.
- K2 Microphone / System sound too loud — lower it.
- K3 System sound stopped / Microphone stopped. *(Round 5: the user-facing name is "System sound", not "Shared audio".
  A recorded source that stops mid-recording goes silent and the recording continues to a normal Stop, so the line is
  the plain fact with no action.)*
- K4 Reconnecting — keep this tab open.
- K5 Recording stopped: connection lost. *(Round 5: no Reset; Start recording is offered directly.)*
- K6 Start disabled → tooltip names the source with no sound yet. *(Retired in round 4: Start needs only both sources attached, never sound, so there is no tooltip.)*
  *(Round 5: Start is disabled only while both source boxes are unticked; tooltip "Tick System sound or Microphone.")*
- K7 Two meetings are already recording — stop one first.
- K8 Action failures with the reason: naming, correction, export, upload/URL, summary failed [Retry].
- K9 Enter your Gemini API key in Settings.
- K10 (round 4, #13) File/URL row stage, so a long job does not look dead: Uploading… (browser sending the file) /
  Downloading audio… / Transcribing… (server `file_stage` on the active meeting) / Done.
- K11 (round 5, Q16) What one Start click could not record: "Microphone unavailable" (recording system sound only; the
  Microphone box unticks) / "System sound not shared" (recording the microphone only) / "No audio was shared — turn on
  “Also share audio” in Chrome’s picker" (nothing started). A closed share picker says nothing. These replace the
  three-step setup lines "Microphone blocked — allow it in Chrome site settings.", "Sharing did not start." and "No audio
  in that share — choose a tab and turn on Share tab audio.", which are retired with the "Enable microphone" and
  "Share audio" buttons and the "Listening with" control (`docs/plan-r5-start-flow.md`).
- Plus: top pill (Recording mm:ss / Stopping), Export Save "Improving…" (disabled), one line "Voiceprint not saved — not enough clear speech" when enrollment is refused.

Removed (non-exhaustive): "Needs review…", "Identity settling…", "Transcript improved", "Improvement unavailable…" and its
duplicates, all "Next:" hints, "Private to this browser", "Speakers cancel echo…", dialog hint paragraphs, voiceprint
saved/pending messages, meter sub-labels, "Audio export waits…", export-file notices ("Provisional attribution",
"Needs review"), summary "next in Ns" / "Rolling summary is off" / empty-state sentences, voiceprint-tab hint. Raw internal
codes never reach the UI (map to K5 or K8). Empty transcript: nothing, or the reference's single line.

## 2. Interfaces (frozen for all WPs)

### I-1 Browser settings (`frontend/src/lib/settings.ts`, localStorage key `moss.settings.v2`, migrate v1)

```ts
type Vendor = "gemini" | "openai_compatible";
interface AppSettings {
  transcription: { vendor: Vendor; url: string; model: string; apiKey: string;
                   refreshSeconds: number; contextSeconds: number };        // 15 / 90
  summary: { vendor: Vendor | "off"; url: string; model: string; apiKey: string;
             rolling: boolean; waitSeconds: number; language: string;
             timeoutSeconds: number; prompt: string };                     // gemini-3.5-flash-lite, true, 60 (r4: 20)
  general: { cleanupAfterStop: boolean };                                   // true
}
```
Migration v1→v2: speakerWindow balanced/economy/max → (15,90)/(30,90)/(15,180); summary built-in → gemini (key empty),
external → openai_compatible (url/model/key carried), intervalSeconds 0 → rolling false.

### I-2 Wire contract (browser → server)

Transcription settings object (same everywhere):
```json
{"vendor": "gemini" | "openai_compatible", "url": "https://…" | null, "model": "gemini-3.5-transcribe", "api_key": "…" | null}
```
- **Live create** `POST` session create body: `{"engine_settings": {"transcription": T, "refresh_seconds": 15,
  "context_seconds": 90, "cleanup_after_stop": true}}`. Missing/empty Gemini key → 400
  `{"code": "api_key_required"}`. Validation errors → 400 with a human `detail`.
- **File / URL upload**: the same `T` as multipart form field `transcription` (JSON string).
- **Summary** `POST /api/meetings/{id}/summary/live|server`: body adds `"provider": {"vendor": "gemini", "model": "…",
  "api_key": "…"}`. (OpenAI-compatible summaries keep the existing browser-side external path.)
- **Test** `POST /api/providers/test` body `{"purpose": "transcription"|"summary", "vendor", "url", "model", "api_key"}` →
  `{"ok": true}` or `{"ok": false, "detail": "<human reason>"}`. Gemini: one cheap model lookup; OpenAI-compatible:
  `GET {url}/models` (model must be listed if the list is returned).

Secrets: the API key lives only in browser storage and in server memory for the meeting/job/request. Never persisted
(SQLite, notices, diagnostics, logs, receipts, exceptions). `diagnostics.engine_settings` must redact it. After a
server restart an in-flight clean-up or File job cannot resume → existing "live version kept" / job-failed paths.

### I-3 Descriptor `engine_options` (server → browser)

```json
{"transcription_vendors": ["gemini", "openai_compatible"], "default_model": "gemini-3.5-transcribe",
 "refresh_seconds": {"min": 5, "max": 60, "default": 15}, "context_seconds": {"min": 90, "max": 300, "default": 90},
 "cleanup_after_stop": {"available": true, "default": true}}
```

### I-4 Speaker display names (Q5)

One rule, implemented once per side: backend `live_surface.default_speaker_name` (saved transcript/export) and frontend
`defaultSpeakerLabel` / `speakerColorToken` (live view, guesses, History). A default name and colour are read off the
speaker's id alone: `local-1`→"You", `local-(n+1)`→"User n"; shared lane `speaker-000n` / File `S0n` → "Speaker n";
named/voiceprint names always win; guesses = plain label + dotted rule (issue #7).
Round 4 (F4) replaced "numbered in order of first speech": that order belongs to one version of the transcript, so
clean-up renamed speakers (5 of 25 surviving speakers in 5 recorded long60 live→refined pairs; the live "Speaker 1" became
"Speaker 3" in r4-ui-e2e run a) and naming one speaker renumbered the rest. Ids are kept by clean-up and were handed
out contiguously in speaking order in all 35 round-2–4 snapshots, so id-derived names change for 0 of 25; a speaker that
disappears leaves a gap, a new one takes the next unused number.

### I-5 OpenAI-compatible adapter (WP-F → wired by WP-B)

`moss_transcribe_diarize/app/openai_compatible_provider.py`: `OpenAICompatibleDiarizer(url, model, api_key,
report_usage)` implementing the same call surface `WindowDiarizer` exposes to `GeminiHybridEngine`,
`LaneGeminiEngine` and `GeminiFileRunner` (returns the same word/segment types with lane-local speaker labels).

## 3. Work packages

| WP | Scope | Owns (primary files) |
|---|---|---|
| A | Preview duplication fix (trim rewrite, earlier-preview dedupe, lane tag on degraded commits) + I-4 backend label + tests | `gemini_live_runtime.py` (trim, labels), `gemini_lane_engine.py` (degraded commit lanes), tests |
| B | Per-meeting provider settings (I-2/I-3), key required, redaction, seconds validation, test endpoint, summary key from request, File/URL settings, wiring I-5 | `phase2_web_cli.py`, `gemini_live_runtime.py` (validate/diagnostics only), `phase2_live.py`, `phase2_summary.py`, `phase2_llm.py`, `phase2.py` (routes), `gemini_file_runner.py` |
| C | Transcript pane: reference rows, floating glass toolbar + find bar, J5 source labels (capture `displaySurface`), I-4 frontend labels, Q6 removals in transcript pane | `TranscriptPane.tsx`, `TranscriptCards.tsx`, `lib/transcriptCards.ts`, `lib/tentative.ts`, `lib/speakerMap.ts`, `lib/transcriptOrder.ts`, `capture/captureClient.ts` (surface only), new `styles/transcript.css` |
| D | Settings dialog (3 tabs, reference modal), I-1 schema + migration, request plumbing (I-2 bodies), Test buttons, J3 scheduling, J4 prompt | `SettingsDialog.tsx`, `lib/settings.ts`, `lib/summaryRequests.ts`, `SummaryPane.tsx` (scheduling), `lib/fileUpload.ts` (body), `final-summary-prompt.txt`, new `styles/settings.css` |
| E | Shell: J7 title, tokens/fonts from LiveTranscribe, top bar/pill, Control panel simplification (keep dropdowns/buttons), History / Voiceprints / Summary pane text removals, export notice removal, K1–K9 wording incl. backend `live_capture_status.py`, K9 gating of Start | `App.tsx`, `ControlPanel.tsx`, `MeetingHistory.tsx`, `VoiceprintBank.tsx`, `SummaryPane.tsx` (text only), `lib/transcriptExport.ts`, `lib/fileUpload.ts` (text), `live_capture_status.py`, `phase2.py` (page shell strings), `index.html`, `styles/index.css` tokens, fonts |
| F | OpenAI-compatible adapter (I-5) + local fake server + contract tests | new `openai_compatible_provider.py`, new tests |

Merge order: A → F → B → D → C → E (lead resolves conflicts; frontend assets rebuilt once at the end).

## 4. Gates

1. Backend suite (`MOSS_TEST_REAL_SQLITE=1 pytest -q tests`) and frontend (`npm test`, `npm run typecheck`, build) green.
2. Duplication replay (`scratchpad/r3/dup-diag/replay.py`) on the merged head: 0% snapshots with ≥5 already-committed words.
3. Chrome walkthrough (desktop 1440 and phone 400 widths) of Controls (Live/File/URL), transcript with preview + guesses,
   find bar, Settings three tabs, Summary tab, History, Voiceprints: screenshots; no removed string visible.
4. Real Gemini ≤ $5 with the key typed into Settings: E1 two-lane ×2, long60 ×1, one File, one URL. Saved DER not worse
   than round 2 (accept6-style spot: E1 labels ≤ 5; long60 ≤ .060), zero preview duplication in the captured snapshots.
5. OpenAI-compatible adapter: fake-server live meeting and File job end to end.
