# WP49 evidence

Gate: `DONE` from round-2 `runner_storage/NOTES.md` F1-F3; no new prototype.

## Verdict

SUPPORTED. `WindowedRunner` is now the explicit File/URL/terminal batch seam for both HF and vLLM. Scheduling remains below windowing. Product File passes `checkpoint_dir=None` until WP53b has a durable owner; the existing checkpoint implementation remains usable when an explicit directory is supplied.

## Unpatched falsifiers

Command: targeted pytest selectors recorded in `unpatched-violating-controls.xml` against production code at `a7a738cf` plus the new tests, before any production edit.

- Result: **6 failed / 6**, as required.
- Unknown field: signature still had `**kwargs`.
- Strict HF File and URL: both durably `decode_failed` before inference.
- Injected HF failure: generation seam received **0** calls because `checkpoint_dir` failed first.
- HF cancellation/window control: composition was not a `WindowedRunner`.
- HF scheduler placement: composition was not a `WindowedRunner`.

## Patched controls

Targeted command covered `test_windowed_transcription.py`, the new backend contract, runner composition, digital silence, failure reasons, and owner-bound File lifecycle.

- Result: **80 passed / 0 failed** in 5.35 s (`postpatch-targeted.xml`).
- 199 / 200 / 201 represented minutes: **100 / 100 / 101** complete delegate calls; final tails **60 / 120 / 60 s**; progress monotonic.
- Strict actual `ModelRunner`, generation replaced only: File and URL both `completed`, segments present, audio downloadable; silence remains covered with 0 inference calls.
- Injected decoder exception: generation reached once, durable `failed/decode_failed`, transcript absent, work root empty.
- Cancellation during window 0: exactly `window-0000.wav` dispatched; later windows and publication refused; work root empty.
- HF and vLLM scheduler composition: three represented windows produced three delegate acquisitions, scheduler returned to zero.
- Explicit checkpoint directory remains covered by the existing checkpoint/resume tests.

## Real inference controls

Harness: `run_real_file_control.py`; public 60 s Bill Ackman corpus clip; product File route; not an acoustic-quality claim.

- Local HF (`real-hf-file.json`): **1** delegate call, `completed`, **18** segments, audio download HTTP 200, **31.934 s** wall, **0** remote requests.
- Remote vLLM (`real-vllm-file.json`): queue 0 running / 0 waiting before load; **1** delegate call/request, `completed`, **18** segments, audio HTTP 200, **3.438 s** wall. Budget used **1/20**, max in flight **1**. Port 18310 tunnel closed after the run.
- First local attempt (`real-hf-file-sqlite-blocked.json`) stopped before inference: SQLite runtime **3.50.4** versus required **3.53.4**, **0** decoder calls. Final inference controls used the prior prototype's explicit semantic-store version allowance; therefore they do not qualify deployment runtime parity.

`phase2_web_cli.py` keeps `max_length_cap` vLLM-only. The real HF control succeeded with the configured HF `max_length=131072`; no evidence justifies imposing the vLLM server cap on HF.
