# Text-path differential — 2026-09-11

**The accepted mixer repair restores settled text improvement locally:** mono
macro WER .137097, repaired account .136379, campaign .140442. The host's .169311
was measured before that repair. No further plumbing change is indicated.

## F1 — The reported host score predates the accepted repair

The local round-10 bundle pins **19ea9365fb9bbc19edb66a036bbc7be85538e288**
in both `/tmp/moss-round10-stage/identity.json` and `sha.txt`. Its settled WER
is .169310833. That candidate does not contain mixer repair **905eadbb**:
its mixer has neither source-analysis PCM nor observed frame-end release.
Thus .1693 does not measure the repaired account path. The fresh paired replay
below uses **3a641f06d363d0d4b6dc0ec7d36fe9d4f74bf868**, including that repair.

## F2 — Why the old account path lost pre-Stop improvement

All **122 rolling windows** in round 10's twelve sessions decoded and applied;
none was refused. The loss was not a disabled rolling decoder or prefix/cannot-link
rejection. It was **when the audio became eligible for canonical commitment**.
The old mixer withheld the last roughly .5 seconds until Stop. Canonical work
freezes complete spans, so .5 seconds of withheld input can block a whole 2.5-second
span. Rolling work requires those samples already committed. An empty queue during
settle was truthful: the missing span/window could not yet be queued.

Ackman and Keyu are direct witnesses. Before Stop, round 10 admitted 952,000 of
960,000 source samples (59.5 of 60 seconds), and committed 920,000 (57.5 seconds).
The final canonical span and rolling window [50,60) seconds therefore waited for
Stop. Both cases had **5 / 5 / 6** applied rolling revisions at immediate / settled /
final capture. Repaired mono and account both admit all 960,000 samples, finish the
span, and have **5 / 6 / 6** revisions. Settled WER now benefits from window six.

Javier demonstrates why revision counts alone are insufficient. Both paths retain
four rolling revisions through settle, yet WER improves when the final complete
canonical span commits. Round 10 admitted 792,000 of 800,000 samples and committed
756,480; repaired input admits all 800,000 and can finish the span near 49.76 seconds.
The genuine endpoint tail and fifth rolling window still wait for Stop. Jamie has
the analogous old 179.5-second admission versus a span ending at 179.51 seconds.
Adam's settle improvement also comes from canonical completion with 17 rolling
revisions unchanged. RTFL's old late canonical tail added errors; source-level
analysis changes its span geometry, as established in the accepted mixer audit.

These observations do not mean rolling always improves text, or that all of the
immediate-to-settled difference is rolling. Immediate already includes earlier
rolling revisions. Settled drains both kinds of eligible work before Stop; final
additionally admits endpoint tails and performs terminal refinement.

## F3 — Fresh paired measurements

Twelve scored sessions from thirteen attempts; RTFL mono required one explicit retry. WER is word error rate,
lower is better. Each triple is **immediate / settled / final**.

| Case | Path | WER | Applied rolling revisions | Total windows decoded |
|---|---|---|---|---:|
| Javier | mono | 0.194690 / 0.159292 / 0.097345 | 4 / 4 / 5 | 5 |
| Javier | account | 0.194690 / 0.159292 / 0.088496 | 4 / 4 / 5 | 5 |
| Ackman | mono | 0.267045 / 0.198864 / 0.159091 | 5 / 6 / 6 | 6 |
| Ackman | account | 0.272727 / 0.193182 / 0.147727 | 5 / 6 / 6 | 6 |
| Keyu | mono | 0.143885 / 0.100719 / 0.064748 | 5 / 6 / 6 | 6 |
| Keyu | account | 0.143885 / 0.100719 / 0.064748 | 5 / 6 / 6 | 6 |
| Adam | mono | 0.146893 / 0.133710 / 0.126177 | 17 / 17 / 18 | 18 |
| Adam | account | 0.146893 / 0.133710 / 0.126177 | 17 / 17 / 18 | 18 |
| Jamie | mono | 0.111498 / 0.094077 / 0.069686 | 17 / 17 / 18 | 18 |
| Jamie | account | 0.108014 / 0.090592 / 0.069686 | 17 / 17 / 18 | 18 |
| RTFL | mono | 0.135922 / 0.135922 / 0.053398 | 8 / 8 / 8 | 8 |
| RTFL | account | 0.140777 / 0.140777 / 0.053398 | 8 / 8 / 8 | 8 |

| Basis | Immediate macro WER | Settled macro WER | Final macro WER |
|---|---:|---:|---:|
| 2026-08-25 campaign, twelve retained sessions | .166656 | .140442 | .095074 |
| Round 10, twelve retained sessions, pre-repair | .166653 | .169311 | .091705 |
| Fresh mono, six sessions | 0.166655 | 0.137097 | 0.095074 |
| Fresh account, six sessions | 0.167831 | 0.136379 | 0.091705 |

