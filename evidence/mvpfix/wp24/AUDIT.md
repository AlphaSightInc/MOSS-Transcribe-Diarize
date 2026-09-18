# WP24 visual/copy/accessibility audit

**Owner review ready; owner acceptance NOT granted.** [52-state checklist](pack/index.md):
156 product screenshots at 1440×900, 1280×800, 400×844, plus three reference screenshots.
A screenshot shows presentation. Its provenance says whether the underlying event actually ran.

## Findings and disposition

| Code | Finding | Disposition |
|---|---|---|
| F1 | Selected History metadata/preview was 4.22:1 against its tinted background. | Fixed with existing `--ink-2`; measured 11.87:1. No token values changed. |
| F2 | Long outcomes overflowed at 400px; desktop status could be covered by the overlapping transcript header. | Fixed narrow header sizing and bounded desktop status to the existing 280/240px rail. No panel redesign. |
| F3 | Speaker dialog said “active meeting” although saved meetings also support naming. | Fixed to “this meeting”; tested active/saved live/file naming. |
| F4 | Share audio is offered while microphone preparation is pending. Clicking immediately can enter `error`; microphone completion then overwrites the explanation with “Microphone connected”. | Deferred: requires lifecycle/enablement behavior, outside copy/aria/CSS scope. `checks/early-share-failure.txt`, `ControlPanel.configureMicrophone/shareAudio`. Wait for microphone-connected status avoids it; no production workaround added. |
| F5 | White Stop text on `--live` was 4.12:1. | Fixed background to existing `--danger`; 6.50:1. Hover remains the existing darker red. |
| F6 | Untitled transcript displayed the reference product name, LiveTranscribe. | Fixed fallback to MOSS; named meetings remain their own titles. |
| D3 | Actual `open_workspace=True` instance still says “Private to this browser”, “Private voiceprints”, and browser-profile history access. | Deferred exactly as brief requires. Shared ownership contradicts those strings; screenshots retained. |

Five findings fixed; two deferred items (F4, D3). No missing interactive accessible names were found.
Lane badges correctly distinguish **System** and **Microphone**; overlapping speech stays in separate rows
(WP2 variant A). Real retained active envelopes show confirmed and provisional rows together; finalizing
shows confirmed rows. No new readiness, identity, lifecycle, frame, or quality policy was introduced.

## Evidence and boundaries

- **Actual execution:** public Bill Ackman/Keyu Jin corpus through real vLLM, real-time two-lane API
  capture and real 30s lease expiry; browser multipart File Meeting; browser Start → active overlap → Stop
  → final through production CaptureClient. Media streams are explicitly fake public-audio devices.
  Browser stop retains the product's own deadline; direct API acquisition uses `deadline:30`.
- **Replayed genuine evidence:** active/provisional/finalizing envelopes, saved transcript, labels, and
  voiceprint bank are unmodified production responses. Replaying them measures presentation only.
- **Explicit fixtures:** 14 N1 failure-message variants, no-speech/truncation notices, three audio
  availability states, 60-row history. These conditions were not induced end-to-end by this pack.
  Summary queued/generating/retry/current/failed/cancelled responses are explicitly fake endpoints.
  “Provider without key” captures settings, not a successful provider request.
- **Share chooser:** the page's pending-share state is captured using an unresolved fake media request.
  A native OS chooser cannot be captured by this headless harness; physical microphone/chooser acceptance
  remains unmeasured. No screenshot is represented as physical hardware evidence.
- **Shared mode:** separate actual `open_workspace=True` local instance, not a replaced header fixture.
- **Reference:** `tools/uifidelity/reference_oracle.py` serves LiveTranscribe's authored bundle. Three
  screenshots are context, not a pixel verdict. Operator-reserved fidelity gate never run.

## Accessibility and visual measurement

Every capture retains computed text/background colors, alpha-composited contrast, font size, threshold,
accessible-name results from Chromium's accessibility tree, focus order, horizontal-scroll measurement,
text-overflow candidates, and header/panel intersection checks in `pack/pack.json`.

Plain body text uses WCAG AA 4.5:1 (large text 3:1). Disabled controls are excluded. Gradients/ancestor
opacity are marked **manual review**, never counted as a measured pass. This is not a complete WCAG
certification: assistive-technology use, focus-ring contrast, all hover states, and all pixel overlaps are
not exhaustively measured. Browser keyboard traversal verified the speaker-name dialog at all widths:
no background controls in its cycle; Escape restored focus **3/3**. Chromium's browser-chrome tab stop
is recorded separately. No positive-tabindex anomaly was found.

Full-page mobile screenshots include vertical scrolling. Desktop History/settings/control panels have
internal scrolling; screenshot bottoms need not show every field. Copy files omit CSS-clipped headings
and unselected select options, but include text reachable by scrolling panels. Ellipsized History titles
and previews are intentional; selected transcript and outcome expose the full content. Screenshot review
sampled real active capture, mobile failures, naming, and summary settings; owner must tick every state.

## Reproduction and decision

One command (with the brief's Python):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/ui-signoff-pack/run.py --regenerate .wp24/owner-review
```

The command owns ports 17884/17885/17886 and tunnel 18124, records queue/request counts, uses at most two
in-flight decoder calls, and stops its processes. TLS, cookies, audio, databases and profiles stay ignored
inside `.wp24/`. Only public transcript text and screenshots are committed. Global WP budget is 150;
`request-count.json` records usage. The generator preserves source envelopes for rare intermediate states.

**Owner decision:** review the checklist and judge visual acceptance. Handle D3 separately; route F4 to a
lifecycle work package. Passing automated checks does not close either deferred item or grant deployment.

## Frozen pre-/new result

- 156/156 captures: zero horizontal overflow, unnamed interactive controls, or checked header/panel overlaps.
- 8019 computed contrast occurrences passed; 606 gradient/opacity occurrences require manual review.
- 315 intentional ellipsis candidates; full text remains in selected detail. These are not 315 defects.
- Final Python: **1908 passed, 2 skipped, 37 subtests passed**, 21 warnings, 152.33s.
- Frontend: **250 passed in 28 files**; typecheck and production build passed.
- Targeted geometry/accessibility: **11 passed**, including unchanged existing geometry tests.
- Current decoder use **49/150**, at most 2 in flight; fresh verification records the later total.
- Frozen production change: `205dc611`; integrated base `0ce5122d`.
- `/new` outcome is exclusively in root `VERIFY-RESULT.md`; this paragraph does not assert it occurred.
