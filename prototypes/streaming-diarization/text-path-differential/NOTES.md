# Text-path differential — 2026-09-11

Structural question: does the account path lose rolling refinement, or did the
pre-repair mixer prevent already received audio from becoming canonical work?
Primitives: admitted PCM extent, frozen canonical spans, owned rolling windows,
revision publication version, and capture. Each describes a different boundary.
Invariants: unchanged decoder/identity configuration and quality bounds, existing
strict capture/settle/final rules, no future evidence, no reference labels as input.
Initial unknowns: fresh twelve-session WER and which retained host candidate
produced the reported score. The local round-10 bundle establishes 19ea9365,
before mixer repair. Final findings: ../../../docs/audits/text-path-differential-20260911.md.

Ranked falsifiers: (H1) repaired account still near .17 with admitted tail complete
would reject the held-tail explanation; (H2) fewer decoded/applied windows would
identify a rolling scheduling/refusal loss; (H3) different owned/context geometry
would identify a plan difference; (H4) both fresh paths near .17 would support
current-runtime nonreproduction of the campaign. Neither path is assumed to fail.

One current runtime factory, bare mono versus actual account/v2 on own HTTPS17862,
sequential paired cases, draft off, same local decoder tunnel. One fresh account
workspace, new session per case, no naming/enrollment. No host/17861 operations.
All raw captures/traces stay under /tmp/moss-text-differential; scores and rolling
counts are retained per case. Existing account-path-differential/run_stack.py
recipe supplies the own stack/factory, not a historical Phase-1 binary.

Reproduction requires the existing decoder tunnel on 18000, installed provider
manifest/model assets, and trusted local TLS certificate/key. Use a new scratch
directory and an unused 17862; do not restart another operator's instance:

```sh
export MOSS_DIFFERENTIAL_REPO="$PWD"
export MOSS_DIFFERENTIAL_SCRATCH=/tmp/moss-text-stack-new
export MOSS_TEXT_OUT=/tmp/moss-text-results-new
mkdir -p "$MOSS_DIFFERENTIAL_SCRATCH" "$MOSS_TEXT_OUT"
cp prototypes/streaming-diarization/account-path-differential/run_stack.py prototypes/streaming-diarization/account-path-differential/instrument.py "$MOSS_DIFFERENTIAL_SCRATCH/"
cp prototypes/streaming-diarization/text-path-differential/measure.py prototypes/streaming-diarization/text-path-differential/rolling_projection.py "$MOSS_DIFFERENTIAL_SCRATCH/"
# Place trusted cert.pem/key.pem in the stack directory, preserving permissions.
# Terminal 1, with this environment:
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/run_stack.py"
# Terminal 2, with the same environment:
.venv/bin/python "$MOSS_DIFFERENTIAL_SCRATCH/measure.py"
```

The stack recipe only accommodates local SQLite runtime version; instrumentation
observes existing provider/identity calls. No algorithm or policy substitution.
The exercised scratch runner's unused old mixing helper was removed from the
retained script; measurement uses actual mono/account adapters, not that helper.
Scores are retained after every case; recorded failures are not automatically
retried. A separate replay real-time-factor failure is never a performance pass.
Final/settle capture failures remain unscored. Stop only the owned server afterward;
preserve both the database and raw evidence, and commit no cookies/audio/text.

Applied rolling counts use source=rolling publication events whose snapshot and
text revision versions are included in the captured document. Counting total text
revision_version alone would wrongly include terminal revisions. Successful decode
counts require actual decode timing on rolling completion; refusals, failures and
undispatched outcomes remain separate. Event sequence gaps are reported explicitly.

Verdict: measured at 3a641f06, mono settled macro .137097 and repaired account
.136379. The host .169311 belongs to pre-repair 19ea9365. No new product change.
Thirteen attempts, twelve valid scored surfaces: first RTFL mono timed out with
one rolling request pending after 30 seconds; an explicit retry under the same
limit succeeded. Original failure stays in results.json; retry-results.json is
separate. Three scored sessions also failed decoder-speed checks. These are not
qualification passes. The owned 17862 server was stopped; all data preserved.
