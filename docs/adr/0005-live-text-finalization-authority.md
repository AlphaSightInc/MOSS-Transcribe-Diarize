# ADR-0005: Text-finalization authority for live mode — rolling and terminal word revision

- **Status:** **Accepted** (2026-08-25). Accepted in advance by the product owner on 2026-08-24
  night as Appendix B Q8 of `docs/plans/live-mode-convergence-implementation-20260824.md`:
  *"The text-finalization ADR is accepted now. The campaign's first E2 step writes `docs/adr/`
  content from D1–D7 verbatim; no further approval needed."* This record is that step. It writes
  down a decision already made; it does not ask for one.
- **Deciders:** product owner (Gao), 2026-08-24 (Appendix B). Plan drafted and independently
  cross-reviewed by Claude then Codex, 2026-08-24 (plan §3.5). Written by the autonomous campaign
  loop (`scripts/ralph-live-convergence`, run `20260825-042645-70858`, iteration 9) under the
  Appendix B §18 conditional pre-authorization of every phase.
- **Required by:** D7 below. ADR-0002 states that its identity sweeps never re-run ASR. Live text
  convergence re-runs ASR over the same audio. D7 refuses to let that ride on the identity record
  and demands its own; this is the first step of plan phase E2 for exactly that reason.
- **Relation to other records:** extends, supersedes nothing. ADR-0002 (two-tier diarization) and
  ADR-0003 (session audio retention) keep every clause they have. ADR-0001's live v2 HTTP contract
  gains the fields in §7.3/§7.4 of the plan; no existing field changes meaning.

## Context

### What is broken, measured

Live mode transcribes each VAD-frozen span — at most 2.5 seconds — as its own MOSS request, then
publishes it. File mode hands MOSS 150-second windows. Same audio, same model, same greedy
decoding; the only difference is how much the model hears at once. On the three fully-referenced
60-second interviews that are this campaign's primary corpus, that difference costs roughly double
the word error (plan §3.1; sources under `prototypes/live-file-gap-*/NOTES.md`):

| Measurement | Value | What it says |
|---|---:|---|
| File WER vs live WER | `.1039` vs `.1999` | live roughly doubles word error |
| Live WER inside a span vs file | `.082` vs `.072` | a span is near file quality *inside itself* |
| Live WER within 0.25 s of a cut | `.483` | the loss is concentrated at the seams |
| Bigram survival across a cut vs interior | `48.5%` vs `89.4%` | cuts destroy lexical continuity |
| Rolling 10 s window / 5 s stride re-decode | `.129` and `.146` | a longer listener recovers most of the gap |
| Per-seam 5-second re-decode | `.218–.230` | repairing only the cut is worse than nothing |
| Terminal full-minute decode | `.104` | file-equivalent, i.e. the gap is closable |

Read together these say one thing: **the words are not lost in the audio, they are lost at the
cut**, and a second listener with more context gets them back. But the only way a second listener
can help is by publishing *different words* than the short span already published.

### Why that needs a decision record at all

Replacing published words is precisely what ADR-0002 ruled out, deliberately. Its shipped L1 sweep
rematches the retained embedding ledger and revises speaker labels; it never re-reads tape audio,
never re-runs VAD, never re-embeds PCM, and never re-runs ASR. Its future L2 sweep may re-hear
audio for diarization evidence and must still never re-run ASR. Both are about *who spoke*.
Neither is about *what was said*.

That line is load-bearing rather than bureaucratic. A label revision is a claim about attribution:
cheap, reversible, and checkable against the same words. A word revision changes the artifact the
user reads. If word rewrites could arrive through the identity sweep, no reader could tell whether
a transcript changed because the system heard better or because it was quietly editing itself, and
no reviewer could bound what a sweep is allowed to do. D7 therefore requires a separate record with
its own producers, validation, failure semantics, and telemetry. This is that record.

### Campaign state at acceptance

The two phases before E2 are measured and their evidence is checked in under
`evidence/live-convergence-0824/`. Neither re-decodes audio, which is why neither needed this
record:

- **E0 (measurement integrity)** — replay reconstruction repaired, typed decode disposition
  shipped, evaluator v2 prototyped and self-tested, paired baseline re-acquired. Four of five
  gates pass; the fresh-vs-fresh live-hash gate is unsigned because the deployed decoder is not a
  function after an idle gap (12 identical greedy requests gave 2 distinct outputs cold, 1 warm),
  and the GPU host is read-only by campaign constraint.
- **E1 (bounded salvage)** — `classify_live_transcript` repairs a decode the grammar rejected, on
  a hard-cap span only. It republishes an answer the model already gave; it never asks for a new
  one. Five of six exit gates pass; the trio-WER gate misses by `.0023` on a decode flip that
  predates the change and is attributed to a named span.

E2 is the first phase that decodes the same audio twice. Hence this record, before its code.

## Decision

