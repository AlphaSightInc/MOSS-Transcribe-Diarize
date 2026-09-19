# Paired codec / local-label probe

## Contract

- **Question:** Does the native MP3 path change decoder-local speaker grouping enough to explain the retained Keyu loss, and do source-isolated controls remain stable?
- **Hypothesis:** Mixed 150-second composite windows produce different local-label spans after MP3 encoding; isolated Bill and Keyu controls do not exchange people.
- **Falsifier:** Paired composite local spans are equivalent, or isolated-person controls acquire a second person rather than ordinary interviewer turns.
- **Tool:** Eleven bounded decoder requests: three exact 150-second WAV/MP3 composite window pairs, paired 60-second Bill and Keyu controls, and one 150-second Jamie context containing the retained short interruption. No retries.

## Run

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  prototypes/streaming-diarization/paired-codec-local-label/probe.py \
  --endpoint http://127.0.0.1:19135/v1 --output results.json
```

## Verdict

**Supported narrowly; implemented.** Eleven calls moved global sent 69 to 80 with no
retry. Across three exact repeated composite windows, WAV returned 40 segments/window
and MP3 44–45. The already mixed Lex-local `S02` fell from 80.07% source purity in WAV
to 76.37% in MP3; paired `S02` mean-vector cosine was 0.934–0.939, while clean `S01`
and `S03` were 0.975–0.976. Isolated Keyu stayed 10 segments and 55.94 decoded seconds.

On the first 375 owned seconds, the implemented production resolver preserved all 111
WAV and 128 MP3 confidently correct eligible intervals. It reassigned three per arm
and abstained on three per arm. Source-time scoring:

- WAV: Bill confusion 11.97→5.31 s and correct 157.11→161.88 s; Keyu confusion
  5.10→2.04 s with 3.06 s unknown; Lex unchanged.
- MP3: Bill confusion 13.62→5.83 s and correct 162.85→168.90 s; Keyu confusion
  7.68→4.53 s with 3.15 s unknown; Lex unchanged.

This reduces confident error. It does **not** recover additional Keyu-correct seconds;
the uncertain minority evidence becomes honest unknown. The retained data does not
support weakening the 0.1 runner-up margin.

Full retained WAV replay confirms the slice. At 6 minutes the resolver kept 102,
reassigned 2, and abstained 3 eligible intervals. At 30 minutes it kept 546,
reassigned 14, and abstained 15. Bill correct time rose 720.30→741.93 s and confusion
fell 56.61→25.53 s; Keyu correct stayed 593.46 s while confusion fell 25.50→10.20 s
and 15.30 s became unknown; Lex was unchanged. No correct participant was lost.

The terminal map retains one float32 vector per eligible interval until the final album.
The retained 30-minute rate was 575 / 30 = 19.17 vectors/minute. Projected to 200
minutes, 3,833 256-dimensional `array('f')` vectors plus actual Python dict/key overhead
measured 4,593,824 bytes (4.381 MiB). The deployed ONNX path computes the interval batch
once; there is no per-interval whole-audio reload fallback.
