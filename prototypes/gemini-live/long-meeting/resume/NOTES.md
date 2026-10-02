# P74-R — same-meeting resume (throwaway measurement bench)

## Six-part contract — recorded before implementation

1. **Question:** can the same signed-in browser replace its crashed capture page, within the lease, without replacing the meeting or compressing lost time?
2. **Primitives:** origin sign-in authority; page capture generation; independently advancing lane sequence/epoch/end cursors; monotonic elapsed-time anchor; abandonment lease. Identity, exclusion, ordering, time, and lifetime cannot substitute for each other.
3. **Invariants:** one live meeting, one authorized writer, one continuous saved audio file; same transcript and speaker ledger; increasing sequence/epoch/time; explicit epoch discontinuity; honest silence for missing audio; terminal meetings stay terminal. Local queued/unacknowledged audio cannot be recovered.
4. **Assumptions/unknowns:** cooperating operator, same sign-in cookie and tab storage; 90 s mixer catch-up and bounded retention unknown; real Bluetooth and real Chrome crash unmeasured; fake engine proves protocol, not recognition quality.
5. **Falsifier:** a 90 s gap cannot be preserved in one audio archive through the real routes. Then recommend linked continuation instead.
6. **Tools:** existing scripted runtime + real Phase2 routes/archive detect protocol, ownership, timing and publication failures; controlled monotonic lease clock avoids real-time long meetings; real Chrome + fake devices detect activation and clock-restart assumptions. No provider/key reads. Each failure changes the proposed protocol or narrows the claim.

Hypothesis: explicit resume returns authoritative lane/clock state and atomically moves capture authority; timestamp-based zero fill preserves elapsed time. Compare takeover-heartbeat S1 and resume-endpoint S2. Measure before proposing product edits.

## Verdict

**Yes, within the existing lease. Recommend S2: an explicit, origin-sign-in-bound resume handshake, one Resume recording button, and elapsed-time silence.** No product implementation is shipped here. Keep the engine, meeting binding, audio stage and speaker ledger alive; replace only the capture page. A 90 s gap passes the falsifier on the real Phase2 routes, Gemini scripted engine, production mixer and real MP3 archive.

The minimum sufficient addition is capture-page exclusion plus an authoritative resume-state response. Ordinary frames, heartbeat, Stop and Abort must all carry the page instance; heartbeat replacement alone is insufficient. An instance id is a writer identity, not another login credential. Origin-cookie authorization still runs first. An explicit takeover compares the expected previous instance and installs the new instance under the same meeting mutation guard; concurrent attempts cannot both win. Ordinary heartbeats still reject instance switching.

**One command, from this worktree:**

```sh
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/long-meeting/resume/measure.py
```

It prints all recorded state and writes separate disposable databases, audio, browser artifacts and receipts under `~/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume/`. Chrome server: HTTPS `127.0.0.1:18987`, stopped in `finally`; no other server or host is used. Browser build goes to evidence, never `app/frontend_assets`. The complete protocol driver needs no browser; run `run.py` alone. `boundaries.py` and `browser_probe.py` reproduce their own cells. `measure.py --summarize` checks retained receipts without new measurements.

Custody: branch `gemini/r5-f3`, clean initial checkout `644694a8`; brief-required startup fast-forward to `54fb5573`. No integration merge, push, commit, provider construction/call, actual API-key read, private audio or production state. Explicit dummy transcription settings prevent the key resolver from consulting the environment. Engine factory always constructs the offline scripted engine. All code here is throwaway measurement-bench code; **candidate product commits: none**. The retained bench answers this protocol question; it is not a second production transport.

## Measurements

N=4 s captured; crash without Stop; G as below; M=4 s continuation; 0.5 s frames, two lanes, 16 kHz. Test clock advances at each frame end. Lease is the real 120 s coordinator with its existing injected clock/timer seams. No 45-minute real-time run.

| Gap G | Resume | New frames | Saved audio | Transcript missing interval | Lease / final result |
|---:|---:|---:|---:|---|---|
| 5 s | 200 | 16/16 | 13 s, one audio.mp3 | 4–9 s | renewed; completed |
| 30 s | 200 | 16/16 | 38 s, one audio.mp3 | 4–34 s | renewed; completed |
| 90 s | 200 | 16/16 | 98 s, one audio.mp3 | 4–94 s | renewed; completed |
| 119 s | 200 | 16/16 | 127 s, one audio.mp3 | 4–123 s | renewed; completed |
| 125 s | 409 | 0 | 4 s, one audio.partial.mp3 | no continuation | expired; interrupted |

