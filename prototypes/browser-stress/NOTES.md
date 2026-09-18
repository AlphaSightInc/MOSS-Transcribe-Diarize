# WP5 prototype verdict — base 37979e53

Question: which adversarial browser sequences break stated lifecycle/durability contracts?
Verdict: **11 PASS / 2 FAIL / 1 BLOCKED**, denominator 14. 113 real decoder requests of 200 permitted; wrapper concurrency <=2.
This is local adversarial browser evidence, not deployment qualification or microphone fidelity evidence.
Standing bench retained here; no product source changes. No novel policy/algorithm proposed or falsified.

| Case | Verdict | Measured evidence |
|---|---|---|
| 1 | PASS | Two Stop clicks 0.3 ms apart; one completed meeting, terminal UI. Duplicate HTTP Stop calls are idempotent; not a contract failure. |
| 2 | PASS | Stop 1.002 s after start, zero visible utterances; completed, Reset, same-page second capture completed. |
| 3 | BLOCKED | Chrome headless never entered hidden state. 240 frames, max gap 0.434 s, +179 words during 60 s proves only visible continuity. |
| 4 | PASS | Both 3 s and 20 s route-abort outages resumed frames, visibly reported recovery, completed. |
| 5 | PASS | Reshare via real chooser automation; 33 further frame responses; one completed meeting. |
| 6 | PASS | Reload mid-capture; same row became interrupted after explicit 30 s lease; total case 39.917 s. |
| 7 | PASS | Same-profile second tab: identical 7 unique meeting IDs. |
| 8 | FAIL | MP3, 244-character name and two-file submission completed (4 recordings). Non-audio and empty files failed without a cause (N1). |
| 9 | FAIL | Unreachable/404/non-media: 3/3 failed, 0/3 explained cause (N1). |
| 10 | PASS | 10/10 nonempty formats; two audio interruptions after 1500 bytes; browser retries exactly 48,861 / 72,837 bytes, both ffmpeg-decodable. |
| 11 | PASS | Rename HTTP 200, voiceprint enrolled, selected speaker name persisted through reload and JSON export. |
| 12 | PASS | 60 scratch-fixture/history rows; two Refresh controls in required Voiceprints state; width/scrollWidth 400/400. |
| 13 | PASS | Unconfigured provider explained on click; zero provider POSTs; transcription remained available. |
| 14 | PASS | Graceful own-server restart: 60/60 history records and transcripts equal; cookie values unchanged; 34.647 s. |

## Findings and fix decision

**F1 — missing failure causes (N1):** `frontend/src/lib/fileUpload.ts:24` renders only generic failure. `moss_transcribe_diarize/app/phase2_file.py:388-391` discards decoder exceptions and marks failed; `frontend/src/components/MeetingHistory.tsx:354-357` projects status only. Reproducer: `run.py 8,9`. WP4 explicitly owns N1; report, do not duplicate its persistence/consumer repair. Cases 8/9 remain FAIL until integrated rerun.

**F2 — hidden-tab measurement blocked:** `document.hidden` was false after `bring_to_front` on another tab. Independent no-audio CDP minimization also remained visible. Need a Chromium automation configuration that truly enters hidden state; do not inject/spoof visibility or claim the 60 s foreground interval qualifies. No physical microphone needed; attended gates remain separate.

**F3 — no other demonstrated product failure.** No production fix or fix-specific regression test warranted. Existing frontend 206/206, locator sentinels 3/3, typecheck and build pass. Build reproduces tracked assets unchanged. Exact two-Refresh test was preserved.

## Failed attempts and corrections (retained, not erased)

- `base/`: inherited desktop nav click timed out because desktop design visually hides navigation. Use visible controls. Initial attempt stopped after three recorded failures; no decoder calls.
- `base-02/`: all 14 attempted. Harness mistakes: one-second UI observation after Stop; mixed Playwright paths/buffers; wrong audio URL; counting Refresh in Sessions instead of Voiceprints; comparing renewed cookie expiry. These are not product defects.
- `base-corrected/`: full local audio arrived before abort; incomplete-transfer predicate correctly failed. Restart launched too soon while previous process drained connections; new server refused occupied control socket. Corrected to wait for prior PID exit (up to 60 s), never overlap servers.
- `adjudicated/`: corrected bad-file reason predicates; throttle test connection at 8192 B/s to ensure abort mid-transfer; browser UI download for full retry; exact Voiceprints sentinel; compare credential values, not expiry metadata. Expected abort network errors retained. Post-restart 404s are probes of retired in-memory live sessions, not missing durable meetings.
- `verdict.json` explicitly maps each final case to its retained run. Never treat older raw PASS labels for generic failure messages as explanation evidence.

## Limits / deviations

- Synthetic Chromium microphone signal only satisfies existing readiness; corpus speech is system-tab-only. No microphone/echo/quality claim.
- 60-row test seeds the isolated scratch SQLite store; it is UI scale evidence, not 60 decoder runs.
- Shipped UI Stop remains its existing 5 s request, then the bench separately waits for durable terminal state; no replacement 30 s API Stop request.
- Source tab uses existing e2e capture approach. No shared service mutations, no paid summaries, no policy/readiness/sentinel/mixer/decoder changes.
- Browser scratch data and logs remain ignored under this worktree. Evidence contains metadata, synthetic fixture labels and masked screenshots; no audio/credentials/private transcripts.
- Fresh-context verification follows `VERIFY.md`; its result must be recorded separately before final report.

Fresh verification additionally tightens two witnesses: case8 submits from two same-profile tabs together (the original base run used a two-file batch); case11 checks the actual voiceprint bank after reload. Their new measurements belong in VERIFY-RESULT.md, not the baseline totals. No baseline concurrency timing claim is made.

Tooling caveat: COMMON prescribed symlinked node_modules and default npm commands. Default Vite/Vitest can write shared dependency caches/config-bundle temporaries through that symlink; no source outside this worktree was intentionally edited, but byte-for-byte external-tree isolation is not established. Fresh verification disables Vitest cache and uses Vite's runner config loader to avoid those writes. Shared caches were not cleaned or altered as a repair.
