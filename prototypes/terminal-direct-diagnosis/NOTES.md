# Terminal decoder exception — direct candidate reproduction

## F1 — mechanism measured, not a vLLM size rejection

All four terminal inputs fail **before any HTTP request**, with the full underlying error:

```
AttributeError: 'NoneType' object has no attribute 'strip'
```

`ops/account-web-launcher.sh` omits `--prompt`. The parser supplies `None`.
`build_terminal_finalizer` → `resolve_inference_options` forwards `prompt=None`.
`TerminalTranscriptFinalizer.finalize` writes the actual retained PCM as a WAV and calls
`WindowedRunner.transcribe` → `_decode_window` → `VllmRunner.transcribe` → `_build_fields`.
The expression `prompt.strip() or DEFAULT_PROMPT` raises before `_post_multipart`.
`WindowedRunner` wraps it as `decoder_exception`, window 0; the finalizer returns decode_failed.

The live canonical adapter supplies only its duration-derived token limit. It does not
supply `prompt=None`, so Python supplies `VllmRunner.transcribe`'s DEFAULT_PROMPT. The
2.5-second live control returns successfully, making one request to the same vLLM.
This directly reproduces the round-7 failure signature without creating a session.
It does not measure vLLM's maximum accepted audio length: none of the terminal requests
reached vLLM. The historical 1,361 successful requests belonged to the earlier retained
interval, not this probe.

## F2 — exact comparison

Runtime: `account-runtimes/c93395fecc2ebf452db66eb4e4ae61afbd855fdb/bin/python`, isolated imports (`-I`).
Source: `~/.local/share/moss-transcribe-diarize/qualification-corpus/mono_javier_intro_50s/audio.wav`.
All probes use the same source's first N seconds, 16,000 Hz mono PCM16.

| Terminal duration | WAV bytes | HTTP requests | Exception | HTTP status/body |
|---|---:|---:|---|---|
| 50 s | 1,600,044 | 0 | AttributeError above | none: no request |
| 2.5 s | 80,044 | 0 | AttributeError above | none: no request |
| 10 s | 320,044 | 0 | AttributeError above | none: no request |
| 30 s | 960,044 | 0 | AttributeError above | none: no request |

Terminal call arguments: `prompt=None`, `max_length=16384`, `max_new_tokens=12000`,
`decoding=greedy`, `temperature=None`. Configured model:
`OpenMOSS-Team/MOSS-Transcribe-Diarize`; endpoint `http://127.0.0.1:8000/v1/audio/transcriptions`.
No multipart form is constructed. The shared builder's remaining configured fields are
response_format=json, stream=true, stream_include_usage=true,
stream_continuous_usage_stats=true, max_completion_tokens=12000, temperature=0.0.
These are **intended fields from code**, not a request observed on the wire. `max_length`
is discarded by the vLLM runner. There are no separate timestamp/word options.

Live 2.5-second control: WAV 80,044 bytes; max_new_tokens=286. Actual multipart fields:
model=OpenMOSS-Team/MOSS-Transcribe-Diarize, response_format=json, stream=true,
stream_include_usage=true, stream_continuous_usage_stats=true,
max_completion_tokens=286, temperature=0.0, prompt=DEFAULT_PROMPT. Exact prompt and fields
are in `results.jsonl`; the prompt is a static instruction, not transcript content.
No timestamp/word options. One request, decoder returned; successful response body and
status were not logged by this probe. No transcript text retained.

`results.jsonl` contains full underlying exception messages and tracebacks for each
terminal case, call parameters, and the live request parameters. No credentials or audio.

## F3 — diagnostic patch and limits

WindowTranscriptionError now emits exception_type and exception_message for a wrapped
exception. The collector retains these fields through window_failure. The measured
structural AttributeError is retained exactly. Typed empty outcomes retain their named
condition; subprocess and OS errors retain status/errno messages. Arbitrary unstructured
messages are explicitly redacted because they may contain rejected transcript text or
credentials. Raw provider bodies are not copied into terminal events.

Tests exercise the actual terminal inference options → WindowedRunner → VllmRunner
failure before HTTP and its event projection, plus all five existing window conditions
and exclusion of arbitrary secret/text messages. Validation: 68 passed, 19 subtests passed
across windowed transcription, terminal finalization, runner composition, and completion
qualification. No prompt fallback fix, silence policy change, or qualification rerun.

## D1 — proposed later behavioral fix

Resolve an absent default prompt to DEFAULT_PROMPT in the shared inference-option
boundary, so File and terminal paths receive a valid prompt. Verify omitted, blank,
and explicit prompts through both compositions. This is a proposed fix, not implemented
in this diagnostic patch. No evidence supports changing audio window bounds.

## Reproduction contract and command

Question: local request construction or length-dependent provider rejection?
Primitives: retained PCM extent, shared runner options, request boundary, typed exception.
Invariants: exact installed candidate; fixed audio source; no session/service mutation;
no transcript/credential output; vLLM PID unchanged.
Hypotheses: (1) None prompt causes failure before HTTP; (2) terminal request parameters
cause HTTP rejection; (3) length triggers provider rejection. Falsifier for (1): a terminal
request reaches HTTP or succeeds without changing options. Four lengths distinguish
local construction failure from size-dependent failure; one live control tests the same
provider with the live adapter's options. No configuration changes or retries required.

On the deployment host, using this script outside any source checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 "$HOME/.local/share/moss-transcribe-diarize/account-runtimes/c93395fecc2ebf452db66eb4e4ae61afbd855fdb/bin/python" -I /tmp/moss-terminal-direct/probe.py
```

This makes one live inference request; the four terminal calls fail before sending.
Probe uses the real finalizer and WindowedRunner, with an in-memory implementation of
the tape read/gaps interface; it creates no Meeting/session and writes temporary WAVs only.
Before/after vLLM: MainPID=169937, NRestarts=0,
ActiveEnterTimestampMonotonic=1208158572270, exactly unchanged. Services not restarted or reconfigured.
