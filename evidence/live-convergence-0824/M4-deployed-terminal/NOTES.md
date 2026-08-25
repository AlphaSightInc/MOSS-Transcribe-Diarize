# M4 step 3d — the E4 build reaches the deployed service

**2026-08-25, iteration 27, branch `ralph/live-convergence-0824`.**
Candidate 8c-4 of `scripts/ralph-live-convergence/context.md`.

## What this bundle shows in one line

On the **running** service, with a real MOSS decoder, a 60-second meeting kept its whole
audio, ran a terminal pass after its stop request had already answered, and replaced its
published surface with a transcript that is the paired file arm **word for word and
timestamp for timestamp** — 120 words, 20 segments, WER `.096000 → .088000`, identical to
the file arm's `.088000`. Nine gates pass and each one reacts when pushed.

## What changed

1. **The deployment hands file mode's own runner to the terminal pass.** `web_cli.main`
   builds the file-mode `WindowedRunner` once (`server.build_file_mode_runner`, extracted
   unchanged from `create_app`) and gives the same instance to `create_app` and to
   `TerminalTranscriptFinalizer`. Its `transcribe_kwargs` come from
   `jobs.resolve_inference_options` — the one rule a file job resolves through — called with
   no per-request overrides. On this deployment that resolves to
   `prompt=DEFAULT_PROMPT, max_length=16384, max_new_tokens=12000, decoding=greedy,
   temperature=None`.
2. **The deployed manifest declares a complete-tape capacity.**
   `bounds_config.max_tape_bytes = 9 600 000` — 300 s of 16 kHz mono PCM16, Appendix B Q10's
   own premise and the campaign's audio cap. `live_manifest_finalizer` learned the optional
   `--max-tape-bytes` flag and two relations to check it against (below).
3. **The service was restarted onto that build and that manifest.**

## The deploy, recorded

| | |
|---|---|
| stopped | pid 44278 (M2 build), started 2026-08-25 05:52:14 |
| started | pid 65689, 2026-08-25 09:37:10 local, same argv |
| log | `~/.local/share/moss-transcribe-diarize/g3/web_cli-campaign-20260825-093710.log` |
| tree | repo HEAD `29681e0` + iteration 27's working tree |
| 4070 Ti | untouched (read-only infrastructure per PRD) |

`restart-pre.txt` / `restart-post.txt` hold the descriptor either side. **Three fields differ
and no others**, all of them the intended signature of this change:

| field | pre | post |
|---|---|---|
| `bounds.max_tape_bytes` | absent | `9600000` |
| `source_revision` | `cc8f778a…` | `29681e04…` |
| `provider_manifest_hash` | `46895832…` | `07e32598…` |

`config_hashes` is **identical**, `combined_config_hash` included: it is
`f(decoder, endpoint, identity)` and retention is none of the three. Every paired arm this
campaign measured is still the same decode configuration.

`manifest-preview-no-tape.json` is the same tool run **without** the flag: it reproduces the
previously deployed manifest exactly except for `source_revision`, which is how we know the
tape declaration is the only thing this deploy changed.
`manifest-preview-with-tape.json` is what was installed.

## The two relations a tape capacity is checked against

Unlike the matcher thresholds, this is not a free parameter — the tape exists so the terminal
pass has `[0, meeting_end)` of the meeting.

- **A whole number of wire frames.** `9 600 000 / 16 000 = 600`. A capacity that cuts a frame
  in half stops taping mid-frame and degrades every meeting that reaches it at a byte nobody
  chose.
- **At least the rolling ring.** `max_retained_samples × 2 = 1 920 000` bytes. A "complete"
  tape shorter than the ring the session already keeps is strictly worse than keeping nothing
  extra.

Both are refusals, both are in the table `tests/test_live_manifest_finalizer.py` parametrises.
Withdrawing the flag clears a previously declared capacity rather than letting it linger —
retention stays opt-in (ADR-0003 D2/D8).

## The measurement

One warm-decoder pass of `lex_javier_milei` (60 s, fully referenced) through
`remeasure_one_case.py` against the restarted service, then the session's final snapshot and
its post-stop event page fetched directly.

