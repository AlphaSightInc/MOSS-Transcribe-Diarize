# WP1 initial checkpoint — INCOMPLETE, NOT ACCEPTED FOR PRODUCTION

Question: does serial lane decode plus lane-scoped identity and lane revisions
preserve lane words/speakers through Stop -> saved, at what span cost?

Nine real Live API experiments completed; 196 decoder requests. Production source
remains unchanged. No whole-design PASS or falsification is established. The
200-request ceiling prevents the remaining requested cases and fixed-build rerun.
An increase to 650 was requested; no answer received at this checkpoint. Do not
interpret elapsed time, this note, or a fresh verification session as approval.

| Case | Prototype | Final system/mic words | Stop -> final seconds |
|---|---|---:|---:|
| same voice | v1 | 86 / 86 | 2.891 |
| parity | v2 | 86 / 56 | 9.672 |
| system alone / mic digital zero | v2 | 86 / 0 | see system_control.json |
| mic alone / system digital zero | v2 | 0 / 56 | 4.822 |
| mic -10 dB | v4 | 86 / 56 | 11.685 |
| mic -15 dB | v4 | 86 / 60 | 12.020 |
| system -10 dB | v4 | 84 / 56 | 11.898 |
| system -15 dB | v4 | 86 / 56 | 11.269 |
| Stop mid-speech, 12 s | v4 | 38 / 31 | 8.611 |

All nine saved text/identity sequences equal their final live surface. All seven
two-active-lane cases end with two distinct speaker IDs and zero unattributed
final words. Saved source_lane provenance is absent: WP2 owns that consumer.
Derived saved lane scoring uses a unique final speaker-to-lane association.

Vocabulary against UNITY-GAIN lane-alone controls: parity 50/50 system and 45/45
mic; mic -10 and -15 retain 50/50 and 45/45; system -10 retains 49/50 and 45/45;
system -15 retains 50/50 and 45/45. These are different candidate versions and
control gains, not paired accuracy equivalence. Stop's 12 s versus 24 s control
is explicitly marked unequal extent and cannot establish retention.

80 measured individual 2.5 s decoder calls (v4): median 0.170431 s, maximum
0.963155 s. This excludes identity and queue latency, and is not two-lane total
span latency. Both-live 24 s cases consumed 26 requests = 65 requests/capture
minute; single-active-lane controls consumed 13 = 32.5/min. Mono baseline cost
was not remeasured. Observed v4 pending signals max 1, canonical queue max 1;
point-in-time sampling cannot establish an unseen peak.

Exact clipped WER remains unmeasured: supplied reference sentence boundaries
cross 24 s (system 29 s; mic 25 s). scores.json includes ordered substitutions,
omissions and additions against overlapping reference rows, with that bias
explicit. At mic -15: 0 substitutions, 1 omission, 10 additions / 51 reference
words; this is not proof that all 10 additions are hallucinations.

Unrun: noise, 48 s alternation, reshare; final-version same/parity/controls;
full production implementation and its unit, phase2, e2e and full Python tests;
bounded-memory exhaustion/release tests; lane-failure injection; fresh /new
verification of a completed fix. Existing unchanged-source control: 70/70 tests.

Known prototype limitations requiring work before production: generic provider
errors are swallowed per lane; no complete failure diagnostics; latest pending
identity observation across a silent-lane transition needs commit-time reconcile;
revision failure/empty outcome handling needs explicit coverage; no draft producer
extension; memory bound is an arithmetic tape-buffer bound, not measured peak;
first versions used time projection at revision seams, fixed only in v4. Thus the
same-voice v1 result is not acceptance of the final candidate. No numeric policy
or production lifecycle changes have been adopted.

Failed attempts: generated overlay signature SyntaxError caught before server
start; corrected. One ad hoc saved-count print command had SyntaxError; corrected.
Initial snapshot queue fields were absent (null); v4 uses actual runtime arbiter
and scheduler instrumentation. These absences are not reported as zero evidence.

## Resume authorization

Fable/user raised the total cap to 650, retaining <=2 in flight, one meeting,
queue check before each batch, and tunnel teardown between paused batches.
196 historical requests count against that total. Ordered WER now uses full
reference text as instructed; no decoder requests spent on alignment.
Falsifiers execute in order: same voice, zero mic, noise mic, alternation,
mid-speech Stop, reshare. Any failure stops the production fix.

## Resumed verdict — listed falsifiers passed; proceed to production implementation

11 resumed real-stack experiments: same/zero/noise/alternation/Stop/reshare on v5;
noise again after removing an identity-dependent word-erasure path (v6); parity,
mic -10/-15, system -10 on v6. No listed falsifier failed. This is not a numeric
accuracy acceptance bar. 467 requests total including the historical 196.
Saved/final text and identity sequences agree in all 20 retained experiments.

Same voice v5: 86/86 words, speaker-0001 vs speaker-0002. Zero/noise: no mic words
or identities. Alternation: 86/69 words, one system and two mic identities.
Stop: 38/31. Reshare: 86/56. v6 parity 86/56, mic -10 86/56, mic -15 86/60,
system -10 84/56. System -10 Stop->final 33.139640 s, canonical queue max 3.
All raw results remain separate by version/run ID. Source-lane provenance is
still derived from exact saved/final positional correspondence, not persisted.
Full-reference edit counts include omitted, unplayed reference audio, as directed.

A further LOGIC prototype (failure_state.py; zero provider requests) exercised a
system-lane failure at a rolling boundary with an existing segment crossing it.
The failed lane's original words, identity and full timestamps survived while
mic revisions applied in 2/2 successive windows. The system decoder was attempted
once, mic twice. Per-lane publication frontiers are necessary: one global frontier
would suppress the failed lane's committed suffix. The existing stop-on-refinement-
failure rule now applies to its producing lane. See failure-state.json for all
states; this policy/structure is measured before production absorption.

The passing experiment can now be absorbed. Remaining implementation defects and
unit/fault coverage must be resolved before any production acceptance claim.
