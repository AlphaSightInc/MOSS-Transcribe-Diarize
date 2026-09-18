# WP3 signal guard verdict — 2026-09-17

Question: distinguish empty audio and playback leakage without losing quiet local speech?
**Zero guard accepted. Leakage suppression REJECTED; telemetry only. P4 remains open.**
Primitives: aligned signed PCM, exact-zero predicate, delayed scalar playback reference,
explained energy. Preserve timeline/sequence, nonzero audio, readiness and frame protocol.
Assumptions: digital linear echo; gains relative to original corpus recording. Physical
speaker/AEC incidence, nonlinear room response and actual attendance are UNMEASURED.

One command (offline): `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> prototypes/streaming-diarization/capture-guards/prototype.py --offline`
The LOGIC skill's interactive shell is replaced by deterministic full-state JSON per step,
as the brief requires an automated corpus ladder. Scripts are absorbed into the standing
measurement bench; no production import uses their candidate threshold.

Experimental threshold: >=99% explained energy; not calibrated or shipped as policy.
| Population | spans | candidate skip/suspect | false suppress | false pass |
|---|---:|---:|---:|---:|
| exact digital zero | 1 | 1 | 0 | 0 |
| noise only | 2 | 0 | 0 | n/a |
| echo only, 60 seconds | 36 | 12 | n/a | 24 |
| near speech -10/-15/-20 dB, 60 seconds | 108 | 0 | 0 | n/a |
| near speech, 0.5 second spans | 12960 | 80 | 80 | n/a |
| echo only, 0.5 second spans | 4320 | 669 (653 suspect, 16 zero) | n/a | 3651 |
Noise is -45/-60 dBFS or absent. Echo gains -10/-30/-50/-70 dB; delays 5/30/60 ms.
Chunk false suppress denotes nonzero local signal, not guaranteed intelligible words.
Targeted real decodes of the strongest false-positive local chunk at each gain returned
1/2/1 lane-alone words. Mixture already lost all those words (0 unique retention), so this
is a signal-separation falsifier, not proof of additional guard-induced intelligible-word loss.

52 real decoder requests, serial: one failed scoring attempt after decode, 45 main cases,
6 targeted chunk calls. Main calls total 87.369362 seconds. No retries inside our scripts.
Main: 27/27 mixed spans unchanged by candidate; near reference WER 0.627586–1.565517.
All echo outputs scored against known playback text; raw words never retained in evidence.
Zero decoded to 0 words in this run; that does not refute previously observed hallucination.
Failed attempt retained in decoder-attempt1.log (parser returns list, not .segments).
Raw numeric results and commands: evidence/mvpfix/wp3/. No audio or private text committed.

Production decision: exact zeros bypass live/terminal model invocation while retaining
sample accounting. Existing mixer renders fully silent spans to zero. Playback statistics
are observations only; no leak threshold, suppression or custom AEC. WP1 must preserve
silent-to-zero rendering in its per-lane producer. Attended protocol must resolve P4.
