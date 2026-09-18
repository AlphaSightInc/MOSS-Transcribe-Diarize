# WP4 fresh-context verification: offline PASS; live acceptance unresolved

## Provenance and execution

- Fresh Codex session, actual pane `MOSS:3.4` (`%27`), reporting for Fable in `MOSS:2.1`.
- Verified on 2026-09-17 EDT; post-run timestamp `2026-09-18T03:35:28Z`.
- Worktree: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp4-oracles-n1`.
- Branch: `mvpfix/wp4-oracles-n1`; tested starting HEAD `c14e9e241c964855a105b74dc46a63d48b72f098`; initial tree clean.
- Read `VERIFY.md` first, then repository `AGENTS.md`, `COMMON.md`, `WP4-oracles-n1-summaries.md`, execution-plan sections 1–2, prototype skill, and committed WP4 evidence. No previous conversation, peer history, or memory lookup used.
- Ran the following command literally once, from the WP4 root; exit **0**:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python evidence/mvpfix/wp4/verify_offline.py
```

The borrowed Python environment imported `moss_transcribe_diarize/__init__.py` inside this WP4 worktree. The verifier placed temporary files and caches inside WP4. No source fixes or reruns were needed. Fresh outputs are in `evidence/mvpfix/wp4/fresh/`; process exit codes are recorded in `execution.json`.

## Fresh results

| Check | Actual result | Exit |
|---|---|---|
| Import provenance | Correct WP4 worktree | 0 |
| Full Phase-2 suite | **805 passed**, 21 warnings, 111.15 s | 0 |
| F6 separately | **2 passed**, 2.12 s | 0 |
| Frontend suite | **209 passed / 24 files**, 2.35 s | 0 |
| Typecheck | Passed | 0 |
| Build | Passed; 33 modules, 102 ms | 0 |
| Oracle reproducer | 8 result rows; expected controls below | 0 |
| File-boundary reproducer | 8 cases; 7 coded failures, 1 speechless completion | 0 |
| Verifier assertions | **18/18 true** | 0 |
| `git diff --check` | Clean | 0 |
| Generated assets diff | No changes after build | 0 |

F6's diff from the common base changes only the synthetic History → Voiceprints markup; original assertions and clock remain unchanged. Tests for summary cancellation/retry/title/private persistence are included in the passing suites.

Non-fatal diagnostics retained verbatim: Phase-2's 21 dependency/deprecation warnings, then a Playwright pending-task / unretrieved `TargetClosedError` at teardown despite exit 0; frontend Vite native-loader compatibility and Node localstorage-path warnings. These are not failed assertions. No claim that teardown is warning-free.

## F1 — Corrected duplication predicate and prototype verdict

Question: can the same reference-based oracle reject lost, misattributed, and copied words while accepting valid overlapping speech?

The original raw shared-word predicate falsely counted 12 duplicates. The corrected predicate counts observed system-reference words absent from the microphone reference, copied onto the microphone lane with a matching system segment start within ±2 s.

Fresh results: valid tagged and legacy fixtures **2/2 accepted**; counts-only, zero-microphone, swapped attribution, and injected playback **4/4 rejected**. Swapped attribution gives **10** errors; injected playback gives **5 duplicates**. Documented public-corpus overlap is **accepted with 0 duplicates**, system **106/106** words, microphone **48/48**, ordered word-error rate (WER) **0 on both lanes**. Corrected predicate passes this measured falsifier; shared-vocabulary-only copies remain outside this duplication witness. Legacy ownership is lexical inference, not acoustic identity proof.

## F2 — G7 phrase predicate and exports

Source and tests inspected independently: G7 accepts the predeclared **eight-word** phrase on the final transcript under an operator speaker distinct from tab speakers (**1 positive fixture**). It rejects **5/5 negative fixtures**: absent phrase evidence, missing words, tab speaker used as operator, no tab witness, wrong phrase. An additional transcript-derived witness test accepts distinct speakers and rejects merged attribution. Fresh production counts-only validation rejects the two-scenario payload with zero transcript words. Runbook requires operator phrase alone, tab alone, then overlap. No real attended G7 run was performed or claimed.

Exports in the fresh Phase-2 suite: production TypeScript renderer **5/5 accepted** (md/txt/json/srt/vtt); word/label/time corruptions **15/15 rejected**; Harness controls accept real **5/5** and reject corrupt **5/5**. Separately, retained actual browser-download evidence from the saved meeting reports **5/5 passed**. Browser downloads were not repeated this session; no private download bytes are committed.

