# M2 step 3 item 2 — session transcript authority (plan §6 M3, §10.5 step 2, ADR-0005)

Recorded by the autonomous campaign loop, run `20260825-042645-70858`, iteration 12.

## What shipped

One seam on `LiveSession`, and the four fields that make it visible.

| Thing | Where |
|---|---|
| `LiveSession.apply_text_revision(proposal) -> TextRevisionOutcome` | `app/live_session.py` |
| the seven validations, all in the session | `_text_revision_refusal` |
| the label projection | `_project_canonical_speaker` + `_base_segments` |
| the effective surface (revised prefix + provisional base suffix) | `_build_effective_transcript` |
| `text_revision_version` / `canonical_through_sample` / `effective_transcript[]` / `finalization_status` | `LiveSnapshot` |
| reconstruction of all four, plus `EffectiveTranscriptSegment` | `live_service_replay.py` |
| 17 T1 tests | `tests/test_live_text_revision.py` |
| the extended round-trip tripwire | `tests/test_live_service_replay.py` |

`CanonicalCommit.transcript`, its prefix chain and `revised_transcript` are untouched (ADR-0005
D2/D3): a word revision is published beside the base, never into it.

## The measured claim

The §10.2 grid scored every arm through `proto_context_arms.SpeakerTimeline` — an **external**
relabelling step. It presumed the session would attribute rolling words from the base's own
labels. `verify_session_text_authority.py` drives the real objects end to end and requires that
presumption to be true of the production code:

```
baseline spans -> LiveSession (real freeze/submit path)
  -> RollingTranscriptConverger (production, grid-selected 10/10)
    -> LiveSession.apply_text_revision (production, seven validations)
      -> snapshot().effective_transcript -> the grid's own scorer
```

```
lex_bill_ackman    wer=0.198864 (grid 0.198864) recall=0.926136 rolling=21 base=0 frontiers=20/30 revisions=6 projection_disagreements=0
lex_javier_milei   wer=0.096000 (grid 0.096000) recall=0.920000 rolling=14 base=0 frontiers=26/38 revisions=6 projection_disagreements=0
lex_keyu_jin       wer=0.100719 (grid 0.100719) recall=0.985612 rolling=16 base=0 frontiers=20/30 revisions=6 projection_disagreements=0
TRIO               wer=0.131861 (grid 0.131861) recall=0.943916 (grid 0.943916)
18 requests, 0 fresh (no GPU)
```

Six gates, all pass:

- **G1** per-case WER equals the grid's `10/10` column to 6 dp; trio means equal `.131861` /
  `.943916` — the selected arm survives the trip through the real session.
- **G2** the session's projection agrees with the measured `SpeakerTimeline` on **51 of 51**
  rolling segments. Zero disagreements. The arm's speaker surface is reproduced, not assumed.
- **G3** one owner per interval, sampled after **every** commit and every revision (98 surfaces,
  66 of them with a rolling prefix beside a provisional suffix): ordered, non-overlapping, no
  base segment inside the revised prefix.
- **G4** every base commit is byte-identical to the baseline span it replays, `revised_transcript`
  stays `None`, and `label_revision_version` never moves (D2/D3).
- **G5** 6 of 6 windows applied per case, `text_revision_version` == revisions applied, zero
  refusals.
- **G6** zero fresh MOSS requests — the decoder is handed a runner that raises, so a cache miss
  is a failure rather than a GPU call.

## Design decisions, and what each cost

- **The projection is computed, not stored.** A revision keeps the words; the speaker is
  recomputed from the base timeline every time the surface is built. That is what makes a later
  `revise_labels` flow into the rolling prefix for free (T1 test
  `test_a_later_label_revision_reprojects_the_rolling_surface`) instead of leaving a stale
  identity frozen into a revision. Cost: a rebuild per surface change, bounded by
  `_surface_version` so a polling portal does not pay for it.
- **The projection is a fallback, not the last word.** A producer that sets
  `canonical_speaker` itself keeps it. E3's witness-owned speaker evidence (plan D5) therefore
  needs no change here — it fills the field and the session leaves it alone.
- **Unattributed (`S00`) is a real candidate in the vote.** The base publishes it honestly
  wherever identity abstained; a projection that suppressed it would invent attribution the
  meeting never had.
- **Ownership at the frontier is keyed on where a segment begins.** A base segment straddling
  the frontier belongs to the revision that already owns its first sample, so nothing is
  published twice (D4). Its tail is not lost: the next rolling window starts at that frontier
  and decodes the audio again.
- **Terminal is exempt from the frontier rule, not from validation.** It *replaces* the surface,
  so it must own all of it from sample 0, and it may do so once (`already_finalized`).
- **A closed session still accepts a revision**, for `revise_labels`' reason: the terminal pass
  runs after the last span by construction.

## Mutations — five, in the production file, each caught

| # | Mutation | Caught by |
|---|---|---|
| M1 | the label projection never runs | G2 (49 of 51 segments disagree) + 7 T1 tests |
| M2 | projection by proximity instead of ownership | G2 (2 of 51) + 3 T1 tests |
| M3 | two owners at the frontier (`end_sample > frontier`) | G3 (24 straddles / 19 out-of-order surfaces, on milei) + T1 |
| M4 | rolling replaces instead of extends | G1 (trio WER .131861 → .851088) + T1 |
| M5 | the text revision version never advances | G5 (6 applied, version 0) + 2 T1 tests |

Control clean before and after; `live_session.py` restored by trap. Zero MOSS requests.

M3 is worth reading twice: it is invisible at the **end** of a case, because six 10-second
windows tile the whole minute and no base suffix survives. It is caught only because the
verifier samples the surface after every commit — and even then only `lex_javier_milei` has a
base segment straddling a 10-second frontier. The corpus exercises the boundary on 1 of 3 cases;
the T1 test covers it unconditionally.

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_session_text_authority.py
.venv/bin/python -m pytest tests/test_live_text_revision.py tests/test_live_service_replay.py -q
prototypes/streaming-diarization/live-convergence/mutate_session_authority.sh /tmp/authority-mutations
```

No GPU is required for any of it.

## Other checks

- Full suite: **1050 passed, 2 skipped, 386 subtests** (1033 before this change) —
  `pytest-full.txt`.
- File-mode decoder A/B against a HEAD worktree: byte-identical,
  sha256 `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` — the same digest
  iterations 7 and 11 recorded, so file mode has not moved across three production changes
  (`file-mode-head.json`, `file-mode-worktree.json`).
- No service restart: the seam has no caller in the runtime yet (§10.5 steps 3-7), so nothing
  the running `web_cli` executes changed.

## What this does NOT do

- No arbiter admission (`submit_live_refinement`), no runtime wiring, no §7.4 events, no portal
  rendering, no export switch. Those are §10.5 steps 3-7, in that order, each its own change.
- `finalization_status` only ever reaches `final`, via a terminal proposal. The `running` /
  `failed` / `unavailable` lifecycle is E4's (plan §12.3) and has no producer yet.