D1–D7 of the plan, verbatim (Appendix B Q8). The text between this line and the next heading is a
byte-for-byte copy of `docs/plans/live-mode-convergence-implementation-20260824.md` §4 D1–D7,
mechanically verified — see [Verification](#verification).

### D1 — Three transcript authorities

**Decision:** provisional short-span output, monotonic rolling canonical prefix, terminal final
surface.

**Reason:** one authority cannot simultaneously minimize first-word delay and maximize context.

### D2 — Preserve immutable base commits

`CanonicalCommit.transcript` and its existing prefix chain remain the immutable record of what the
short path originally published. Rolling word correction does not overwrite that field.

**Reason:** audit history, label correction, replay, and current accounting depend on immutable
base commits.

### D3 — Separate word revisions from label revisions

Add `text_revision_version`; retain `label_revision_version`. Do not overload
`CanonicalCommit.revised_transcript`, whose current invariant is “same words, revised labels.”

**Reason:** a word replacement and a speaker relabel have different validation, evidence, and
failure modes.

### D4 — Monotonic rolling prefix, not arbitrary patches

Rolling convergence owns `[0, canonical_through_sample)`. Each accepted revision starts exactly at
the previous frontier and moves it forward. The unrevised short-span suffix remains provisional.

**Reason:** one owner per interval prevents duplicated text, holes, out-of-order corrections, and
oscillating overlaps.

### D5 — Longer witness owns its speaker evidence

The witness's local MOSS speaker segments select their own PCM intervals. WeSpeaker embeds those
owned intervals and maps them to the meeting album. It must never embed the complete mixed-speaker
window or leading context.

**Reason:** prior controlled evidence shows context audio can contaminate speaker embeddings and
collapse voices.

### D6 — Keep 2.5 seconds until rolling text ships green

Do not change the production hard cap in E0–E2. First land rolling correction on the current base.
Only E3 may promote one-second output, and only as provisional.

**Reason:** this separates two risks and preserves a stable speaker anchor while rolling text is
proved.

### D7 — Terminal re-ASR requires a new decision record

ADR-0002's shipped L1 and proposed L2 explicitly never re-run ASR. Rolling and terminal word
correction must be governed by a new ADR or an explicit amendment defining text-finalization
authority. They must not be smuggled into “identity sweep.”

### What "text-finalization authority" means, stated once

D7 requires this record to *define* text-finalization authority, not merely to permit it. The
definition is five sentences, each already fixed by the plan's module and data contracts (§6, §7):

1. **Who may replace published words.** Exactly two producers: the rolling converger over
   `[0, canonical_through_sample)`, and the terminal finalizer, once per session. Nothing else —
   not the ADR-0002 identity sweep, not the portal, not export, not a decoder retry — may change
   transcript text.
2. **Through what seam.** One method: `LiveSession.apply_text_revision(proposal) ->
   TextRevisionOutcome`. A proposal is inert data (epoch, base text-revision version, source,
   owned sample interval, segments); the session validates it and either applies it or refuses it
   with a stable reason. There is no second path, and callers do not re-implement the rules.
3. **Against what validation.** Same session epoch; starts exactly at the current rolling frontier;
   ends after its start and no later than committed audio; absolute segment samples inside the
   owned interval; segments ordered and non-overlapping; base text-revision version current;
   terminal finalization replaces the full rolling surface at most once. Seven checks, all in the
   session, none optional.
4. **Visible how.** `text_revision_version`, `canonical_through_sample`, `effective_transcript[]`,
   and `finalization_status` on the snapshot; `rolling_decode_queued`/`_completed`,
   `text_revision_applied`/`_refused`, and the three `terminal_finalization_*` events carry counts
   and timing but never transcript text. A refusal is counted by reason. Nothing is rewritten
   silently.
5. **Reversible how.** `CanonicalCommit.transcript` and its prefix chain are untouched (D2), so
   every revision is a diff against a preserved original, and replay can always reconstruct what
   the short path actually said.

Two producers, one seam, seven validations, four snapshot fields, seven events, zero silent
rewrites. That is the authority.

### Overrides applied to the verbatim text

Appendix B of the plan wins over the plan body wherever they conflict, so one clause of the
verbatim text above is superseded and is recorded here rather than edited there:

- **D6, last sentence** ("Only E3 may promote one-second output, and only as provisional") —
  Appendix B Q6 **deletes the one-second preview from scope entirely**. The hard cap stays at
  2.5 seconds and remains a named parameter (`hard_cap_samples`, flowing from the bounds config and
  the descriptor). Moving to 1.0 s becomes a new calibration campaign that re-runs the E3 gates,
  not a configuration flip. D6's operative half — do not move the cap while rolling text is being
  proved — stands, and is now unconditional rather than "until E3".

Nothing else in D1–D7 is overridden. D1–D5 and D7 apply exactly as written.

## Consequences

- **The transcript becomes a living document in a second dimension.** ADR-0002 already made
  speaker labels versioned and rewritable; this makes words versioned and rewritable. Consumers
  must render `effective_transcript` as one replacement surface, not as an append-only log.
- **Two authorities publish over the same audio, so each interval needs exactly one owner.** D4's
  monotonic frontier is the entire mechanism preventing duplicated text, holes, out-of-order
  corrections, and oscillating overlaps. Its price, accepted here: a revision that arrives for
  audio behind the frontier is refused, not merged. Late evidence for old audio is the terminal
  pass's job, not the rolling pass's.
- **Exports keep reading base commits until terminal/effective export tests pass**, then switch
  once, in the same reviewed change (plan §10.5 step 7). Until that change the portal and an export
  of the same session can legitimately show different text. That window is expected, bounded, and
  ends at the switch.
- **GPU cost rises by design.** A second decode of the same audio at the window/stride the E2 grid
  selects, bounded to at most `2 × W` seconds of rolling PCM held per session and one
  queued-or-running rolling witness per session. Whether that fits real time is not assumed: the
  rescoped G7 (one live session, combined inference RTF `< 1`, bounded queues, no dropped canonical
  commits) is where it is proved, and unresolved short canonical work outranks rolling refinement
  in the arbiter.
- **Speaker evidence stays segregated (D5).** The rolling witness embeds only its own timestamped
  speaker intervals, never the mixed window or its leading context. E1 already enforces the same
  rule where salvage hands intervals to identity; this extends it to the witness.
- **Replay reconstruction is the one place a new field can be lost silently.** Server-side JSON
  comes from `dataclasses.asdict`, so added dataclass fields serialize themselves, but
  `live_service_replay.py`'s reconstructors are hand-written — the defect E0 repaired. Every field
  added under this ADR extends the round-trip regression test in `tests/test_live_service_replay.py`
  in the same change.
- **Failure is a status, not an exception.** A failed terminal pass leaves `finalization_status =
  failed` and preserves and exports the rolling surface with explicit non-final status; it never
  discards it and never presents it as final.

## What this record does not authorize

- **Re-running ASR inside an identity sweep.** ADR-0002's L1 and L2 keep their "never re-run ASR"
  clause intact. Text authority is a different module with a different seam, and the two must stay
  separable in code as well as prose: an identity sweep that could edit words would erase the
  distinction D7 exists to protect.
- **Redefining `revised_transcript`.** It stays label-only — invariant "same words, revised labels"
  — until reviewers approve replacing the old surface entirely. Word revisions ride
  `text_revision_version`, never that field (D3).
- **Moving the 2.5-second hard cap** (D6, plus Appendix B Q6 above).
- **Promoting evaluator v2 to sole promotion authority.** D8 keeps it running beside current
  evaluation until reviewers accept a migration; existing baseline reports stay reproducible.
- **Extra VAD or embedding phases.** D9 allows them only for uncertainty-routed disagreement
  regions and only after a prototype shows benefit; Appendix B puts that outside this campaign.
- **Terminal tape retention policy.** The owner decided it separately (Appendix B Q10: retain the
  complete mixed session tape for the session's lifetime, delete it after terminal finalization
  evidence is written; ≤ ~10 MB PCM at the ≤5-minute session cap, so no TTL framework is
  warranted). That refines ADR-0003 and belongs in ADR-0003, recorded by the E4 step that
  implements it — not folded in here.
- **Shipping whatever E2 builds.** Authority to build is not authority to promote. If no grid arm
  passes the preregistered gates, no rolling production code is implemented (plan §10.4), and this
  record still stands as the decision that governed the attempt.

## Alternatives considered

- **Amend ADR-0002 instead of writing a new record** — rejected by D7 itself. The amendment would
  have to sit inside the record whose defining constraint is "no re-ASR", where every future reader
  of the sweep design would have to re-derive which half applied to them.
- **Let any interval be corrected whenever better evidence arrives** (patch-anywhere) — rejected as
  D4. Without a single owner per interval, two witnesses over overlapping audio produce duplicated
  text, holes, and corrections that oscillate as each new window disagrees with the last. A
  monotonic frontier makes "who owns this second of audio" answerable at every instant.
- **Overwrite base commits in place** — rejected as D2. Audit history, label correction, replay,
  and sample accounting all read them, and overwriting also destroys the diff that makes a word
  revision reviewable at all.
- **One authority instead of three** — rejected as D1, and the rejection is measured, not
  aesthetic. A single short-span authority is exactly what produces the `.483` seam WER above; a
  single long-window authority cannot publish a first word until its window closes. The split
  exists because no single window length both minimizes first-word delay and maximizes context.
- **Repair only the cut** (five-second re-decode per seam) — measured and rejected before this
  record: WER `.218–.230`, worse than publishing nothing extra, because a seam-local window
  inherits two new cuts of its own.

## Verification

The "verbatim" requirement of Appendix B Q8 is mechanically checked rather than asserted. The
verifier extracts every `D<n>` section from the plan's §4 and requires D1–D7 to appear in this
record byte-for-byte, in order, with no interleaved text:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_adr_text_finalization.py
```

Exit 0 means this record still quotes the plan exactly. If a later amendment edits the plan's
decisions, that command fails until this record is amended too — which is the point: the two must
not drift apart silently.

Evidence bundle: `evidence/live-convergence-0824/M2-text-finalization-adr/`.
