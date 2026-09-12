# End-to-end workspace verification — 2026-09-11

**10 PASS; 2 FAIL.** Real Chromium drove the real local Phase-2 workspace and decoder.
File/URL transcription, live text, both naming controls, exports, interrupted audio,
history and phone navigation worked. Summary generation failed for both configured
models on the short live transcript; saved-voice recognition took 10.84 seconds,
missing the requested roughly 3-second target. No product code or host configuration
was changed. These are feature observations, not deployed acceptance certification.

The key distinction: text can appear before a stable speaker identity is ready, and a
successful model HTTP response need not contain a valid summary. Those boundaries
explain why responsive text passed while early recognition and summaries failed.

## Evidence and scope

Harness: [`tests/e2e/verify_workspace.py`](../../tests/e2e/verify_workspace.py).
Evidence directory: [`evidence/e2e-feature-verification-20260911`](../../evidence/e2e-feature-verification-20260911).
Every row has a screenshot and checked result JSON. The shared
[`network.jsonl`](../../evidence/e2e-feature-verification-20260911/network.jsonl)
records row numbers, timestamps, HTTP methods/statuses, model IDs and download metadata;
it omits credentials and request bodies. Actual transcript, model-response and audio
artefacts are separate files. This audit quotes no transcript text.

Origin `https://127.0.0.1:17861/` returned 200 immediately; decoder
`http://127.0.0.1:18000/v1/models` also returned 200. This is self-signed local TLS, not a
production trust test. The operator restarted/replaced local stack state during the
priority guard task: the original file/URL meeting IDs disappeared from the database,
but their checked artefacts were retained. The later server checkout was independently
observed at `b76b5b5c`; the operator reported `f038bd57` for the initial run. This evidence
therefore spans that local stack change, rather than claiming one pinned release.
Details: [`run-custody.json`](../../evidence/e2e-feature-verification-20260911/run-custody.json).

## Twelve checklist rows

Each evidence cell links the assertions and screenshot; the result JSON names its
transcript/download artefact. Network records are filtered by the same row number.

