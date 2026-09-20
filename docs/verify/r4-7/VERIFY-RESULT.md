# R4-7 verification result

**Verdict: PASS-with-note.** Every command in `VERIFY.md` completed with its
expected product result. The commands ran in the restarted pane, not a post-work
`/new` session; fresh-context isolation is therefore **UNMET**, not silently
claimed.

## Exact results

- Branch/SHA: `round4/runtime` at
  `89f833acd4c654dd702664a17ed19783a2999c95` before the deliverable commit.
- Runtime: `3.53.4 3.53.4`; `_sqlite3` came from the disposable CPython prefix.
- Capacity: `SUPPORTED`; 384,000,000 B per tape; 768,000,000 B for two;
  finalizer/runtime/app descriptor agree; 0 decoder requests.
- Stopped backup/restore: `SUPPORTED`; source, restored, and downloaded audio
  MD5 all `b7d78ab885378363cc61181f731dc192`; transcript/status unchanged.
- Disk exhaustion: `SUPPORTED`; real `ENOSPC` errno 28 after 645,922,816 B;
  saved and reopened state both `failed/decode_failed`, never `completed`.
- 201-minute File tail: 1 passed, 2 warnings, 0 failed in 3.79 s.
- Backend final rerun: 2,116 passed, 5 skipped, 19 warnings, 37 subtests
  passed, 0 failed in 214.07 s.
- Frontend: 28 files and 311/311 tests passed in 2.99 s; `tsc --noEmit`
  clean; Vite transformed 34 modules and built in 116 ms.
- Cleanup: disk image detached; no pane-owned server/tunnel/process remained.

## Failed verification attempt retained

The first literal backend pass after writing verification documentation produced
2,115 passed / 1 failed / 5 skipped / 37 subtests. The sole failure was
`test_verify_layout_current_tree`: the first draft put `VERIFY.md` at repository
root, while `scripts/check_verify_layout.sh` requires
`docs/verify/<wp>/VERIFY.md`. Moving the document to `docs/verify/r4-7/` made the
focused layout control pass; the untouched full backend suite then matched the
baseline above. No product or test-contract behavior was weakened.

## Remaining independent check

Run `docs/verify/r4-7/VERIFY.md` from a truly fresh `/new` session if strict
context independence is required. This is a verification-process remainder,
not a runtime-product falsifier. Its handoff SHA gate checks that the committed
deliverable's parent is the pinned candidate.
