import { describe, expect, it, vi } from "vitest";
import { createFileJobPoller, submitJob } from "./jobs";
import type { WsEvent } from "./types";

describe("file jobs adapter", () => {
  it("submits multipart through XHR and reports byte progress", async () => {
    const file = new File(["audio"], "interview.wav", { type: "audio/wav" });
    const request = fakeUploadRequest(job("queued", 0), [
      { loaded: 2, total: 5 },
      { loaded: 5, total: 5 }
    ]);
    const onUploadProgress = vi.fn();

    await submitJob(file, {
      bearerToken: "shared-bearer",
      createXmlHttpRequest: () => request,
      onUploadProgress
    });

    expect(request.open).toHaveBeenCalledWith("POST", "/api/jobs", true);
    expect(request.send).toHaveBeenCalledWith(expect.any(FormData));
    expect((request.send.mock.calls[0][0] as FormData).get("file")).toBe(file);
    expect(request.setRequestHeader).toHaveBeenCalledWith("Authorization", "Bearer shared-bearer");
    expect(request.setRequestHeader).not.toHaveBeenCalledWith("Content-Type", expect.anything());
    expect(onUploadProgress).toHaveBeenNthCalledWith(1, { loaded: 2, total: 5 });
    expect(onUploadProgress).toHaveBeenNthCalledWith(2, { loaded: 5, total: 5 });
  });

  it("reports a refused unauthenticated upload", async () => {
    const file = new File(["audio"], "interview.wav", { type: "audio/wav" });
    const request = fakeUploadRequest({ detail: "capture bearer required" }, [], 401);

    await expect(submitJob(file, { createXmlHttpRequest: () => request })).rejects.toMatchObject({
      name: "JobsApiError",
      status: 401,
      message: "capture bearer required"
    });

    expect(request.setRequestHeader).not.toHaveBeenCalledWith("Authorization", expect.anything());
  });

  it("publishes a completed segment snapshot before closing file state", async () => {
    const dispatched: WsEvent[] = [];
    const onTerminal = vi.fn();
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(job("waiting_review", 0.95)))
      .mockResolvedValueOnce(response({
        segments: [{ id: "segment-1", start: 1.25, end: 3.5, speaker: "S01", text: "Hello" }]
      }));
    const poller = createFileJobPoller({
      jobId: "job-17",
      fetch: fetcher as typeof fetch,
      dispatch: (event) => dispatched.push(event),
      onTerminal
    });

    await poller.poll();

    expect(dispatched.map((event) => event.type)).toEqual(["transcript_update", "session_state"]);
    expect(dispatched[0]).toMatchObject({
      session_id: "job-17",
      metadata: { operation: "snapshot" },
      items: [{ segment_id: "job-17:segment-1", state: "final", text: "Hello" }]
    });
    expect(dispatched[1]).toMatchObject({ mode: "file", status: "closed" });
    expect(onTerminal).toHaveBeenCalledWith(expect.objectContaining({ status: "waiting_review" }));
  });

  it("does not dispatch an in-flight response after mode-switch cancellation", async () => {
    let resolveResponse: ((value: Response) => void) | undefined;
    const fetcher = vi.fn(() => new Promise<Response>((resolve) => { resolveResponse = resolve; }));
    const dispatch = vi.fn();
    const poller = createFileJobPoller({ jobId: "job-17", fetch: fetcher as typeof fetch, dispatch });

    poller.start();
    poller.stop();
    resolveResponse?.(response(job("transcribing", 0.5)));
    await Promise.resolve();
    await Promise.resolve();

    expect(dispatch).not.toHaveBeenCalled();
    expect(poller.running()).toBe(false);
  });
});

function job(status: string, progress: number, error: string | null = null) {
  return { id: "job-17", status, progress, error, updated_at: 1_725_000_000 };
}

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload
  } as Response;
}

function fakeUploadRequest(
  payload: unknown,
  progressEvents: readonly { loaded: number; total: number }[],
  status = 200
): XMLHttpRequest & { open: ReturnType<typeof vi.fn>; send: ReturnType<typeof vi.fn>; setRequestHeader: ReturnType<typeof vi.fn> } {
  const request = {
    status,
    responseText: JSON.stringify(payload),
    open: vi.fn(),
    send: vi.fn(),
    setRequestHeader: vi.fn(),
    upload: { onprogress: null as ((event: ProgressEvent<EventTarget>) => void) | null },
    onload: null as (() => void) | null,
    onerror: null as (() => void) | null,
    onabort: null as (() => void) | null
  };
  request.send.mockImplementation(() => {
    for (const progress of progressEvents) {
      request.upload.onprogress?.({ lengthComputable: true, ...progress } as ProgressEvent<EventTarget>);
    }
    request.onload?.();
  });
  return request as unknown as XMLHttpRequest & typeof request;
}
