# ADR-0016: G10 pixel exemptions for D7/D9 transcript controls

- **Status:** Accepted (2026-09-23, round-6 lead) — host controls passed; independent review PASS (`REVIEW-H2H4-CLAUDE.md`)
- **Date:** 2026-09-23
- **Scope:** `transcript_pane_fidelity` only

## Context

The release mandate pre-approves pixel differences caused only by user-requested UX changes. D7 requires a saved uncertain speaker to remain visible with a prominent “Needs review” notice; D9 requires passage-level reassignment (`grilling-decisions-20260919.md`). D13 also requires honest interrupted/partial presentation. These are transcript behaviors, not general permission to refresh the reference.

The exact H1 interrupted one-segment S00 meeting, replayed by the lead on the same host and pinned reference `6a8d0c1f…`, gave old b9 PASS (1440×900 total/largest 0.9126%/0.1181%; 1280×800 1.1288%/0.1507%) and new f7 FAIL (3.0324%/1.6043%; 3.8327%/2.0463%). At pane size 1052×869, old→new changed 24,434/914,188 pixels: D7 direct box 2,837, D9 943, lane 176, header 3,715, tools 8,704, other 8,059. Direct-box counts are not causal fractions. The lead's 05:05 element replay places components 1 and 3 on a tools bar shifted about 28 px by the D7 notice; component 2 on the S00 legend chip; component 4 on the uncertain speaker label; components 5–7 on D9 buttons; component 8 on displaced passage text. The title did not change in that run. A separate completed ten-segment meeting already passed the original G10 comparator.

## Proposed decision

The fixture exempts only five additions/movements: the D7 review banner, S00 legend chip, S00 utterance label, D9 reassignment buttons, and the old/new union of the tools bar **only when the D7 banner renders**. Candidate-only selectors may match zero or multiple elements; each match masks its own bounding box plus the comparator's existing one-pixel edge. A paired selector remains required unless its candidate side is explicitly marked optional. The existing Transcript/Summary toggle exemption remains. Each applied/missing box is reported in comparator evidence.

The tools union is the least broad box this comparator can use for a moved bar. It masks the old bar, new bar, and intervening band while D7 is present. This can hide a future tools visual regression inside that union; G10 remains sensitive to tools whenever the D7 banner is absent. A per-pixel displacement transform would need a different comparator and is outside this refresh. In the historical D7/D9 fixture, passage text remains measured despite its observed displacement; no exemption covers title, generic header, whole legend, whole transcript body, fonts, OS, or unrecorded UI changes. The D55 Q5 fixture below explicitly extends that rule for all legend chips and transcript cards, with a separate fixture-content check for each masked card.

The viewports, pinned reference identity, channel tolerance, four-connectivity, and **2% total / 1% largest-component bounds are unchanged**. This proposal does not turn an unmeasured host run into a pass.

## Required acceptance evidence

On the host, under the staged Python/SQLite/Chrome runtime and with zero decoder requests: (1) the exact H1 `RcqY4pA-` meeting passes both viewports under the refreshed harness; (2) the completed ten-segment meeting still passes; (3) a test-only `.tr-title` visual corruption outside all exemptions fails. Record actual post-exemption percentages, masked boxes/areas, and source SHA. If any control fails, this ADR remains proposed and G10 remains failed. No baseline exception is admitted for fonts or OS differences.


## Host evidence (accepted 2026-09-23 ~05:45 EDT)
Real host (`ga0-alienware-rtx4070ti`), staged `f7fe4adc` runtime + this comparator/fixture in a scratch checkout, pinned clean reference
`6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70`, Chrome 152, zero decoder requests (round-6 `status/h2h4-host-run.sh`):
- New unit tests: RED 4 failed / 1 passed on `f7fe4adc`; GREEN 5/5.
- H1's exact meeting (interrupted, one segment, S00): **PASS** 1.2144 % / 0.6826 % (1440×900) and 1.5137 % / 0.8706 % (1280×800).
- Completed ten-segment meeting: **PASS** 0.9297 % / 0.1181 % (unchanged from the old build).
- Title-corruption violating control: **FAIL** 7.9231 % / 5.9222 %, as required.
Mandate source: auto-mvp-0911 grilling ("pixel-fidelity diffs attributable only to user-requested UX changes = pre-approved exception").
Bounds (2 % / 1 %), tolerance and viewports are unchanged; fonts/OS are not exempt. Residual risk: the 1280×800 largest region is 0.87 %
of the 1 % bound on this meeting — shifted text and chips remain measured by design. The acceptance receipt now records each exemption's
masked boxes and the pre-exemption pixel count per viewport.

## D55 Q5 amendment — proposed for freeze-5

D55 explicitly changes the transcript's live presentation: adjacent same-speaker turns become cards, settled generic names are numbered by current settled identity, and unsettled text has distinct styling. The historical comparator and its accepted D7/D9 fixture remain intact. `reference_ui_screenshot_diff_q5.json` adds two paired, required **generic selectors**: `.legend-chip` masks **every chip** and `.transcript-card` masks **every card**, including its label and passage pixels. The frozen three-segment fixture currently renders two chips and three cards; those counts are observations, not selector limits. Each mask covers the union of its old and new element boxes. A missing or changed paired count fails, but the unions collectively cover much of the transcript band. Therefore the Q5 comparator also requires every masked card's visible speaker label and passage text to equal the fixture, and fails on any mismatch. This content check restores detection of wrong labels or words inside masked cards; card styling inside those boxes remains unmeasured by pixels. The title, speaker count, tools, unused pane area, and every other unlisted area remain pixel-measured. The 1440×900 and 1280×800 viewports and 2% total / 1% largest-region bounds remain unchanged. A future native Q5 visual baseline should cover card styling.

On the Mac, pinned reference `6a8d0c1f…`, Chrome, and the same local comparator fixture, freeze-4 `8d8fb682` already fails the historical comparison at 7.5087%/5.5392% and 8.4831%/6.1593% (total/largest, two viewports). Q5 without its new exemption measures 15.5055%/6.7324% and 17.2342%/7.4881%. The Q5-scoped fixture measures 0.6285%/0.1309% and 0.6635%/0.1670%; the report records two chip boxes and three card boxes at each viewport. These are local attribution results, not host qualification. The lead must run and review the same Q5 config on the host before accepting the refreshed baseline.

Review control, 2026-09-28: a local control build replacing the first card's visible label with `Wrong Person XYZ` fails `Q5 card 0 speaker label differs from fixture`; a separate build replacing its passage with `Wrong passage` fails `Q5 card 0 passage text differs from fixture`. `tests/phase2/test_reference_ui_exemptions.py::test_q5_masked_cards_reject_wrong_label_and_passage_text` holds the permanent negative controls. The unmodified build passes both viewports with the content check reporting 3 cards / 3 passages. The independent review's earlier wrong-label/wrong-text build passed the pixel-only masks; these controls show what the new check recovers. Host G10 remains unmeasured.
