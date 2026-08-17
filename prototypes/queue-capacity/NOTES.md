# Impossible queue-capacity frame prototype

## Question

How should production handle a valid frame whose previewed canonical work count exceeds the queue's
total capacity, when a generic manifest floor is not established?

## Command

```sh
.venv/bin/python -m pytest -q \
  tests/test_live_service_runtime.py::test_impossible_multi_span_frame_fails_without_audio_admission \
  && npm --prefix frontend test -- --run src/capture/captureClient.test.ts
```

The Python case drives the production `preview_frame_work_items` seam with a three-span frame and
queue depth one. The frontend case drives the production frame-response path.

## Measurements inherited and checked

- Shipping geometry: at most one frame span for positive queue depth one.
- Claude/y5 aggressive fresh-state measurement: 166 spans, disproving its earlier proposed floor 25.
- All-state aggressive maximum: not established after 12 iterations; therefore no loader floor is
  justified.
- Runtime preview is exact for the current frame before admission and already reports queue depth,
  required work items, and total capacity.

## Verdict

Do not add an unproven static floor. Split permanent capacity mismatch from transient occupancy at
the runtime preview seam. Permanent mismatch is terminal and non-retryable; transient occupancy
remains non-terminal retryable 429. The browser stops local capture on the permanent code rather
than retrying or recreating an identically impossible session.
