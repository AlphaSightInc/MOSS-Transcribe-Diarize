# One attended MOSS session — operator plan

**Reserve approximately two hours; this is an estimate, not a completion promise.**
The goal is to measure physical capture, identity and usability on one identified
candidate. Passing automated tests cannot show whether a real microphone hears the
operator correctly while speakers play. Unavailable prerequisites stay blocked.
No deployment, renewal, service restart or fallback is authorized by this plan.

## Before the sitting

- **A1 — Engineer preparation:** freeze and record installed/served candidate SHA,
  target origin, browser version and active configuration. Complete available local
  checks first; retain failures. Integration source at this plan's writing is
  `c609d7f3`; do not assume the host serves it. Arrange existing G7 collector/profile
  and any host authority separately; the older runbook's example SHA is historical.
- **A2 — Trust and equipment:** MacBook with physical microphone, headphones and
  speakers, Chrome, working system-audio share. Use normal trusted TLS on the exact
  target origin per [WP13 runbook](tls-renewal-runbook.md). Historical 7861 was
  self-signed; 7862 trusted does not qualify 7861 or establish candidate identity.
  Stop if Chrome warns; no certificate exceptions or loopback bypass for target use.
- **A3 — Inputs and privacy:** public playback clip with exact reference, a quiet
  room, and operator consent for recordings. Fix microphone position, OS gain and
  speaker volume; record these plus requested/actual echo-cancellation setting.
  Provision an OpenRouter key privately in the browser for Gemini 2.5 Flash Lite;
  never paste it into commands, chat, screenshots or Git. Confirm whether configured
  relay fallback is reachable; it is a separate explicit selection.
- **A4 — Evidence:** keep audio, lane PCM, full transcripts, cookies and screenshots
  with content private. Share only candidate/configuration, counts, timings, condition,
  fixed error codes and pass/fail/reason. Redact screenshots before review. No private
  test input or raw provider response belongs in the campaign repository.

## Ordered sitting (120 minutes estimated)

| Step | Estimate | Operator action and retained outcome |
|---|---:|---|
| A5 Trust/readiness | 10 min | Confirm candidate and normal Chrome trust; check mic and shared-audio meters; record actual devices/routes. Prerequisite failure stops dependent capture. |
| A6 Speakers echo protocol | 30 min | Six conditions below; human-operated recording and scoring on an authorized decoder endpoint. |
| A7 G7 x2 | 30 min | First headphones, then speakers with AEC on. Each G7 run includes BOTH tab+mic and entire-screen+mic scenarios, so four scenario captures overall. |
| A8 Visual and summaries | 20 min | Three viewports, dialogs, failure copy and summary checks below. |
| A9 Voiceprints with AEC mic | 20 min | Enroll/recognize/unknown/delete/pending cases below; measure visible name time. |
| A10 Decisions/evidence | 10 min | Record failures, denominators, unresolved items and operator judgments; stop owned recorder/collector/tunnel processes. |

Retries, provider latency or unavailable screen-audio support can extend or prevent
completion; retain the first failed attempt. Two G7 runs is not two isolated meter
checks: each must satisfy its full collector predicates on its actual route.

### A6 — Echo first: actual speakers, AEC on and off

