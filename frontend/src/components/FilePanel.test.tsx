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
    const upload = installUploadRequest({ id: "job-9", status: "queued", progress: 0, error: null });
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ id: "job-9", status: "waiting_review", progress: 0.95, error: null }))
      .mockResolvedValueOnce(response({
        segments: [{ id: "s1", start: 0, end: 1, speaker: "S01", text: "File transcript" }]
      }));
    vi.stubGlobal("fetch", fetcher);
    const root = document.createElement("div");
    document.body.append(root);
    render(<FilePanel captureBearer="shared-bearer" />, root);

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
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));

    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "/api/jobs/job-9",
      "/api/jobs/job-9/segments"
    ]);
    expect(fetcher.mock.calls.map(([, init]) => new Headers((init as RequestInit).headers).get("Authorization")))
      .toEqual(["Bearer shared-bearer", "Bearer shared-bearer"]);
    expect(upload.setRequestHeader).toHaveBeenCalledWith("Authorization", "Bearer shared-bearer");
    expect(sessionStatus.value).toBe("closed");
    expect(transcript.value).toEqual([expect.objectContaining({ text: "File transcript", state: "final" })]);
    expect(root.textContent).toContain("Transcript ready.");
  });

  it("reports upload bytes and states the whole-file retry limit", async () => {
    const upload = installUploadRequest(
      { id: "job-9", status: "queued", progress: 0, error: null },
      { loaded: 3, total: 10 },
      false
    );
    const root = document.createElement("div");
    document.body.append(root);
    render(<FilePanel captureBearer="shared-bearer" />, root);

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

    expect(root.textContent).toContain("Uploading file: 3 / 10 bytes.");
    expect(root.textContent).toContain("Failed uploads restart from the beginning; upload resume is unavailable in Phase 1.");
  });

  it("surfaces a server refusal when no bearer was retained", async () => {
    const upload = installUploadRequest({ detail: "capture bearer required" }, undefined, true, 401);
    const root = document.createElement("div");
    document.body.append(root);
    render(<FilePanel captureBearer="" />, root);

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

    expect(upload.setRequestHeader).not.toHaveBeenCalledWith("Authorization", expect.anything());
    await vi.waitFor(() => expect(root.textContent).toContain("capture bearer required"));
  });
});

function response(payload: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response;
}

function installUploadRequest(
  payload: unknown,
  progress?: { loaded: number; total: number },
  completeImmediately = true,
  status = 200
) {
  const request = {
    status,
    responseText: JSON.stringify(payload),
    open: vi.fn(),
    send: vi.fn(),
    setRequestHeader: vi.fn(),
    upload: { onprogress: null as ((event: ProgressEvent<EventTarget>) => void) | null },
    onload: null as (() => void) | null,
    onerror: null as (() => void) | null,
    onabort: null as (() => void) | null,
    complete() {
      request.onload?.();
    }
  };
  request.send.mockImplementation(() => {
    if (progress) {
      request.upload.onprogress?.({ lengthComputable: true, ...progress } as ProgressEvent<EventTarget>);
    }
    if (completeImmediately) request.complete();
  });
  vi.stubGlobal("XMLHttpRequest", vi.fn(function FakeXmlHttpRequest() { return request; }));
  return request;
}
