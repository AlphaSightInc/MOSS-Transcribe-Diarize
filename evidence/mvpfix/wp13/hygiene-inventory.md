# Hygiene inventory at d8ee6f4109f277a22bfbca298da9ebdf85b218c8

`git ls-files` + file sizes: no tracked .txt/.log file over 1,000,000 bytes.
Named `evidence/mvpfix/wp1/fix-broad.txt`: 258,059 bytes; retained, no removal needed.
WP3 `chunks.json`: 3,396,624 bytes, 17,640 per-chunk diagnostic rows. Relocated to
ignored `evidence/mvpfix/wp3/raw/chunks.json`; committed `chunks-summary.json` keeps
exact aggregate counts. Producer/consumer paths updated; no NOTES line references
require retaining the full log. Offline regeneration preserves every decision.
Historical corpora and structured result artifacts are retained. The named WP1
file's >1 MB premise is false at this base; the WP3 raw log did require relocation.
Future raw WP logs: ignored `evidence/mvpfix/*/raw/`; WP13 runs: ignored `.wp13runtime/raw/`.
Small exact-count summaries are committed instead.

`tests/phase2/test_lane_consumer_geometry.py` was the sole writer of
`evidence/mvpfix/wp2/production-{390,400,1280}.png`; now uses pytest tmp_path.
Frontend test source has no screenshot call. Previously committed screenshots remain
unchanged. Tests use a worktree-local TMPDIR to keep transient files in this tree.

`.gitignore` contained literal merge markers around WP1/WP9 rules. Removed markers,
retained both rules and WP9 log exception. Added worktree-local runtime/cache ignores.
Root VERIFY files were already absent; a script plus tests now reject reintroduction.
