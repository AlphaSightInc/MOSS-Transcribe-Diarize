# WP22 fresh-context verification — 2026-09-18

Scoped verdict: full suites, retained-run audits, fresh production-vector probe
and final cleanup PASS. R1/R2 remain OPEN; neither
successful exhausted-tape refinement nor full return to baseline is established.

## Session and source

- Fresh session `01a0b383-f517-7f00-a7d5-ddc67e28aad2`, distinct from parent
  `01a0b339-0f54-7d82-9cc9-f119bc04f5c3`; pane `MOSS:3.3` (`%21`).
- Branch `mvpfix/wp22-memory-longrun`; inspected HEAD
  `977d036edd43620c4272b036f27bc7dbb08b2ed6`; starting worktree clean.
- Cwd/import source: `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp22-memory-longrun`;
  import resolved to its `moss_transcribe_diarize/__init__.py`.
- Used prescribed shared-venv Python, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=.`,
  checkout-local `.wp22/t` TMPDIR and `.wp22/npm-cache`. No package installation.
- `git merge-base --is-ancestor 1745b96f HEAD` passed. Production diff against
  `1745b96f` is only `speaker_identity.py:626-629`: three comment lines plus
  `options.enable_mem_pattern = False`. CPU provider, threads, model, features,
  thresholds, retention, protocol and lifecycle unchanged. Real C source `a28eecd9`.
- Read VERIFY.md, SCOPE.md, full NOTES.md, draft REPORT.md, COMMON.md, execution
  plan sections 1–2 and required prototype skill. Reviewed retained red/focused,
  before/after/final, merged and post-real full-suite logs, including failed attempts.

## Question, evidence and falsifiers

Question: which memory survives because work still needs it, and which is retained
by the native encoder? Pending PCM serves unfinished work; tapes serve the terminal
pass; transcript/identity history serves correction; native workspace serves model
execution. These owners have different lifetimes. Unchanged outputs/policies and
audio release are invariants; cold-start RSS recovery is not assumed.

Prototype verdict: variable-length ONNX memory-pattern caching contributes to native
retention. Disabling it reduced end RSS from 1,451,147,264 to 995,377,152 bytes for
18 probes and 871,596,032 to 664,567,808 bytes for 80 varying probes. Inference sums
were 28.061/27.894 s and 64.774/64.624 s. Arena-off/shrink controls were rejected.
Fix: `moss_transcribe_diarize/app/speaker_identity.py:629`. Fresh comparison of the
retained arrays confirmed **98/98 exact vectors**, maximum absolute difference 0
(`fresh-retained-vectors.json`). This does not attribute all remaining RSS.

Each check had a concrete falsifier: suites detect regressions (fail acceptance);
summary detects missing checkpoints/changed content/retained PCM (reject release or
equivalence claim); real audit detects saved-word/audio/request/tape disagreement
(reject durability claim); vector comparison detects changed identity output
(reject fix); status/assets/listeners detect unintended changes or leftovers
(restore only authorized generated output, clean up our processes before commit).

## Executed checks

Commands below use prescribed `python` and environment; logs in
`evidence/mvpfix/wp22/`. Every completed command exited 0, first attempt.

| Check | Result | Evidence |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider --basetemp=.wp22/pytest-fresh tests` | 1911 passed, 2 skipped, 37 subtests; 21 warnings; 153.70 s | fresh-python.txt |
| `npm --prefix frontend test -- --run` | 249 tests / 28 files passed; 2.62 s | fresh-frontend.txt |
| `npm --prefix frontend run typecheck` | exit 0 | fresh-typecheck.txt |
| `npm --prefix frontend run build` | exit 0; assets unchanged | fresh-build.txt |
| `python prototypes/streaming-diarization/memory-longrun/summarize.py` | all three retained profiles pass accounting/release checks | fresh-profile-summary.txt |
| `python prototypes/streaming-diarization/memory-longrun/audit_real.py evidence/mvpfix/wp22/real-1789715856876413000` | parsed JSON exactly equals committed audit.json | fresh-real-audit.json; fresh-audit-comparison.json |

No new 30-minute real or stub capture was required by VERIFY.md: its step 4 reruns
the retained-profile summary; step 6 reruns the production ONNX probe separately.
All three profiles committed 28,800,000 samples and released pending PCM/all tapes.
Before/after content exactly equal: 1440 segments / 4320 synthetic words. RSS at
30 minutes: 667,467,776 before vs 623,951,872 after bytes; after-Stop 641,908,736.
Count-only replay content matches; system album entries 15/20/20, mic 20/20/20 at
5/15/30 minutes. Its memory is excluded. HTTP supplement completed 1800 audio s
in 63.090675 wall s; queue empty at sampled checkpoints, not every instant.
Mono terminal status `unavailable`; both lane profiles `failed` because of R1.
These are successful release/content checks, not successful terminal refinement.

