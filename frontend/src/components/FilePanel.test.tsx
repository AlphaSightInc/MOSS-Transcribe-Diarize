// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilePanel } from "./FilePanel";
import { resetSessionState, sessionStatus, transcript } from "../state/session";

describe("FilePanel", () => {
  afterEach(() => {
    document.body.replaceChildren();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    resetSessionState();
  });

  it("submits, polls, and renders completed job segments through the shared transcript state", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ id: "job-9", status: "queued", progress: 0, error: null }))
      .mockResolvedValueOnce(response({ id: "job-9", status: "waiting_review", progress: 0.95, error: null }))
      .mockResolvedValueOnce(response({
        segments: [{ id: "s1", start: 0, end: 1, speaker: "S01", text: "File transcript" }]
      }));
    vi.stubGlobal("fetch", fetcher);
    const root = document.createElement("div");
    document.body.append(root);
    render(<FilePanel />, root);

    const input = root.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("file input missing");
    Object.defineProperty(input, "files", { value: [new File(["audio"], "sample.wav")] });
    act(() => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const start = [...root.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "Start transcription");
    if (!start) throw new Error("start button missing");
    await act(async () => { start.click(); });
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));

    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "/api/jobs",
      "/api/jobs/job-9",
      "/api/jobs/job-9/segments"
    ]);
    expect(sessionStatus.value).toBe("closed");
    expect(transcript.value).toEqual([expect.objectContaining({ text: "File transcript", state: "final" })]);
    expect(root.textContent).toContain("Transcript ready.");
  });
});

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}
