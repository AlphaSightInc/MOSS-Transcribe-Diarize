# WP51a evidence

## Gate and scope

- Prototype gate: DONE for the seam; actual UI download hydration was the required new acceptance gate.
- Structural question: preserve one durable review truth when Live poll, failed History, reopened Meeting, view, and download actions race or disagree.
- Minimum primitives: optional `needs_review` on the typed session event; explicit truth before active-session fallback; speaker identity from `speaker_entity_id`; existing download action and serializers.
- Falsifier: failed `/api/meetings` hides the banner/marker; absent becomes false; `S00` reaches view/download bytes; healthy explicit false stays true; empty transcript enables SRT.
- Decoder: 0/0 remote requests; no tunnel opened.

## RED before WP51a source changes

- Actual reopened-download test: **1 failed, 14 skipped**; the rendered saved speaker was literal `S00` instead of `Speaker uncertain`.
- After the view correction, the same test remained RED because downloaded JSON still contained literal `S00`; this proved serializer-level raw fields also needed normalization.
- Live poll projection: **2 failed, 31 skipped** because neither explicit `needs_review=true` nor `false` reached the typed `session_state` event.
- Absent/false control: **1 failed, 1 passed, 15 skipped**; absent durable truth incorrectly cleared a previously known review state, while explicit healthy false correctly cleared it.
- Failed command retained: the first Vitest path included the `frontend/` prefix under `npm --prefix frontend`, so Vitest found no test files; the corrected path begins `src/`.

## GREEN

- Decisive actual-download gate: **1 passed, 14 skipped**. One reopened saved review Meeting, one deliberately failing History route, five real menu actions, five captured Blob byte streams.
- Download denominator: 5/5 (`md`, `txt`, `json`, `srt`, `vtt`) contained `Needs review` and `Speaker uncertain`; 0/5 contained literal `S00`.
- Review truth controls: 4/4 passed (reopened review download, known absent preserved, explicit false applied, poll true/false).
- Focused frontend set: **89 passed / 89** across poller, Meeting History, Transcript Pane, speaker map, and serializers.
- TypeScript: clean. Vite production build: 34 modules, 101 ms; assets regenerated.
- Empty SRT: serializer content 0 bytes; UI remains disabled with zero transcript turns.

## Format naming adjudication

The PANE prose names CSV, but the binding implementation plan says preserve the **five existing serializers**, and both production UI and end-to-end oracle define those five as Markdown, plain text, JSON, SubRip, and WebVTT. This WP exercised and preserved those five; it did not add a sixth CSV format.