Use [WP3 attended protocol](attended-echo-protocol.md) and its existing recorder:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> scripts/attended-echo/measure.py serve
```

Open its printed loopback recorder page; Start/share/Stop are human actions. For each
AEC setting (on, off), record (1) playback only, operator silent; (2) operator phrase
alone, playback paused; (3) both together (double-talk). Same complete public excerpt,
under 60 s, at fixed volume/position. Read the recorder's displayed phrase once:
“The quiet blue river passes seven old bridges while the morning train carries fresh
oranges into town.” This is the echo phrase, separate from G7's phrase below.

Confirm actual track settings match the requested AEC setting and inspect block
clocks/meters for drops. Save all six private recordings. The protocol's `score`
command compares system, mic and production-style mono on the SAME recording,
at most three serial decoder calls each (up to 18 total); run only with the agreed
endpoint/budget. Report ordered omissions/additions/reference denominators, unique
word retention and timings. Playback-matching mic words support echo leakage;
unmatched words may be decoder additions. Shared vocabulary needs human review.
Compare near-alone against double-talk at each AEC setting. WP3's suppression
prototype failed; there is no suppression toggle to enable. Correlation remains
optional telemetry, never a remedy or acceptance witness by itself.

### A7 — G7 twice, with the real operator

Follow [G7 runbook](g7-preadmission-runbook.md) with the engineer's exact candidate
and collector configuration. Its cutover commands need separate host authority;
this plan does not run them. First complete headphones, then speakers+AEC on.
For EACH run: microphone+meeting tab AND microphone+entire screen with shared audio.
Unavailable entire-screen audio is blocked, not replaced with a tab.

Have both sources audible before the first readiness Enter (meter window 10 s).
After Start: pause playback and read **Copper planets orbit distant stars above
violet gardens** alone; confirm its end. Stay silent while playback speaks alone;
confirm. Only then overlap sources. Let the collector control Start/Stop; never
script Enter, fake the mic, or substitute prerecorded operator attendance.

Final saved transcript must contain at least **7/8 phrase words in order under one
operator speaker distinct from all tab-only speakers**. Six words/reversed order,
missing tab witness or collapsed identity fails even if meters and speaker counts
look right. Existing frame continuity, finalization, ownership and playable MP3
predicates still apply. Record route-specific collector verdicts, phrase count,
reference-word errors and Stop→saved times. Reopen and compare exports. Preserve
every failed attempt; no route's pass substitutes for another's.

### A8 — Visual sign-off and real summaries

Operator reviews the actual served app at **1440x900, 1280x800 and 400 px width**:

- **V1:** workspace layout, scroll/overflow, selected-meeting header and history;
  live/provisional/saved text, system/microphone lane badges and cross-lane overlap.
- **V2:** rename, enrollment and settings dialogs; focus, buttons, checkbox, disabled
  state, cancellation and readable errors; exactly two Refresh controls in Voiceprints.
- **V3:** invalid media and unreachable/404 URL show safe causes in History AND
  selected meeting; speechless media says no speech; known truncated-media notice.
- **V4:** Gemini 2.5 Flash Lite selected using browser-owned key; final summaries for
  50 s and 180 s public transcripts; check five-field validity, timestamps, names,
  source fidelity, retry/cancel/title and reload persistence. Deliberately select and
  check configured relay separately if available; no silent provider switching.

Record sign-off or specific remaining defects per viewport. Automated geometry is
supporting evidence only. A missing key leaves summaries blocked; a schema-valid
summary still requires the operator to read it against the source.

### A9 — Voiceprints through the actual AEC microphone

Use a scratch private workspace and existing WP7/WP17 cases. Keep AEC on and record
actual settings. Known public playback can exercise system enrollment; the operator
supplies real mic speech. Recognition bank is workspace-private; lane speaker IDs
remain independent even when both routes recognize the same saved name.

- **VP1:** enroll eligible mic speech, start another meeting, measure first visible
  correct name against the existing <=4 s requirement. Record API and visible times
  separately if both are available. Repeat with system enrollment -> mic recognition;
  optionally complete mic->system and system->system routes with known source speech.
- **VP2:** unknown voice must abstain; delete the known profile and verify next capture
  does not restore its old name. Re-enroll: new profile; add another eligible meeting;
  immediate repeat must not duplicate the same sample. Reopen saved names/exports.
- **VP3:** short/provisional evidence may remain pending; **2 s eligible speech is
  not 2 s recording duration**. Exercise pending enrollment and explain it rather than
  lowering thresholds. Duplicate names must not merge canonical identities.

WP17's 4/4 API routes used synthetic replay, not AEC mic or browser paint. Record
quality/latency for this real device separately; do not import its 3.53 s as a result.

## Decisions after the evidence

| Code | Question and consequence |
|---|---|
| P3 / D2 | Define retention bar AND exact reference/input population before any new acceptance run. Existing WER bounds remain unchanged; observed misses cannot be rounded/averaged into pass. Recommend retaining present bounds until explicitly adjudicated. |
| P4 | If speakers+AEC still loses quiet speech or leaks playback, choose measured repair work or explicitly amend route support. Headphones currently cannot waive required speakers support; no mono fallback is authorized. |
| D3 | Is shared/open workspace only internal convenience or supported product mode? Recommend retaining browser-private production scope until explicit amendment plus mode-specific evidence. |
| D5 | Is safe file/URL failure explanation release-blocking? Repairs now exist and have local/browser evidence; decide release gating explicitly, with final-candidate examples. Recommend requiring understandable failures. |

End with pass/fail/blocked for each planned item and a named owner for unresolved
work. Attendance, visual approval, provider correctness and release authority stay
separate judgments. This sitting alone is not final capacity or deployment approval.
