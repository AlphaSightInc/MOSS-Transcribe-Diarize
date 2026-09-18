# VERIFY-RESULT — WP10

**PASS.** Every step of `VERIFY.md` executed literally in a new shell
(`/bin/bash --noprofile --norc`) started from `/`, i.e. with no inherited shell state and no
cwd from the implementation session. 2026-09-18, branch `mvpfix/wp10-zero-guard-seams`.

| step | expected | observed | verdict |
|---|---|---|---|
| 1 package resolves inside this worktree | path under `…-wt-wp10-zero-guard-seams/` | `…-wt-wp10-zero-guard-seams/moss_transcribe_diarize/__init__.py` | pass |
| 2 the nineteen seam contracts | 147 passed, 0 failed | `147 passed, 4 warnings, 9 subtests passed in 6.58s` | pass |
| 3 WP3 guard contracts at the relocated seam | 40 passed, 0 failed | `40 passed, 19 subtests passed in 3.21s` | pass |
| 4 WP10 guarantees | 9 passed | `9 passed in 2.78s` | pass |
| 5 requirements falsifier | `7/7`, exit 0 | `verdict 7/7 requirements met`, `falsify exit=0` | pass |
| 6 full Python suite | 1792 passed, 2 skipped, 0 failed | `1792 passed, 2 skipped, 21 warnings, 37 subtests passed in 137.65s` | pass |
| 7 frontend | 26 files / 230 tests, clean typecheck, clean tree | `26 passed (26)`, `230 passed (230)`, `tsc --noEmit` clean | pass |

## Honest notes

* Step 7's tree was **not** clean on the first look: the frontend suite rewrote
  `evidence/mvpfix/wp2/production-{390,400,1280}.png` (byte-level screenshot churn from
  another WP's bench). `VERIFY.md` predicts this and says to restore them; done, after which
  `git status --short` shows only this branch's own untracked evidence and `VERIFY.md` itself.
  Nothing outside this worktree was touched at any point.
* `moss_transcribe_diarize/app/frontend_assets/*` is unchanged — WP10 touched no frontend
  source, so no rebuild was performed or needed.
* Nothing was falsified. The one claim I could not verify offline is the original WP3
  measurement it rests on (a real decoder inventing ~40 words for a span of digital zeros);
  that is WP3's evidence, re-used rather than re-measured, and WP10 does not change the
  threshold it established.
