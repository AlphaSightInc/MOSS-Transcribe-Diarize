# R4-C: invented short words on the microphone lane (issue #3)

The user sees short words in other languages (Russian, Japanese, and so on) on the local
microphone lane, probably caused by room noise. This prototype measures where those words
come from, where they survive, and which rule removes them without losing real local speech.

## One-command reproduction (run from the worktree root)

```sh
PY=../MOSS-Transcribe-Diarize-wt-r4-c.venv/bin/python
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/micfixture/build.py          # Q-MIC public lanes
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/mic-hallucination/build.py   # v1: 300 s, speech-rich
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/mic-hallucination/build2.py  # v2: 480 s, long listening stretches
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/mic-hallucination/run.py en-hp,en-sp       # cached Gemini calls
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/mic-hallucination/run.py --v2
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/mic-hallucination/sweep.py          # rule arms, cached
PYTHONDONTWRITEBYTECODE=1 $PY prototypes/gemini-live/mic-hallucination/verify_product.py # current product gate
```

`pilot.py` covers noise-only 30 s windows. `w3.py` streams one mic WAV through the
production `GeminiLiveWordSource` at 1.0×. `listen_only.py` builds whole mic lanes that
contain no local speech. Responses are cached in the shared `.cache`, so re-runs cost $0.

## Contract

- **Structural question.** A Gemini word on the microphone lane was either spoken by a
  local participant or invented from sound that is not local speech: room events, mouth
  noise, or the far end's voice left over after echo cancellation. What reachable evidence
  tells these apart without depending on the language?
- **Minimum primitives.**
  - The gated microphone words of one provider call.
  - Their timing.
  - One test for local speech context: a continuous attributed span of at least 2 s, with
    gaps of at most 0.6 s. This is the existing `attributed_embedding_intervals` evidence
    that a voiceprint or a Local ID already needs.
  - The whole-recording (terminal) pass, which stays the authority for the saved text.
- **Invariants.**
  - No word list or language list is used.
  - Mixed Chinese and English text is never removed because of its script.
  - Real local words that are part of sustained speech are never removed.
  - The terminal pass decides the saved transcript.
- **Assumptions and unknowns.**
  - Room events are generated signals (`noise.py`), not recordings.
  - The echo-cancellation residue (called AEC residual below; AEC = acoustic echo
    cancellation) is simulated: gated fragments of far-end speech at −38 dBFS overall,
    about 10 dB below the far end. This is a stress level. The real Chrome AEC3 residual
    level on the user's device is **unmeasured**.
  - The Mandarin speech comes from local macOS text-to-speech voices (Tingting and
    Meijia). Word timing is proxied by reference turns.
- **Falsifier.** A rule fails if it removes more than 0.5% of non-backchannel local words,
  or if it removes less than 90% of the invented words that survive the gates.
- **Tool decision.** Real Gemini calls were needed because the invented words are provider
  behaviour. Everything else replays the production `MicrophoneWordGate` chain (WebRTC
  word gate, acoustic echo, voice echo, text echo) over the cached words.

## How ProjectClerk handled it (read only)

| Lever | Where | Transfer |
|---|---|---|
| Strict mic speech detector before any ASR call. Window RMS must be at least 0.010 (−40 dBFS). Silero speech probability must be at least 0.6 over 2 contiguous 256 ms chunks. System lane: 0.004, 0.5, 1 chunk. | `Sources/Transcription/VadGate.swift:17-43`, `WhisperKitEngine.swift:130-131` | The main lever. Its effect was recorded in the ProjectClerk testing notes only: mic hallucinations "~25+ → 2", mic lines 208 → 158 (`docs/testing-notes.md:228-241`). Ours is the pre-fix shape: any WebRTC frame opens a window, and any voiced frame within ±0.2 s keeps a word. |
| Hard-coded foreign-script drop: a segment or word is dropped when at least half of its letters are Cyrillic, kana, Hangul or Thai. | `TranscriptSanitizer.swift:12-31`, `WhisperKitEngine.swift:168,180` | Assumes every meeting is Chinese plus English (`docs/plan-2026-06-18-residuals.md:9-13,65`). Caught 2 "КОНЕЦ" in live replay (`docs/lt1-filter-calibration-2026-07.md:41`). |
| Phrase and outro lists, gated on `noSpeechProb` | `WhisperKitEngine.swift:66-79,163-167` | Dormant: `noSpeechProb` was flat at 0.00 (`lt1-filter-calibration-2026-07.md:44-51`). Gemini exposes no such field. |
| Decoder settings: `.vad` chunking, `noSpeechThreshold` 0.4, `logProbThreshold` −0.8, language auto | `WhisperKitService.swift:117-129` | Whisper only. |

## Where invented words survive in this repo

All counts are after every production gate. "Stray" means a word whose midpoint lies more
than 0.3 s outside any local turn or backchannel.

- **Noise-only 30 s windows (pilot, 24 batch calls).**
  - Stationary noise, breaths, keys, coughs and throat sounds gave 0 words.
  - Creak and mixed events gave `Hm.`, `Miau.` and `Mamma mia!`.
  - AEC residual gave `Oui.`, `Ya.`, `Bi.`, `你。` and `呀。`.
  - With headphones and a silent far end, **15 of 15** invented words pass every gate.
