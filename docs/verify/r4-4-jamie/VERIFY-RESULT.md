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
