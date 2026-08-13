---
id: T-05
map: map-001-phase1-chrome-client
title: Reference UI control triage — what survives Phase 1
type: grilling
status: closed
assignee: claude
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

## Resolution (2026-08-13)

### Layout — the reference already defines the answer

`.main` is a three-column grid: `var(--side-col) minmax(0,1fr) var(--side-col)` —
left `ControlPanel`, centre `TranscriptPane`, right `HistoryPanel`. Crucially the reference
already ships a **designed collapsed state**: 48 px rail, `.panel-body` hidden, panel title
rotated (`writing-mode: vertical-rl; transform: rotate(180deg)`), with a 0.28 s transition.

**Ruling: the right column stays as the permanently-collapsed 48 px rail, non-interactive.**
Phase 1 therefore invents **no** geometry — the three-column grid and the centre pane's exact
width are preserved pixel-for-pixel. The rail is visually inert rather than a dead button, so it
never invites a click that does nothing. This is the cheapest possible answer to "what are the
Phase 1 pixels": they are the reference's own right-collapsed state.

### Control disposition

| Control | Ruling | Reason |
|---|---|---|
| Mode segmented control | **Two segments: Live \| File** | Drop what cannot work. Accepts that segment proportions differ from the reference's four-segment original — a small contained deviation |
| URL / Batch modes | **dropped** | Phase 2 |
| Microphone picker (`/api/devices/input`, `/api/devices/live`, `micRanking.ts`, `liveDevices.ts`) | **dropped** | Server-side device enumeration has no remote meaning. `getUserMedia({audio:true})` takes Chrome's default. See the trap below |
| Local mic mute | **KEPT**, as `track.enabled = false` | Implementer call — see reasoning below |
| Remote/system-audio mute | **dropped** | Muting the meeting audio you are transcribing is incoherent |
| Output volume (`/api/output-volume`) | **dropped** | Host-local, no remote meaning |
| Native pickers (`pick-file`, `pick-files`, `pick-folder`, `pick-save-file`) | **dropped** | Host filesystem dialogs on the server. File mode uses browser upload — shape defined by T-07 |
| `export-to-folder` (transcript and audio) | **dropped** | Writes to the server host. Replaced by browser download — T-08 |
| `HistoryPanel` (Sessions + Voiceprints tabs) | **dropped**; column becomes the inert rail | Both tabs are Phase 2 |
| `SummaryView` | **dropped** | No LLM layer (C10) |
| `LlmSettingsModal` | **dropped** | Inert without an LLM layer (C10). Its **styling is reused** by the preflight modal |
| `ToastLayer`, `SegmentedControl` | **kept** unchanged | Generic, no host dependency |
| Speaker labels (`speakerMap.ts`, `resolveVisibleSpeakerLabel`) | **kept**, generic ids only | Rename is Phase 2; `display_name` equals `speaker` per T-02 |
| Transcript search (`transcriptSearch.ts`) | **kept** | Pure client-side over held transcript |
| Keyboard shortcuts | **kept** for surviving targets only | Shortcuts whose targets are dropped are removed, not left as no-ops |

### New UI with no reference pixels

1. **Capture preflight → a modal over the app shell**, reusing `LlmSettingsModal`'s styling so it
   inherits real type, spacing and button language rather than inventing a visual vocabulary. The
   shell stays untouched underneath; dismissable back to idle. Contents per T-06.
2. **Shared-token entry** — same modal language, shown once per browser.

### Trap — dropping the mic picker has no in-app remedy

`getUserMedia({audio:true})` takes **Chrome's default input**, and Phase 1 gives the user no way
to change it. On the very machine Gate 1 ran on, the device list includes `BlackHole 2ch`,
`Virtual Desktop Mic`, and a multi-output device — any of which as default yields a **silent mic
lane**.

The preflight's two meters *do* catch this (the research doc is explicit: never silently
downgrade to an empty lane), so the failure is detected. But the remedy — change Chrome's default
input — lives in buried browser settings, so a user with the wrong default hits a failing
preflight with no in-product path forward.

**Required mitigation, cheap:** when the mic lane meters silent at preflight, the status line must
say *how* to fix it, naming Chrome's site-settings path, rather than only reporting failure. Note
that `enumerateDevices()` returns empty labels before permission is granted anyway, so a picker
could not have been populated pre-permission — which is part of why deferring to failure-time is
defensible. If field use shows this biting, reinstate the picker as a **failure-only fallback**;
do not add it to the happy path.

### Implementer call — why local mic mute is kept when the picker is dropped

These look inconsistent and are not. Both are host-local in the reference, but they differ on
whether the user has an alternative path:

- **Mic picker:** Chrome's own site-settings UI can change the input device. The capability still
  exists for the user, just not in our product. Dropping it removes a control, not an ability.
- **Mic mute:** Chrome offers **no per-tab microphone mute**, and OS mute is global. Dropping it
  removes an ability with no substitute — mid-meeting muting is a genuine need.

Cost is also asymmetric: mute is `track.enabled = false`, one line, no state machine, so it does
not offend C11's minimize-client-judgment rule. The picker would need enumeration, ranking,
eligibility, and permission-ordering logic.
