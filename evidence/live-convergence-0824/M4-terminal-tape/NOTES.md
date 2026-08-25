# M4 step 3a — the complete mixed tape: P-M4-B is closed

Campaign iteration 24, 2026-08-25. Plan E4 step 1 of §12.3, and the precondition
`PREREGISTRATION-M4.md` §3 named **P-M4-B**: *no session retains a complete tape today*. Until
this change a terminal 150/120 pass had nothing to run over, so M4 could not start. It can now.

| file | what it is |
|---|---|
| `verify.json` / `console.txt` | `verify_terminal_tape.py` exit 0 — nine gates on the real runtime over the trio, GPU-free |
| `pytest-tape.txt` | the 13 new T1/T2 tests |
| `pytest-full.txt` | the suite: 1104 passed, 2 skipped, 392 subtests (1091 before) |
| `mutations/` | six mutations of the shipped modules, each caught; control clean before and after |
| `file-mode-{head,worktree}.json` | the file-mode decoder A/B against a HEAD worktree |
| `sha256.txt` | digests of everything above; `shasum -a 256 -c` from the repo root verifies the bundle |

## 1. What shipped

`CompleteMixedTape` in `moss_transcribe_diarize/app/live_tape.py` — one meeting's whole mixed
track, on the session sample clock, in one in-memory buffer under a capacity the deployment
declares. The coordinator holds it beside the two retentions it already had; the runtime declares
the capacity through the new `LiveServiceBounds.max_tape_bytes` (read from `bounds_config`), and
releases the tape at `session_closed` and at any terminal failure, recording one
`session_tape_released` event carrying the accounting. The decision record is the
**2026-08-25 addendum to ADR-0003 (D8)**, which is where ADR-0005 deferred it.

The seam is one sentence: *give me `[0, meeting_end)` of mixed PCM*. Nothing else is exposed.

## 2. The numbers

Nine gates, trio, deployed endpoint configuration, real `webrtcvad`, real arbiter, replayed
decodes, **zero fresh MOSS requests** (294 replays):

| case | tape samples | peak bytes | gaps | differing samples vs corpus | bytes after release |
|---|---:|---:|---:|---:|---:|
| lex_bill_ackman | 960 000 | 1 920 000 | 0 | **0** | 0 |
| lex_javier_milei | 960 000 | 1 920 000 | 0 | **0** | 0 |
| lex_keyu_jin | 960 000 | 1 920 000 | 0 | **0** | 0 |

The tape's streaming digest equals the digest of the corpus PCM on every case, and reading it back
before release returns bytes that differ from the corpus in **zero** samples at **zero** maximum
absolute delta. Peak retained bytes are `accepted_samples x 2` exactly — one buffer, no second copy
— which is prediction **P5**'s claim, and the capacity table read from `LIVE_SAMPLE_RATE` and
`PCM16_BYTES_PER_SAMPLE` reproduces P5's other half: **1 920 000 / 5 760 000 / 9 600 000** bytes at
60 / 180 / 300 s.

File mode byte-identical: `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2`,
unmoved since iteration 7 and now across nine production changes.

## 3. Three findings

**F1 — the tape is inert on quality, and that is gated rather than hoped.** Every case is run twice
through the same runtime, once with a declared capacity and once without, and the two arms agree on
scores, frozen spans, committed transcripts, committed-prefix hash, effective surface, revision
version, accounting and rolling status. One rolling field is *reported* rather than compared:
`retained_high_water_samples` is how much audio the witness's ring happened to hold when the pump
thread last looked, and the no-tape arm is run **twice** so a reader can see two identical
configurations already disagreeing about it (measured across repeats: 208000 vs 168000 on
`lex_bill_ackman`, 240000 vs 232000 on `lex_javier_milei`). What is gated for that field is its
bound.

**F2 — a hole is refused, never zero-filled, and that is the whole reason the gap manifest exists.**
Audio is admitted only at the tape's own next sample. A frame claiming a later sample would leave a
hole, and a hole in a PCM buffer reads as *silence*: a terminal pass would decode audio the meeting
never contained, and the sample counts would still add up. So a non-contiguous frame degrades the
tape by name (`tape_frame_not_admissible`, with the expected and received sample), the gap manifest
reports the interval, and a reader asking for `[0, meeting_end)` is refused rather than served
fabricated quiet. Mutation M5 zero-fills instead and is caught by the T1 test alone — sixty seconds
of contiguous corpus audio cannot reach that branch.

**F3 — four of six mutations are caught by the tests alone, and each has a stated reason.** The
trio corpus cannot exhaust a capacity bound (M3, M6), cannot produce a hole (M5), and cannot
distinguish a tape that grades its own extent from one graded against `accepted_samples` (M2)
because on a healthy meeting the two numbers are equal. The two the corpus *does* catch are the two
that change what a complete meeting looks like: a dropped frame (M1) and a tape that outlives the
session (M4). This is the seventh iteration of the same lesson the E2 steps recorded — the corpus
reading is necessary and not sufficient.

## 4. The decision, and what it costs

**D-M4-1 is now implemented as ADR-0003 D8**: memory, deployment-declared capacity, D2/D3/D5
inherited unchanged. Two consequences a reader should carry forward:

1. **The deployed service still declares no capacity**, so it still retains no tape and terminal
   convergence would report itself unavailable there. Declaring `bounds_config.max_tape_bytes` in
   `~/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json` (and recomputing its
   `bounds_config_hash` / `component_config_hash`; `combined_config_hash` is unaffected, being
   `f(decoder, endpoint, identity)`) plus a service restart is a step E4 owes before its exit
   measurement, not this one.
2. **A capacity a meeting outgrows costs the terminal pass and nothing else.** Measured: a meeting
   whose tape stopped after one frame published exactly the transcript it published with a tape
   four times the size, with exact accepted/accounted equality and no terminal failure.

## 5. Reproduction

```bash
# nine gates on the real runtime over the trio; no GPU, zero MOSS requests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_terminal_tape.py \
  --output /tmp/terminal-tape.json

# the shipped properties, in isolation and through the runtime
.venv/bin/python -m pytest tests/test_live_terminal_tape.py -q

# every property is load-bearing (restores the production files on exit, including on failure)
prototypes/streaming-diarization/live-convergence/mutate_terminal_tape.sh /tmp/tape-mutations
```
