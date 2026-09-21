# Headed visible-word session probe

## Verdict — RUNNABLE-HERE

`launchctl managername` is `Background`, yet the repaired headed instrument's exact browser launch is runnable from this tmux session. Chrome 153.0.8010.53 launched with `headless=False` and exactly `--mute-audio`, loaded loopback HTTP 200, and returned a visible, non-empty DOM (96-byte `outerHTML`, marker present, `document.hidden=false`). This falsifies **BLOCKED-ON-SESSION** for headed launch/rendering.

The result does **not** re-open L9 hidden-tab qualification: the one headed DOM observation was visible, and no native hiding mechanism was attempted from this Background session.

## Structural contract

- **Question.** Can the S9 headed instrument own enough Chromium state here to launch and observe a rendered DOM, rather than fail for lack of an Aqua login session?
- **Minimum primitives.** The exact launch contract, one loopback navigation/DOM observation, and one production-stack startup are sufficient. Removing launch loses the session answer; removing DOM confuses process startup with rendering; removing the stack gate hides a separate runtime blocker.
- **Invariants.** `headless=False`; Chromium arguments equal only `['--mute-audio']`; loopback-only transport; zero remote decoder/provider requests; no microphone, playback, GPU, or product edit.
- **Assumptions / unknowns.** The probe proves Playwright's headed browser process and DOM, not a human's visual inspection of an Aqua window. A 300-second real S9 run is unmeasured: it needs SQLite 3.53.4, a frozen candidate stack, a real configured decoder, and attended word-end reference alignment.
- **Falsifier.** A repeat of `probe.py` that cannot launch, navigate, or return its marker/positive DOM length makes this verdict false. A run that silently adds a Chrome argument or uses headless mode is not evidence for this verdict.
- **Tool decision.** The loopback probe isolates session capability without a decoder. The short-stack runner uses the exact instrument internal path and production `create_phase2_app`; it stops honestly at the SQLite gate instead of monkeypatching it or contacting a decoder.

## Evidence

| Check | Result | Receipt |
|---|---|---|
| A1 launch | PASS — Chrome 153.0.8010.53; `headless=false`; args exactly `--mute-audio` | `evidence/round4/headed-session/browser-probe.json` |
| A2 DOM | PASS — HTTP 200; marker `headed DOM`; `outer_html_length=96`; visible | `evidence/round4/headed-session/browser-probe.json` |
| A3 5-second candidate-stack instrument arm | BLOCKED-ON-RUNTIME before navigation — `Refusing SQLite runtime 3.50.4; exactly 3.53.4 is required.` | `evidence/round4/headed-session/short-stack-runtime-receipt.json` |
| A4 retained S9 source extraction | PASS — Adam Frank 180 s, 8 source rows, 531 unconfirmed word rows | `evidence/round4/headed-session/s9-adam-frank-180s-*.jsonl` |

The public CLI intentionally refuses a duration other than 300 seconds. `short_stack_run.py` calls its unchanged internal runner at five seconds only to falsify browser/API/DOM wiring. It was stopped by the product's SQLite pin before a browser page or synthetic local decoder ran. Therefore it supplies no recognition, finalization, or latency result.

## R4-10 / R4-11 consequence

Schedule **attended** R4-11 word-end alignment first: use the retained 180-second Adam Frank clip with muted speakers and headphones, and complete all 531 word ends in the template. Then R4-10 may convert that completed template to one-word instrument input and run S9's real 300-second frozen-SHA measurement under its decoder budget. The headed browser itself does not require an Aqua relaunch recipe; a local real-stack trial here remains blocked until the required SQLite runtime is supplied.

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/headed-session/probe.py \
  --output /private/tmp/moss-headed-session-browser-probe.json
```

Expected: JSON with `managername: Background`, `headless: false`, `chromium_args: ["--mute-audio"]`, HTTP 200, marker, and positive DOM length. A fresh output path is required. The short-stack command is deliberately expected to exit 1 on this host with the recorded SQLite error; it must not be made green with a pin/module bypass.

## Validation

- Focused instrument controls: `23 passed`.
- Full backend: `2130 passed, 5 skipped, 8 xfailed, 37 subtests passed in 186.67s`.
- Full frontend: `312 passed (28 files)`.
- Frontend typecheck and production build: PASS.
