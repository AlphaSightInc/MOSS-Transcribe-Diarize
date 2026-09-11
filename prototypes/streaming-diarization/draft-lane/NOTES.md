# Draft lane — default off

Question: can reader-only words beat the canonical freeze floor without changing identity,
quality surfaces, or delaying canonical work? Minimum primitives: one bounded audio window,
one optional request, and an under-lock lifecycle/coverage fence. The canonical queue and
committed audio prefix remain authoritative. No new identity evidence or policy.

A throwaway seven-case state probe (fresh, queued canonical, draft busy, preview covered,
committed, aborted, oversized) admitted only fresh/bounded work and refused publication after
coverage or abort. Absorbed into `tests/phase2/test_draft_lane.py`; no prototype scheduler ships.
Regression tests also hold a draft in flight while canonical commits, and exercise the real
reader without a browser. These test runtime scheduling, not GPU contention.

Runtime option `draft_lane_seconds=None` (CLI omitted) is off. An enabled lane uses one
request across the runtime, at most 2.5 seconds and 286 generated tokens, the existing runner
and prompt resolution. It never enters the canonical/rolling arbiter or identity preparation.
Snapshots expose `draft` beside, never inside, `session`; `draft_stats` is content-free.
Drafts never advance the canonical version, so enabled snapshot polling must not suppress
updates using that version alone. Canonical/provisional coverage retires draft text atomically.

Unknown: an already-running GPU request cannot be preempted by a later canonical request.
Real single/two-session measurements are required before recommending enablement. Until then,
keep off. Falsifier: added canonical delay, changed final word error rate, stale publication,
or no worthwhile latency gain. Bounds and identity policy stay untouched.

No transcript text belongs in this evidence directory.

## Measured verdict

**Keep off.** Single-session coverage p50 improved 1.80 → 0.77 s, with twice the decoder
requests. A successful two-session repeat reached 1.30 / 1.72 s, above the 1.0-second target.
An earlier concurrent arm failed; it remains retained, with final WER null. Full results,
Stop-wait caveat, and sample limits: `docs/audits/draft-lane-20260911.md` at the repository root.

The request counter reports HTTP decoder calls, not just admitted spans. `published` in
runtime draft statistics counts snapshot publications, including replacement with empty text.
No transcript, prompt, audio, or cookie is stored in this directory.

## Reproduce locally

Use the project `.venv/bin/python`. Set `DRAFT_TLS_DIR` to the existing localstack certificate
folder and `DRAFT_CORPUS` to the existing `mono_javier_intro_50s` corpus directory. Use a fresh
private scratch directory and an unused local port; do not reuse a shared stack's state.

```sh
.venv/bin/python prototypes/streaming-diarization/draft-lane/run_local_stack.py \
  --state /tmp/moss-draft-measurement --cert "$DRAFT_TLS_DIR/cert.pem" \
  --key "$DRAFT_TLS_DIR/key.pem" --port 17862
```

Omit the draft argument for off. Restart only this scratch server with
`--draft-lane-seconds 1.0` for on. The launcher uses the existing local tunnel, never creates
one or changes the host. Local model metadata and provider manifest must already exist.

```sh
PYTHONPATH=. .venv/bin/python prototypes/streaming-diarization/draft-lane/latency_probe.py \
  --base https://127.0.0.1:17862 --cafile "$DRAFT_TLS_DIR/cert.pem" \
  --wav "$DRAFT_CORPUS/audio.wav" --reference "$DRAFT_CORPUS/reference.jsonl" \
  --stop-deadline 5 --out /tmp/moss-draft-measurement/probe.json
```

For concurrent measurement, start two instances simultaneously with distinct output paths.
Each creates its own temporary cookie and deletes it on exit. The probe reads the reference
only after replay, for final scoring; it never feeds reference text or speaker labels into
inference. Failed/non-final sessions receive null WER. This probe extends the supplied
`latency_probe.py`: visible canonical previews/drafts count toward coverage, true edit-distance
WER replaces the legacy heuristic (also retained), final text is not truncated or exported,
and Stop is polled to a terminal result. The original 30-second Stop wait remains an explicit
CLI default for reproducing the failed arm; pass five seconds to match the portal.

Rebuild the retained aggregate without running a provider:

```sh
python prototypes/streaming-diarization/draft-lane/summarize.py \
  --requests prototypes/streaming-diarization/draft-lane/decoder-requests.jsonl
```
