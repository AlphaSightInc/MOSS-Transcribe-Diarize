# Headed Chromium mute control

FIX-3.1 requires headed Chromium with `--mute-audio`; the inherited harness instead
removed Playwright's default mute argument.

- Pre-fix control: collection ERROR because no `_chromium_args` contract existed.
- Fix: one launch-argument function includes `--mute-audio` exactly once alongside
  the fake microphone and tab-capture arguments; the harness no longer ignores mute.
- Post-fix visible-word suite: `11 passed in 1.22s`; diff check clean.

No physical microphone is used and no audible output is authorized.
