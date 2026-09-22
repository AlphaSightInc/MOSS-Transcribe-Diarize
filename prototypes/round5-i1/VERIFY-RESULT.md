# Fresh verification result — D31 production L1 harness gate

Verdict: PASS with one documentation-count discrepancy.

- Fresh clone: `/private/tmp/moss-round5-i1-verify` (the path was absent before cloning).
- Verified SHA: `79dd74653a0b1ee2d00231d5c77a8b45a6590b21` (`round5/impl-l1`).
- Prescribed Python imported `moss_transcribe_diarize` from the fresh clone.
- Diff: `git diff --check 58882514` passed; no changed files under `moss_transcribe_diarize` or `frontend/src`. Frontend source untouched.
- D31/identity controls: 15 passed, 0 failed.
- Full backend: 2323 passed, 5 skipped, 2 xfailed, 0 failed (37 subtests passed; 19 warnings).
- Bundle: 22 passed, 0 failed.
- Decoder/provider requests: 0. This verification started no provider, tunnel, GPU, or shared MOSS listener; its focused controls use injected in-process clients. The committed D31 summary also records `decoder_requests: 0`.
- Final fresh-clone status: clean.

Blocker/discrepancy: `VERIFY.md` still expects 2324 backend passes, while this updated SHA reports 2323. The focused expected count was updated to 15, and all required commands have zero failures; update the stated backend expected total before treating the written expectation as exact.
