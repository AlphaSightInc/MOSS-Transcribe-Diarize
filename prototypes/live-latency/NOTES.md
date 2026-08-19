# Live latency measurement bench

## Question

Where does the attended 3–5 second word-to-screen delay accrue before any cap, silence, queue,
or reader policy changes?

## One-command baseline preservation

```sh
python3 prototypes/live-latency/preserve_baseline.py \
  --output evidence/phase1/g3-attended/live-latency-baseline-20260819.json
```

The command consumes the three retained M4 `mtd-capture latency` raw files and the sanitized
canonical-event export under `/tmp`. It prints the full evidence document and refuses to call the
fresh-app run a baseline unless the app's declared 20-advance gate passed.

## Baseline verdict — 2026-08-19

The first run was too short. A stop/start attempt then reproduced a lifecycle fault in the stale
installed app: both lanes claimed to capture, but the microphone produced no server frames and the
latency probe never resolved a mixer origin. Relaunching the app restored both lanes and yielded 23
committed advances with an intact timeline.

The active attended reader is `/live` at 500 ms cadence; the React poller is not the handoff target.
On the successful run, last-sample-to-probe-fetch age was 2.399 s p95, paired fetch was 142 ms p95,
and the existing analytic last-sample-to-visible bound was 3.041 s p95. Of 30 canonical spans,
27 ran to the 2.5 s hard cap. Decode was 0.427 s p95 and 0.617 s max. The additive first-sample
visible bound is therefore 5.541 s, matching the reported 3–5 s experience.

Verdict: **span accumulation plus post-span visibility dominate**. This is diagnostic evidence,
not authorization to tune the hard cap. Queue wait, commit-to-fetch, actual DOM render, and
start/end age at actual render remain required before the preregistered cap/silence sweep.

## Diagnostic seam implemented

The server now records queued, started, and processed instants from one injected monotonic clock.
Events expose queue wait, cumulative canonical processing, queued-to-processed, and the server
monotonic read instant. The active `/live` portal correlates a processed event with the committed
span and ends measurement on the next `requestAnimationFrame` after DOM mutation. It reports
queue, processing, decode, commit-to-fetch, events fetch, fetch-to-DOM, and first/last-word render
bounds through `window.mossLivePortal.latencyReport()`.

Absolute browser, server, and capture clocks are never subtracted. Server-local durations,
browser-local durations, and capture-local ages are measured independently and only then added.
The macOS `mtd-capture latency` schema is v3: it reports exact newest-span start/end capture ages
while retaining the v2 `committedLatency` alias as end-of-span age. Focused tests cover multiple
commits in one poll, actual post-DOM timing, inclusive-cursor deduplication, and exact clock-domain
arithmetic.

## Preregistered cap/silence sweep — no policy change

One command:

```sh
.venv/bin/python prototypes/live-latency/proto_cap_silence_sweep.py \
  --output evidence/phase1/g3-attended/live-cap-silence-sweep-20260819.json
```

The sealed sweep ran the production endpoint, decoder token cap, real vLLM endpoint, production
WeSpeaker encoder, accepted album/terminal-sweep policy, and a serial queue over two discovery and
two unopened validation corpora. The 2.0 s cap preserved transcript and identity, but its median
first-word p95 improvement was 487.675 ms—12.325 ms short of the frozen 500 ms discovery gate—and
its unparseable rate exceeded the zero-regression gate. Shorter caps passed latency but harmed
identity, WER, request load, or parse stability. No candidate reached held-out validation.

Verdict: **NO_POLICY_CHANGE**. Keep hard cap 2.5 s and minimum silence 0.5 s; do not regenerate the
manifest. The measured baseline explains the 3–5 s report, but no tested knob produced a safe,
material improvement. Fresh served-path and attended measurements remain deployment gates.