## F3 — Live acceptance FAILED / INCONCLUSIVE means

These are retained measurements inspected this session, not new decoder runs:

- **Alternation FAILED**, although the meeting completed. Final/reopened system WER **11/106 = 10.377%**, mic **6/48 = 12.5%**, both above unchanged final bound **9.5074%**. Pre-terminal system **16/106 = 15.094%**, mic **16/48 = 33.333%**; unchanged immediate bound **16.6655%**. Final/reopened attribution errors **2**, duplicates **2**. Alternation did **not** pass. Duration **56.705 s**, Stop **2.69 s**, **108 frames/lane**, microphone gain **0.03**.
- **Overlap INCONCLUSIVE as the requested completed negative control**. Overlap was intended to fail semantically on the current mixer, but this run was interrupted at the combined **40 decoder-call cap**. Snapshot/reopened mic **0/48 words**, WER **48/48 = 1.0**; system **31/106 = 29.245%**. This interrupted failure is **not an expected-negative-control PASS**. `valid_semantic_negative_control` is false.

The requested positive/negative live ladder remains unsatisfied. Existing QUALITY_BOUNDS were not relaxed. Retained request log contains exactly **40 records**; verification made **0 decoder calls**, restarted no service/tunnel, and consumed no further budget.

## F4 — N1 failure classes and UI

Fresh 8-case production-boundary bench: URL **403 → acquisition_http_403**, **404 → acquisition_http_404**, **timeout → acquisition_timeout**; unsupported container and transcode failure **→ transcode_failed**; decoder exception **→ decode_failed**; malformed output **→ decode_invalid**. These **7/8** cases fail with safe reasons. Confirmed no-speech **1/8** completes with **0 segments** and **“No speech detected.”** Unconfirmed empty output is separately tested as `decode_invalid`.

The full suite includes **9 parameterized outcome cases** covering persistence after reopen, owner isolation, safe logged codes/reasons, and browser-like URL User-Agent. Frontend **2 outcome-display fixtures** verify failure reason or speechless notice on both the History row and selected meeting status. The bench injects controlled failures/speechless diagnostics; it does not establish live network or real music-decoder behavior.

## F5 — Gemini 2.5 Flash Lite

`frontend/src/lib/finalSummary.ts` suggests `google/gemini-2.5-flash-lite` first; `FinalSummary.tsx` exposes it while retaining Flash and custom model entry. `tests/e2e/verify_summaries.py` defaults to Flash Lite; local wiring tests pass. Retained `summary-live-status.json` records no key found in the permitted environment/operator shell files and **0 paid calls**. The requested **50 s / 180 s** paid functional check remains **BLOCKED on an OpenRouter key**. Key discovery was not repeated and no paid call was authorized by `VERIFY.md` or made in this session. No live schema/timestamp/current-artifact or summary-quality success is claimed.

## Changes, limits, and deviations

- Existing WP4 implementation changes: shared lane oracle; G7 validator/runbook; e2e lane/export validators; F6 fixture; file/URL failure handling and persisted outcomes; History/API display; summary model suggestions; accompanying tests and retained evidence. This verification adds only this result and fresh test/numeric logs.
- Prior failed attempts remain in `evidence/mvpfix/wp4/STATUS.md`: rejected raw duplication predicate; malformed heartbeat before audio; initial fixture failures; first full suite **791 passed / 5 failed**; second **803 passed / 1 failed**; budget-interrupted overlap. No fresh test attempt failed.
- The initial staged whitespace check exited **2** for a trailing blank line in the generated `fresh/typecheck.txt`; removed that blank line only before repeating the staged check. Test output content and exit status are unchanged.
- Retained method deviations: batch prototype instead of interactive terminal UI; deterministic lane semantics exercised through a separate protocol check in workspace row 4, while rendered-browser speech capture remains a smoke check. Required live ladder and paid summary checks remain unresolved as stated above.
- No fresh execution deviation from `VERIFY.md`. No push, merge, deploy, GitHub write, shared-service action, external-worktree edit, private transcript/audio commit, or key disclosure. Only local result/evidence commit requested. Verifier exited; no WP4 verifier/test process remained in the post-run process listing.
