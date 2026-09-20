# R4-4 verification result

**PASS** — 2026-09-20, fresh Python/Node processes in
`/private/tmp/moss-round4-20260920/jamie`, branch `round4/jamie`, merge-base
`89f833acd4c654dd702664a17ed19783a2999c95`.

- Import: `/private/tmp/moss-round4-20260920/jamie/moss_transcribe_diarize/__init__.py`.
- Prototype: PASS; fresh CPU ONNX; full state printed; decoder requests 0.
- Result assertions: PASS; FALSIFIED, four policies, 0 merges, 3 false births each,
  words/timestamps unchanged, 4.221 s and 12.663 s populations separated.
- JSON: PASS.
- Backend exact final state: **2,116 passed, 5 skipped, 2 expected xfailed,
  37 subtests, 0 failed** in 198.39 s.
- Frontend fresh-process run: **311/311 passed** in 3.03 s.
- TypeScript: PASS. Vite: PASS. `git diff --check`: PASS.
- Verification-document layout guard: PASS.

Attempt 1 is retained as negative evidence: a deliberately stripped environment hid
`uv` (four failures), and root `VERIFY.md` correctly failed the repository layout guard
(one failure): 2,111 passed / 5 failed / 5 skipped / 2 xfailed / 37 subtests. The recipe
was moved to `docs/verify/r4-4-jamie/` and rerun with the literal documented environment;
all five failures disappeared. No product file changed to obtain PASS.

The two xfails are strict R4-4 violating controls. An XPASS would fail verification.

## Lead-issued fresh context — 2026-09-20

Overall: **PASS**. The handoff's `FALSIFIED` prototype verdict reproduced exactly; all verification gates passed.

| Step | Result | Exact result |
|---|---|---|
| Branch | PASS | `round4/jamie` |
| Merge base | PASS | `89f833acd4c654dd702664a17ed19783a2999c95` |
| Import custody | PASS | `/private/tmp/moss-round4-20260920/jamie/moss_transcribe_diarize/__init__.py` |
| Fresh CPU prototype | PASS | Exit 0; verdict `FALSIFIED`; device `cpu`; fresh encoder session `true`; decoder requests 0 |
| Prototype denominators | PASS | Jamie source 4.221 s; three-repeat retained Jamie 12.663 s; adjudicated Jamie 0.0 s; sessions replayed 0/10 claimed |
| Prototype invariants | PASS | 4 policies; word changes 0; timestamp changes 0; merges 0/4 policies; false births 3/4 policies; Jamie unknown 4.221 s/policy |
| Prototype predicate | PASS | `jq -e` returned `true` |
| JSON syntax | PASS | 2/2 files valid |
| Backend | PASS | 2,116 passed; 5 skipped; 2 expected xfailed; 0 strict xpass; 0 failed; 37 subtests passed; 21 warnings |
| Frontend tests | PASS | 28/28 files; 311/311 tests; 0 failed |
| TypeScript | PASS | 0 errors |
| Vite build | PASS | 34 modules transformed; build succeeded |
| Diff check | PASS | 0 whitespace errors |
| Parent diff scope | PASS | 9 changed paths; 0 production paths |

Parent-diff paths:

- `docs/verify/r4-4-jamie/VERIFY-RESULT.md`
- `docs/verify/r4-4-jamie/VERIFY.md`
- `evidence/round4/jamie/EVIDENCE.md`
- `evidence/round4/jamie/results.json`
- `prototypes/jamie/NOTES.md`
- `prototypes/jamie/README.md`
- `prototypes/jamie/run.py`
- `prototypes/jamie/snippets.json`
- `tests/test_round4_jamie_violating_controls.py`
