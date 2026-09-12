# Browser latency bench

Question: where does known input speech wait between capture and visible text?
Primitives: audio sample coordinate; descriptor-sized frame; two-lane mixed frontier;
canonical result; snapshot cursor; signal/DOM publication. Each names a distinct wait.
Invariants: preserve both lanes, canonical/identity ordering, committed-boundary preview
retirement, abort fencing, cursor semantics; never confuse any text with spoken text.
Unknowns: shared decoder load, physical microphone latency, cross-process clock offset.
Falsifier: unchanged ready-to-DOM latency across controlled reader phases would reject
faster polling as useful. A non-speech preview invalidates first-any-text as speech latency.

Tools: temporary source hooks locate browser stages; the real E2E row 4 exercises the
product; controlled reader phases remove decoder variance; sample correlation establishes
injected onset; production-mixer header replay estimates the lookahead wait without audio.
No model/identity/policy change. Result: controlled median reader wait 128.4 → 82.8 ms;
validated known-speech latency 3.29 → 3.28 s, essentially unchanged. Keep only faster active
polling. See `docs/audits/browser-latency-budget-20260911.md` for all limitations/results.

## Reproduce

Run from repo root, using the existing local stack (no database reset). `CORPUS` is the
mono_javier_intro_50s directory. The installed Python environment needs Playwright,
SciPy, soundfile and NumPy; browser binaries are required for this **optional bench**.
It is not a required deterministic test. The E2E harness creates its own account/meetings.

```sh
.venv/bin/python prototypes/streaming-diarization/browser-latency/build_instrumented.py /tmp/browser-bundle
.venv/bin/python prototypes/streaming-diarization/browser-latency/measure.py --corpus "$CORPUS" --output /tmp/browser-row4 --bundle /tmp/browser-bundle/app.js
.venv/bin/python prototypes/streaming-diarization/browser-latency/make_fixture.py "$CORPUS" /tmp/browser-known-corpus
.venv/bin/python prototypes/streaming-diarization/browser-latency/measure.py --corpus /tmp/browser-known-corpus --output /tmp/browser-known --bundle /tmp/browser-bundle/app.js --known-onset 4
.venv/bin/python prototypes/streaming-diarization/browser-latency/budget.py /tmp/browser-known --known-onset 4 --out /tmp/browser-budget.json
.venv/bin/python prototypes/streaming-diarization/browser-latency/reader_probe.py --before /tmp/baseline-bundle/app.js --after /tmp/browser-bundle/app.js --out /tmp/reader-phases.json
```

Build the baseline bundle in a separate checkout of 24197fdd with the same temporary
hook builder. Never check out the live local-stack worktree. Builder restores source and
shipped assets in `finally`; interruption by a hard kill still requires checking the diff.
Hooks are confined to a Playwright route serving the instrumented bundle. They do not
change the running service. Fake-source alignment and the “the following” check apply
only to this fixture, not arbitrary speech. The mixer replay assumes the measured local
descriptor (16 kHz, 8,000 wire samples, 16,000 maximum mixed samples).

`results/` retains four runs' content-free frame/snapshot/event timings, alignment scores,
row-4 scalar results, validated budgets, and all 14 reader phases. Original row-4 before
failed and remains in the denominator. Temporary cookies, audio, transcripts and screenshots
are excluded. The older unvalidated synthetic runs are rejected, not pooled into a mean.
The matching-prefix check was added after they exposed an impossible first-text timing.