| Row | Result | Checked outcome | Evidence |
|---|---|---|---|
| V01 Bootstrap | PASS | Fresh workspace signed in; built app ready. | [JSON](../../evidence/e2e-feature-verification-20260911/row-01.json), [screen](../../evidence/e2e-feature-verification-20260911/row-01.png) |
| V02 MP3 upload | PASS | Completed; 9 segments; 1 speaker; word error rate 10/115 = **8.70%**, below 15%. | [JSON](../../evidence/e2e-feature-verification-20260911/row-02.json), [screen](../../evidence/e2e-feature-verification-20260911/row-02.png) |
| V03 Media URL | PASS | Same checked outcomes and **8.70%** word error rate; local HTTP-served MP3 submitted through the URL form. | [JSON](../../evidence/e2e-feature-verification-20260911/row-03.json), [screen](../../evidence/e2e-feature-verification-20260911/row-03.png) |
| V04 Live mic + shared audio | PASS | Both meters nonzero; first text **3.825 s** after Start; Stop to completed **2.187 s**; 3 final segments. | [JSON](../../evidence/e2e-feature-verification-20260911/row-04.json), [screen](../../evidence/e2e-feature-verification-20260911/row-04.png) |
| V05 Rename row + legend | PASS | Same speaker renamed fixture-label-1 then fixture-label-2; each acknowledgment 200; rows, legend and public history data updated. Final JSON export contains fixture-label-2 after Stop on the same page, **without reload**. | [JSON](../../evidence/e2e-feature-verification-20260911/row-05.json), [screen](../../evidence/e2e-feature-verification-20260911/row-05.png), [export](../../evidence/e2e-feature-verification-20260911/renamed-export.json) |
| V06 Five transcript exports | PASS | MD/TXT nonempty; JSON parsed and round-tripped; SRT/VTT parsed with positive durations, ordered starts and speaker prefixes. | [JSON](../../evidence/e2e-feature-verification-20260911/row-06.json), [screen](../../evidence/e2e-feature-verification-20260911/row-06.png) |
| V07 Audio export | PASS | Downloaded MP3 decoded by ffmpeg; ffprobe duration **50.000 s**, matching 50.000 s source. | [JSON](../../evidence/e2e-feature-verification-20260911/row-07.json), [screen](../../evidence/e2e-feature-verification-20260911/row-07.png), [MP3](../../evidence/e2e-feature-verification-20260911/download.mp3) |
| V08 Interrupted audio | PASS | Closed capture tab mid-live; lease expired into `interrupted`; **11.436 s** `.partial.mp3` downloaded and decoded. | [JSON](../../evidence/e2e-feature-verification-20260911/row-08.json), [screen](../../evidence/e2e-feature-verification-20260911/row-08.png), [MP3](../../evidence/e2e-feature-verification-20260911/interrupted.partial.mp3) |
| V09 Both relay models | **FAIL** | MacStudio: HTTP 200, invalid summary document. RTX4090: HTTP 502 `empty_content`. Neither generated a rendered valid summary on the measured short live meeting. | [JSON](../../evidence/e2e-feature-verification-20260911/row-09.json), [screen](../../evidence/e2e-feature-verification-20260911/row-09.png) |
| V10 Voice bank + repeat recognition | **FAIL** | fixture-label-2 present in bank; same corpus recognized as fixture-label-2 after **10.845 s**, exceeding 3 s. Enrollment and eventual matching work. | [JSON](../../evidence/e2e-feature-verification-20260911/row-10.json), [bank](../../evidence/e2e-feature-verification-20260911/row-10-bank.png), [screen](../../evidence/e2e-feature-verification-20260911/row-10.png) |
| V11 History selection | PASS | Transcript scrolled into view; visible header title matches selected card and mode. Initial File/URL and later Live selection both checked; final evidence is Live. | [JSON](../../evidence/e2e-feature-verification-20260911/row-11.json), [screen](../../evidence/e2e-feature-verification-20260911/row-11.png) |
| V12 Phone width | PASS | Populated workspace at **400 px**; document scroll width **400 px**; history/file navigation usable; screenshot visually reviewed. | [JSON](../../evidence/e2e-feature-verification-20260911/row-12.json), [screen](../../evidence/e2e-feature-verification-20260911/row-12.png) |

WER normalization lowercases and splits into ASCII alphanumeric words, treating punctuation
and hyphens as boundaries. Counts, reference path and transcode command are reproducible
from the harness. These English-corpus scores do not establish multilingual quality.

## Failures to route

**F1 — V09: summary content, not connectivity.** Select the completed live meeting
`4XEDDwdaowqbw63xwSsE3s95` in this test workspace. Open Browser AI settings, select each
relay model, save, and Generate/Regenerate summary. Cancel an orphan attempt first if
its creating tab closed. Use the unchanged default prompt and 200-second browser timeout.

The diagnostic MacStudio response contains 509 characters of valid JSON, all five required
keys, and an **empty `summary` string**. It ended with `finish_reason=stop`, using 142
completion tokens; this captured response was not truncated at the 1024-token limit.
`frontend/src/lib/finalSummary.ts::validateSummary` correctly rejects that empty field.
The RTX4090 response is exactly the safe `empty_content` error; the brief's reasoning-token
budget concern remains a hypothesis here because this error intentionally does not expose
upstream reasoning/usage. Full evidence: [primary response](../../evidence/e2e-feature-verification-20260911/relay-response-1789170282-1.json),
[RTX error](../../evidence/e2e-feature-verification-20260911/relay-response-1789170302-2.json),
[diagnosis](../../evidence/e2e-feature-verification-20260911/diagnoses.json).

Route to model/prompt qualification: preserve empty-output rejection; measure prompt/schema
behavior on short finalized transcripts and the RTX reasoning budget. Do not assume raising
all token limits repairs the MacStudio case. Both models were selected explicitly. Natural
primary-to-secondary fallback was not exercised by these final attempts: primary returned
HTTP 200 with invalid document content, whereas the implemented fallback applies to specified
HTTP 502 errors. No failure was injected into the live relay. The first measured pair and
the diagnostic repetition both failed; earlier automatic summaries on the longer file
transcripts do not establish reliable short-transcript behavior.

