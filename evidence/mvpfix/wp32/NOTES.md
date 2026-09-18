# WP32 review method and prototype verdict

Reviewed source: `37979e539f04d4ea740a1a94d021cd3bb894a0e2` to
`d8fa767f3ccbb577584643d7e23f80f55d92b2f5`. Own branch:
`mvpfix/wp32-final-crossreview`; initial tree clean. Import resolved inside WP32.
No production or existing-test changes. Independent Standards and Spec agents
followed the code-review skill; exact user-requested two-dot diff took precedence.

## Structural contract

- Question: can the integrated diff violate protected behavior despite green tests?
- Primitives: lane owns source audio/identity; session owns admission/publication;
  owner owns access; terminal state ends capture; persisted result survives runtime.
  None can be removed without conflating authority, provenance or lifetime.
- Invariants: protected values/protocol; owner isolation; terminal cleanup; truthful
  accounting; legacy representation. Numeric preservation is not behavior equivalence.
- Unknowns: real GPU/service/physical capture, native hang behavior, full byte parity
  over all inputs. Existing qualification evidence is not a new measurement here.
- Falsifier: one reachable source path/probe contradicts a claimed invariant.
- Tool decisions: diff/blame detects policy/test changes; actual production seams
  detect incorrect aggregation/state; suites detect integration regressions; fresh
  source spot-check detects unsupported audit claims. Failure becomes a finding,
  not an unauthorized production redesign.

## Prototype commands and measured verdicts

1. `node evidence/mvpfix/wp32/prototype-legacy.cjs`: actual base/current TypeScript
   modules, synthetic no-lane/no-id saved transcript. **Byte-equivalence falsified**:
   md 72/72, txt 69/69, srt 91/91, vtt 99/99 bytes identical; JSON 497/523 differs
   only by two speaker suffixes in target keys. 4/5 formats identical. No text loss.
2. Copy `prototype-reset.test.tsx` into `frontend/src/components/WP32prototype.test.tsx`,
   run `npm --prefix frontend test -- --run --configLoader runner src/components/WP32prototype.test.tsx -t 'WP32 prototype'`,
   then delete that temporary copy. Actual ControlPanel/CaptureClient; browser
   devices/HTTP simulated. **Universal recovery falsified**: ended pre-session mic
   leaves configuring, Reset false, Switch mic/Reshare visible. 1 witness passes;
   23 inherited cases filtered out. `prototype-reset-state.txt` prints full relevant
   state. Initial run passed but console output was suppressed; retained its log,
   reran with process.stdout solely to expose state. Known pre-existing WP27 finding.
3. `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <common-python> evidence/mvpfix/wp32/spec_probe.py`:
   real terminal adapter and lane compositor, synthetic PCM/stub model result.
   **Lane-independent truncation accounting falsified**: none/system/microphone
   truncation flags correct in 2/3 cases; microphone-only flag lost.

These small automated probes replace an interactive TUI for this read-mostly audit.
Retained as reproducible audit bench, not production modules. No new algorithm,
policy or threshold proposed. Falsification stops fixes; lead owns nontrivial changes.

## Full gates and limits

- Python: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp32/t" <common-python> -m pytest -q -p no:cacheprovider tests`:
  **1941 passed, 4 skipped, 21 warnings, 37 subtests passed; 182.76 s**.
- Frontend: `npm --prefix frontend test -- --run --configLoader runner`:
  **265 passed / 28 files; 2.95 s**. Runner loader keeps shared dependencies read-only.
- Typecheck: `npm --prefix frontend run typecheck`, exit 0.
- Skips identified by rerunning only their four collected cases with `-rs`:
  two new optional WP28 WAV parity cases; two existing external identity/F-cert
  corpus checks. **4 skipped**, no failure. Real-encoder parity not remeasured.
- Spec focused suite: 108 passed, 2 skipped, 4 warnings; 12.29 s.
- No rebuild needed: no frontend production/assets change. No GPU, provider,
  shared ports, deployment, merge, push, GitHub, audio/private transcript commits.
- Native fresh-session spot-check is prescribed separately after full gates.
  Do not describe a queued `/new` command as completed verification.

Read-only inspection attempts encountering an unmatched optional vitest-config
glob and an absent root package.json were corrected with explicit file paths;
no test failures or candidate changes resulted. Raw suite/probe outputs retained.
