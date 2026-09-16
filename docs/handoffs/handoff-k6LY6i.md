# Handoff — make the UI pixel-faithful to LiveTranscribe, and prove it

Written 2026-09-15 ~23:00 EDT. The operator's verdict on the current UI: **"still crappy, not production
ready."** They are right, and the reason the previous session missed it is worth stating plainly: every check
run so far tested **function** (does the control exist, does the row pass, does the layout survive 400 px) and
**nothing tested appearance**. The reference project was never opened. Do not repeat that.

**Run `/goal` and keep going until the UI is pixel-faithful and every aspect is retested.** Use the codex agent
in tmux **`MOSS:1.2`** (`gpt-6-astra low`, YOLO, idle, context 0%) for the heavy lifting: `/diagnose`,
`/prototype`, and the implementations. Send it plain-English tasks with `tmux send-keys -t MOSS:1.2 -l "..."`
then a separate `Enter`.

## The reference

`~/Desktop/AI_Projects/LiveTranscribe` — a Swift app that ships a web frontend.

- **Authored source (the truth):** `frontend/src/App.tsx` (1773 lines) and `frontend/src/styles/index.css`.
- **Built output:** `ProjectResources/Frontend/{index.html,styles.css}` — `Package.swift:157` does
  `.copy("../ProjectResources/Frontend")`. That `styles.css` is one minified line; read the authored CSS.

**Important, so you do not chase the wrong thing:** MOSS has *already* copied the reference's design tokens.
`--paper #f6f5f1`, `--ink #14161c`, `--accent #1a1d24`, `--live #d7503a`, and the Inter / Fraunces /
Source Serif 4 / IBM Plex Mono stack are identical in both. **The gap is structure and component fidelity, not
the palette.** Diff the component trees and class vocabulary, not the colours.

Note `frontend/src/components/TranscriptPane.tsx:327`: a comment records that the reference's
Transcript|Summary toggle was deliberately deleted ("ruled Phase 2 deletion, charter §5 exemption"), leaving an
empty `transcript-view-placeholder` purely to preserve `margin-left: auto` alignment. Other deliberate
divergences probably exist. Re-audit each against what the operator actually wants; "it was ruled out once" is
not a reason to keep something that looks wrong.

## The three defects the operator named, with root causes already located

### 1. The page layout is far from the reference
Not yet diagnosed beyond the token finding above. Do a real visual diff: run the reference frontend, screenshot
both at identical widths, compare structure element by element. There is no pixel-comparison harness in this
repo — build one; its absence is the missing feedback loop that let this ship.

### 2. Speaker rename works for some labels, not others — **root cause found**
`frontend/src/components/TranscriptPane.tsx:311`:
```tsx
disabled={!canNameSpeakers || !entry.committed || entry.speakerId === "S00"}
```
with, at line 122:
```tsx
const canNameSpeakers = activeSessionId !== null
  && captureMeetingId.value === activeSessionId
  && sessionStatus.value === "active";
```
A chip is inert when the speaker is **uncommitted/provisional**, when it is **`S00`** (the unidentified bucket),
or when you are **not on the active capture page** (e.g. viewing from history). That is exactly "two thirds
respond, one third does not."

**The real defect is that a disabled chip looks identical to a live one.** `styles/index.css` defines
`.legend-chip`, `.legend-chip:hover` and `.legend-chip.is-unidentified` — and **no disabled styling at all**, so
it still paints a hover border and gives no affordance cue. The operator clicked something that looked
interactive and nothing happened. Fix the affordance (cursor, opacity, suppressed hover, a visible reason), and
reconsider whether history-page renaming should work at all rather than being silently dead.

### 3. The rename dialog has a huge checkmark — **root cause found**
`TranscriptPane.tsx:341` renders a bare checkbox inside `.history-dialog`:
```tsx
<label><input type="checkbox" checked={saveVoiceprint} ... /> Save voiceprint</label>
```
The only checkbox rules in `styles/index.css` are `.check-row input[type="checkbox"]` (16 px, line 888) and
`.speaker-popover .sp-voiceprint input[type="checkbox"]` (line 2111). **Neither selector matches this dialog**,
so it falls back to unstyled browser default — the "HUGE checkmark logo". The reference solves the same problem
elegantly in its speaker popover; copy that treatment rather than inventing one.

## How to verify — the missing capability

There is no visual regression testing in this repo. Until there is, "tested" means nothing for appearance.
Build it: screenshot MOSS and the reference at matched widths (1440, 1024, 400), diff, keep baselines. Chrome
runs headless from MacStudio via `tests/phase2/browser_support.browser_executable()`; see
`tests/e2e/stress_ui.py` for the established pattern.

## Where to test

**Internal instance: `https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7862`** — runtime `18e8a035`, open
workspace, trusted Let's Encrypt cert, no key or sign-in, keyless summaries through the macstudio relay. Use
that hostname over the tailnet; the certificate has exactly one SAN, so an IP or `.local` will warn. Phase-1
still serves `:7861`, untouched. A local stack on `https://127.0.0.1:17861` (`--allow-local-self-signed`) is
faster to iterate against.

Live capture runs headless from MacStudio despite it having no microphone:
`--use-fake-device-for-media-stream --use-fake-ui-for-media-stream --use-file-for-fake-audio-capture=<wav>`.
UI truth already established: chips are `button.legend-chip`; the rename dialog exposes **Display name**, a
**Save voiceprint** checkbox (checked by default), **Cancel** and **Save name**; exports are Markdown, Plain
text, JSON, SubRip, WebVTT; **Download audio** is a link on the history card, not a toolbar button.

## What is already done, so you do not redo it

Function is broadly green and measured: 12 e2e rows, lifecycle 7/7, reshare 6/6, UI stress 7/7, 5/5 shared
workspace concurrency, real URL and YouTube ingestion, keyless summaries. File WER 0.0935 at ~22x real time;
live WER 0.0870 / 0.0457 / 0.1241, now matching file. Four defects were found and fixed tonight (summary
timestamps and JSON fencing, a pgid process leak, the disabled relay, a 24,408-restart crash loop).

**Full state, traps and prior rulings: `docs/handoffs/handoff-2XXXXX.md` and
`docs/handoffs/auto-mvp-0911-handback.md`.** Read both before changing anything. Session memory:
`~/.claude/projects/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/memory/auto-mvp-0911-progress.md`.

## Rules that still bind

Never edit `QUALITY_BOUNDS`, the identity policy, or an evaluator expectation to make a gate pass. Push only to
`private` (`origin` is a PUBLIC fork); never force-push; never push to `dev` or `main`. **Verify every push
against the remote ref** (`git ls-remote private <ref>`), never a local echo — an earlier session reported three
pushes that had silently gone nowhere. Check `git rev-parse --abbrev-ref HEAD` before any fast-forward: a codex
agent switched that worktree's branch underneath a session.

Also note: BSD `mktemp` needs its `X`s at the end, so the `/handoff` skill's
`mktemp .../handoff-XXXXXX.md` template fails on macOS and leaves a literal `handoff-XXXXXX.md` behind.

G7 (replacing Phase-1 on `:7861`) is **attended by design** — four prompts, the last asking a human to confirm
"the transcript visibly contains both speakers." Do not script those answers. The candidate is staged inert, the
canary attach path is proven from the host, and `demo-precheck` returns GO; the launch command is in
`handoff-2XXXXX.md` §1.

## Suggested skills

`/goal` to drive the loop, `/diagnose` and `/prototype` delegated to `MOSS:1.2`, and `claude-in-chrome` or
Playwright for the visual work.
