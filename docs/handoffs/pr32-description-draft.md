# PR #32 description draft — integrated repairs, acceptance incomplete

Separate source decoding prevents the mono mixer from erasing an entire quiet microphone
lane. The integrated candidate keeps lane provenance through saved transcripts and five
exports, repairs capture/Stop failure handling and voiceprint observation lifetime, and
uses a canonical speaker album for recurring voices across file windows.

**Local draft only; no GitHub write. As of integrated SHA
`c609d7f3e03091becda8aa8588655447a51ea434`, 2026-09-18.** WP19 is accepted and merged.
WP12, WP21 and WP22 are not merged; WP8's documents are imported/refreshed by WP23.
This pin is source provenance, not the identity of a deployed runtime.

## Claims backed by retained evidence

- **F1 — Lanes and saved consumers:** WP1/WP2/WP10/WP11 preserve source identity and
  legal cross-lane overlap; exact-zero dispatch does not discard nonzero quiet speech.
  WP11 export oracle 50/50; WP14 real downloads five formats each 6/6 turns; WP16
  50/50 exports. WP8's old oracle defects and expected-overlap-failure loophole are repaired.
- **F2 — Capture and durability:** WP3 releases failed browser capture resources;
  WP14 explains lease expiry; WP15 moves accepted Stop completion out of helper lease
  authority. One unpaused 600 s run saved 2589 words and a 600 s MP3; Stop took
  179.408107 s. That is successful completion, not fast finalization or 30-minute acceptance.
- **F3 — Files:** WP4/WP16/WP18 supply safe causes, digital-silence completion,
  upload-capacity preflight and detected-truncation notice. WP19 same-input file
  identities improve 7->3 at six minutes and 31->3 at 30 minutes. Attribution is
  84/92 and 420/464 correct segments; text/time unchanged. Fifteen-window resolver
  costs 332.007926 s including embedding; local diarization errors remain.
- **F4 — Names:** WP9 allows owner naming after Stop; WP17 preserves observations for
  private voiceprint matching. Four API recognition routes measured 3.5264–3.5283 s.
  WP19 adds explicit File enrollment from retained audio using existing admission.
  These are not physical-mic or browser-render latency measurements.

## Verification and remaining failures

[Campaign ledger](mvpfix-campaign-20260918.md) retains every WP1–WP22 commit range,
changed-file population, exact verification counts and failed attempts. Full branch
counts differ with source population; they are not added together. WP19 fresh checks:
**1889 Python passed, 2 skipped, 37 subtests; 249 frontend passed; lease 20/20**.
Those are WP19-branch results, not a final integrated qualification run. Lead's
first-parent messages record frontend 230/230 at `a92bb4aa` and focused export
22/22 at `79467f08`; no full-Python final-head count is present there.
WP23's local integrated-base suite passes **1901 Python tests, 2 skipped,
37 subtests; 249 frontend tests**. Logs in `evidence/mvpfix/wp23/`; fresh document
spot-check under `docs/verify/wp23/`. This does not supply live acceptance.

WP17/WP20 each retain **0/2 passing full quality cases** under unchanged immediate
16.6655% and final 9.5074% word-error bounds. WP20 overlap system is 24/106 immediate
and 13/106 final errors. Endpointing did not explain the reported overlap defect;
no endpoint change was promoted. WP6's four-session run completed only 2/4 with
foreign-load pauses; no eight-session or final-SHA capacity acceptance.

## Not claimed

- **N1:** Deployment, trusted target Chrome/TLS, certificate renewal activation,
  cutover, CI, tracker closure or release authorization.
- **N2:** Attended G7, speakers/acoustic echo cancellation, native hidden-tab continuity,
  physical voiceprint acceptance or operator visual sign-off.
- **N3:** Final-SHA capacity, 30-minute memory plateau/durability, accepted WP12 Stop
  optimization, or an all-passing local qualification bundle. WP21 is pending integration
  and its retained first dry run stopped before decoder use.
- **N4:** Live Gemini Flash Lite functional/semantic summary acceptance. The 50/180 s
  check needs an operator-supplied browser key; relay availability is separate.
- **N5:** Resolution of P3 retention, P4 speakers fallback, D3 shared workspace or D5
  failure-gating decisions. No quality/identity/readiness/lease threshold relaxation.

## Next evidence

Use the [attended plan](attended-session-plan.md) for the operator sitting and
[known limitations](../known-limitations-20260918.md) for exact remaining limits.
After WP21 lands and the final candidate is frozen, `bash scripts/mvpfix-qualify.sh`
is the planned local bundle command (not available at this integrated pin); respect
its explicit UNRUNNABLE/SKIP statuses and own-port/budget requirements. It does not
replace attended or deployed acceptance. No `Closes #...` declarations yet.
