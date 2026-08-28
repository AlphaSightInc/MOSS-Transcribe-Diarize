// @vitest-environment jsdom

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const currentSourceRoot = path.dirname(fileURLToPath(import.meta.url));
const referenceSourceRoot = process.env.MOSS_REFERENCE_FRONTEND_SRC
  ?? "/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src";

async function countSourceTree(root: string): Promise<{ files: number; lines: number }> {
  let files = 0;
  let lines = 0;

  for (const entry of await readdir(root, { withFileTypes: true })) {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      const nested = await countSourceTree(entryPath);
      files += nested.files;
      lines += nested.lines;
      continue;
    }
    if (entry.isFile()) {
      files += 1;
      lines += (await readFile(entryPath, "utf8")).match(/\n/g)?.length ?? 0;
    }
  }

  return { files, lines };
}

describe("App shell", () => {
  afterEach(() => {
    document.body.replaceChildren();
    document.head.querySelectorAll('meta[name="moss-authority"]').forEach((node) => node.remove());
  });

  it("renders the phase-one shell with an inert collapsed rail", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    expect(root.querySelector("#transcript-panel")).not.toBeNull();
    expect(root.querySelector(".main")?.getAttribute("data-right-collapsed")).toBe("true");
    expect(root.querySelector(".history-panel .panel-body")).toBeNull();
    expect(root.querySelectorAll("[data-transcript-segment]")).toHaveLength(0);
    expect(root.querySelector('a[href="/live"]')).toBeNull();
    expect(root.querySelector('[aria-label="Capture bearer"]')).not.toBeNull();
    expect(root.querySelector('[aria-label="Listening setup"]')?.textContent).toContain("Speakers");
    expect(root.textContent).toContain("Enable microphone");
  });

  it("keeps only Live and File modes, and the File tab exposes browser file selection", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    const modeTabs = root.querySelectorAll('[role="tab"]');
    expect([...modeTabs].map((tab) => tab.textContent)).toEqual(["Live", "File"]);
    expect(root.textContent).not.toContain("URL");
    expect(root.textContent).not.toContain("Batch");

    const fileTab = [...modeTabs].find((tab) => tab.textContent === "File");
    if (!fileTab) {
      throw new Error("Missing File mode tab");
    }
    act(() => {
      (fileTab as HTMLButtonElement).click();
    });

    expect(root.querySelector('[data-mode="file"]')).not.toBeNull();
    expect(root.querySelector('input[type="file"]')).not.toBeNull();
  });

  it("leaves Account history to the shared workspace surface", () => {
    const authority = document.createElement("meta");
    authority.name = "moss-authority";
    authority.content = "account";
    document.head.append(authority);
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    expect(root.querySelector('[data-authority="account"]')).not.toBeNull();
    expect(root.querySelector(".history-panel")).toBeNull();
    expect([...root.querySelectorAll('[role="tab"]')].map((tab) => tab.textContent)).toEqual(["Live"]);
  });

  it("retains the in-memory bearer when switching from Live to File", async () => {
    const upload = fakeUploadRequest({ id: "job-9", status: "queued", progress: 0, error: null });
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ id: "job-9", status: "waiting_review", progress: 1, error: null }))
      .mockResolvedValueOnce(response({ segments: [] }));
    vi.stubGlobal("fetch", fetcher);
    vi.stubGlobal("XMLHttpRequest", vi.fn(function FakeXmlHttpRequest() { return upload; }));
    const root = document.createElement("div");
    document.body.append(root);
    render(<App />, root);

    const bearer = root.querySelector<HTMLInputElement>('[aria-label="Capture bearer"]');
    if (!bearer) throw new Error("capture bearer missing");
    bearer.value = "shared-bearer";
    act(() => {
      bearer.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const fileTab = [...root.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
      .find((tab) => tab.textContent === "File");
    if (!fileTab) throw new Error("file tab missing");
    act(() => {
      fileTab.click();
    });

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
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalled());

    const [, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer shared-bearer");
    expect(upload.setRequestHeader).toHaveBeenCalledWith("Authorization", "Bearer shared-bearer");
  });

  it("records source-tree counts and rendered collapsed-rail evidence", async () => {
    const root = document.createElement("div");
    document.body.append(root);
    render(<App />, root);

    const [reference, current] = await Promise.all([
      countSourceTree(referenceSourceRoot),
      countSourceTree(currentSourceRoot)
    ]);
    const main = root.querySelector(".main");
    const historyRail = root.querySelector(".history-panel.collapsed");
    const railEvidence = {
      dataRightCollapsed: main?.getAttribute("data-right-collapsed"),
      historyRailPresent: historyRail !== null,
      historyRailInteractive: historyRail?.querySelector("button, input, select, textarea, a") !== null,
      historyBodyPresent: historyRail?.querySelector(".panel-body") !== null
    };

    expect(reference.files).toBeGreaterThan(0);
    expect(reference.lines).toBeGreaterThan(0);
    expect(railEvidence).toEqual({
      dataRightCollapsed: "true",
      historyRailPresent: true,
      historyRailInteractive: false,
      historyBodyPresent: false
    });
    console.info("REFERENCE_UI_COUNTS", JSON.stringify({ reference, current }));
    console.info("REFERENCE_UI_RENDERED_RAIL", JSON.stringify(railEvidence));
  });
});

function response(payload: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response;
}

function fakeUploadRequest(payload: unknown) {
  const request = {
    status: 200,
    responseText: JSON.stringify(payload),
    open: vi.fn(),
    send: vi.fn(),
    setRequestHeader: vi.fn(),
    upload: { onprogress: null as ((event: ProgressEvent<EventTarget>) => void) | null },
    onload: null as (() => void) | null,
    onerror: null as (() => void) | null,
    onabort: null as (() => void) | null
  };
  request.send.mockImplementation(() => request.onload?.());
  return request;
}
