# E2E rendered transcript measurement (throwaway prototype)

## Question and structure

**Structural question:** Does a live transcript look stable and timely to a person before Stop, and does its visible text survive finalization? HTTP events alone cannot answer because the frontend groups, replaces, and hides rows.

**Minimum primitives:** (1) a real-time audio clock and two lane frame streams; (2) the production live HTTP ingress and frontend; (3) a 250 ms browser DOM observation with row, segment, text, and speaker state; (4) a final saved transcript; (5) one deterministic reducer from observations to counts. The clock anchors delay; the ingress supplies live state; the DOM supplies what was visible; the final supplies survival; the reducer makes runs comparable. Removing any one leaves a requested metric unmeasured.

**Invariants:** Input advances at 1.0x. DOM samples remain in observation order. Only pre-Stop frames count as live. Each audio second has at most one first text and first label observation. Unknown times and fields remain `UNMEASURED`. Stub text and labels validate plumbing only; they are not quality evidence. Screenshots are browser pixels at 1440x900. No audio is played or sent to Google by this harness.

**Assumptions/unknowns:** A segment's `start`/`end` are audio-relative; the first public `frame_accepted` event is a usable approximate origin for archived MOSS filmstrip. The historical browser observation used direct session frames through the production HTTP capture ingress, with Chrome rendering the real UI; it did not exercise physical microphone/tab capture. Any Gemini runtime must preserve the same HTTP API for this runner. Whether Gemini first text arrives before Stop is unmeasured until a Gemini run.

**Falsifier:** A paced E1 stub and one accept6 stub fail to produce DOM rows/final saved transcript, or the archived MOSS filmstrip cannot be reduced with the same definitions. Such a failure rejects the comparison harness. UI quality claims remain unmeasured on stubs.

**Tool decisions:** Reuse round-6 `run.py`, `local_stack.py`, `tap_proxy.py`, and `loopback_vllm_stub.py` to preserve the known HTTP ingress and browser observation path; adapt paths/ports and add only visual metrics/screenshots. Use the production frontend in headless Chrome because a server snapshot cannot reveal visible grouping. Use an offline reducer on archived MOSS because GPU access is prohibited. The E1 run attacks the long, four-voice count case; a 60 s accept6 run attacks a simpler published acceptance shape. A startup/smoke check detects missing local dependencies before spending paced minutes. If any fail, fix the harness or mark the field unmeasured rather than infer a product result.

## Source custody

Initial harness source copied 2026-09-28 from `/private/tmp/moss-dx-replay/prototypes/round6-replay/` (branch `dx/replay`): `run.py`, `local_stack.py`, `tap_proxy.py`, `analyze.py`, `m2_fixture.py`, `loopback_vllm_stub.py`, `vad_spans.py`. Archived MOSS run is read-only at `/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/real-E1-001/`. E1 fixture comes from the same archive's `fixture/`; accept6 is selected through `prototypes/gemini-live/common/corpus.py`.

## Verdict

**Harness passes the stated falsifier.** The real frontend produced DOM rows and a completed saved transcript for a 60 s public accept6 stub and the 302 s E1 stub. The archived MOSS E1 filmstrip reduces under the same definitions. This is software QA of the visual measurement path; no Gemini runtime has been measured by this pane, and synthetic stub words/labels say nothing about transcription or diarization quality.

| Arm | Frames; max sender lag | Last pre-Stop rows / named labels / uncertain rows | First text p50/p90; coverage | Label p50/p90; coverage | Exact live-to-final text keys; final segments | Gemini clamped/dropped offsets per call |
| --- | --- | --- | --- | --- | --- | --- |
| Archived real MOSS E1, 302 s | 1,335 DOM; sender lag `UNMEASURED` | 164 / 10 / 24 | 0.729/2.212 s; 301/302 audio seconds, approximate clock | 2.211/4.212 s; 299/302, approximate clock | 30/755; 120 | `NOT_APPLICABLE` (0 Gemini calls) |
| Loopback stub E1, 302 s | 1,244 DOM; 0.525 s | 62 / 7 / 36 | 0/0 s; 224/302 | 0.763/1.756 s; 152/302 | 0/854; 2 | `UNMEASURED` (stub engine has no Gemini counters) |
| Loopback stub accept6 Bill Ackman, 60 s | 271 DOM; 1.752 s | 3 / 2 / 1 | 0/3.633 s; 36/60 | 0.511/5.106 s; 29/60 | 0/71; 1 | `UNMEASURED` (stub engine has no Gemini counters) |

Counts are rendered rows, excluding `Speaker uncertain` from named-label counts. Slice boundaries: MOSS 32.384/min; E1 stub 12.119/min; accept6 stub 2/min. The MOSS archive agrees with the earlier 164 rows, 181 segments, 30/755 strict text survival, and 120 final segments. It lacks the sender's exact start clock, marked `UNMEASURED`; latency uses the first polled accepted frame and is approximate. Stub timing values reflect artificial window text, not user latency. Three PNGs per stub arm were verified at 1440×900, including after the browser rendered final output. Local stub requests: E1 804/804, accept6 70/70. Provider calls and spend: 0 and $0. All three owned listeners stopped.

**Limit:** This replay feeds PCM through the production live session HTTP frame endpoint while a real Chrome frontend renders. It does not exercise physical media capture or browser fake-device capture. The feature brief described the older harness as fake-media injection, but its source uses direct frame POSTs (`run.py` `capture_arm`). A future Gemini runtime comparison remains `UNMEASURED` until the lead runs the external-stack command below.

**Timing anomaly handoff:** `common/gemini_common.py` at `193cb485` exposes per-call `WindowResult.timing_anomalies = {clamped, dropped}` after repairing out-of-window word offsets; ledger rows now include that dict. The lead expects the product runtime to expose engine counters for Gemini calls, errors, retries, clamped/dropped words, and cost. This pane made zero Gemini calls; per lead direction, stub anomaly rates stay `UNMEASURED`. For a later Gemini E2E run, use the runtime's call denominator and counters (and ledger rows where applicable) to report `sum(clamped)/calls` and `sum(dropped)/calls` beside the visual comparison. Do not infer zero anomalies from a successfully rendered DOM.

## One-command runs

From `$WT`, with `PYTHONDONTWRITEBYTECODE=1` and `$WT.venv/bin/python`:

```sh
python prototypes/gemini-live/e2e/run.py --stub --system /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/system.wav --mic /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/E1-microphone.wav --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/stub-E1-new
```

For the lead's later **Gemini-backed runtime** after it is listening locally on 18520 and still serves the unchanged HTTP API and frontend:

```sh
python prototypes/gemini-live/e2e/run.py --stack-url https://127.0.0.1:18520 --system /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/system.wav --mic /Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/E1-microphone.wav --out /Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P64/gemini-E1-new
```

`--out` must be a new directory. The runner starts and stops only its own stack in `--stub` mode. For an external runtime, its owner starts and stops that service. `summary.json` contains `visual_metrics`; `filmstrip.jsonl` and the three PNGs are browser evidence. Reduce any compatible archived run with `visual_metrics.py --run RUN --out SUMMARY.json`. The archived MOSS origin is the first polled `frame_accepted` event, so latency is approximate by poll delay; its other visual counts use DOM frames directly. Slice boundaries are adjacent rendered rows in the last pre-Stop frame per audio minute. Label flips count changes on the same DOM `target_keys`; replacement keys are not linked.
