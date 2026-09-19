# WP51b evidence

## Gate and design

- Prototype gate: DONE; round-2 P4 F3/F4 supported meeting-bound correction and reserved-name refusal. The F5 residual had separate reproduced evidence.
- Structural question: keep correction intent bound to the Meeting and passage IDs that created it, while existing generation ordering prevents stale Open publication.
- Minimum primitives: captured `{meetingId, passageIds}`, current-session equality check, existing History generation, one normalized reserved-label predicate.
- Invariants: active/unsettled stays 409; interrupted is correctable; words unchanged; zero voiceprints; no ETag/revision protocol.
- Falsifier: any A passage sent to B, late A result mutates B, stale Open reverts acknowledged correction/view/export, or any reserved label creates a person.
- Decoder: 0/0 remote requests; no tunnel opened.

## RED before WP51b source changes

- Backend reserved labels: **7 failed / 7**, 7 deselected, in 3.68 s. Each of `S00`, `s00`, `  S00  `, `UNKNOWN`, `Speaker uncertain`, `Preview`, `SPEAKER_01` returned 200 and minted a `manual-*` identity on the unpatched correction path.
- Delayed Open with an A dialog: **1 failed**, 2 passed, 14 skipped. B became active while the A dialog survived; submitting targeted B with A's `seg_0001`.
- Open across correction acknowledgement: **1 failed**, 17 skipped. The stale Open response changed rendered `Casey` back to `Alex`; the export would therefore also be stale.
- Shared frontend drift control: **7 failed**, 8 skipped before the shared reserved-label predicate existed.
- Targeted source custody: before these RED runs, `phase2.py:1091-1134,2444-2452`, TranscriptPane correction state/submission, and MeetingHistory `selectMeeting` were unchanged from `a7a738cf`; earlier WP51a edits were in review publication/presentation regions only.

## GREEN

- Backend correction suite: **15 passed / 15** in 3.03 s.
- Reserved-name denominator: 7/7 rejected 400; allowed controls 3/3 accepted 200.
- Durable correction controls: active 1/1 refused 409; settled interrupted 1/1 accepted; words unchanged; voiceprints 0.
- Delayed Open/correction ownership: 4/4 response/error arms pass. Requests to B carrying A passage IDs: 0/4.
- Stale Open guard: 1/1 corrected view and actual plain-text export retained `Casey`, not stale `Alex`.
- Shared drift fixture: reserved 7/7 recognized by frontend and rejected by backend; allowed 3/3 remain ordinary names.
- Existing refresh-generation guard remains green in the full MeetingHistory focused suite.
- Focused frontend set: **85 passed / 85**. TypeScript clean. Vite build: 34 modules, 98 ms; assets regenerated.

## Failed attempts retained

- First Python collection failed because a test function name contained `-`; renamed with `_` before the RED measurement.
- First stale-Open test yielded too few microtasks and falsely passed; adding one event-loop turn exposed the expected `Alex` reversion.
- First response-order expectation assumed B must always win. The prescribed generation guard correctly keeps A when the correction acknowledgement wins first; the test now asserts the winner by response order.
- First TypeScript check found two test callbacks returning `dispatchEvent()` booleans; callbacks now return void.
