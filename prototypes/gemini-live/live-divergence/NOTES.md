# Long60 live-versus-cache identity probe

## Question and contract

Find the first difference between an attended, 1.0x HTTP replay and the cached
real-response run on long60, while spending at most $0.50. Keep request bytes,
provider words, and canonical speaker mapping separate. The falsifier for the
different-request hypothesis is that every live system WAV and model/config key
matches the corresponding cached request.

The smallest useful primitives are accepted 16 kHz PCM, scheduled system
window bounds, WAV bytes and cache key, returned words, and registry mappings.
Preview, word gating, and relabels occur after the logged provider response.
The probe wraps the integration product methods in process, runs the real HTTPS
server, and uses the existing account-cookie replay client. It does not edit
product code.

## Commands

Run from the WP1 worktree with the shared venv and the exact integration checkout
at `f962d97dfd196a6e258248481d4c1293fe19f95b`:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/live-divergence/preflight.py --integration /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r2-int --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp1/live-divergence
```

The completed run used `server.py` around the integration `phase2_web_cli` HTTPS
stack, `replay.py` against `https://127.0.0.1:18710`, and the following
read-only reduction:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/live-divergence/analyze.py --integration /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r2-int --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp1/live-divergence --cached-events /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/lead/cached-der/events.jsonl
```

## Measured verdict

- Frozen first 900s: 14,400,000 accepted and accounted samples. All 60 S15/L90
  system requests follow the scheduled bounds and hit P1 cache by exact product
  WAV bytes plus model/config key. No request-byte or schedule miss.
- Fresh returned word tuples match cached, repaired words for 28/60 windows.
  The first word-tuple difference is `[0,15]`; the first local speaker-label
  distribution difference is `[0,60]`: fresh `spk:0=21, spk:1=140`, cached
  `spk:0=21, spk:1=99, spk:2=41` (161 words each). The latter only splits one
  canonical speaker into two local labels and does not yet change a canonical
  speaker target.
- The first canonical target change is window `[810,900]` seconds, samples
  `[12,960,000,14,400,000]`: the exact WAV/key hits cache, fresh provider
  returns 268 words, cache has 271, and registry maps fresh `spk:1` to
  `speaker-0001` versus cached `speaker-0003`. The `spk:0` target remains
  `speaker-0001`. Earlier provider variations may also have changed accumulated
  registry state; the precise contribution of each is unmeasured.
- The comparison uses the lead's successful 172-window cached replay at
  `evidence/P66/lead/cached-der/events.jsonl`. Its preflight and this HTTPS run
  both report source `f962d97d`; the separate WP3 pre-fix S1 trace was not used
  for the final verdict. Both traces agree on the first-900s mappings.
- Final HTTP session is `closed/final`, with $0.334286667 cost on this run. Prior
  WP1 Bill smoke was $0.012508; cumulative WP1 paid spend $0.346794667.

The different-window hypothesis is falsified for these 900 seconds. Source
divergence is already present in the provider response before the word gate,
preview, registry, or relabel code sees it. The provider/backend reason for
varying answers on identical requests is unknown; three matching later spot
checks did not establish determinism across all windows. This 900-second prefix
does not independently reproduce the full long60 DER gap.

## Evidence

`/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp1/live-divergence/`:

- `input-preflight.json`: frozen source and prefix hashes, scheduled cache hits.
- `server-trace.jsonl`: exact request WAV hashes/keys, responses, mappings, usage.
- `analysis.json`: first differences and counts.
- `replay/run-001/summary.json`: HTTP pacing/accounting receipt.
- `final-snapshot.json`: settled status and metered cost.