Historical regression: 1 failed/1 passed before fix; 58 focused passed afterward.
Baseline 1889/2/37; first post-change 1889 passed/1 failed/2 skipped/37 subtests
(30 ms helper lease expired during setup; stub Identity, unrelated to encoder).
Unchanged final suite 1890/2/37, merged 1911/2/37 (149.16 s), post-real 1911/2/37
(158.29 s); prior failures retained. Fresh full suite has no failed tests.

## Retained real 30-minute run — independently reopened, no decoder calls

- Final/completed; capture 1800.001202 s; Stop→final **101.69791649999388 s**.
- 7200 acknowledged frames; 28,800,000 accepted/accounted samples; no pauses.
- **6269 saved words**, exact ordered segment-text equality with terminal snapshot
  and reopened SQLite. MP3 **1800 s**, 16 kHz mono, **10,800,693 bytes**.
- 1080/2600 requests, peak two in flight. Foreign traffic 36/65 resource samples;
  64 independent RSS samples. These are contended timings, not isolated capacity.
- System 569 segments / 5521 words; mic 55 / 748. System repeated public speech;
  mic -10 dB first 300 s then zeros. Last mic end 299.88 s; no words in silent tail.
- Three tapes complete, no refused samples: 57,600,000 bytes each;
  **172,800,000 → 0 bytes** total at release.
- Current process RSS nearest 5/15/30 minutes: **932.4375 / 981 / 973.25 MiB**
  (977,731,584 / 1,028,653,056 / 1,020,526,592 bytes), sampled at
  296.092893 / 896.372979 / 1796.799548 s.
- Post-final **1148.953125 MiB** (1,204,764,672 bytes); sampled peak
  **1277.484375 MiB**. Start 616 MiB; after 30 s 901.640625 MiB.

## Open findings and limits

**R1 — exhausted-tape terminal failure, pre-existing and unfixed.** Exact path:
`live_tape.py:291` exhausts capacity; `read()` at `:323` raises
`CompleteMixedTapeUnavailable`. `live_lane_decode.py:250-254` catches each failed
lane read, retains base segments and returns no results; `:319-328` calls
`TerminalTranscriptFinalizer._refused()` without keyword-only `gaps`, required at
`live_transcript_convergence.py:1053-1059`. TypeError reaches
`live_service_runtime.py:1198-1203`; finalization stays None, so `:1221-1227`
publishes `failed` / `finalizer_defect`, instead of intended `tape_unavailable`.
The `finally` at `:1207-1212` invokes `_release_tape_locked` (`:1998-2012`), then
`live_coordinator.py:1135-1148` releases mixed/system/mic tapes. Canonical content
survives. Same omitted argument exists at accepted `1745b96f`; retained tiny
reproducer and both long lane profiles expose it. C used a larger tape and did not
exhaust it. All paths above are under `moss_transcribe_diarize/app/`.

**R2 — post-final RSS does not return to baseline.** Late capture is approximately
flat, but 1148.953125 MiB post-final exceeds both 616 MiB start and 901.640625 MiB
warm 30 s. Tape release does not establish release of native/runtime memory.
Residual allocation ownership, long post-final decay, repeated-session accumulation
and four-session safety remain unmeasured; do not assert a Python leak or full release.

Word/speaker accuracy remains unadjudicated; 56 system segments unattributed, mic 0.
Saved equality proves persistence agreement, not semantic correctness. Isolated GPU
capacity, operator/device fidelity and deployment qualification remain unmeasured.
No identity-policy tuning. Prior measurement deviations remain explicit: scripted
prototype, accelerated stub A/B, and C's prescribed SQLite-version bypass.

## Final production probe and cleanup

`python prototypes/streaming-diarization/memory-longrun/onnx_memory.py --arena production --varying --output evidence/mvpfix/wp22/fresh-production-varying.json`
ran after Python finished; exit 0. Output retained in `fresh-production-varying.txt`.
The constructor had no options override. NumPy `array_equal` compared the fresh
`.wp22/vectors-production-varying.npy` with `.wp22/vectors-on-varying.npy`:
**80/80 exact**, max absolute difference **0** (`fresh-vector-comparison.json`).
80-call inference sum **63.3058349560597 s**; RSS loaded **258,572,288** bytes,
last embedding **664,633,344**, maximum sampled **666,845,184**, session destroyed
**664,682,496**. Actual observations; no universal RSS acceptance threshold.

No listeners on 18122/17882; all started verification commands exited. Checkout cwd
process inventory showed only the cleanup command itself (`fresh-cleanup.txt`).
Generated assets and WP2 production-1280.png unchanged; no restoration needed.
Regenerated OWNERS.md/profile-summary.json unchanged. New text-log trailing
whitespace normalized; `git diff --check` and staged diff check passed.
Only this worktree's verification docs/report/evidence added or updated; no source
or test edits, new real run, GPU call, tunnel, other-pane message, push, merge or
deployment. No new verification deviation. Local verification commit is the commit
containing this result; its final SHA is reported in the pane response.
