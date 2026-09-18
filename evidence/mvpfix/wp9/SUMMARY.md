# WP9 implementation evidence, before fresh verification

Base a92bb4aa; own branch mvpfix/wp9-rename-identity.
Question: can owned saved meetings be renamed independently of transient capture?
Before: 1/5; after: 5/5. Durable GET and history agree 5/5.
Real frontend serializers: 25/25 exports; four completed summary inputs retain names.
Silence: exact original WP7 birth span 25.25–27.75 s replayed from its fixture:
0 nonzero bytes, 0 model requests, 0 identity preparations, 0 extra births.
No identity production changes or thresholds.
Affected Python: 20/20, 3.44 s. Frontend: 239/239, 27 files, 2.38 s.
Typecheck/build pass. These are local semantic/UI tests, not deployment acceptance.
Full phase2: 805 passed, 2 failed, 22 errors (829 total), 109.74 s.
All 24 original failures reproduce unchanged at a92bb4aa (3.65 s).
Base mutation with new regressions: Python 10 failed/1 passed; frontend 6 failed/18 passed.
Initial frontend baseline included two invalid active-summary assertions (8 failed/16
passed); first full frontend had 2 failed/232 passed; corrected to respect summary lifecycle.
Initial prototype failed exact SQLite gate; existing test-only override used subsequently.
Failed attempts and exact outputs retained, not hidden by successful follow-ups.

Source fixes: phase2.py, phase2_speaker_identity.py, TranscriptPane.tsx, speakers.ts.
File IDs frozen before first label edit; no storage migration, re-embedding or bank-policy change.
CONTEXT.md documents WP9 scope; prototype NOTES.md records design, reference and limits.
Two older UI assertions updated because WP9 explicitly widens the old active-only contract.
History card markup unchanged (reference has no speaker field).

Boundary limitation: existing full-suite tests create/remove hardcoded /tmp sockets and
one tempfile directory despite TMPDIR. No outside source/worktree/service changes.
Existing suite regenerated two WP2 screenshots inside this worktree; restored base bytes.
Fresh verifier must not repeat full suite uncontained. VERIFY.md names affected checks.
Fresh-context result is not claimed here: requires /new then VERIFY-RESULT.md.
