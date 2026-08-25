# M2 step 6 - the portal renders the surface, and the arm is on the screen

Plan §10.5 step 6: "update portal to render `effective_transcript` as one replacement surface".
Steps 1-5 built the rolling authority, put it inside the real runtime and proved the §7.3
snapshot reaches a client unchanged. This step is the first one a reader can see.

## What shipped

`moss_transcribe_diarize/app/live_portal.py`, one render function and two helpers:

- `renderTranscript` reads `session.effective_transcript` instead of stitching
  `session.committed`. The server publishes the whole of what a reader should be shown on every
  snapshot -- the rolling authority's words over the interval it owns, then the short base
  path's words after that frontier -- so the transcript node is **replaced**, never appended to.
  One owner per interval was already resolved server-side (ADR-0005 D4); the page does not
  re-decide it.
- `speakerLabel` turns the canonical identity the surface carries back into the `Sxx` token the
  rest of the meeting is written in -- the server's own `display_speaker_label` rule. Nobody
  attributed, and an identity this snapshot never established, both read as `S00`.
- `displaySeconds` turns sample indices into seconds using the rate the **descriptor declares**.
  A snapshot that declares none is refused (`malformed snapshot descriptor`) rather than
  rendered from an assumed rate: a plausible wrong timestamp is worse than a visible failure.
- The status panel gains the other three §7.3 fields on the same terms `label_revision_version`
  already had -- said only once there is something to say: `text revisions`,
  `converged through sample`, and `finalization` (E4's, absent while `not_started`).

The span still being spoken is **not** part of the surface and is still shown after it, exactly
as the base path published it: nothing has committed it, so no authority owns it yet.

## What changed for the reader

Before this step the page printed one row per committed span, each on its own **span-relative**
clock, so every row started near `[0]` and a rolling correction was invisible. Now every row is
one surface segment on the **session** clock, and a correction lands in place.

## Gates (`verify_portal_surface.py`, exit 0, zero MOSS requests, no GPU)

The instrument reads the DOM, not the snapshot:

    frames -> LiveServiceRuntime.accept_frame -> ... -> apply_text_revision
      -> snapshot().to_dict() -> json -> the portal script the service serves
        -> the transcript node -> parse_transcript -> the grid's own scorer

Three already-owned instruments: step 4's driver (`verify_runtime_rolling.run_case`, with the
new `collect_surfaces=True`) supplies every distinct snapshot the meeting passed through,
`LIVE_PORTAL_HTML` supplies the page, and the headless browser is the T2 tier's own
(`tests/test_live_portal._run_node_probe`, scenario `servedPolls`) -- one browser emulation in
this repo, not two.

| case | arm | polls | render mismatches | screen WER | screen recall |
|---|---|---|---|---|---|
| lex_bill_ackman | base | 121 | 0 | .261364 | .863636 |
| lex_bill_ackman | rolling | 121 | 0 | .198864 | .926136 |
| lex_javier_milei | base | 121 | 0 | .144000 | .920000 |
| lex_javier_milei | rolling | 121 | 0 | .096000 | .920000 |
| lex_keyu_jin | base | 121 | 0 | .194245 | .956835 |
| lex_keyu_jin | rolling | 121 | 0 | .100719 | .985612 |
| **TRIO** | **base** | 363 | **0** | **.199870** | **.913490** |
| **TRIO** | **rolling** | 363 | **0** | **.131861** | **.943916** |

- **G1** the base arm is on the screen: `.199870` / `.913490` -- the published live trio.
- **G2** the rolling arm is on the screen: `.131861` / `.943916` -- the §10.4 selected arm,
  per case to 6 dp. The screen and the snapshot agree per case, so the render neither lost nor
  invented a word.
- **G3** the render is a pure function of the snapshot it was given: at **every one of 726
  polls** the transcript node equalled an independent render of that poll's snapshot alone,
  built with the server's own label rule. Equality at every poll is the replacement property
  stated exactly -- a page that accumulated diverges at the first poll after the first revision.
- **G4** not vacuous: `S00` and sixteen established speakers reached the screen, and every case's
  rolling sequence contains polls at six distinct `text_revision_version` values.
- **G5** nothing but the surface reaches the screen: no canonical identity, no authority name.
- **G6** ordered and inside the meeting.
- **G7** zero fresh MOSS requests (178 replayed).

## Mutations (`mutate_portal_surface.sh`, six, all caught, control clean before and after)

| # | mutation | caught by |
|---|---|---|
| M1 | render the committed spans again (the pre-step-6 page) | verifier G1/G2/G3/G6 + T2 |
| M2 | append the surface instead of replacing it | verifier G3/G6 + T2 |
| M3 | print the canonical identity, not the `Sxx` token | verifier G3/G5 + T2 |
| M4 | unattributed speech rendered as the first speaker | verifier G3 + T2 |
| M5 | the provisional tail is dropped | **T2 only** |
| M6 | assume a sample rate instead of reading it | verifier G3/G6 + T2 |

M5 is T2-only and that is a finding, not a gap: this instrument's base path commits every span
it freezes and never publishes a provisional suffix, so sixty seconds of real audio cannot see
the live tail disappear. The `happy` scenario reads the transcript after a poll that *has* one.

## Tests

`tests/test_live_portal.py`, 25 passed (22 before). Three new:

- `test_the_portal_replaces_the_surface_when_a_rolling_revision_lands` -- nothing hand-written:
  a real session commits real spans through the real canonical pump, a rolling producer offers
  the real `apply_text_revision` seam a real proposal, and the two snapshots a viewer actually
  receives on `/snapshot` are replayed into the served portal script. The base words are **gone**
  from the screen, the revised words stand where they stood, the span the revision never claimed
  is untouched, and the speaker is the one the base timeline had established.
- `test_the_portal_never_attributes_speech_the_server_left_unattributed`.
- `test_the_portal_refuses_a_snapshot_that_declares_no_sample_rate`.

The `S00` literal in the page is bound to the server's `UNATTRIBUTED_SPEAKER` by
`test_live_portal_document_uses_memory_only_authority_shell`.

## Findings

- **F1: the live album establishes one canonical speaker per span on this instrument** -- 16 on a
  one-minute two-speaker interview. That is the deployed identity behaviour, not the render's,
  and it is exactly what E3 exists to fix; it is recorded here because it is what makes the
  screen show `S01`..`S16`, and because the G4 diversity check would otherwise look like a
  richer corpus than it is.
- **F2: the base arm and the rolling arm print a different number of rows for the same audio**
  (bill 30 -> 21, milei 28 -> 14, keyu 26 -> 16). A ten-second witness publishes whole
  sentences where twenty-four 2.5-second spans publish fragments. Fewer, longer rows is what the
  reader gains, and it is visible on the screen before any metric is computed.

## Not done here, deliberately

Export still reads current commits. Plan §10.5 step 7 switches it **last**, once terminal and
effective export tests pass, in one reviewed change. The deployed `web_cli` was **not** restarted
onto this build: rolling would turn on in the live service before its export is settled, and
nothing measured here needs the running service.

## Commands

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  prototypes/streaming-diarization/live-convergence/verify_portal_surface.py
prototypes/streaming-diarization/live-convergence/mutate_portal_surface.sh /tmp/portal-mutations
.venv/bin/python -m pytest tests/test_live_portal.py -q
```
