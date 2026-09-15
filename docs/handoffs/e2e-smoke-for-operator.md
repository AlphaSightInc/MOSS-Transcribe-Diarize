# Run the post-preadmission browser smoke test

Run from the repository root on the operator machine with its existing trusted TLS configuration and installed Playwright Chromium. Do not supply a CA file. The production command uses normal browser certificate verification; the loopback TLS bypass cannot be used with the production hostname.

Run the no-decoder smoke:

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --base https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861 \
  --rows 1,6,11,12 \
  --output "/tmp/moss-smoke-$(date +%Y%m%d-%H%M%S)"
```

Read the last line: `1:PASS | 6:PASS | 11:PASS | 12:PASS | total 4/4 PASS, 0 FAIL`. Inspect `results.json`, row JSON/screenshots, and `network.jsonl` in that output directory. Exit 0 means selected checks passed; 1 means failed; 2 means invalid arguments; 77 means the required browser is unavailable (not a pass).

Treat rows 6 and 11 in this command as **empty-workspace checks**: export disabled, history empty. Their evidence explicitly says `scope: empty_workspace`. They do not qualify populated exports or selected-meeting headers. No corpus, ffmpeg, decoder or relay is required for this command.

Run populated file/live/export/audio checks with the existing 50-second corpus:

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --base https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861 \
  --corpus evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s \
  --rows 1,2,4,6,7,11 \
  --output "/tmp/moss-smoke-audio-$(date +%Y%m%d-%H%M%S)"
```

Install/use ffmpeg and ffprobe for audio rows; allow tab capture on the operator machine. Row 9 qualifies both configured relay models, so it is left out above while `ga0-rtx4090:1235` is unreachable. Check the demo's summary provider with the command below instead. Select prerequisites explicitly: 5 needs 4; 7 needs 2; 10 needs 4; 8 needs 4 and 10; 9 needs one of 2/3/4. Rows 13 and 14 exercise outages and repeated capture and are intentionally omitted above. Row 3 serves a local URL fixture: use it only against a stack able to reach that fixture, not the remote production origin.

```sh
MOSS_SUMMARY_PROVIDERS=external OPENROUTER_API_KEY=<key> \
  MOSS_BASE=https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861 \
  .venv/bin/python tests/e2e/verify_summaries.py
```

It summarizes a 50 s and a 180 s transcript through the browser's own summary worker. Row 9 only ever used the 50 s clip, which is how a timestamp defect that failed realistic meetings went unnoticed.

Use a new or empty output directory each time. Every invocation opens a fresh isolated browser context and creates its own workspace; it never loads saved cookies or edits existing workspaces. Meetings/names/summaries are created only in that workspace. Evidence and test meetings are retained; nothing is deleted. Keep `browser-state.json` private if you need to inspect that test workspace later.

## Local verification

Verified on isolated port 17863, separate SQLite state, draft lane 1.0, **relay unset**, without a corpus:

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --base https://127.0.0.1:17863 --allow-local-self-signed \
  --rows 1,6,11,12 --output /tmp/moss-operator-smoke-20260911/pass
```

Result: 4/4 PASS. Network evidence contains exactly one mutation, `POST /api/workspace/bootstrap`; zero decoder/summary submissions. Nine CLI/isolation regression tests pass. Retained evidence: `evidence/operator-smoke-20260911/`. This local self-signed run does not claim verification of production TLS or deployment. No host operations or changes to port 17861's database.

Scratch paths in commands above are local inputs/output destinations, not bundled evidence; retained outputs from the original Mac run are MacStudio-local (not in repo).
