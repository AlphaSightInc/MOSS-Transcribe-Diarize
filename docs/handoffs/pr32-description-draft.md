# PR #32 description draft — integrated repairs, acceptance incomplete

Separate source decoding preserves quiet microphone speech that the mono mixer could
erase. The integrated candidate now includes faster Stop identity mapping, terminal
identity fallback, capture setup recovery, faster file identity resolution, bounded-audio
failure reporting and local durability evidence. **Live word accuracy and capacity still
fail measured gates; whole-product acceptance remains incomplete.**

Local draft only; no GitHub write. Source pin **`a625d1a17d103fd522fb734335aa691aa09085f7`**,
as of WP34’s 2026-09-18 09:04:52 UTC snapshot; **WP31 accepted and merged**.
WP25/WP30/WP33 remain in flight. WP8’s documents were imported by WP23; its branch
was not merged. This source pin does not identify a deployed runtime.

## Retained evidence

- **F1 — Speech and saving:** independent system/mic identities, lane-aware history
  and five exports, exact-zero dispatch guards. Lead ladder at `1745b96f`: all five
  overlap cases retain 37/37 system and 32/32 mic unique witnesses, n=1 each;
  vocabulary retention is not ordered word accuracy. WP26 replay recovers 2 segments /
  16 words with 54/54 prior assignments and 56/56 word/time/lane rows unchanged.
- **F2 — Stop and memory:** merged WP12 Stop 3.788534/7.490138/16.964282 s at
  24/60/180 s. WP22 real 30-minute run saves 6269 words and 1800 s MP3; Stop
  101.697916 s under contention. Capture RSS near 5/15/30 min 932.4375/981/973.25 MiB;
  post-final 1148.953125 MiB. WP29 second stub session adds 25.6875 MiB; owner unknown.
- **F3 — Files and exhaustion:** WP28 15-window resolver 93.031965 s versus serial
  320.838881 s; full output equality on two fixtures, remaining attribution errors
  unchanged. WP29 9/9 exhaustion cases preserve committed text and truthful partial
  audio; seven affected completed meetings retain an unavailable-refinement notice.
- **F4 — Capture and presentation:** WP27 early-Share errors survive setup and late
  completion; 15/15 error traces offer Reset. WP24 52 states ×3 viewports =156 captures,
  zero measured contrast/overflow/name failures; owner sign-off pending. Pre-session
  track ending remains WP32 F2, assigned to WP33.
- **F5 — Durability:** WP31 fresh reopens 13 stores/60 meetings, preserving 47 old
  transcripts and 13 new meetings. Base rollback reads 8/8 but shows 0/8 lanes and
  exports 32/40: reduced-capability reader only. Active DB-only copy is not safe backup.

## Validation and open failures

[Campaign ledger](mvpfix-campaign-20260918.md) has **34 rows**, exact branch pins,
source verification counts, file inventories, failures and limits. WP34 preparation
on this integrated base: **1945 Python passed, 5 skipped, 37 subtests; 265 frontend
passed /28 files**. WP34 fresh document spot-check is recorded separately under
`docs/verify/wp34/`; preparation is not fresh-context verification or runtime qualification.
The lead’s reported progression 1865→1901→1910→1919→1920→1941 is preserved in the
ledger as brief-reported: those numbers are absent from merge/build commit messages.

WP25 long workspace alternation final system **11/106=10.37736%** versus **9.5074%**
bar; separate standalone/fresh checks report **9/106=8.49057%**. Immediate mic
**11/53=20.75472%** exceeds **16.6655%**; overlap final system **13/106=12.26415%**.
WP17/WP20 endpointing hypothesis was falsified. WP25 4×600 **0/4**, contended drain
exceeded the harness’s 90 s Stop observation limit before terminal start; clean rerun
pending. WP32 F1–F5 remain open at this integration pin; WP33 assignment is not a fix.

## Not claimed

- **N1:** Deployment, current trusted target Chrome/TLS, renewal activation, host reboot,
  cutover/CI, tracker closure or release authorization.
- **N2:** Attended G7, physical speakers/AEC, native hidden-tab continuity, physical
  voiceprint acceptance or owner visual sign-off; same-lane simultaneous-speech recovery.
- **N3:** Final-SHA capacity, fast 30-minute Stop, post-final/repeated-session memory
  bounds, complete live backup, lane-faithful base rollback or an all-passing bundle.
- **N4:** Live Gemini 2.5 Flash Lite 50/180 s functional/semantic summary acceptance;
  browser-owned key still required. A required-row SKIP is not acceptance.
- **N5:** Resolution of P3 retention, P4 speakers fallback, D3 shared workspace, D5
  failure-gating or P5 same-lane scope; no quality/identity/readiness threshold relaxation.

Use the [attended plan](attended-session-plan.md), [known limitations](../known-limitations-20260918.md)
and [durability runbook](../data-durability-upgrades.md). WP21’s
`bash scripts/mvpfix-qualify.sh` is now integrated; WP25 bench parameterization is still
in flight. Inspect FAIL/SKIP/UNRUNNABLE and request-budget limits; command availability
or status comparison does not establish qualification. No `Closes #...` declarations.