| arm | WER | TBSA | DER | speaker accuracy |
|---|---|---|---|---|
| file | `.088000` | `.881244` | `.151833` | `.848167` |
| rolling (at stop) | `.096000` | `.906296` | `.117333` | `.882667` |
| **terminal (published)** | **`.088000`** | `.881244` | `.151833` | `.848167` |

`terminal == file` is not "within a bound" here — it is the *same 120 words on the same 20
segment boundaries*, which is what injecting file mode's own object was for. The terminal
pass decoded 960 000 samples of tape in `1.918 s`.

The event order the service actually produced, after `POST /stop` had already returned 200:

```
262 session_closed                  accepted_samples=960000
263 terminal_finalization_started   finalization_status=running
264 text_revision_applied           source=terminal  revised_segments=20  v7  status=final
265 terminal_finalization_completed outcome=finalized tape_samples=960000 decode=1.918s
266 session_tape_released
```

## The gates

`verify_deployed_terminal.py --bundle <this dir>` → exit 0, nine gates (`console.txt`,
`gates.json`). `--selftest` pushes each gate past its own bound and requires exactly that gate
to fail → exit 0 (`selftest.txt`). D-M4-9 ("no terminal event carries a word of the meeting")
is derived from *this meeting's* published words — no three-word run of them may appear in any
terminal event payload — rather than from a list of allowed tokens, so a status vocabulary
that overlaps ordinary English cannot trip it and a leaked phrase cannot hide behind one.

## What this bundle is NOT

It is **not** the M4 exit. One case, one pass, and G-M4-1/G-M4-2's per-case convergence bounds
are scored over five cases at the exit (candidate 8d). What it establishes is narrower and was
not previously known: the deployed service, not a harness, runs the pass.

## The finding that blocks 8d

**The campaign's paired driver stops reading before the terminal surface exists.** The replay
client returns as soon as `POST /stop` answers — which is now, by design, *before* the terminal
pass runs. This pass's `live-hypothesis.jsonl` therefore carries the **rolling** surface
(WER `.096000`, 14 segments) and its trace ends at seq 263, with the terminal events 264–266
arriving afterwards. They were recovered here by polling the service directly, which is why
`events-after-stop.json` and `final-snapshot.json` are separate files in this bundle rather
than part of the pass.

Nothing is wrong with the service. The instrument has to learn to wait: the replay client
needs to poll `finalization_status` until it leaves `running` (or `not_started`/`unavailable`,
which are already terminal answers) before it snapshots and writes the hypothesis. Until it
does, every M4 exit number would silently be a rolling number.

## Reproduce

```bash
# the gates, from this bundle (no GPU, no service, zero MOSS requests)
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_deployed_terminal.py \
  --bundle evidence/live-convergence-0824/M4-deployed-terminal
# nine reactions, one per gate
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_deployed_terminal.py \
  --bundle evidence/live-convergence-0824/M4-deployed-terminal --selftest
# the manifest tool, previewing rather than writing
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ops/finalize-live-provider-manifest.py \
  --input  "$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.provisional.json" \
  --output /tmp/preview.json --source-revision "$(git rev-parse HEAD)" \
  --hard-cap-samples 40000 --max-retained-samples 960000 --frame-samples 8000 \
  --min-match-score 0.35 --min-match-margin 0.1 \
  --album-admission-seconds 2.0 --birth-min-seconds 1.0 \
  --max-tape-bytes 9600000 --dry-run
```

## Files

| file | what it is |
|---|---|
| `gates.json`, `console.txt` | the nine gates and their detail |
| `selftest.txt` | one reaction per gate |
| `pass/` | the paired pass, in `verify_m2_exit.case_paths`' five-file layout |
| `final-snapshot.json` | the session after its terminal pass landed |
| `events-after-stop.json` | seq 259–266, the page the replay client never read |
| `restart-{pre,post}.txt` | the descriptor either side of the restart |
| `manifest-preview-{no-tape,with-tape}.json` | the deploy's only difference, isolated |
| `inertness.txt` | the six shared-driver instruments, and the one named exception |
| `file-mode-{head,worktree}.json` | file-mode decoder A/B, `ad381d8b…` unmoved |
| `pytest-{targeted,full}.txt` | 217 targeted, 1141 full (1133 before) |
| `sha256.txt` | digests of every file above |
