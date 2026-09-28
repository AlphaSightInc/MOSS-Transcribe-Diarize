# D53 implementation notes

Prior throwaway prototype: `round6/proto-ui-u1u2` @ `b2b3b8a8`, screenshots and measured decision in `moss-round6/evidence/ui-u1u2/INDEX.md`. User chose V1a + V2a. This branch implements the choice; it does not carry prototype fixture or variant switcher.

## Structural question
How can a selected completed Meeting open a dedicated summary page even when the optional Live root is absent, while keeping summary and browser-owned settings bound to that selection? How can the passage action sit within each settled turn's row without changing its correction behavior?

## Minimum primitives
The history selection remains authoritative in `MeetingHistory`. UI signals project the selected completed Meeting and open state. `MeetingHistory` portals the upper-right entry and full summary page to the document body, so both work with or without Live capture. The page makes the underlying workspace inert while open. The existing `FinalSummarySettings` and `FinalSummary` render only in that page. The existing passage correction callback is exposed through a compact button in the turn text row. No new backend data or persistence.

## Invariants
Summary only for the selected completed Meeting; changing to an active/failed selection closes the page. Key/model/prompt remain in local browser storage. `Browser AI settings`, `Final summary`, `final-summary-generate`, exact `Reassign passage` name, `data-reassign-passage`, and `#passage-speaker-title` stay. G9 lifecycle/provider semantics, G10 bounds/viewports, and transcript text stay. No host, GPU, provider, or real decoder calls.

## Assumptions and unknowns
The selected Meeting object is refreshed or opened through `MeetingHistory.replaceSelection`. The full page covers the workspace while open, with Back restoring the selected record. The local G10 comparator uses a lead-provided reference source copy because the pinned SHA is unavailable in the Mac checkout; host qualification remains lead-owned.

## Falsifier and tools
Reject if summary opens for a noncompleted or stale meeting, settings leave browser storage, G9 selectors fail, a passage dialog changes, 400 px overflows, or G10 changes outside the authorized U1 surface. Frontend component tests exercise state and controls; typecheck/build catch bundle drift; local fake-provider G9 exercises real browser lifecycle; reference screenshot comparator measures G10. Full backend suite checks acceptance collateral, not UI appearance.

## Verdict
The fake-provider browser path found that a Summary page hosted only in `App` disappears when Live capture is unavailable. Hosting it from Meeting History fixed that falsifier. The fixed upper-right button initially covered the History tabs; moving it beside the Live area passed the desktop and 400 px browser checks. FE 313/313, typecheck, build, full backend `tests/` 2,417 passed/0 failed (5 skipped, 2 expected failures), local external/relay fake-provider browser path, and G10 U1 attribution pass. Mac-local G10 against LiveTranscribe remains above the 2%/1% bound on both freeze-4 and this branch; see ADR-0016 for the exact values. Host qualification is unmeasured.
