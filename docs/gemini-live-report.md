# Gemini Live Bake-off — decision report (2026-09-28)

Markdown copy of the published report (https://claude.ai/artifact/7s7ufT7cauULkbDbfdi5Mx). Branch `gemini/live-hybrid`;
qualified runtime `0b9deed5` + preview fixes L-3 `fe1610f5`, L-4 `3901d2db`; base `8d8fb682`.
MOSS comparator = recorded H1 #3 receipts (no GPU used in this campaign).

## Verdict

A Gemini-powered live engine beats self-hosted MOSS on speaker accuracy and passes every hard bar, behind the same
UI and HTTP API. Speaker error before Stop falls from 0.145 to 0.099; the final transcript matches MOSS
(0.105 vs 0.110); the E1 meeting shows 4 labels for 4 real voices instead of 10. The price: labels appear
11–19 s after speech (words at once), meeting audio goes to Google, and it costs about $1.35–2.90 per
meeting-hour. "Gemini 3.8 Live" alone cannot label speakers; the design uses Gemini 3.5 Transcribe Live
(words), Gemini 3.5 Transcribe (who spoke) and the existing local WeSpeaker fingerprint model (linking).

## Scorecard (final SHA 0b9deed5, real HTTP API, 1.0× pace, public audio)

| Bar (D6) | MOSS | Gemini | Target | Result |
|---|---:|---:|---:|---|
| Settled DER, 6 clips × 2 passes | 0.145 (raw 0.171) | **0.099** (raw 0.108) | < 0.145 | PASS |
| Final DER | 0.110 | **0.105** | ≤ 0.110 | PASS |
| E1 labels at Stop (true 4) | 10 | **4** | ≤ 5 | PASS |
| Dropped passages | not measured | **0/1,216 s** | 0 | PASS |
| Words visible, median | ~2.3 s | **< 1 s** | ≤ 5 s | PASS |
| Labels visible, median | ~2.5 s | **11–16 s clips, 18.3 s E1, 19.3 s at min 40** | ≤ 20 s | PASS |
| Cost / meeting-hour | GPU host | **$1.35 / $2.57 (43 min) / $2.90 (E1)** | ≤ $3 | PASS |
| Final WER | 0.095 | 0.104 | report | worse |

Long meeting (43 min, 5 voices, Lex recorded across four sessions): 5 labels, Lex one label throughout, settled DER
0.050, final 0.034. Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/gemini-final-0b9deed5-*`.

## Design

- **Words:** Gemini 3.5 Transcribe Live streams provisional words (grey "Speaker uncertain" preview), opened only
  on voiced audio.
- **Who spoke (system lane):** every 15 s, Gemini 3.5 Transcribe diarizes a window growing to 3 min; a speaker
  ledger maps window-local labels to meeting IDs by word overlap + WeSpeaker fingerprints; a new speaker needs 2 s.
- **Mic lane:** separate; words + 30 s windows while voiced; text + acoustic echo gate; one local speaker.
- **After Stop:** whole recording in ≤ 15-min chunks; merge split voices (fingerprint ≥ 0.65 unless they converse);
  timestamp repair; WebRTC gate against invented words; voiceprints saved for auto-naming.
- Details: `docs/design-gemini-live.md`; bake-off: `prototypes/gemini-live/{words,window,continuity}/NOTES.md`.

## Findings

- **F1** 3.8 Live has no speaker labels and is a slower word source (4.2 s) than 3.5 Transcribe Live (0.69 s).
- **F2** 3.5 Transcribe diarizes well within a call, not across calls; growing 3-min windows fix the seams.
- **F3** Pure Gemini 0.254 vs 0.099 with the fingerprint linker (ruling L1).
- **F4** Mono mixing loses the local user when they talk over others; separate lanes recover it.
- **F5** Final pass needs the fingerprint merge rule (0.125 → 0.105, 4/4 draws) and 15-min call cap.
- **F6** 16 product defects found by end-to-end measurement and fixed (per-word rows, Stop tail, invisible preview,
  settle semantics, parity drift, hidden retries, silent-audio calls, label lag, echo-duplicated preview, preview
  repeating committed text: 64% → 6% of screens …).
- **F7** The newest ~15 s is unlabelled preview: "immediate" DER 0.29 vs MOSS 0.20; settled/final are better.

## Decisions for the user

- **D9** Live engine: O1 Gemini (recommended if cloud audio is acceptable) · O2 both, MOSS default ·
  O3 port long-context settlement + mic lane to MOSS.
- **D10** Accept the WeSpeaker linker (recommended).
- **D11** Accept cloud audio and $1.35–3.44/h (privacy decision first; rotate the key used here).
- **D12** Label delay 11–19 s at 15-s ticks (recommended) vs 10-s ticks at ~$3.40/h.
- **D13** Round-6 UI merged here ahead of round 6; re-sync when round 6 merges.

## Risks

R1 crosstalk (RTFL); R2 Gemini variance, preview-model/pricing changes, Live cost is a list-price estimate;
R3 loud speaker echo (> −15 dB) and quiet talkers; R4 several people on one mic = one speaker; R5 measured to 43 min,
after-Stop pass ~1 min per 10–15 min audio; R6 spliced synthetic meetings still over-count; R7 attended real-mic
session not yet run (reserved for the user).

## Try it

```
cd ~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live
scripts/gemini-live/start-gemini.sh        # → https://127.0.0.1:18600/
```
