import { describe, expect, it, vi } from "vitest";
import { createFileJobPoller, submitJob } from "./jobs";
import type { WsEvent } from "./types";

describe("file jobs adapter", () => {
  it("submits the selected file using the server multipart contract", async () => {
    const file = new File(["audio"], "interview.wav", { type: "audio/wav" });
    const fetcher = vi.fn(async () => response(job("queued", 0)));

    await submitJob(file, { fetch: fetcher as typeof fetch });

    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/jobs");
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("file")).toBe(file);
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