For all four accepted gaps: decoded MP3 duration = 4+G+4 exactly; interior silence has maximum PCM amplitude 0 (excluding 100 ms at codec edges); prefix and resumed transcript timestamps preserve G exactly. Speaker entity `speaker-0001`, manual name **Alex**, original engine object and meeting id survive. This proves state continuity on a scripted recognizer, not acoustic identification after real-provider silence.

| Design | 90 s result | Old original wakes | Decision |
|---|---|---|---|
| Unchanged | new heartbeat 409; adopted-sequence/reset-clock frame 400 | no handoff exists | cannot resume |
| S1 takeover heartbeat | final audio 98 s; only 14/16 new frames accepted | heartbeat 409, but valid next frame **200**; it consumes sequence/audio time | reject; lacks frame fencing and state return |
| S2 resume endpoint + all-mutation fence | final audio 98 s; 16/16 new frames | frame/heartbeat/Stop/Abort **409**; stale takeover **409** | recommend |

S1's driver reads private state to continue, explicitly recorded in its receipt. Its heartbeat response does **not** supply that state; its final audio result is not proof that S1 alone is sufficient. The two conflicting new-frame 400s are retained.

**F1 — Live catch-up is paced.** Existing mixer emits at most 1 s per accepted frame POST. With two 0.5 s lanes, it can emit at most 4 s per second of continued capture while 1 s of new speech accrues. For 119 s gap +45 s continuation: 180/180 frames accepted, 168 s MP3, peak retention **472,000/960,000 samples per lane (29.5/60 s)**, first resumed live row after **30 s**. Short M=4 cases preserve all final audio by the existing bounded Stop drain; 30/90/119 s gaps do not reach resumed live speech before that Stop. No new mixer algorithm, larger retention or transcript-time compression is needed to pass the requested final-timeline gate. Immediate live transcription after a long gap is not promised.

**F2 — Writer/lifetime boundaries pass.** Two simultaneous same-cookie tabs: one 200, one 409. Same-account/different-sign-in session: 403; foreign-account frame: 404. Lost resume-response retry returns the same current writer/state without a second lease renewal. Old acknowledged frame replay is fenced with 409 before ingress can silently return its cached acknowledgement. New sequence 0 still returns old acknowledgements without new audio, demonstrating why server cursors are mandatory. Higher epoch without discontinuity returns 409; adopted sequence with discontinuity returns 200. Malformed resume returns 400 without dropping old presence. At exactly the lease deadline, resume returns 409 even before the timer callback; after real expiry/publication it stays interrupted and returns 409.

**F3 — Real Chrome reload works through the actual CaptureClient/worklet.** Chrome 154.0.8037.98, public synthetic tone tab, fake microphone, fresh disposable profile. The throwaway subclass supplies adoption/header/offset seams; production CaptureClient frames, heartbeat scheduling, microphone constraints, graph and worklet are used. Reload makes the old page disappear without Stop; the new page chooses Resume. Measured receipt: 7.446 s from reload to resumed state; old context 3.144 s, new context 0.032 s; first lane sequences 6, epochs 2 (previous epoch 1), both discontinuous; 12/12 observed resumed frames 200; microphone frames remain muted/silent; echoCancellation stays true; same id completes with one saved archive. No transport errors. Resume round trip 2.3 ms. The capture clock offsets both start and end timestamps. Server capture timestamp and mixed sample clock are distinct: initial source skew means a marker must translate through the mixed cursor/sample pair, not use raw capture timestamps as transcript seconds.

Gesture-free microphone reacquisition with previously granted permission succeeds with transient activation **false**; AudioContext is running and advances to **0.216 s**. This is fake-device/profile evidence only. No autoplay override is passed. The end-to-end tab chooser is automated by source title; it cannot certify a human picker. A separate Chrome page-load call with no activation and no auto-select flag receives no reply in 3 s: **tab no-click denial UNMEASURED in this bench**. Respect the brief's established one-click requirement.

Chrome track labels are opaque per-acquisition `web-contents-media-stream://…` values and **change on reload**. `share-label-assumption-rejected.json` retains the initially failing label-equality check; the protocol/settings gates remain separate. The same synthetic tab was selected by its title through the Chrome flag, not recovered from the saved track label. Persist prior source **kind/descriptive UI label** as a reminder, never as a reusable source handle. The fake microphone reports `default`; this does not prove a physical microphone remains the same.

