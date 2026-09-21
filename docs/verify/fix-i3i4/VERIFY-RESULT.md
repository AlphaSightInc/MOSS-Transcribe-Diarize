# Retained-resume fix verification result

**PASS (current executor context).** No decoder, provider, external-network, or
tunnel calls were made. A separate fresh-context agent was not launched.

- RED receipt before production edits: `8 failed / 8` with `--runxfail`; normal
  run `8 xfailed / 0 failed`.
- Focused final controls: `14 passed`.
- Focused lifecycle regression gate: `67 passed`.
- Full backend: `2213 passed / 0 failed / 5 skipped / 2 expected xfailed / 37 subtests`.
- Frontend: `312/312`; TypeScript clean.
- `_assert_no_active_meetings`: AST-identical to `0de56e1a`.
- Product scope: only `phase2.py`, `phase2_file.py`, and
  `windowed_transcription.py`; secret scan empty.
- Mix-bound end-to-end result: crash after windows 0–1; restart dispatched
  exactly windows 2–3; final transcript equaled uninterrupted windows 0–3.