**Both current paths reproduce settled WER near .14.** The repaired account path
does not remain near .17. One pass per path is not a measured statistical noise
band or a host qualification pass. The historical campaign used two passes per
case; the macro comparison is descriptive, not proof of bit-for-bit reproduction.

Across the twelve scored sessions, **122 rolling windows decoded and applied**, 61 per path. There were
zero rolling decode failures, revision refusals or trace gaps. Every case has
identical rolling start/end/owned-window geometry to the campaign. No revision
rule bypass, larger window or extra post-capture wait was introduced.

| Case | Settle wait seconds: mono / account | Text revision version I / S / F, both paths |
|---|---:|---|
| Javier | 0.762590 / 0.786273 | 4 / 4 / 6 |
| Ackman | 1.283383 / 1.333356 | 5 / 6 / 7 |
| Keyu | 1.013813 / 1.327227 | 5 / 6 / 7 |
| Adam | 0.253271 / 0.265209 | 17 / 17 / 19 |
| Jamie | 1.016876 / 1.057424 | 17 / 17 / 19 |
| RTFL | 0.000624 / 0.004748 | 8 / 8 / 9 |

All twelve scored settled captures drained with zero pending canonical/rolling work,
`finalization_status=not_started`, and no timeout; all final captures were genuinely
`final`. Final text revision versions include the terminal revision, so they are
one greater than the final rolling counts above.

Three scored replays separately failed canonical decoder p95 real-time-factor
performance: **Javier 3.16841 mono / 1.65972 account; RTFL account 2.79203**,
strict limit 1. All quality surfaces were valid and are retained, but these runs
are not performance passes. The other nine scored sessions reported no replay
performance failure.

The first RTFL mono attempt failed: `settle timed out after 30s: canonical=0, rolling=1`.
It remains unscored in results.json; the retry is separate in retry-results.json.
The failure trace has no service events, so its blocked request and cause are unknown.
No longer wait or sampling workaround was used. These twelve valid surfaces do not
erase that failed attempt or establish a complete gate pass.

A misleading historical cost statistic was excluded: the campaign summary sums
the cumulative rolling `decoded_audio_samples` at each completion. Five 10-second
windows therefore appear as 150 seconds (10+20+30+40+50), although actual total
decoded rolling audio is 50 seconds. Window geometry and the final cumulative
counter establish the comparison; this unrelated summary bug does not change WER.
No cost-statistic code was changed.

## F4 — Scope and decision

This is a same-current-runtime differential, not execution of a historical Phase-1
binary. Both paths use the same runtime factory, identity manifest and decoder
through the existing local tunnel. The mono adapter bypasses Account/v2; the account
adapter uses a fresh workspace on the agent-owned HTTPS17862 stack with speakers
and a silent microphone. Draft is off; replay is paced at 1x. No reference speaker
labels enter decoding or identity. No host operations or access to the operator's
17861 database. The existing own-stack database is preserved.
The owned server was stopped after measurement. Pulling peer work through
`c70a96e2` afterward changed acceptance exercises, not the measured runtime/mixer
or the three-surface harness. Measurement remains explicitly pinned to `3a641f06`.

Applied rolling counts select `source=rolling` publication events included in each
capture's snapshot and text-revision versions. They do not count terminal revisions
as rolling. Decode counts require actual decode timing; failure/refusal outcomes
remain separate. Full trace sequence continuity is checked. The capture harness
waits for canonical and rolling work, refreshes the snapshot, raises on timeout,
and requires a genuinely final terminal state. No capture rule is relaxed.

No new product fix is proposed: the identified plumbing repair is already accepted.
QUALITY_BOUNDS, _validate_quality and identity policy remain untouched. The fresh
local measurement is evidence for round 11, not a substitute for host qualification.

## Evidence

- [Fresh content-free scores, captures and rolling-window evidence](../../prototypes/streaming-diarization/text-path-differential/results.json)
- [Explicit RTFL mono retry, original failure retained separately](../../prototypes/streaming-diarization/text-path-differential/retry-results.json)
- [Geometry, capture validity, denominators and macros](../../prototypes/streaming-diarization/text-path-differential/validation.json)
- [Round-10 content-free per-pass projection](../../prototypes/streaming-diarization/text-path-differential/round10-projection.json)
- [Bench contract and reproduction](../../prototypes/streaming-diarization/text-path-differential/NOTES.md)
- [Accepted mixer differential and controls](mixer-repair-differential-20260911.md)

Raw fresh captures/traces: `/tmp/moss-text-differential/runs/{mono,account}/<case>/`.
Retained host inputs: `/tmp/moss-round10-stage/result/raw/pre_admission-collector/artifacts/quality/`.

Code witnesses: `app/live_transcript_convergence.py::_plan` requires both accepted
and committed samples through the rolling window end; `app/live_mixer.py` uses
observed `capture_end_timestamp_ns` to release completed frames. Historical
rolling-cost overcount is in `live-surface-optimization/measure_three_surfaces.py`
when summing cumulative completion counters, not in the text scorer.
