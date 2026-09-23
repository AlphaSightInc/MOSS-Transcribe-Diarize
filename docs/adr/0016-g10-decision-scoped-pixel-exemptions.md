# ADR-0016: G10 pixel exemptions for D7/D9 transcript controls

- **Status:** Proposed, pending the three host controls below
- **Date:** 2026-09-23
- **Scope:** `transcript_pane_fidelity` only

## Context

The release mandate pre-approves pixel differences caused only by user-requested UX changes. D7 requires a saved uncertain speaker to remain visible with a prominent “Needs review” notice; D9 requires passage-level reassignment (`grilling-decisions-20260919.md`). D13 also requires honest interrupted/partial presentation. These are transcript behaviors, not general permission to refresh the reference.

The exact H1 interrupted one-segment S00 meeting, replayed by the lead on the same host and pinned reference `6a8d0c1f…`, gave old b9 PASS (1440×900 total/largest 0.9126%/0.1181%; 1280×800 1.1288%/0.1507%) and new f7 FAIL (3.0324%/1.6043%; 3.8327%/2.0463%). At pane size 1052×869, old→new changed 24,434/914,188 pixels: D7 direct box 2,837, D9 943, lane 176, header 3,715, tools 8,704, other 8,059. Direct-box counts are not causal fractions. The lead's 05:05 element replay places components 1 and 3 on a tools bar shifted about 28 px by the D7 notice; component 2 on the S00 legend chip; component 4 on the uncertain speaker label; components 5–7 on D9 buttons; component 8 on displaced passage text. The title did not change in that run. A separate completed ten-segment meeting already passed the original G10 comparator.

## Proposed decision

The fixture exempts only five additions/movements: the D7 review banner, S00 legend chip, S00 utterance label, D9 reassignment buttons, and the old/new union of the tools bar **only when the D7 banner renders**. Candidate-only selectors may match zero or multiple elements; each match masks its own bounding box plus the comparator's existing one-pixel edge. A paired selector remains required unless its candidate side is explicitly marked optional. The existing Transcript/Summary toggle exemption remains. Each applied/missing box is reported in comparator evidence.

The tools union is the least broad box this comparator can use for a moved bar. It masks the old bar, new bar, and intervening band while D7 is present. This can hide a future tools visual regression inside that union; G10 remains sensitive to tools whenever the D7 banner is absent. A per-pixel displacement transform would need a different comparator and is outside this refresh. Passage text remains measured despite its observed displacement. No exemption covers title, generic header, whole legend, whole transcript body, fonts, OS, or unrecorded UI changes.

The viewports, pinned reference identity, channel tolerance, four-connectivity, and **2% total / 1% largest-component bounds are unchanged**. This proposal does not turn an unmeasured host run into a pass.

## Required acceptance evidence

On the host, under the staged Python/SQLite/Chrome runtime and with zero decoder requests: (1) the exact H1 `RcqY4pA-` meeting passes both viewports under the refreshed harness; (2) the completed ten-segment meeting still passes; (3) a test-only `.tr-title` visual corruption outside all exemptions fails. Record actual post-exemption percentages, masked boxes/areas, and source SHA. If any control fails, this ADR remains proposed and G10 remains failed. No baseline exception is admitted for fonts or OS differences.
