# WP16 file/URL measurement bench

Absorbed from the WP16 throwaway prototypes after their verdicts. Not product startup,
deployment or qualification tooling. See `NOTES.md` for question, invariants and falsifiers;
full commands, outcomes and limitations live in `evidence/mvpfix/wp16/`.

One command for a browser case (with the documented private stack/tunnel already running):

```
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/.wp16runtime/tmp" /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/streaming-diarization/wp16-file-url-long/probe.py long.wav
```

`prepare.py` composes the public audio; `sources.py` provides real local HTTPS/404/HTML
and an HTTP origin that accepts without responding. `stack.py` only instruments the
existing local-stack recipe's window calls. `sample.py` samples process RSS/shared GPU
queue every 30 seconds. `probe.py` drives actual file selectors/forms, saves API snapshots
privately, reloads History, clicks exports/MP3, and checks a different browser workspace.
`oversize.py` uses a real sparse file exceeding current capacity, without allocating its
claimed bytes. `admission.py` is the contrasting header-only server control, not browser
file proof. `preflight.py` is the measured size-only composition prototype; `silence.py`
is the exact-zero boundary prototype. Neither is imported by production.

`surfaces.py`, `score.py`, and `summarize.py` turn actual observations into compact evidence;
`verify_evidence.py` checks that evidence and reruns the existing export oracle against
retained browser downloads/API snapshots without services or GPU dispatch.

All private media, saved snapshots, browser state and TLS material belong to ignored
`.wp16runtime/`; no audio in git. Count total requests across stack restarts, not just the
launcher process counter, and stop every own process after the campaign.
