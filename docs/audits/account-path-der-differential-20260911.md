# Account-path diarization differential — 2026-09-11

**Two mixer effects explain the measured path difference: a held final frame reduces
pre-Stop coverage, and attenuation changes endpoint/embedding windows, producing a
real extra provisional identity in Adam. Account state carryover is rejected for
this corpus path. Identity policy and QUALITY_BOUNDS are unchanged.**

## Contract

**Question:** does the account/v2 input path change the audio or identity evidence
relative to the campaign's mono runtime path?

**Primitives:** PCM samples determine what the decoder/VAD/encoder hear; committed
span boundaries determine causal embedding windows; a per-session album determines
matching; account labels name identities without defining them. Removing any one
would conflate input, timing, matching, and presentation.

**Invariants:** identical decoder and manifest; no reference labels as inputs;
normal causal identity order, rolling and finalization; no forced reconciliation
to measure counts; no changes to the host or the operator's 17861 database.

**Unknowns:** old campaign reproduction is unmeasured until scored. Local decoder
performance is not host qualification. Shared-tunnel queue load is not controlled.
One paired pass cannot estimate run-to-run variance.

**Falsifier/tools:** replay identical corpus audio through the shared bare runtime
and actual account HTTPS/v2 adapter. Equal boundaries/identity outcomes reject a
path-specific explanation. Compare mixer output sample-by-sample before attributing
a result to identity. Retain interval/match observations without changing calls.

## F1 — Path custody

Rolling recovery was already pushed at
`06a57d2f914c1aadd01e23b1c5ed28641c9fa60e`.
Content-free identity instrumentation is `463b1d66`.

`phase2_cutover.start_phase1` restores saved units; it does not synthesize a legacy
service command. The legacy transport at `56d859bb` supported BOTH direct mono
frames and v2 frames through `LiveCompatibilityMixer`. Thus Phase 1 does not
universally imply unmixed audio. This experiment uses the campaign-style **mono**
adapter of the current shared runtime, versus the current actual **account/v2**
path, avoiding an old-code/new-code confound. It does not claim to launch the old
HTTP server or reproduce the host's restored unit.

Both use the same current runtime factory, decoder endpoint through the existing
tunnel, identity manifest, and finalizer. Account service runs only on 17862 with
its own state directory `/tmp/moss-der-differential/state`; 17861 is untouched.
Draft lane remains off.

## F2 — Audio is not identical

Production `LiveCompatibilityMixer` applies -6 dB headroom to both lanes even
with a silent microphone in speakers mode. All six complete output streams match
the exact existing integer formula:
`trunc(input_int16 / 32768 * 10**(-6/20) * 32767)`.
This is attenuation plus requantization, not cross-lane interference. The mixer
also withholds approximately 0.5 seconds until final flush. Same length after
flush does not imply the same input timing before Stop.

Sample/RMS results are retained below and in input-effects.json. The isolated
controls in F5 establish which consequences affect the score.

## F3 — Account state is not runtime identity state

`build_live_runtime_factory` supplies `identity_preparer_factory`; each
`LiveServiceRuntime.create` calls it, constructing a fresh album and sweeper.
The encoder is shared; accumulated speaker references are not.
`phase2_live._transcript_document` maps account labels into display `speaker`,
retaining `speaker_entity_id`. Quality scoring reads the raw runtime's effective
transcript, not those display labels. The account identity service observes
runtime evidence; it does not feed bank matches into canonical admission.

The successful account matrix and repeated Javier runs reuse one newly created
workspace without naming/enrollment. Read-only inspection of this scratch database
finds zero voiceprints and zero voiceprint samples. Every account session begins
with zero existing canonical speakers. Two successful Javier runs in this same
workspace both yield DER .172, 1 emitted speaker, 1 birth, 1 admitted, 0 provisional
and 0 abstaining spans. This tests the actual empty-bank campaign path, not a
populated-bank user workflow; the code also shows bank labels do not feed admission.

## F4 — Count semantics

Every quality surface now retains emitted/reference count, identities born,
album-admitted count, provisional-only count and cumulative abstaining canonical
spans. An additional unattributed-segment count distinguishes deferred attribution
from whole-span abstention. No names, vectors, or transcript text enter this
projection. Missing provider instrumentation is null, not zero.

Album counts are cached after existing preparation/commit and final reconciliation.
Snapshot reads never reconcile pending vectors or embed audio. Hence pre-stop
counts preserve the existing reconciliation schedule; final includes the normal
last reconciliation. Birth and abstention totals survive bounded event eviction.

Validation before rebase: **1,421 Python tests + 37 subtests passed, 2 existing skips**.
The required quality fixture was corrected from `{}` to a valid reference row.
No frontend code or acceptance thresholds changed.

## F5 — Isolated causal controls

