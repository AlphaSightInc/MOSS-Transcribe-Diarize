# M4 step 3b — the terminal finalizer (plan §6 M6, §12.3 steps 4-6)

Campaign iteration 25, 2026-08-25. Production code shipped; **the deployed service is not on it**
(no restart this iteration — the deployed manifest still declares no `max_tape_bytes`, and the
lifecycle that runs this pass is step 3c).

## What shipped

`TerminalTranscriptFinalizer` in `moss_transcribe_diarize/app/live_transcript_convergence.py` —
the meeting's second longer listener, beside the rolling one. It reads `[0, meeting_end)` through
the tape seam, hands it to **file mode's own `WindowedRunner`** (injected, not constructed, so
"terminal == file on identical bytes" is an identity rather than two configurations that have to
keep agreeing), places the words on the session clock, names the decoder's local speakers on the
meeting's album, and returns **one** `TextRevisionProposal` over `[0, meeting_end)`. It publishes
nothing: `LiveSession.apply_text_revision` decides, and its `already_finalized` rule is what makes
the replacement happen exactly once.

Three failures, all named, none raising (plan §5.2): `tape_unavailable` (the audio to converge on
was not retained → `finalization_status=unavailable`), `decode_failed`, and `no_transcript` (→
`failed`). All three keep the rolling surface, because capture already succeeded.

## The question this bundle answers

Handed the paired file arm's **own decode**, does the adapter publish the paired file arm's **own
surface**? If yes, any terminal delta measured later is a statement about the decoder (M4 R3) and
never about this code.

## Verdict — nine gates, all pass

| case | terminal WER | file | rolling | terminal DER | file | Δ all five axes | surface `S00` |
|---|---|---|---|---|---|---|---|
| lex_bill_ackman | `.159091` | `.159091` | `.198864` | `.075500` | `.075500` | `0.000000` | 0 |
| lex_javier_milei | `.088000` | `.088000` | `.096000` | `.151833` | `.151833` | `0.000000` | 0 |
| lex_keyu_jin | `.064748` | `.064748` | `.100719` | `.079000` | `.079000` | `0.000000` | 0 |

The five axes are WER, DER, coverage, text-speaker accuracy and content recall, all through one
scorer for both arms. The published segments are the file arm's segments bound for bound, and its
speaker partition renamed one-to-one. Each pass planned **1** window over 60 s at 150/120, which is
prediction P6's trio row.

These are not `G-M4-1` and `G-M4-2`: those are scored on a fresh deployed pass with a real decoder
at the M4 exit. This is the same arithmetic with the decoder held fixed, which is the only way to
tell the two failure modes apart later.

## Verdict — the speaker-naming policy, decided by measurement (ADR-0005 D8)

Plan §12.3 step 5 says "resolve terminal speaker identities using owned speech evidence" and does
not say how. Both candidate rules were run over the same meetings, with the selection rule fixed
in `verify_terminal_finalizer.py`'s docstring **before** the run and deliberately biased toward
needing no new rule at all ("if both qualify, ship `projected`"):

| arm | who names a segment | Δ DER vs file | Δ text-speaker accuracy | surface `S00` |
|---|---|---|---|---|
| `projected` | the session's existing per-segment projection | `+.383834` … `+.572000` | `-.409090` … `-.628868` | 21 of 48 |
| `mapped` | one-to-one **per speaker**, by overlap with the published surface | `0.000000` × 3 | `0.000000` × 3 | 0 |

Both arms publish byte-identical words; the whole difference is naming. The per-segment projection
is right for a rolling window and structurally wrong for a terminal pass, which heard the whole
meeting and whose local labels are therefore a *partition of it*. Nothing is embedded, so
ADR-0005 D5's prohibition is satisfied vacuously.

Incidental finding worth carrying forward: on these 60-second two-speaker clips the live album had
birthed up to **16** canonical speakers. That is the microfragment population plan §11.4 names and
candidate 7d already records; it is why the projected arm scatters as far as it does.

## Files

| file | what it is |
|---|---|
| `verify.json` | the full run: both arms, three cases, per-case scores, deltas, accounting, partition tables, the selection |
| `console.txt` | the same run's console, including the selection summary and the decode cost |
| `pytest-terminal.txt` | `tests/test_live_terminal_finalizer.py` — 17 passed, 4 subtests |
| `pytest-full.txt` | `tests/` — 1121 passed, 2 skipped, 396 subtests (1104 before this change) |
| `mutations.txt`, `mutations/` | six mutations, each caught; control PASS before and after |
| `inertness.txt`, `inertness-*.txt` | the shared driver's new `terminal=` parameter changes nothing in the two checked-in instruments that already use it |
| `file-mode-{head,worktree}.json` | file-mode decoder A/B against a HEAD worktree |
| `sha256.txt` | digests of everything above |

## Reproduction

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_terminal_finalizer.py \
  --output /tmp/m4-terminal-finalizer.json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/test_live_terminal_finalizer.py -q
prototypes/streaming-diarization/live-convergence/mutate_terminal_finalizer.sh /tmp/mut-terminal
```

## Cost

Zero MOSS requests. 196 base decodes and 12 terminal decodes, all replayed from recorded answers
(`base_fresh_requests: 0`, `terminal_fresh_requests: 0`). No GPU, no service, no 4070 Ti contact.

## What is still open for M4

- **3c** — the async `finalization_status` lifecycle, the three §7.4 `terminal_finalization_*`
  events, the release moving to after terminal evidence is written, and the deployed manifest's
  `max_tape_bytes` declaration plus a service restart.
- **The M4 exit (8d)** — the 14 preregistered gates on a fresh paired pass of all five cases.
