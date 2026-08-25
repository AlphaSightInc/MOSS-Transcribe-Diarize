# M2 step 3 item 7 — the export switch (plan §10.5 step 7, §14 T3)

**Verdict: the export carries the surface the reader was shown, and nothing else moved.**
Six preregistered gates pass on real trio audio with zero MOSS requests; six mutations in
production code are all caught; the file-mode decoder is byte-identical to HEAD.

## What shipped

| File | Change |
| --- | --- |
| `moss_transcribe_diarize/live_surface.py` | NEW leaf module: `UNATTRIBUTED_SPEAKER`, `display_speaker_label` (moved), `published_speaker_label` (new, total) |
| `moss_transcribe_diarize/app/live_session.py` | re-exports those three; no other change |
| `moss_transcribe_diarize/live_speaker_accuracy.py` | `hypothesis_from_live_snapshot` reads `effective_transcript` when the snapshot carries one; the committed reading survives verbatim as the pre-surface fallback |
| `moss_transcribe_diarize/live_replay.py` | `evaluator.jsonl` schema 2: written from the surface, carrying sample integers instead of `span_id` |
| `tests/test_live_export_surface.py` | NEW, 9 T3 tests incl. the export-equals-screen binding on a real runtime + the served portal page |

The switch is one branch: **a snapshot that carries `effective_transcript` is exported from it,
and from nothing else.** A snapshot from before §7.3 existed has no such field and is exported
exactly as it always was. G1 and G5 below are what make "exactly as it always was" a measurement
rather than a claim.

## Gates (`verify_export_surface.py`, exit 0)

| Gate | Claim | Result |
| --- | --- | --- |
| G1 | the switch does not move a session nobody revised | base arm: export == committed reading, word for word, speaker for speaker, every timestamp inside one sample; WER/recall equal to 6 dp |
| G2 | the base arm still reproduces the published live trio **through the export** | `.199870` / `.913490`, per case to 6 dp |
| G3 | the rolling arm reproduces the §10.4 selected arm through the export | `.131861` / `.943916`, per case to 6 dp |
| G4 | export text equals visible effective text (§14 T3) | 3 cases × 2 arms: exported sequence == the portal DOM, same speaker, words and seconds |
| G5 | the fallback is byte-identical on real pre-surface artifacts | 5 of 5 checked-in `live-hypothesis.jsonl` reproduced byte for byte from their own traces |
| G6 | zero fresh MOSS requests | 178 replayed decodes, 0 fresh |

```
lex_bill_ackman    base    export_segments=30  dom=30  wer=0.261364 recall=0.863636
lex_bill_ackman    rolling export_segments=21  dom=21  wer=0.198864 recall=0.926136
lex_javier_milei   base    export_segments=28  dom=28  wer=0.144000 recall=0.920000
lex_javier_milei   rolling export_segments=14  dom=14  wer=0.096000 recall=0.920000
lex_keyu_jin       base    export_segments=26  dom=26  wer=0.194245 recall=0.956835
lex_keyu_jin       rolling export_segments=16  dom=16  wer=0.100719 recall=0.985612
TRIO base          wer=0.199870 (grid 0.199870) recall=0.913490 (grid 0.913490)
TRIO rolling       wer=0.131861 (grid 0.131861) recall=0.943916 (grid 0.943916)
```

## Design decisions, and what each cost

**D1 — the export prefers the surface whenever the field is present, not when a revision
happened.** The alternative ("switch only once `text_revision_version > 0`") keeps two live
readings of a current snapshot, and the one a session gets would depend on whether its witness
had landed yet. G1 is what makes one reading safe: on the base arm the two readings agree word
for word on real audio, so preferring the surface costs nothing and removes a branch a reader
would otherwise have to reason about. Cost: sample-derived seconds replace parsed seconds, which
moves a timestamp by up to one sample (`6.25e-5` s); the gate states that slack instead of hiding
it, and the scores are unchanged to 6 dp.

**D2 — the display rule moved to a leaf module rather than being imported from `app`.** The first
attempt imported `published_speaker_label` from `app.live_session` into the scorer, and the T3
tier caught it in one run: `scripts/ralph-afk/live-canary-clauses.py` loads
`live_speaker_accuracy.py` straight out of a bare checkout, with `-S` and no installed package,
so an `app` import breaks the F-certification reducer. `live_surface.py` is a sibling the scorer
can import, `app.live_session` re-exports it, and every existing caller is untouched. Cost: one
more module; the alternative was a second Python spelling of a rule the portal already spells
twice (Python and JS).

**D3 — the replay evaluator becomes schema 2 and drops `span_id`.** A revision that spans several
base spans has no span id to report, so the row carries the sample integers it is actually defined
by (plan §7.1). Cost: an artifact field disappears; nothing in the repo reads it, and what
replaces it is the coordinate the surface is written in.

## Mutations (6, in production files, restored by a trap on exit)

| # | Mutation | Caught by |
| --- | --- | --- |
| M1 | export the committed spans even when a surface exists (the pre-step-7 export) | verifier G3/G4 + T3 |
| M2 | export the canonical identity, not the `Sxx` token | verifier G1/G4 + T3 |
| M3 | an unestablished identity is exported as the first speaker | **T3 only** |
| M4 | the export no longer clamps to the corpus window | **T3 only** |
| M5 | the fallback ignores a sweep's correction | **T3 only** |
| M6 | whitespace-only surface segments become rows | **T3 only** |

Four of six are caught by the test tier alone, each for a stated reason: the trio corpora
establish every identity their surfaces carry, their sessions end inside their own corpus window,
no checked-in baseline contains a relabelled span (0 of 5 bundles, 0 of 235 commits), and the
deployed session drops empty segments before they reach the surface. Sixth iteration of the same
lesson (11–17): the corpus reading is necessary and not sufficient.

## Standing gates

- File-mode decoder A/B against a HEAD worktree: identical, sha256
  `ad381d8bd247e4a8ebe56240dfbc29c0b5a86ffb35a2fcb411c07bbd5b7707f2` — unmoved since iteration 7.
- `pytest tests/ -q`: 1091 passed, 2 skipped, 392 subtests (1082 / 386 before).

## Reproduce

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_export_surface.py
prototypes/streaming-diarization/live-convergence/mutate_export_surface.sh /tmp/export-mutations
.venv/bin/python -m pytest tests/test_live_export_surface.py -q
```

## What this does NOT close

E2's exit gates are measured **through the deployed service**, and the service still runs the M1
build. §10.5 is now complete, so the next step is the one the order was protecting: restart
`web_cli` onto this build, run `run_paired_passes.sh`, and read the M2 gates (rolling WER,
content recall, correction p95, RTF, exact accounting) off a real paired rerun — then the §10.6
5-minute soak.