Ackman settled DER: mono .122667, account .152500. Both emit two speakers. Mono
commits 60 seconds; account accepts 59.5 into the canonical runtime and commits
57.5. Last settled text ends at 57.44 seconds; both final texts reach 59.94.
On the common committed 57.5-second prefix, DER is .127652 mono / .115652 account.
This diagnostic crop does not replace the full-corpus gate: it locates the error.

Keyu settled DER .089167 / .140833, final .079000 / .074333. Common-prefix DER
.091130 / .103478: a smaller interior difference remains alongside the held tail.

Adam is different: settled DER .091167 / .119889, speaker confusion .004444 /
.030444, emitted speakers 2 / 3. Account has 3 births, 2 admitted, 1 provisional;
mono has 2 births, both admitted. Account final emits 2 but still retains the
third provisional identity in its registry/album. Final text covering the corpus
does not imply that a provisional identity was merged away.

First Adam endpoint difference: original [32.5,35.0), mixed [32.5,33.28).
Account span 18 is [41.35,42.89), with a 1.22-second embedding interval and best
existing-speaker score .1954222813, below unchanged .35. It births identity 3.
Mono instead embeds 2.34 seconds in [40,42.5), matching speaker 2 at .5925375250;
the following .39-second span contains no eligible interval. This is measured
evidence/window divergence, not workspace-name carryover. The attenuation-only
Adam replay reproduces exactly the same 18 provider observations through span 18
(boundaries, embedding intervals, existing counts and best scores; elapsed time
excluded), including .1954222813044011 and identity 3. It has no account layer and
no held frame. Settled DER .123944, 3 emitted / 2 reference, 2 admitted + 1 provisional.
The reference identifies one continuous speaker over this particular [40,43) turn.
This locates the divergence at mixer attenuation -> VAD/endpoints -> embedding
window, before account naming. Identity code and audio-time sweep cadence are shared.

The initial Javier account attempt hit the strict 30-second settle timeout and
was aborted by the replay harness, not helper expiry. Retained events show late
canonical decodes taking 9.06, 12.65 and 12.54 seconds, versus earlier .10–.18 s;
identity work stayed approximately .4 s. Shared decoder delay is measured; its
external cause is unknown. No settled/final score is assigned to that attempt.

Ackman's four arms separate the two mixer effects:

| Input/path | Settled DER | Emitted/reference |
|---|---:|---:|
| Original mono, no hold | .122667 | 2/2 |
| Attenuation only, bare runtime | .106167 | 2/2 |
| One-frame hold only, original bytes | .167167 | 2/2 |
| Account/v2 (both effects) | .152500 | 2/2 |

Holding the frame adds .044500 DER with original gain; the full account result is
.046333 worse than attenuation-only. Attenuation alone improves this case, so
removing headroom globally is NOT justified by Adam alone. Hold-only releases the
original retained frame on Stop; it does not discard any final audio.

## F6 — Six-case settled comparison

August is the two-pass mean. Local is one paired pass; Javier account uses the
explicit successful retry, with its failed attempt retained separately. The bare
runtime exactly reproduces August's Adam, Jamie and RTFL DER; Javier differs by
.0004, Ackman and Keyu improve. This is not an exact historical binary replay or a
bisect. It reproduces the direction of the Phase-2 difference on all six cases.

| Case | August DER | Mono DER | Account DER | Emitted mono/account | Reference |
|---|---:|---:|---:|---:|---:|
| Javier | 0.113000 | 0.112600 | 0.172000 | 1/1 | 1 |
| Ackman | 0.128250 | 0.122667 | 0.152500 | 2/2 | 2 |
| Keyu | 0.111167 | 0.089167 | 0.140833 | 2/2 | 2 |
| Adam | 0.091167 | 0.091167 | 0.119889 | 2/3 | 2 |
| Jamie | 0.094352 | 0.094352 | 0.103849 | 3/3 | 3 |
| RTFL | 0.430644 | 0.430644 | 0.406546 | 4/5 | 4 |

| Case | Speech DER mono/account | Final DER mono/account |
|---|---:|---:|
| Javier | 0.092889/0.136451 | 0.017800/0.028200 |
| Ackman | 0.107081/0.145448 | 0.075500/0.060500 |
| Keyu | 0.078495/0.123669 | 0.079000/0.074333 |
| Adam | 0.077717/0.106683 | 0.066222/0.059556 |
| Jamie | 0.081653/0.091911 | 0.059215/0.071560 |
| RTFL | 0.352785/0.327188 | 0.335454/0.333752 |

Local settled DER macro: **0.156766 mono / 0.182603 account**.
RTFL improves despite an extra emitted identity. Adam's extra provisional identity
is a real regression; the others are not uniformly an identity failure. Javier's
DER is entirely missing timed coverage, with one speaker on both paths.

## F7 — Birth/admission counts, not just visible labels

Settled surface; each cell is mono/account. Abstention counts whole committed
canonical spans that abstained, not each unattributed segment.

