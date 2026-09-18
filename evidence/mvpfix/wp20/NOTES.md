# WP20 verdict: reject lane-local endpointing as the overlap remedy

**No production fix promoted.** The reported full-reference overlap uses identical
mixed and lane-local speech boundaries for both lanes. Its extra immediate errors
are attributable to an unfinished canonical tail; its final error persists when
the same lane tape is decoded alone. No threshold/policy change is justified.
Branch: mvpfix/wp20-lane-endpointing. Measured production base: de35ef365724caad47c407bd41c34e21182d20c7.

## F1 — the structural question and measured answer

Question: does the other lane move boundaries and thereby damage this lane?
Necessary primitives: admitted source PCM, endpoint interval, decoder response,
published surface, independent reference. The recording/accounting mono is distinct
from source audio and from publication. Existing WebRTC mode 1, silence/speech
thresholds, 40000-sample hard cap, token cap, identity, readiness, lifecycle, nine-key
frame protocol and QUALITY_BOUNDS remain unchanged. No live_vad.py exists here;
the actual existing VAD is WebRtcSpeechProvider in live_provider_bundle.py.

Shadow policies observe the exact admitted PCM separately for each lane, on the
real stack, with existing VAD and endpoint config. They partition the complete
sample timeline. Standalone replay then decodes those partitions through the
production bounded inference/silence/salvage adapter. 191 local spans: 56 all-zero,
154 exact-PCM-and-reason reuse from independently replayed results, 37 new spans
of which 9 are zero and cause no decoder call. All partitions gap-free and <=40000
samples. This is an endpoint logic prototype, not a modified production scheduler.

Full-reference overlap: system 12/12 nonzero boundaries identical, microphone
10/10 identical. Every local canonical word equals the baseline canonical words.
The proposed mechanism is falsified for this reported case. At 24 s overlap,
system 10/10 and microphone 10/10 intervals also match. At 48 s overlap, system
20/20 still match; microphone boundaries do change, with 10 differential word edits
against 133 baseline words. Those are NOT ground-truth errors or a proven gain.
See span-details.json for every span, reason, word count and standalone difference.

## F2 — per-stage quality, full independent references

WER = (substitutions + omissions + additions) / reference words. System 106 words;
microphone 53, using the accepted WP17 correction unchanged. Canonical-all is
measured after every span including Stop flush; it is not the immediate surface.
Local-canonical-all is the shadow intervention; no candidate live surface is claimed.

| Case / lane | Published immediate | Canonical pre-Stop | Canonical all, mixed -> local | Published final / reopened | Same-boundary terminal alone |
| --- | ---: | ---: | ---: | ---: | ---: |
| Alternation system | 16/106 | 18/106 | 18/106 -> 18/106 | 9/106 | 11/106 |
| Alternation microphone | 11/53 | 15/53 | 11/53 -> 9/53 | 5/53 | 5/53 |
| Overlap system | 24/106 | 26/106 | 18/106 -> 18/106 | 13/106 | 13/106 |
| Overlap microphone | 6/53 | 9/53 | 9/53 -> 9/53 | 5/53 | 5/53 |

Alternation immediate 15.0943% / 20.7547%; overlap immediate 22.6415% / 11.3208%.
Final alternation 8.4906% / 9.4340%; overlap 12.2642% / 9.4340%.
Existing exact bars remain immediate <=16.6655%, final <=9.5074%. Both complete
cases FAIL overall; final/reopened lane scores equal in both. No after-fix quality
claim: there is no promoted fix. The narrower alternation mic canonical gain is
2/53 errors; its 9/53=16.9811% still exceeds the immediate bar and does not address
the reported overlap problem.

Horizon isolation: overlap pre-Stop accepted 28.5 s, committed 27.5 s, rolling
frontier 20 s; the final 1.5 s of the 29 s source has not committed. The corresponding
system canonical score is 26/106 versus 18/106 after its tail commits: eight extra
omissions. Alternation's system finished much earlier, so all its system spans are
already committed. Rolling replacement improves both system scores by two errors
(18 ->16 and 26 ->24). The observed eight-error immediate gap is thus explained
without a boundary change. Earlier WP17 33/106 is not reproduced exactly; snapshots
are scheduling-dependent. No horizon relaxation or quality-bar change made.

## F3 — standalone and terminal-window isolation

179 actual producer windows independently replayed with identical lane PCM and
geometry: canonical 137/137 exact word equality; rolling 30/30; terminal 11/12.
The one different terminal window is alternating system (two word edits, 104 baseline
words). This is retained variability, not silently retried into a pass.

The system tapes share exactly 464000 samples (29 s); alternation adds exactly
400000 zero samples (25 s). No speech PCM differs. Two additional paired controls
through the real WindowedRunner, each one terminal window:

