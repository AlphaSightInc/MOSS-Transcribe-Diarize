# WP19 measured acceptance

**PASS A1–A5 locally and in fresh-context verification at 30418b2e.**
Fresh Python 1889 passed / 2 skipped / 37 subtests (157.94 s); frontend 249/249;
typecheck PASS; fresh lease 20/20. Six-minute replay exactly matches retained rows,
62.804387 s; 30-minute reference scoring revalidated (runtime retained, not rerun).
See docs/verify/wp19/VERIFY-RESULT.md and fresh-summary.json.
Base c2e45867; branch mvpfix/wp19-file-identity-album.

F1 — WP18 falsifier becomes a canonical album: local window voices match ONE reference
per canonical speaker, then existing admission and final sweep apply. No new thresholds.
Manifest .35 score/.10 margin, .5 s matching, 1 s birth, 2 s admission, 10 exemplars,
16 speakers; existing .70 merge rule. Per-call state isolates meetings. Unknown short
utterances abstain; later evidence can rescue an early abstention. Text/time unchanged.

F2 — Real decoder, same-input old/new controls: 6 min 7 -> 3, 30 min 31 -> 3 identities.
Six min 84/92 segments correct (91.3043%); 322.11/338.04 reference-overlap s (95.2875%).
Thirty min 420/464 correct (90.5172%); 1592.97/1684.98 s (94.5394%). Zero abstentions.
Accuracy uses one global one-to-one mapping, then each segment's maximum temporal
reference overlap. Every row retained. Not word accuracy; local decoder diarization
errors remain. Repeating two public clips tests recurrence, not broad-corpus quality.

F3 — Resolver including CPU embedding: 62.894428 s / 3 windows, 332.007926 s / 15 windows.
18 fresh serial vLLM requests over own 18119, no retries, no shared service changes;
request timing/tokens/queue recorded in accept-real files. Tunnel stopped.

F4 — Production Account vLLM default album; --file-identity legacy restores previous
resolver for one release. Uses supplied live manifest. Direct legacy class, single-window
and HF decode unchanged. Because terminal and File shared a runner, terminal composition
keeps the same decoder with its prior resolver; live algorithm/policy/modules untouched.

F5 — A4 save/reopen/rename/enroll/private-bank succeeds with real File task, window
stitching and WAV/MP3 archive plus perfect-vector fake decoder. Five production frontend
export serializers consume that exact saved synthetic artifact. Explicit file enrollment
reconstructs from retained audio/selected canonical intervals and uses existing admission
and bank; no schema change, no implicit enrollment. Missing audio yields unavailable.
MP3 prototype cosine .969589 vs PCM; 5 s eligible, .6 s refused. Enrollment re-embeds on
request, so adds CPU work. Actual live/private user audio was not used.

F6 — Lease test replaces wall-time expiration with the existing fake timer driving the
real renewal/expiry callback after capture; 30 ms policy unchanged. 20/20 independent
runs. Full Python 1889 passed, 2 skipped, 37 subtests, 21 warnings, 152.64 s. Frontend
249/249 in 28 files; typecheck pass. Tests' initial author mistakes retained in test-summary.

Deviations: unattended state-printing bench replaces interactive TUI; validated prototype
absorbed into product and reusable bench. Verification docs live in docs/verify/wp19 per
repo gate. A4 export verified through frontend serializer, not nonexistent server route.
Initial frontend loader omitted native mode; later use --configLoader native to avoid
shared dependency config bundling. No source edits outside WP19. No build needed because
frontend production code/assets unchanged. No push/merge/deploy/GitHub or peer messages.
