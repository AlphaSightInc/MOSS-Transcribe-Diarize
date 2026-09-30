# Gemini Live Bake-off — decision report (2026-09-28)

Markdown copy of the published report (https://claude.ai/artifact/KSifNWFMk8wTghZSgW1cq6 (earlier version in the other org: https://claude.ai/artifact/7s7ufT7cauULkbDbfdi5Mx)). Branch `gemini/live-hybrid`;
qualified runtime `0b9deed5` + preview fixes L-3 `fe1610f5`, L-4 `3901d2db`; base `8d8fb682`.
MOSS comparator = recorded H1 #3 receipts (no GPU used in this campaign).

## Round 2 (2026-09-29) — ready for in-person review

Branch `gemini/r2-integration` head `fb8f5498`; final qualification on `9fb217f4` (engine identical; later commits fix
summary/refinement races and UI contract bugs). Defaults: Balanced 15 s / 90 s speaker windows, clean-up after Stop ON
in the background (D20/D21), built-in summaries on `gemini-3.5-flash-lite`.

**Verdict.** Saved transcripts are accurate: speaker error (DER) **0.104** on six short clips ×2 and **0.035** on the
43-minute meeting (5/5 speakers). Words appear at once; confirmed names a median **13.8 s** after speech. The meeting is
usable **12 s** after Stop; the improved version lands **55–75 s** later. Cost **$1.62/meeting-hour** metered,
**$2.76** if output is billed (A5 unconfirmed). One soft gate misses: fast guesses cover 62% of the waiting time on short
clips (target 70%) and are 94% right on the long meeting (target 95%).

| Check | Result | Target | Verdict |
|---|---|---|---|
| Saved DER, 6 clips ×2 | 0.104 (live view 0.103) | ≤ 0.110 | PASS |
| Saved DER, 43-min (5 voices) | 0.035, 5 IDs (live view 0.164, 6) | ≤ 0.060 | PASS |
| E1 speakers | 4 | ≤ 5 | PASS |
| Dropped passages · speakerless speech | 0 · 0 s | 0 · 0 | PASS |
| Words · names (p50) | 0.0 s · 13.8 s | ≤ 1 s · ≤ 15 s | PASS |
| Guesses coverage · accuracy | short 62% · 98%; 43-min 88% · 94% | ≥ 70% · ≥ 95% | MISS |
| Background clean-up | usable 12 s after Stop; +55–75 s; export 409 meanwhile; renames kept | — | PASS |
| Two people on one mic + echo (saved) | 94–95% local words kept; 99.8–100% echo dropped; 2 Local IDs | ≥ 90% | PASS |
| Summaries | 45 rolling, 0 errors; final regenerated on improved version | valid | PASS |
| File / URL | 0.103 · 0.034; voiceprints saved (unchanged path, reused) | ≤ 0.110 · ≤ 0.060 | PASS |
| Cost / meeting-hour | $1.62 metered · $2.76 with output estimate | report; spend ≤ $50 | PASS |

Known limits: live view on long meetings can mis-group speakers until clean-up lands; loud (−10 dB) speaker echo drops
some local words live (84.8% on `f962d97d`; saved 94%); guesses ~94% right on long meetings; actual Google invoice
UNMEASURED (round-2 spend ≥ $17.51 from usage records). Gemini is non-deterministic on byte-identical audio (28/60
long60 windows matched) — the background whole-recording pass is the correction.

Final-head smoke on `fb8f5498`: E1 5-min meeting ready 12.5 s after Stop, improved 52 s later, 5/5 rolling summaries, final
summary regenerated on the improved version, $0.21; backend suite 2631 passed.

Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/qual-9fb217f4/{scorecard.md,scorecard.json,spend.json}`, `evidence/P66/smoke-fb8f5498/RECEIPT.md`.

## Round 1 (2026-09-28)

### Verdict

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
| E1 labels at Stop (true 4) | 10 | **4–5** (6 runs) | ≤ 5 | PASS |
| Dropped passages | not measured | **0/1,216 s** | 0 | PASS |
| Words on screen after spoken, median / p90 | ~2.3 s | **0.7 s / 1.0 s** | ≤ 5 s | PASS |
| Speaker name on those words, median | ~2.5 s | **11–16 s clips, 18.3 s E1, 19.3 s at min 40** | ≤ 20 s | PASS |
| Cost / meeting-hour | GPU host | **$1.35 / $2.57 (43 min) / $2.90 (E1)** | ≤ $3 | PASS |
| Final WER | 0.095 | 0.104 | report | worse |

Long meeting (43 min, 5 voices, Lex recorded across four sessions): 5 labels, Lex one label throughout, settled DER
0.050, final 0.034. Receipts: `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P62/gemini-final-0b9deed5-*`.

## Design

- **Words:** Gemini 3.5 Transcribe Live streams provisional words (grey "Speaker TBD" preview), opened only
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

## Readiness and follow-up answers (2026-09-28)

- **Ready for user testing?** Yes for an attended pilot on this Mac after A1 (rotate the Gemini key) and A2 (10-minute
  real-capture check: real tab share + real mic, headphones and speakers). Not yet for remote testers (A4: needs a
  deployment behind sign-in). Brief testers (A3): words appear at once in the grey "Speaker TBD" card, names fill in
  ~15 s later, use headphones.
- **Label renamed** "Speaker uncertain" → "Speaker TBD" in live view, cards, saved transcripts and exports (`ad798f4c`);
  both names stay reserved.
- **Two delays:** words on screen 0.7 s median / 1.0 s p90 after spoken (3.5 Transcribe Live); speaker name on those
  words 11–19 s median. Responsiveness is the first number.
- **Q1 3.8 Live vs 3.5 Transcribe Live:** 3.8 Live is a talk-back voice assistant (audio out; transcript per turn;
  4.2 s; WER .150); 3.5 Transcribe Live is streaming speech-to-text (text out while speaking; 0.7 s; WER .135; no
  invented words on silence). Neither labels speakers. 3.5 Transcribe Live is sufficient; 3.8 Live is not used.
- **Q2 one pass instead of fast + accurate?** No: fast words need seconds of audio, stable speakers need minutes.
  Live-only has no speakers; batch-only gives words in 2.3–3.1 s with worse WER and unstable speakers, or costs
  ~$16/h with 3-min windows every 2 s. Keep two passes (the fast one is display-only). Real simplification option
  D14: drop the after-Stop pass (live 0.099 vs final 0.105 on 6 clips; long meetings lose 0.050 → 0.034 DER).
- **Preview fixes after the report:** over-trim of fresh words fixed (`135e00a2`); preview repeats of committed text
  64% → 10% of screens with fresh words kept.
- **Pilot guards (final branch 7ad946dc, runtime db643d8c):** preview-stall restart (witness: batch words ≥ 10 s the
  preview missed) and final-pass coverage guard (witness: committed live rows; retry once, else keep live rows). A
  WebRTC-witness v1 fired 22× on normal E1 audio (music counts as voiced) and raised label p50 18 → 62 s; reverted.
  A preview-witnessed rolling retry fired 12× (mic preview hears echo) and was removed. Shipped set on real E1:
  0 triggers, label p50/p90 19.0/26.5 s, calls/cost unchanged. Backend 2,544 passed, frontend 331.
