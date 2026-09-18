# Known limitations — 2026-09-18

**The integrated candidate is not fully accepted.** Source pin
`c609d7f3e03091becda8aa8588655447a51ea434` includes WP19. Measurements below retain
their original branch/input scope; they are not fresh measurements on that head.
[Campaign ledger](handoffs/mvpfix-campaign-20260918.md) supplies commits, source
verification files and full counts. WER means substitutions + omissions + additions,
divided by independent reference words; identity accuracy is a separate measure.

| Code | Limitation and measured extent | What remains |
|---|---|---|
| L1 | **Immediate/final word accuracy fails.** WP17 overlap system immediate 33/106 = 31.13208%; WP20 24/106 = 22.64151%. Both final 13/106 = 12.26415%. Existing immediate/final bounds 16.6655%/9.5074%. Alternation mic immediate 11/53 = 20.75472%. Both WPs: 0/2 full cases pass. | Immediate snapshots depend on publication timing. WP20 found identical full-reference lane boundaries (12/12 system, 10/10 mic); endpointing remedy falsified, no promoted fix. Final error also occurs when decoded alone. |
| L2 | **Quiet mic additions remain.** At gain .03 (-30.4576 dB), reference correction changed 10 additions/48 words to 5/53 = 9.43396% final, only .07344 percentage points below final bound. Five omitted reference words were source-backed; remaining four fillers + repetition still count as additions. | Same PCM alone reproduces them, so those ten additions were not proved lane leakage. Human acoustic adjudication of remaining five is unmeasured. No gain/threshold fix was made. |
| L3 | **Stop cost scales with full-meeting terminal work.** WP12 24 s traced serial 11.327668 s -> concurrent acoustic 6.839325 s; later mapping candidate 3.788534 s. Earlier 60 s serial 26.635716 s; later mapping candidate 7.490138 s. Candidate 180 s 16.964282 s versus mono 12.717313 s, both above 10 s. | These are separately retained observations, not same-response controlled before/after timing at every duration. WP12 is not merged/accepted. No 180 s serial-lane before value or 30-minute after guarantee is supplied. Candidate still leaves two Lex turns/16 words unassigned. |
| L4 | **Long live completion remains slow/incomplete.** WP15 unpaused 600 s capture completed, 2589 saved words and 600 s MP3, Stop 179.408107 s. Tapes each 19.2 MB then zero; 460 calls. | 8/27 resource samples had sibling contention. Real unpaused 1800 s, 57.6 MB per-tape edge and final-SHA timing remain unmeasured. WP12 timings cannot be substituted into this different run. |
| L5 | **File speaker repair costs CPU time and is imperfect.** WP19 resolver includes embedding: 62.894428 s/3 windows; **332.007926 s/15 windows**. Same raw decodes: 6 min 7->3 IDs, 30 min 31->3 IDs; 84/92 (91.3043%) and 420/464 (90.5172%) segments correct. Reference-overlap time 95.2875%/94.5394%; zero abstentions. | Repeated public clips test recurrence, not natural long-meeting diversity. Local decoder speaker errors persist. Old WP16 84.442–94.615 s whole-file timing predates album repair and cannot describe final throughput. |
| L6 | **Memory growth not yet explained.** WP15 server RSS first/peak/final 631.406/1201.047/1200.516 MiB over 600 s; final remains high despite released tapes. Three tape caps total 172.8 MB (57.6 MB each), not an RSS ceiling. | WP22 has no committed result at this snapshot; 5/15/30-minute structure profile, leak/allocator attribution and plateau unknown. RSS is sampled current server resident memory, not system/GPU allocation or proof of a leak. |
| L7 | **Capacity is unaccepted.** WP6 4x600: 2/4 final and 2 helper-lease interruptions; 12/32 foreign-load samples, three pauses totaling 269.986569 s. | WP15 lease repair does not retroactively pass WP6. No clean four-session/eight-session or final-SHA campaign. WP21 partial first bundle: static gates only, runner KeyboardInterrupt, zero decoder calls. |
| L8 | **Same-lane simultaneous speakers are not solved.** Independent system/mic namespaces address cross-lane overlap only; same voice across lanes intentionally receives distinct speaker IDs. | No source-separation or same-lane overlap accuracy acceptance; P5 scope remains explicit. Duplicate display names are not shared identity. |
| L9 | **Hidden capture unmeasured.** WP5 capability 0/5 native hidden observations; WP14 headed attempts also remained visible. | A visible 60-second run is not hidden-tab continuity. Need genuine native hidden state and capture/frame continuity evidence. |
| L10 | **Summary functional/semantic acceptance blocked on key.** WP4 paid calls 0; requested Gemini 2.5 Flash Lite 50/180 s check absent. WP14 summary row skipped: no configured relay models. | Browser-owned key and source-reviewed real summaries needed; schema tests/provider menu/old different-SHA provider results are insufficient. No secret should enter evidence. |
| L11 | **Attended evidence absent.** Physical speakers AEC on/off, echo six-condition matrix, G7 headphones and speakers+AEC, visual sign-off at 1440x900/1280x800/400 px, actual mic voiceprints unmeasured. WP17 API recognition 4/4 at 3.5264–3.5283 s is synthetic replay. | Follow [attended plan](handoffs/attended-session-plan.md). Browser name paint latency remains separate; no fake attendance. |
| L12 | **Host trust/operations not qualified.** WP13 historical normal client trust: 7861 FAIL self-signed, 7862 PASS trusted; local renewal controls pass, installation not done. | Current target trust, Chrome permissions, DNS renewal/reload, restore/cold boot and deployment all require actual evidence/authority. No current host claim from the old observation. |
| L13 | **Media/identity evidence has bounds.** WP16 measured audio-only M4A, not video MP4; truncation notices detect reported FFmpeg conditions, not every damaged file. WP19 File enrollment needs retained audio and does CPU embedding per request. | Missing warning does not prove completeness; missing audio makes enrollment unavailable. Saved/export equality proves persistence, not semantic correctness. |

WP12's accepted diagnosis attributes 180 s candidate Stop to 4.769188 s drain,
11.783398 s critical system terminal decoding (mic 9.257648 s concurrently), and
observation overhead. Decoder critical stage is 69.5% of Stop time; terminal
embedding falls 43.08/111.90/335.52 audio-seconds -> zero at 24/60/180 s. This does
not remove full-meeting decoding or establish acceptance of the isolated candidate.

No changed quality bars, identity values, readiness thresholds, nine-key wire
protocol, two-Refresh sentinel or lifecycle promises are proposed here. Performance
misses need explicit adjudication; lost words, wrong speakers and invalid summaries
cannot be silently recast as performance-only deferrals.