**F2 — V10: recognition works but misses its latency target.** Name committed speech,
confirm fixture-label-2 in Voiceprints, open a fresh capture page in the same workspace, and play
this corpus through both lanes. Measure Start click to the first visible fixture-label-2 label.
The captured result is 10.845 s, not approximately 3 s. See V10 above.

The current matching rule (`app/phase2_voiceprint_match.py::match_voiceprint`) refuses
provisional observations and observations below one second. Account matching consumes
those observations through `app/phase2_speaker_identity.py`. This explains why provisional
text need not carry a saved name, but **does not prove which stage consumed the 10.845 s**.
Endpoint delay, decoder work, embedding preparation and UI publication were not separately
timed. Route to the streaming-identity agent to measure those boundaries before changing
thresholds. A one-second eligibility floor is not a promise of one-second recognition.

## Harness diagnosis and limits

- **H1 — Capture preflight:** initial Chromium fake-media UI approval interfered with tab
  selection; muting browser output then left shared audio connected but quiet. The final
  harness uses camera/microphone auto-approval, selects the named audio tab, and removes
  Playwright's audio-muting default. No media API is mocked. Chromium documents the
  [approval flag distinction](https://chromium.googlesource.com/chromium/src/+/lkgr/content/public/common/content_switches.cc).
- **H2 — Browser downloads:** reused persistent Chrome 153.0.8010.37 test profiles crashed
  with native SIGSEGV during downloads, both during and after capture. The final fresh
  browser/context, saved cookie/settings state, stable download directory and explicit
  new-headless configuration completed downloads. These variables were not individually
  isolated; this is not proof of a MOSS product defect or proof that headless mode alone
  fixes it. [Playwright's headless modes](https://playwright.dev/python/docs/browsers).
- **H3 — Existing lifecycle boundaries:** provisional speech is not yet nameable. Summary
  waits must bind the newly acknowledged attempt ID, and history locators must target the
  interactive panel rather than duplicate server fallback markup. The harness now does so.
  One rapid Stop→Reset→capture attempt showed `Invalid state`; a fresh capture page worked.
  Its native-browser versus product-lifecycle origin remains unisolated, with retained
  evidence in the initial logs under `/tmp/moss-e2e-20260911`.
- **H4 — Honest denominator:** one MP3 upload, one URL submission, one V04 live latency/Stop
  run. Seven live sessions were admitted in total: the required run plus naming, recognition
  and browser-failure recovery fixtures. Preflight retries admitted no sessions. Remaining
  recordings were functional recovery checks, not repeated V04 latency samples. Models
  were diagnostically repeated to retain raw failure content. Original errors and later
  checks are distinguishable in network timestamps; this is not an uninterrupted first-pass
  12/12 claim.

## Run and guard

```sh
.venv/bin/python tests/e2e/verify_workspace.py \
  --corpus ~/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s \
  --output /tmp/moss-e2e-new-run
```

Runs against an already-started stack; does not start/restart application services, install
browsers, change host service profiles, or modify TLS. It starts only its own tiny corpus
HTTP server and test browser. Use a new output path for a fresh campaign; `--rows` resumes
selected checks without rerunning an admitted V02/V03/V04. `--new-workspace` is explicit
recovery for an externally reset server database. Browser state contains credentials and
is kept outside committed evidence.

Shared guard `tests/phase2/browser_support.py` runs before corpus preparation. Missing
browser executable produces explicit SKIP evidence and exit **77**; it cannot become a
passing checklist row. Present-browser launch errors and product failures remain failures.
This was checked with a simulated missing executable and deliberately absent corpus.
Final harness syntax/import/help checks passed. Full Python guard suite previously passed
**1330 tests + 37 subtests**, with two optional corpus skips; all **24 required files / 393
required tests** had zero skips and passed the unchanged acceptance evaluator. Guard commit:
`433e67b2`, pushed independently before E2E resumed; [guard audit](browser-guard-required-files-20260911.md).
