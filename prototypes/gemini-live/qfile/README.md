# Q-FILE HTTP qualification

Run from the worktree root, with the lead's exact integration SHA:

```sh
MOSS_GEMINI_STATE=/absolute/scratch/qfile PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/qfile/run.py --worktree /absolute/integration/worktree --expect-sha <sha> --out /absolute/evidence/qfile.json
```

The command launches one HTTPS Gemini server on loopback port 18730, uploads six `accept6` public WAVs and registered `long60`, waits for saved File Meeting completion, scores, names one speaker per completed clip, writes `qfile.json` after each clip, and stops the server. `--port` may select 18730–18739. `--case interview_keyu_jin_60s` limits a dry run to one clip; that output has no full-gate verdict. The server's SQLite, retained audio, certificate, key, and log stay under `MOSS_GEMINI_STATE`; the evidence output contains JSON only. Use a fresh state directory for each run.

## `moss.qfile.v1` schema

- `worktree`, `source_sha`, `selection`, `server_port`, `started_at_utc`, `updated_at_utc`: source and run custody. `run_failure` records a launch or runner failure outside an individual clip.
- `cases[]`: one object per selected clip, in run order. `case_id`, `tier`, `audio_seconds`, `audio_bytes`, `meeting_id`, `meeting_status`, `transcript_rows`, and `speaker_count` describe the input and saved HTTP result. `transcription_wall_seconds` runs from upload start to terminal Meeting status; `wall_seconds` also includes scoring and naming.
- `cases[].scorer` is `h1_offline.score_case.final` for `accept6` or `common.score` for `long60`. `metrics` is the selected scorer's native final metrics object, including `der`; `null` means scoring never completed.
- `cases[].enrollment`, `named_speaker_seconds`, and `voiceprint_id_present` report the completed Meeting's name response. The selected speaker has the greatest total saved row duration. `failure` is `null` on success or a typed error/Meeting outcome.
- `cases[].engine_diagnostics` and `usage_cost_usd` copy server fields when present. `usage_cost_status` is `MEASURED` or `UNMEASURED`; the estimate never populates measured usage.
- `cases[].cost_estimate` is `null` unless the File Meeting completed. It is explicitly `ESTIMATE`, not a billing receipt: one 900 s / 30 s-overlap terminal chunk pass over the uploaded WAV, with each chunk selected by the production WebRTC voice detector. `chunks[]` gives each start/end and `sent_estimate`; `audio_seconds_sent_estimate` counts repeated overlap seconds. `input_usd` uses Gemini 3.5 Transcribe's standard audio input list-price estimate of $0.003/min; `output_usd` uses Google's $0.002/min output estimate; `total_usd` is their sum. Retries, coverage retries, text input, and any difference in the server-normalized mix remain unmeasured. Source: [Google Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing), checked 2026-09-29.
- `aggregate` counts selected, completed, scored accept6 cases, enrolled cases, measured and unmeasured cost cases, plus `estimated_cost_cases` and `estimated_cost_usd` for completed cases. `accept6_der_macro` is the equal-weight mean of six H1 final DERs when all six score; `long60_der` is the production scorer's DER. `qfile_gate` is `PASS` only when all seven selected cases complete, accept6 macro ≤ 0.110, long60 DER ≤ 0.06, and all seven enroll. It is `FAIL` for a complete seven-case run missing any condition and `UNMEASURED` for a partial run.

The runner preflights the registered population, WAV format, references, exact worktree SHA, both scorers, and the Unix control socket path before starting the server. Keep `MOSS_GEMINI_STATE` short enough for that socket (for this worktree, `.qf` works). It does not score accelerated Live replay or use private audio.
