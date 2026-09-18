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

## Per-lane build: attended overlap check still required

On the per-lane candidate, microphone and shared-system speech are decoded separately:
**both lanes are expected to retain words during cross-lane overlap**. The old
“never overlap sources” presenter workaround is obsolete for this build, pending
attended measurement; this statement is an expected contract, not attended proof.
Confirm the served candidate supports per-lane decoding before using this protocol.

With headphones, speak a known sentence while the interview plays a different known
sentence. Record both references and lane attribution. Check live text, Stop → saved
meeting → reopen → exports for both sentences, omissions, additions and speaker/lane
mix-ups; use the existing ordered word-error oracle. Same-lane simultaneous speakers
remain outside this contract. Headphones do not establish speakers-mode echo quality:
that needs a separate attended measurement. Do not label the automated no-decoder smoke
or its 4/4 result as overlap acceptance.

Run the read-only checks in [TLS renewal runbook](tls-renewal-runbook.md) first.
WP13 observed trusted TLS on 7862 but self-signed TLS on 7861; do not bypass the latter
or treat 7862 as a qualified substitute for the admitted candidate on 7861.

## Local verification

Verified on isolated port 17863, separate SQLite state, draft lane 1.0, **relay unset**, without a corpus:

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --base https://127.0.0.1:17863 --allow-local-self-signed \
  --rows 1,6,11,12 --output /tmp/moss-operator-smoke-20260911/pass
```

Result: 4/4 PASS. Network evidence contains exactly one mutation, `POST /api/workspace/bootstrap`; zero decoder/summary submissions. Nine CLI/isolation regression tests pass. Retained evidence: `evidence/operator-smoke-20260911/`. This local self-signed run does not claim verification of production TLS or deployment. No host operations or changes to port 17861's database.

Scratch paths in commands above are local inputs/output destinations, not bundled evidence; retained outputs from the original Mac run are MacStudio-local (not in repo).

## Campaign refresh — WP23, integrated source c609d7f3 (2026-09-18)

**Historical smoke results above are not final-candidate qualification.** Confirm
the exact served SHA and target TLS first. These commands are future authorized
checks; WP23 ran no browser/decoder campaign. See the [campaign ledger](mvpfix-campaign-20260918.md)
and [attended plan](attended-session-plan.md).

**A1 — Independent lane oracle.** From an isolated candidate checkout, against the
identified trusted target (substitute its origin and private output path):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> tests/e2e/verify_demo_lanes.py \
  --base https://TARGET-ORIGIN --case both --output PRIVATE-OUTPUT/lane-oracle.json
```

Both alternation and overlap must pass their actual immediate/final/reopened
per-lane WER, attribution and duplication predicates. Default microphone gain is
.03. WP17's corrected independent reference is 53 words; old 48-word reports remain
historical. WP20 still failed quality; do not count expected failure as success.
This synthetic source replay does not establish physical microphone/AEC acceptance.

**A2 — Browser stress, 16 cases.** WP14 extended the WP5 bench:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> prototypes/browser-stress/run.py \
  all --base https://127.0.0.1:17865 --output PRIVATE-OUTPUT/browser-stress
```

Use its dedicated isolated WP5-style stack and fixture state, after port/budget
scheduling; `all` includes stack-control assumptions and is not safe to point at a
shared deployed service. A `--base` argument alone does not isolate all its internals.
Cases 15/16 add 25/35-second lease-outage behavior. Report the actual 16-case table,
including blocked hidden-tab capability; no historical 16/16 pass is claimed.
Do not use a visible-state result to satisfy hidden capture.

**A3 — Qualification bundle once WP21 lands.** Planned entry point, absent at c609d7f3:

```sh
bash scripts/mvpfix-qualify.sh
```

Read `tools/qualify/README.md` in the landed version first. Its initial branch uses
app 17881, tunnel 18121 and accounting 18122; 18122 overlaps WP22's assigned tunnel,
so schedule ownership and treat an occupied port as UNRUNNABLE. Do not reuse/stop it.
The first retained WP21 run completed static gates then stopped with KeyboardInterrupt
before decoder use; it is not a qualification pass. Current bench interface gaps must
remain UNRUNNABLE. After the final SHA is frozen, retain
`evidence/qualify/<sha>-<utc>/summary.json` and all gate denominators. `--long` requests
30-minute files/four-session capacity; initial interfaces cannot execute those safely.
Summary row SKIP-with-reason is not summary acceptance. The bundle cannot replace
attended G7/echo, visual approval, physical voiceprints or host release gates.