Harness failures were retained, not scored as product failures: first stub called a nonexistent capture method; a later no-click display probe disturbed native focus; Playwright evaluation/chooser automation changed activation semantics. The latter prompted the independent page-load probe. An occupied 18978 belonged to another pane and was left untouched; this bench uses 18987. One blocked chooser run was interrupted by its own PID; its `finally` stopped its server. Final receipts verify server shutdown.

## Proposed product protocol and client

**D1 — Explicit S2 handshake.** Add `resume` to the Phase2 mutation authorization set (same originating Sign-in session; another account still 404, another Sign-in session still 403). Request has expected old page id, new page id/initial heartbeat, no engine settings or credentials. Under one per-meeting capture guard: validate payload first; require active/open capture and unexpired lease; compare expected writer; adopt the new writer; keep heartbeat sequence increasing and reset/adopt its monotonic send base; renew the ordinary lease once. Duplicate same old→new request returns current state, does not re-take ownership or refresh the lease. Old lease callbacks remain generation-fenced by the existing coordinator. Stop accepted first still wins; expired/terminal/server-restarted meetings never reopen. Product must coordinate expiry/Stop and takeover through the existing lifecycle owner; prototype locks cover the real capture HTTP mutations, not every internal revocation race.

Return: existing meeting id and descriptor; each lane's next sequence, current/next device epoch, last accepted capture end, lane health; mixed cursor and accepted mixed samples; capture-clock-now anchor; remaining lease; next heartbeat sequence/send base; redacted original engine settings if UI needs them. Expose those small accessors from ingress/mixer/coordinator; do not import private fields as this prototype does. Carry the page id in a header on frame, heartbeat, Stop and Abort; check it after Account/origin authorization and under the same guard as admission. Extend both ordinary CaptureClient headers and the separate Stop/Abort helpers. Typed `capture_replaced` closes the old graph, removes capture eligibility, preserves its view/poller, and never starts a new meeting or retries takeover automatically.

**D2 — Restore a meeting-specific capture record.** On Start and every actual microphone/source/mute change, persist in tab-scoped storage: meeting id; last page id; actual recorded sources (including deliberately silent lanes); resolved microphone device id; mute; echo setting (currently always true); display source kind/descriptive label. This is a small extension of the current `lt:session:reattach` record, not a global preference lookup. Capture id is not authority by itself; the HttpOnly cookie remains required. Do not persist PCM queues, bearer grants or duplicate provider keys. Preserve server-held original engine/settings/tape/identity object; changed global browser preferences must not alter the resumed meeting. If storage/device is unavailable, say what cannot be restored; do not silently choose another microphone under an “exact same” claim.

On reload, own stored meeting + active snapshot + no Stop intent -> Resume available with original settings/remaining lease, and Detach/view still available. Other history observers remain read-only. On one Resume click, invoke getDisplayMedia synchronously before awaiting anything; acquire requested microphone with the stored id, reapply mute, attach zero-driven lanes for sources not selected, then call resume/adopt. Refused/cancelled media selection does not create a new meeting. If the picker exceeds the lease, show expired/linked-continuation alternative. Adopt server sequences and next epochs before allowing the first queued frame; mark each first frame discontinuous. Offset new context `currentFrame/sampleRate` to returned capture clock plus elapsed local monotonic time since handshake; offset both endpoints, and translate source clock to mixed clock for gap display. Network round trip, last-frame queuing age and device-clock drift bound real timing accuracy; exact live network timing is unmeasured. Unsent queues cannot be recovered; accepted uncertain frames are retained on the server and resolved by returned next sequence.

**D3 — Honest gap, stable settings, explicit choice.** Retain zero fill and add a separate timeline notice, e.g. “Recording interrupted 00:04–01:34.” Derive its boundaries from last accepted/first resumed frame on the mixed clock; save capture-gap metadata beside transcript segments so Stop/refinement/reload cannot erase it. It is not a speaker row or spoken words and is excluded from recognition input/summary text. This notice/persistence is proposed, not implemented/measured here. Keep the existing 120 s lease. A GET/snapshot/reader must never renew it; a successful explicit resume gets the ordinary 120 s lease and subsequent valid heartbeats renew normally. Resume after the deadline, closing, accepted Stop, or restart is refused.

Automatic summary ownership also follows successful capture adoption: reinstate the initiating browser's watcher once, retire it on replacement, retain original summary preferences, and prevent a replaced page from generating duplicate automatic summaries. Summary/provider behavior remains unmeasured here. This requires the ADR-0011 amendment/regression gates below; it is not part of the $0 protocol success claim.

