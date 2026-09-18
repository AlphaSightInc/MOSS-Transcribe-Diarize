# WP5 fresh-context verification result

**Execution PASS against VERIFY.md expectations: 6 PASS / 2 known N1 FAIL / 0 BLOCKED of 8 browser cases.**
This reproduces the stated failures; it does not make the product all-pass. The separate retained baseline remains **11 PASS / 2 FAIL / 1 BLOCKED of 14** (`evidence/mvpfix/wp5/verdict.json`, `prototypes/browser-stress/NOTES.md`). No browser rerun or discarded failure.

## Identity and actual fresh-context status

- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp5-browser-stress`.
- Branch: `mvpfix/wp5-browser-stress`; verified base: `29d69b0ecefa666b2ed523f75e28c8e806d9d7d7`; initially clean.
- Verification date: 2026-09-17 EDT (2026-09-18 UTC); actual execution pane: `MOSS:3.2`, `%26`. Lead reference: Fable, MOSS:2.1.
- This session began with the fresh-verification assignment. No previous conversation, rollout, or memory files were consulted. Only the prescribed worktree/briefs and applicable instructions were read. **Literal prior `/new` execution is unverified**; this session did not issue `/new`. Do not treat fresh task context as proof of that command.
- Initial ports 17865/18105: zero listeners. Import witness resolves the package inside this worktree (`fresh/import.txt`). Decoder preflight: running 0, waiting 0.

## Question, contract, and tool decisions

Question: do adversarial browser actions preserve truthful capture termination, durable meetings, and usable saved results?
Primitives: browser capture, server session/lease, durable meeting, UI projection. Each owns a distinct witness; one cannot substitute for another.
Invariants: terminal cleanup, persisted data/cookies, complete downloads, cause-bearing failures, exactly two Refresh controls in Voiceprints, and 400px layout. No product policy or threshold changes.
Falsifiers: mismatched browser verdicts, generic failure counted as explanation, truncated downloads accepted, missing persisted data, changed sentinel/assets, or decoder budget exceeded. These would be retained and reported rather than retried away.
Tools: the prescribed suites detect source/build/locator regressions; the real browser and own stack measure UI/transport/persistence; process checks detect leftover owned services; evidence inspection prevents staging private artifacts. No new production algorithm or policy was proposed.

## Commands and exact counts

Main command, from the worktree:

```sh
NPM_CONFIG_CACHE="$PWD/runs/wp5/npm-cache" bash prototypes/browser-stress/verify.sh
```

The script was unmodified. Its Python uses `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` and worktree-local `TMPDIR`.

| Check | Actual result | Evidence under evidence/mvpfix/wp5/fresh/ |
|---|---|---|
| Frontend | PASS: 206/206 tests, 24/24 files | frontend.txt |
| Typecheck | PASS, exit 0 | typecheck.txt |
| Build | PASS, exit 0; 33 modules; tracked assets unchanged | build.txt, cleanup.json |
| Exact locator sentinels | PASS: 3/3, 1.51s | sentinels.txt |
| Browser selected population | 6 PASS / 2 FAIL of 8 | browser/campaign-results.json |
| Expected-population assertions | PASS; verify.sh exit 0 | verification.json |
| Additional visibility capability probe | BLOCKED: hidden 0/5 observations | visibility-probe.json |

The browser subprocess exited 1 for the two retained failures, as required. `verification.json` contains fixed suite labels; the actual 206/206 and 3/3 counts above were independently read from their logs.

| Case | Fresh verdict | Exact measurement | Seconds |
|---|---|---|---:|
| 1 | PASS | Stop clicks 0.299999997 ms apart; 1 completed meeting; terminal UI | 11.936 |
| 8 | FAIL (N1) | 3/5 variants pass: MP3, 244-character filename, concurrent two-tab uploads; 4/4 valid recordings complete. Invalid/empty: 2/2 failed, 0/2 causes. Two submit-coroutine starts 0.242209004 ms apart; not a server-arrival timing claim | 15.775 |
| 9 | FAIL (N1) | Unreachable, 404, non-media: 3/3 failed, 0/3 explained causes | 9.192 |
| 10 | PASS | 10/10 nonempty text exports; 2/2 audio transfers aborted after 1500 bytes, full retries exactly 48,861 and 72,837 bytes, both ffmpeg-decodable; 12/12 checks | 1.711 |
| 11 | PASS | Rename HTTP 200; enrolled; 1 voiceprint in bank after reload; 1/1 selected-speaker exported turns correctly named; UI label persisted | 11.510 |
| 12 | PASS | 60/60 scratch/history rows; exactly 2 Refresh controls in Voiceprints; viewport/scroll width 400/400px | 0.249 |
| 13 | PASS | Missing-provider setup explained; 0 provider POSTs | 0.665 |
| 14 | PASS | 60/60 history records equal, 60/60 transcript fields equal (including nulls), cookie values unchanged | 34.658 |

Case 10 text-export byte counts, live/file respectively: md 176/229; txt 173/226; json 570/754; srt 195/248; vtt 203/256.
Cases 2–7 were not rerun as capture cases; case 3 received only the additional no-audio capability probe. Their baseline verdicts remain retained evidence, not new measurements.

## Decoder budget and cleanup

Counter **113 -> 127 = 14/80 additional submissions**, 66 unused under this assignment; cumulative 127/200. The counter was never reset. Wrapper semaphore remains at most two requests in flight; observed actual peak concurrency was not instrumented.
To enforce the user's stricter cap, the sole temporary bench edit changed `stack.py`'s cumulative guard from 200 to **193 = 113 + 80**, including the replacement server. It was restored byte-for-byte after shutdown; this is a declared deviation from an entirely unchanged checkout during execution. No product code changed.
Original stack PID 52541, replacement 53548, tunnel 52525, bench/browser and observed child processes all stopped. Cleanup inspection found zero owned processes and zero listeners on 17865/18105 (`cleanup.json`). The separate probe closed its browser. The SIGTERM message from the original server is the prescribed graceful restart, not an extra failure.

## Case 3: one cheap Chromium configuration attempt

Question: can native Chromium visibility change without spoofing DOM properties? Hypothesis: removing background-disabling defaults and using CDP focus/lifecycle controls may expose a hidden page. Falsifier of the blocker: native `document.hidden === true`; that would establish capability only, still requiring the full 60-second capture test.
One Chrome **153.0.8010.53**, headless launch; no audio/decoder calls. Removed `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`, and `--disable-background-timer-throttling` from Playwright defaults.

| Action | hidden | visibilityState | hasFocus |
|---|---|---|---|
| Initial page | false | visible | true |
| Second tab brought forward | false | visible | true |
| Emulation.setFocusEmulationEnabled(true), second tab forward | false | visible | true |
| Emulation.setFocusEmulationEnabled(false), second tab forward | false | visible | false |
| Page.setWebLifecycleState({state: "hidden"}) | false | visible | false |

Last command failed with `Protocol error (Page.setWebLifecycleState): Unidentified lifecycle state`. Zero visibilitychange events; **0/5 hidden observations**. No visibility getters were replaced. **This configuration did not unblock case 3.** Other configurations remain unmeasured; this does not prove Chromium can never hide a page. Need a browser configuration that demonstrably produces native hidden state, followed by the actual capture-continuity test. Probe source/result retained in `fresh/visibility-probe.py` and `.json`; no retry.

## Limits, deviations, and retained evidence

- **F1:** N1 remains a real product failure owned by WP4: invalid file/URL failure causes are missing. Generic failure is not explanation. No production repair in this verification branch.
- **F2:** Hidden capture continuity remains BLOCKED; the visible 60-second baseline interval is not hidden evidence. This probe adds capability evidence only.
- **F3:** All other selected contracts reproduced correctly. Baseline 14-case population is unchanged; no microphone fidelity, echo, recognition-quality, paid-summary, or deployment claim.
- Synthetic microphone readiness, public corpus system-tab speech, scratch SQLite rows, shipped 5-second Stop behavior, expected download/navigation aborts, and retired live-session 404s remain the documented bench caveats. Sixty transcript-field comparisons include failed fixture rows with null transcripts; they are not sixty decoded transcripts.
- Read-only shared Python/node_modules/corpus reuse only. Vitest cache disabled, Vite runner config temporary/local, npm cache and runtime outputs local. No task-authored changes outside the worktree; byte-for-byte external-tree isolation was not audited. No shared-service control, push, merge, or deployment.
- Eight screenshots visually inspected: form fields, names and main transcript text masked. Some history previews contain short **public corpus** fragments; no private transcript input was used. Metadata JSON/JSONL excludes API documents, cookies and credential values. Audio, SQLite, TLS keys, browser profiles and private runtime logs remain ignored in `runs/wp5`, never staged.
- Changes committed: this result plus `evidence/mvpfix/wp5/fresh/` verification logs, metadata, screenshots, probe and cleanup evidence. Production source, baseline verdict, existing NOTES.md, VERIFY.md, and built assets unchanged. No new regression test warranted for an evidence-only change.

Evidence staging inspection: 35 files, 886 browser JSON/JSONL records checked; no retained transcript/body/cookie/credential fields, audio, databases, keys or profiles staged. All 8 screenshots inspected. `git diff --cached --check` reports one raw-log formatting warning (`fresh/typecheck.txt:4`, blank line at EOF); original tool output retained unchanged. No other whitespace finding.
