# Verdict

**SUPPORTED: bounded saved-desktop rendering, not 200-minute acoustic or live-poll qualification.**
Measured candidate `be2dd06d45cca24ce3e56eff843a4d245f168c09` on 2026-09-19, Chrome153.0.8010.53,1440×900. All120/720/4824 alternating-person passages rendered; exact final words remained; unique-tail search found one match; no browser errors.

| Represented duration | JSON bytes | Load to visible tail | Tail search |
|---|---:|---:|---:|
|5 min|50360|563.739 ms|15.666 ms|
|30 min|302403|632.276 ms|25.330 ms|
|201 min|2031839|1258.286 ms|71.270 ms|

No timing acceptance bar was invented. Deterministic route fixtures isolate the real built UI from persistence, decoding, physical capture and continuous live polling. Text density is synthetic; matching payload size does not establish representative speech density or mobile behavior.

First run overlapped root's offline word-error scorer: correctness passed,201-minute load1303.958ms/search71.406ms. It is retained separately, not silently replaced. One clean rerun after the scorer exited supplies the timing table above.

Compact result: `results.json`. Full fixtures and viewport screenshots:
`/Users/gao/Documents/Codex/2026-09-19/moss-round2/saved-transcript-render-uncontended/`.
Initial receipt: sibling `saved-transcript-render/`.

Disposition: retain this formerly throwaway probe as a small standing saved-browser measurement bench. No production optimization or package was added. Reuse it when a future transcript-render change could drop long-output rows or degrade tail search.
