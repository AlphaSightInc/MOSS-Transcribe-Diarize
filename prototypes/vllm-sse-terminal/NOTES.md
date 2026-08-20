# vLLM SSE terminal-marker probe

## Question

Does the production `VllmRunner` return when vLLM sends `data: [DONE]`, or only when the HTTP
response reaches EOF?

One command:

```sh
.venv/bin/python prototypes/vllm-sse-terminal/probe.py
```

The probe sends a valid streamed transcript and usage through the real multipart HTTP and SSE
consumer path. Its chunked HTTP server sends `[DONE]`, deliberately keeps the response open for
2 seconds, then sends the terminating HTTP chunk. It prints the transcript, token count, elapsed
time, hold-open time, and whether the runner returned before EOF.

## Verdict — 2026-08-19

Before the production change, elapsed time was **2.434 s** and `returned_before_eof` was false:
the parser ignored `[DONE]` and waited for the server to close the response.

After breaking on `[DONE]`, elapsed time was **0.481 s** and `returned_before_eof` was true while
text and completion-token accounting remained intact. The focused runner suite passed 5 tests and
3 subtests. Verdict: **accept the terminal-marker fix**; TCP EOF is not the SSE completion signal.

This protocol defect was **not** the cause of the attended 2026-08-19 outage. A second MacStudio
run on the patched parser accepted 85 browser frames and froze nine spans, but the first inference
returned no body bytes. Direct `curl` requests inside the Alienware WSL instance reproduced the
same result against `127.0.0.1:8000`: streamed HTTP returned headers but zero SSE bytes for 15 s;
a non-streamed request returned zero bytes for 15 s. The dedicated vLLM request counters did not
advance, its gauges reported zero running/waiting work, and the host GPU remained at 100% SM with
88 MiB free. The local SSE fix is protocol hardening only; attended recovery requires restoring
the dedicated Alienware model service, then repeating the live test.