| Case | Born | Album-admitted | Provisional-only | Abstaining spans |
|---|---:|---:|---:|---:|
| Javier | 1/1 | 1/1 | 0/0 | 0/0 |
| Ackman | 2/2 | 2/2 | 0/0 | 1/1 |
| Keyu | 2/2 | 2/2 | 0/0 | 0/0 |
| Adam | 2/3 | 2/2 | 0/1 | 0/1 |
| Jamie | 4/4 | 2/2 | 2/2 | 0/0 |
| RTFL | 4/5 | 4/4 | 0/1 | 0/0 |

## F8 — PCM and endpoint measurements

RMS is measured in signed 16-bit sample units. Both complete streams have the same
sample count. Every mixed sample matches the
existing -6 dB integer formula; timestamp sealing holds approximately the final
0.5 seconds before Stop. VAD means voice-activity detection; each decision is 10 ms.

| Case | Input RMS | Mixed RMS | Gain dB | VAD decisions changed | Endpoint spans original/mixed |
|---|---:|---:|---:|---:|---:|
| Javier | 2980.339 | 1493.416 | -6.00170 | 59/5000 | 27/25 |
| Ackman | 3251.214 | 1629.163 | -6.00162 | 35/6000 | 24/24 |
| Keyu | 3519.120 | 1763.392 | -6.00171 | 11/6000 | 24/24 |
| Adam | 3518.941 | 1763.319 | -6.00162 | 109/18000 | 77/78 |
| Jamie | 3163.717 | 1585.273 | -6.00187 | 192/18000 | 80/80 |
| RTFL | 558.146 | 279.455 | -6.00872 | 218/9000 | 47/51 |

Ackman and Keyu retain identical endpoint boundaries despite changed VAD decisions.
The other four have different boundaries (Jamie has the same count, different cuts).

## D1 — Decision and limits

**Keep identity policy and bounds unchanged.** The account mixer changes what the
model hears and when canonical audio becomes available; it is not an equivalent
input wrapper around the campaign path. Fix/decision work belongs at that input
boundary, not at birth floors, matching thresholds or retrospective merging.

Treat the settled-surface comparison as a documented input-boundary mismatch:
queued work may be drained correctly while the mixer still retains the last frame
and the endpoint holds an unfinished span. More waiting alone cannot seal it.
Do not silently move the capture after Stop, add synthetic trailing audio, relax
the bound or remove mixer headroom on the strength of this experiment. Safe
two-source gain and explicit capture-end semantics need their own scoped decision.

There is no blanket claim that attenuation worsens recognition: it improves Ackman
in isolation, and the full account path improves RTFL. The Adam control establishes a specific harmful causal chain.
Residual interior text/timestamp differences in Javier and Keyu are measured, not
assigned wholly to one identity mechanism. One pass does not estimate decoder
variance; exact scores are not a production qualification claim.

The initial mono smoke run completed but its RTF exception occurred before capture
persistence; its trace is retained only in scratch and excluded. Of 12 matrix
attempts, 11 supplied valid three-surface captures and Javier account timed out.
One explicit Javier retry plus three isolated controls and one same-workspace
repeat supplied five further valid captures. The scored Javier mono run retained
a canonical p95 RTF failure (2.15928 > 1); the other completed reported runs did not.
No failed settle/final surface was scored. All attempts used the unchanged
30-second settle deadline. The scratch 17862 server was stopped after measurement;
its database and raw evidence are preserved. No host operation or 17861 mutation.

## Evidence and reproduction

- [Content-free scores, all three surfaces, counts and controls](../../prototypes/streaming-diarization/account-path-differential/results/measurements.json).
- [PCM/RMS and exact endpoint partitions](../../prototypes/streaming-diarization/account-path-differential/results/input-effects.json).
- [Anonymous embedding-window durations and best-match observations](../../prototypes/streaming-diarization/account-path-differential/results/identity-windows.json).
- [Reproduction scripts and scope](../../prototypes/streaming-diarization/account-path-differential/NOTES.md).
- Raw captures/traces: /tmp/moss-der-differential (not committed).
- Current mono/account descriptors are identical. August's provider, endpoint,
  decoder and identity hashes also match. Descriptor source revision belongs to
  the pinned provider bundle (29681e0479305449bb40caa49154fe4b1ae85eea);
  actual measured code is 463b1d66.

Final integrated regression: **1,434 Python tests + 37 subtests passed, 2 existing
skips; 202 frontend tests passed**, after incorporating peer changes through
253aaf2c. The initial post-rebase suite exposed a pre-existing timing-test fixture
that lacked the browser context required by the new bank() fresh-page lifecycle.
The fixture now routes its static DOM at context scope, supplies the real context,
and delays observation on the newly attached page. The original .18–.5-second
timing assertion and explicit missing-browser skip convention are unchanged.
No acceptance selector, identity policy, QUALITY_BOUNDS or _validate_quality was
changed by this work.