## User choices

| Code | Choice and trade-off | Recommendation |
|---|---|---|
| O1 | Auto microphone immediately + separate tab click restores mic sooner but creates a partial recording and more lifecycle/activation handling. One Resume recording button restores all selected sources together but waits for the click/picker. | **One button**; minimal, visible, easier to preserve the settings. Auto-mic is feasible on the measured fake profile only. |
| O2 | Preserve elapsed silence + gap notice keeps audio and transcript honest but delays live catch-up. Compress missing time is faster but changes the meeting clock and hides loss. | **Silence + separate notice**; disclose the measured catch-up delay. |
| O3 | Keep 120 s bounds abandonment. Longer global grace keeps orphan meetings/capacity occupied. Read-based “reload detected” grace can be triggered by a reader and does not prove capture is coming back. | **Keep 120 s**; explicit valid takeover renews normally. A longer user-selected grace requires a separate bounded measurement/decision. |
| O4 | Same-account second device automatic takeover breaks origin ownership and can replace valid capture accidentally. Explicit origin-cookie/tab-record takeover gives one writer; another Sign-in session remains a reader. | **Explicit same-origin Resume**, with “replaces the previous capture page” copy; other device/session refused. Duplicated same-cookie tabs compete by compare-and-swap; one wins, old becomes viewer. |

## Recorded decisions and regression changes required before a product build

**A1 — Documents.** Amend ADR-0004's decisions 1–4/consequence only for the Phase2 capture-origin resume case; preserve legacy bearer/view expiry rules and accepted-Stop lease handoff. Amend ADR-0006's reload-read-only paragraph to distinguish stored originating tab from history observer and to fence all capture mutations. ADR-0001: give `resumable: true` a real handshake contract; ordinary heartbeat instance stability remains, with explicit takeover exception and global sequence ordering; update relevant M01–M25 obligation/node map (especially presence/release, coordinator ownership M20, scope M21, evidence M22–M25), not erase its native/legacy gates. `CONTEXT.md` lines 21–23: capture remains non-resumable after server crash/expiry; distinguish browser within-lease recovery. Lines 239–260: explicit presence takeover, ordinary duplicate freshness, coordinator lifetime unchanged. `docs/design-gemini-live.md` round-4 lease/timeline and `docs/design-capture-setup.md`: capture record, Resume/picker/failure/mute behavior. ADR-0011: automatic summary worker transfers to resumed originating page; observers/replaced page never auto-generate. ADR-0013's credential custody remains unchanged. ADR-0005 spoken-text authority remains unchanged: interruption metadata never becomes recognizer speech.

**A2 — Frontend tests.** `ControlPanel.test.tsx:295` gains eligible-origin Resume behavior; retain legacy `{sessionId}` read-only fallback when settings are absent. `:601` Stop failures, `:741` history observers, `:780` history cannot replace capture, `:819` transport recovery remain meaningful, augmented for capture-replaced/view preservation. `persistence.test.ts:50,61`: round-trip actual settings/page id; missing/malformed storage returns view-only, no source substitution. `App.test.tsx:161,174`: accepted Stop does not resume; original meeting clock stays. `captureClient.test.ts:614,653,1091,1117,1430,1558`: preserve epoch/replay/out-of-order/terminal/malformed/mute meanings; add adopt sequence/epoch/send-base, new-context offset on both endpoints, silent source, lost handshake response, typed replacement fence with no Stop/new meeting, and header on separate Stop/Abort helpers. Summary-watcher tests: resumed owner starts one watcher, old owner retires, observers stay silent; fake provider only. Export/poller tests: gap metadata survives Stop/refinement and never appears as spoken summary input.

**A3 — Backend tests.** `test_owner_bound_live_meeting.py:821` owner/durable two-lane flow gains resume/state/archive/name preservation; `:2492` terminal conflicts, `:2521` lease loss never resumes, `:2569` create lease remain **unchanged semantics**, augmented with pre-expiry takeover/125 s expiry/server restart. `test_live_helper_presence.py:76,104`: ordinary ordering/switch refusal unchanged; explicit takeover/new-clock/duplicate response/CAS coverage. `test_live_helper_failure.py:84,113,164,295,341`: arm, duplicate no-renew, stale callback, expiry/release and diagnostic meanings preserved; add takeover-vs-expiry/accepted Stop/revocation races. `test_live_ingest.py:90,102,147,169`: cached ack, order, epoch and pruning unchanged; test writer fence occurs before cached ack. `test_live_mixer.py:252,392,630`: gap zero fill, stalled-lane catch-up and immutable accepted ends unchanged; add 90/119 s route/archive/gap-metadata tests and bounded-retention Stop drain. `test_live_session_v2.py:267`: expired registry cannot reopen. `test_accepted_stop_lease.py:12`: accepted Stop outlives lease unchanged; resume cannot steal closing capture. New same/different cookie/account tests and concurrent/lost-response takeover tests are mandatory.