| Trial | Alternation, 54 s | Overlap, 29 s |
| --- | ---: | ---: |
| 1 | 9/106 | 13/106 |
| 2 | 11/106 | 13/106 |

The baseline alternation was 9/106; first standalone replay was 11/106. Thus the
final difference survives without any coordinator, identity assignment or lane
merge and varies with decoder silence context; model variation also occurs on the
identical 54 s tape. No claim that lower SNR alone caused it: SNR was not measured.
No 150-second terminal seam occurs in these <=54-second runs. Fixed ten-second
rolling intervals also reproduce alone; no mixed VAD is used by their planner.

## F4 — 24/48-second controls and latency limits

These reproduce WP17's duration inputs exactly: alternation zeroes the opposite
half on the source clock; overlap retains both full clips. They are different
speech populations from each other and from the full-reference captures. Arbitrary
24/48-second cuts lack exact reference words; per-span ground-truth WER is
UNMEASURED, not inferred proportionally or from the decoder's own transcript.
Complete corpus reference rows are coarse; they do not supply word timestamps.

| Duration / case | Local vs mixed system edits | Local vs mixed mic edits | Stop -> observed final | Maximum sampled pending work |
| --- | ---: | ---: | ---: | ---: |
| 24 s alternation | 0/39 | 6/30 | 5.411 s | 1 |
| 24 s overlap | 0/83 | 0/61 | 11.389 s | 2 |
| 48 s alternation | 0/83 | 13/73 | 10.501 s | 2 |
| 48 s overlap | 0/155 | 10/133 | 18.697 s | 2 |

Denominators here are baseline output words, NOT truth. The 24/48 controls' 8/8
terminal and 20/20 rolling standalone replays match; all actual stage counts are in
stage-summary.json (the full-reference runs account for the remaining windows).
Pending work sampled every frame is not a continuous arbiter queue high-water.
Full-reference Stop times: alternation 11.466 s, overlap 10.851 s. All 6/6 captures
complete/final; no frame, heartbeat or Stop failure. Stop body was deadline 30.

WP12's separately retained candidate reports 24 s parity Stop 3.788534 s and
180 s 16.964282 s; its final report says candidate remained isolated. This WP20
base still has serial lane terminal decoding. Different code/input/load prevents
calling that historical candidate a matched regression control. No local-endpoint
scheduler was promoted, so its queue/Stop/readiness effects remain UNMEASURED.
The explicit no-overlap-win falsifier stops implementation before those gates;
we do not substitute a shadow scheduler estimate for a production timing result.

## V1 — verification, budget, boundaries

Initial full Python: 1874 passed, 2 skipped, 21 warnings, 37 subtests passed,
149.29 s. Skips: operator identity corpus and real F-cert speaker corpus absent.
Frontend: 244 passed / 27 files, 2.71 s. Typecheck/build pass; assets byte-unchanged.
Retained evidence audit PASS; product quality FAIL. No production or test edit.
Relevant controls detect stale evidence, changed hard caps, wrong-tree imports,
product/policy modifications, regression failures, and leftover owned listeners.

Requests 390/500 =179 baseline +179 standalone producer replays +28 new nonzero
local partitions +4 paired padding requests. At most two in flight in the stack;
replays serial after server shutdown. GPU admission metrics idle before both runs.
Owned server PID39790 and SSH PID39215 stopped; ports 17880/18120 no listeners.
No push/merge/deploy/GitHub/shared-service action. Read-only WP12 history and shared
corpus/model/dependencies; all created data in this worktree. No private audio or
transcripts in Git. Exact reproduction commands in COMMANDS.md.

Deviations/limits: scripted states instead of interactive TUI; prototype uses
shadow endpointing plus production-decoder replay rather than replacing production
scheduling, because the requested overlap mechanism failed its falsifier. Per-span
WER requires independently aligned word references, currently unavailable. No
candidate immediate/final or latency acceptance invented. Fresh /new verification
is recorded separately in docs/verify/wp20/VERIFY-RESULT.md when executed.

## V2 — fresh-context verification completed, 2026-09-18

Tested 8b46938aedc97fc50167f08ceb7838def0a159a6 in the clean WP20 tree. Audit PASS;
prototype REJECTED_NO_OVERLAP_WIN; product quality FAIL. Raw-surface scores match
6/6 records (12 lane scores); raw padding scores match 4/4. Full Python 1874 passed,
2 skipped, 21 warnings, 37 subtests passed in 150.98 s; frontend 244/27 files in
2.62 s; typecheck/build PASS; assets unchanged; listeners absent on 17880/18120.
Zero new decoder calls; historical 390-call ledger unchanged. Report, limitations,
execution deviations: `docs/verify/wp20/VERIFY-RESULT.md`; logs: `fresh-*` here.
