# WP22 — memory retention and 30-minute durability

Branch: `mvpfix/wp22-memory-longrun`; real-run source `a28eecd9`.
Merged accepted WP12 integration `1745b96f` before Part C, as explicitly authorized.
Final verification commit: supplied in the final pane response.
Fresh `/new` verification: PENDING; this is the pre-reset draft.

F1 — Measured memory fix: disable ONNX memory-pattern caching in speaker_identity.py.
Question: retained audio/history or native encoder workspace? Owners plateau except
required transcript/identity history; variable-length native workspace retains memory.
18 native probes: 1384→949 MiB; 80 varying probes: 831→634 MiB; all 98 vectors exact.
Arena-off/shrink controls rejected. Actual constructor control: 80/80 vectors exact.
Thirty-minute stub profile RSS: before 637 MiB, after 595 MiB; 1440 segments exact.
All PCM/tapes release; required transcript/identity metadata remains. No policy value,
frame protocol, model, identity feature, lease, or lifecycle change.

F2 — Real 30-minute run: final/completed; Stop→final 101.697916 s.
Capture 1800.001202 s, 7200 frames, 28,800,000/28,800,000 samples accounted.
6269 saved words exactly match terminal snapshot and reopened SQLite.
MP3 exactly 1800 s, 16 kHz mono. 1080/2600 requests; peak two concurrent.
System corpus repeated; mic -10 dB first 300 s then zeros. No load-based pauses.
Sibling traffic detected in 36/65 samples; timing is contended, not isolated capacity.
Three tapes: 57,600,000 bytes each, complete/no refusal; total 172,800,000→0 at release.
RSS near 5/15/30 min: 932/981/973 MiB; sampled peak 1277; post-final 1149 MiB.

F3 — Content limits: 569 system / 55 mic segments; 56 system segments unattributed.
Mic ends at 299.88 s, no words in its silent tail. Word/speaker accuracy unadjudicated.
R1 — Pre-existing exhausted-tape path omits required `gaps`; terminal reports failed.
Not fixed here; all three bounded stub profiles retain canonical content/release tapes.
R2 — Post-final RSS does not return near startup (616 MiB; warm 30 s 902 MiB).
Native retention reduction is measured; full release/repeated/four-session safety unproven.

Tests: baseline 1889 passed/2 skipped/37 subtests; regression red then 58 focused pass.
After fix 1890/2/37; merged and post-real full suites 1911/2/37; frontend 249 tests/28 files.
Post-real Python 158.29 s; typecheck/build exit 0; generated assets unchanged.
Earlier fixture-import and 30 ms lease setup failures retained/adjudicated in NOTES.md.
Fresh results: pending actual `/new`.

Files: speaker_identity.py; two regression-test files; design doc; memory-longrun bench;
`evidence/mvpfix/wp22/`; `docs/verify/wp22/`; .gitignore. No retention thresholds changed.
Evidence: OWNERS.md/profile-summary.json; real-1789715856876413000/{result,audit}.json;
raw counts/RSS/request/tape logs; native controls. No audio in git.
Deviations: scripted prototype (not TUI); accelerated/stub A/B and local SQLite bypass,
explicitly separate from real C. Only own worktree modified; no push/deploy/GitHub.
Own stack/tunnel stopped. No further GPU request needed for verification.