**A4 — Browser acceptance.** `phase2_acceptance_browser.py:45–57,326–350` continues to keep history observers read-only after reload; add a separate originating-capture reload → Resume → continued frames → one archive case, settings/mute/sequence/epoch/clock/gap notice assertions, cancelled picker, vanished microphone, old live tab, and Stop-before-resume. Rebuild the candidate frontend bundle before acceptance; the server serves built assets. Existing accepted ADR/tests are not rewritten in this design-only task.

## Size, risks and evidence limits

Estimate (not measured implementation size): **server 180–260 lines; client 220–340; backend/frontend regression tests 350–550** plus documentation. Covers accessors, atomic all-mutation page fence, endpoint, small capture record/adoption/UI, gap metadata/notice and summary-watcher ownership; no mixer DSP rewrite, larger buffers, new database table, feature flag, provider call or credential storage. A separate fast-gap-drain design would add work and requires a new prototype; excluded from this estimate.

**R1:** network/queue age and device-clock drift leave actual elapsed-time error unqualified; exact synthetic timeline and current browser transport are local evidence. **R2:** long-gap live transcript catch-up is delayed (30 s at 119 s gap); immediate Stop still preserves final audio in the scripted matrix, real-provider drain latency remains unmeasured. **R3:** exact physical mic/tab continuity cannot be guaranteed from `default` aliases or opaque labels; Bluetooth/unplug, chooser cancellation and real crash need acceptance. Browser restart restoring sessionStorage/cookie, expired/server-restarted meetings, summary worker transfer, real provider state/recognition after silence, lease/revocation race stress and product UI/built bundle are not qualified by this prototype. Server expiry and accepted Stop retain their existing terminal rules. No full backend/frontend suite run: no product code/test change or final commit; these are local protocol/browser bench measurements, not product certification.

Frozen final receipts: `evidence/P74/resume/SUMMARY.json`; protocol `runs-20261002-120610/matrix.json`; boundaries `boundaries-20261002-120628/result.json`; browser `browser-20261002-120628/result.json`, `interrupted.png`, `resumed.png`. Earlier runs/failed share-label equality remain separate evidence; no adverse S1 result was discarded. The corrected summary removes the false premise that a media track label is a stable source identifier; it does not assert exact automatic tab restoration.

## P74-RS server product replay (2026-10-02)

The original prototype above is frozen history (commit `61ca865a`); `de54d1b2`
integrates the binding product base `c7884d46`. The current default
`measure.py` command (also `--product`) now runs the PRODUCT resume endpoint,
without `ResumeProtocol` middleware or private capture-state reads.
`--summarize` still reads the retained original protocol/browser receipts.
Only the server protocol matrix is requalified here; Chrome restoration is RC work.

One command: `PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f3.venv/bin/python prototypes/gemini-live/long-meeting/resume/measure.py --product`.
Four 4 s continuations: 16/16 frames, one exact 13/38/98/127 s MP3 at
5/30/90/119 s gaps, zero interior gap amplitude, same engine/name/meeting,
completed. 125 s refuses and stays interrupted. 119 s +45 s: 180/180 frames,
168 s MP3, 472000/960000 retained samples, first resumed live row after 30 s.
The adopted snapshot and saved document include interruption bounds, and
ordinary owner-bound/headerless tests retain their expectations. Full product
regressions and full-suite receipts are indexed by P74-RS-STATUS.md.

Product verdict: PASS at $0. New regression matrix: 26 failures on `c7884d46`,
all green on the candidate; one headerless normal-meeting control green on both.
Full backend command from R5B-COMMON: 2945 passed, 9 skipped, 2 xfailed,
37 subtests passed in 437.80 s. No existing test expectation changed.
Final product matrix: `evidence/P74/resume/RS-product-20261002-141816/matrix.json`;
full suite: `evidence/P74/resume/RS-full-backend.txt`.
