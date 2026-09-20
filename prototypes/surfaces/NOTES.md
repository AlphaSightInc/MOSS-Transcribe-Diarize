# R4-8 surfaces prototype verdicts

## Contract

**Structural question.** Can native macOS state expose a genuinely hidden capture page;
can summary exit semantics be staged without an external request; and can the frozen
candidate be served through localhost without TLS or deployment?

**Minimum primitives.** (1) An Aqua-owned headed browser window plus observed Page
Visibility events. (2) The real browser summary worker, two transcript durations, and a
separate loopback OpenAI-compatible provider. (3) One loopback HTTP listener and one SSH
local forward. Removing any primitive would replace the behavior being measured.

**Invariants.** Never write/emulate Page Visibility; never send off-host; never expose a
provider credential; never use GPU, microphone, or playback; never edit product code.

**Assumptions and unknowns.** The current pane is a Background launchd session. Native
hiding, m4mbp forwarding, browser microphone permission, physical routes, real-provider
semantics, and media inference remain unmeasured.

**Falsifiers.** A visibility mechanism that tells the page it is hidden; any new artifact
containing a secret pattern/value; any off-host request; wrong verifier exit semantics;
or an app listener bound beyond loopback.

## Item 1 — native hidden/minimised tab

**Verdict: BLOCKED-ON-SESSION.** `launchctl managername` printed `Background`; the
prepared runner exited 77 before launching Chromium. Playwright resolves to
`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`.

`native_visibility.py` tries, in required order: Google Chrome's AppleScript `minimized`
window property; a second Chrome process with a full-screen occluding window; then
System Events app-hide. The last requires Accessibility TCC; the script reports denial
and never grants it. Every attempt records `document.hidden`, `visibilityState`, and
`visibilitychange` events. `run_hidden_cases.py` applies the first successful native
mechanism to browser-stress cases 3 and 15 for 60 seconds.

One-command reproduction from an Aqua GUI Terminal (with the owned stack already ready):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <project-python> \
  prototypes/surfaces/run_hidden_cases.py 3,15 --headed \
  --base https://127.0.0.1:<owned-stack-port> \
  --output evidence/round4/surfaces/hidden-cases
```

Current evidence: `evidence/round4/surfaces/hidden-session-gate.txt`. Needed: launch
from the physical console with `open -a Terminal`, then run the same command. Cases 3/15
have **0 native observations** and were not mislabelled UNRUNNABLE.

## Item 2 — summaries dry-run

**Verdict: SUPPORTED for the three functional paths.** Entire run executed inside the
macOS loopback-only sandbox. The shell sourced the operator file with export enabled and
tracing disabled; it never printed or copied its value. The fake provider discards
headers and bodies and retains content-free request metadata only.

- Disabled browser-stress case 13: PASS; **0 provider POSTs**.
- Healthy path: exit **0**; **2/2** current (50 s and 180 s).
- Violating path: exit **1**; **1/2** current, with only the 180 s canned response invalid.
- Unconfigured path: exit **77**; **0 attempted**.
- Fake provider: **4 local POSTs** total, all `/v1/chat/completions`; valid responses carry
  a `00:00:01` detail timestamp. External POSTs: **0** by sandbox contract.

One command:

```sh
./prototypes/surfaces/run-summaries.sh
```

**Secret-scan caveat.** The exact required repository-wide grep is already nonempty at
untouched `89f833ac`: seven documentation placeholders contain `<key>`. They are not
credentials and are outside this slice. New/owned paths have zero matches. See
`evidence/round4/surfaces/secret-scan.txt`. Therefore the brief's expectation that the
repository-wide command be empty is impossible without unrelated baseline edits.

## Item 3 — m4mbp localhost recipe

**Verdict: artifact written; MacStudio launch scope verified.** See
`docs/handoffs/attended-localhost-recipe.md`. Port 18442 avoids every excluded port.
The full candidate composition started under the R4-7 Python reporting SQLite 3.53.4,
loaded the Live manifest, listened only on `127.0.0.1:18442`, and returned HTML to a
loopback curl. It was then stopped; no meeting, capture, or decode was invoked.

Unverified: `ga0@m4mbp` SSH/DNS/forward, localhost secure-context browser behavior,
microphone, playback, voiceprints, echo capture, decoder reachability, and inference.
Evidence: `evidence/round4/surfaces/localhost-smoke.txt`.

## Seams and implementation decision

No production change is justified by these verdicts. Later measurement uses these
existing seams only:

- hidden cases: `prototypes/browser-stress/run.py:112-118`, `:136-170`, launch flags
  `:367-375`;
- summary configuration and exit contract: `tests/e2e/verify_summaries.py:40-50`,
  `:83-105`, `:106-163`;
- attended localhost: prototype launcher plus the existing production app factory;
  no product file changes.

**Implementation falsifier to carry:** do not propose a capture/product change unless an
Aqua run first records `document.hidden=true` from native OS state and then shows a
product failure while hidden. A real-summary pass changes only provider URL/key and must
retain exit 0/1/77 behavior with no secret artifact.

## Final process state

GPU/decoder requests: **0 / 0 budget**. Provider calls: **4 local / 0 external**. No
owned browser, server, tunnel, or port 18442/18443 listener remains.