- **Live rolling rows: the main surviving path.** Measured on the v2 listener fixture
  (480 s per lane, long silent stretches).
  - A-sp: 62 invented words (English fragments, `對。`).
  - B-sp: 94, including Japanese `ノ ミ シャ ソ ヤ`, `じゃあ。`, Polish `jest`, `ja` and
    Chinese single characters.
  - B-hp: 9 (a looped `tu`).
  - Real short replies were also shown in the wrong script: `Sure.` became `ショー` and
    `手。`.
  - These rows stay visible until Stop and the cleanup pass. If cleanup is off or fails,
    they stay for good.
- **Live preview (the W3 instant-word model, auto language since 856ff83b).**
  - Headphones: 0 invented rows.
  - Speakers with AEC residual: 9 to 11 invented rows per 300 s (`입니다.`, `はい。`,
    `Ciao.`, `Sí. Ya.`).
  - A real `Uh-huh.` was shown as Hindi `हां।`.
  - These rows disappear at the next live commit.
- **Saved transcript (whole-lane terminal pass).**
  - 0 invented words on all 6 lanes that contain local speech.
  - Listen-only lanes: headphones gave 0 words. Speakers with AEC residual gave 104 (A)
    and 73 (B) invented words that survive the gates. **Not fixed; see D2.**

## Rule arms (live rolling path, 6 lanes, production chain, cached words)

The reference has 1,194 non-backchannel units and 64 backchannel units.

| Arm | Non-backchannel units kept | Backchannel units kept (live) | Invented words |
|---|---:|---:|---:|
| Baseline (current product) | 1122 | 52 | 165 |
| Script consistency (a word's script must appear in the meeting's own text; no list) | 1122 | 52 | 148 |
| ProjectClerk's list (Cyrillic, kana, Hangul, Thai) | 1122 | 52 | ≈148 (same kana-only set) |
| Per-word WebRTC voicing of at least 200 ms (VadGate analog, v2 only) | −11 of 562 local words (−2%) | — | 34 of 165 |
| Energy floor: peak at least −20 dBFS (v2 only; depends on mic gain) | −20 of 562 | — | 23 of 165 |
| **Window needs a ≥2 s continuous attributed span (0.6 s joins)** | **1122** | **20** | **3** |
| Same rule, variants: ≥1.5 to 2.5 s, or ≥4 words over ≥1 s; joins of 0.5 to 1.0 s | 1122 | 20 | 3 |
| Joins of 1.5 s (edge of the working range) | 1122 | 20 | 25 to 62 |

The terminal (saved) path is unchanged by the rule. Its whole-lane call always has
context. Saved backchannels stay at 51 of 64 units, with 0 invented words.

The 3 remaining words (`是。哦。六。`, B-sp, 243 to 246 s) sit in a window that also holds
the first second of a real turn.

## Verdict

**Adopted in `MicrophoneWordGate.filter`, the live rolling path only.** When a mic window's
gated words hold no continuous attributed span of at least 2 s, none of its words are
published live. The diagnostics count them as `mic_words_dropped_unanchored`.

- `verify_product.py` on the product code gives: invented words 165 → 3 (−98%).
- Non-backchannel retention is unchanged on all 6 lanes: 94.3% and 94.9% on the Q-MIC-based
  lanes, matching round 3's 94 to 95%.
- The saved transcript is unchanged.
- **Cost:** backchannels spoken in a listening stretch are held out of the live view
  (52 → 20 units) and appear after Stop. If cleanup is off or fails, they are lost from the
  saved text (D3).

## Not adopted, with evidence

- **Script consistency.** It removes only 10% of the invented words (kana), because
  invented words mirror the meeting's own scripts: Latin fragments in English meetings,
  single Han characters in Chinese ones.
- **Per-word voicing and energy.** Both cost real words, and the energy floor depends on
  the mic gain.
- **A text-length preview filter (hide mic preview rows under 4 units).**
  - Measured on 5 W3 streams: invented preview events 41 → 10, backchannel rows 81 → 1.
  - The first words of each mic turn appear 0.9 s later at p50 (p90 1.0 s).
  - Preview rows carry no word timing, so stop-start speech is at risk; that risk is
    unmeasured (D1).
- **Lane-level rule on the terminal pass.** It removes both listen-only garbage sets
  (their longest spans were 1.9 s and 1.0 s), but the margin is only 0.1 s, and it drops a
  participant whose only speech is short. It also makes a short Stop-time tail recovery
  report a failure (D2).

## Scoring notes

- The A-sp terminal output is in Traditional Chinese (the Meijia voice), so the simplified
  reference under-counts its retention. This is a scoring artifact.
- Whole-lane terminal calls left out the English terms inside the Mandarin TTS sentences
  (`API`, `latency`). This was observed on synthetic speech only; human code-switched
  speech is unmeasured.

## Spend

The ledger lane `r4c-mic-halluc` recorded 246 batch calls at $0.6335 (metered) and 6 W3
streams at $0.121 (list-price estimate; Live usage metadata is absent). The total is
**$0.7545**, under the $1.00 cap. There were 0 errors. All audio was public or generated
locally.
