# Fresh verification result — D31 production L1 harness gate, retry 1

Verdict: PASS.

- Fresh clone: `/private/tmp/moss-round5-i1-verify-fresh-20260922` at
  `01647fbc77fdc5b61da2c43abce14fcbe84616b5`.
- Fetched read-only scorer integration:
  `fd825ee7166966e700b2c10e09b52ac0f82fb812`.
- Prescribed Python imported `moss_transcribe_diarize` from the fresh clone.
  `git diff --check 58882514` passed; changed product/frontend paths: 0.
- D31 controls: 19 passed, 0 failed.
- Full backend: 2,327 passed, 5 skipped, 2 xfailed, 0 failed; 19 warnings and
  37 subtests passed.
- Bundle: 22 passed, 0 failed.
- Decoder/provider requests: 0. No provider, tunnel, GPU, or shared listener
  was started. Final fresh-clone status: clean.
