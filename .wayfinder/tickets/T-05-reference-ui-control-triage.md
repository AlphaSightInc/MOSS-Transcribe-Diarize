---
id: T-05
map: map-001-phase1-chrome-client
title: Reference UI control triage — what survives Phase 1
type: grilling
status: open
assignee:
blocked_by: [T-02]
---

## Question

C2 says: same pixels, **drop** controls that cannot work — do not reinterpret them, do not add
a superset. Produce the definitive Phase 1 UI inventory: every control in the reference
frontend ruled **keep / drop / Phase 2**.

Go component by component. Reference surface (`/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src`):

- `Topbar.tsx`, `ControlPanel.tsx` (544 lines), `TranscriptPane.tsx` (999),
  `HistoryPanel.tsx` (484) + `historyPanelSurface.tsx`, `SummaryView.tsx`,
  `LlmSettingsModal.tsx` (625), `ToastLayer.tsx`, `SegmentedControl.tsx`
- `App.tsx` (1773 lines) — the orchestration, including keyboard shortcuts

Known-hard cases to rule explicitly:

1. **Mode segmented control** — reference offers `live | file | url | batch`. Phase 1 has live
   and file; url and batch are Phase 2. Does the control show two options, or four with two
   disabled? "Drop what cannot work" argues two — but the segmented control's proportions are
   part of the pixels. Decide and say why.
2. **Host-local controls, already ruled out by C2** — confirm each is removed cleanly rather
   than leaving dead layout: `/api/pick-file`, `/api/pick-files`, `/api/pick-folder`,
   `/api/pick-save-file`, `/api/output-volume`, `/api/devices/input`, `/api/devices/live`,
   `export-to-folder` (transcript and audio), `/local-mic`, `/remote-audio`.
3. **Microphone selection.** Reference ranks and selects devices server-side
   (`micRanking.ts`, `liveDevices.ts`, `LiveMicrophoneInfo`, eligibility `ok|warn|unavailable`).
   Phase 1's mic lives in the browser. Is a device picker kept at all, and if so does it come
   from `navigator.mediaDevices.enumerateDevices()` — which C2 arguably forbids as
   reinterpretation? This is the sharpest C2 boundary case; rule it deliberately.
4. **`HistoryPanel`** — both its tabs are Phase 2 (sessions history, voiceprints). Does the
   panel disappear entirely in Phase 1, changing the app's whole two-column geometry? If so,
   what *are* the Phase 1 pixels, given the reference's layout assumes it?
5. **`SummaryView` and `LlmSettingsModal`** — Phase 2 per C10. Same geometry question.
6. **Speaker labels.** `speakerMap.ts` / `resolveVisibleSpeakerLabel` render display names;
   rename is Phase 2, so Phase 1 shows generic diarization ids. Confirm the pane looks right
   with `SPEAKER_01`-style labels only.
7. **What Phase 1 must *add* that has no reference pixels** — the shared-token entry field and
   the two-lane capture preflight. Name them here; their design belongs to T-06 and to the
   fidelity-method ticket.
8. **Keyboard shortcuts** (`keyboardShortcuts.ts`) — which survive when their targets are gone.

Output: a table with one row per control, its Phase 1 ruling, and the reason. This table is
what makes "pixel-for-pixel" a checkable claim instead of an aspiration.
