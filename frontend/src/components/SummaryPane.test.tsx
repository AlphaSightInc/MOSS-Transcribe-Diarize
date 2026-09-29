// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { SummaryPane } from "./SummaryPane";
import { sessionId, sessionStatus } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";

const root = document.createElement("div"); document.body.append(root);
afterEach(() => { render(null, root); sessionId.value = null; sessionStatus.value = "idle"; selectedSummaryMeeting.value = null; vi.unstubAllGlobals(); vi.useRealTimers(); });

it("renders a rolling summary from the frozen live response", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ summary: "The team agreed.",
    source: { committed_samples: 48000, text_revision_version: 4 }, generated_at_ms: Date.now() }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!.click());
  await vi.waitFor(() => expect(root.textContent).toContain("The team agreed."));
  expect(fetcher.mock.calls[0][0]).toBe("/api/meetings/m/summary/live");
});

it("applies a changed summary provider without reopening the meeting", async () => {
  const { defaultAppSettings, saveAppSettings } = await import("../lib/settings");
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key) });
  const settings = defaultAppSettings();
  saveAppSettings({ ...settings, summary: { ...settings.summary, provider: "off" } });
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  expect(root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")?.disabled).toBe(true);
  await act(async () => saveAppSettings(settings));
  expect(root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")?.disabled).toBe(false);
  localStorage.removeItem("moss.settings.v1");
});

it("keeps the last rolling summary through a 502 and retries at the next interval", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const first = { summary: "The first good update.",
    source: { committed_samples: 48000, text_revision_version: 4 }, generated_at_ms: Date.now() };
  const second = { ...first, summary: "The recovered update.", generated_at_ms: Date.now() + 120_000 };
  const fetcher = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => first })
    .mockResolvedValueOnce({ ok: false, status: 502 })
    .mockResolvedValueOnce({ ok: false, status: 502 })
    .mockResolvedValueOnce({ ok: true, json: async () => second });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!.click());
  await vi.waitFor(() => expect(root.textContent).toContain(first.summary));

  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(root.textContent).toContain(first.summary);
  expect(root.querySelectorAll(".summary-notice")).toHaveLength(1);
  expect(root.querySelectorAll('[role="alert"]')).toHaveLength(0);
  expect(root.textContent).toContain("Retrying at the next interval.");
  expect(root.textContent).not.toContain("next in 0s");

  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(root.textContent).toContain(first.summary);
  expect(root.querySelectorAll(".summary-notice")).toHaveLength(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(fetcher).toHaveBeenCalledTimes(4);
  expect(root.textContent).toContain(second.summary);
  expect(root.querySelectorAll(".summary-notice")).toHaveLength(0);
});

it("offers Retry when a final summary artifact or request fails", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const failed = { state: "failed", attempt_id: "attempt", source_version: 1,
    artifact_version: 0, error_code: "provider_error", document: null };
  let reads = 0;
  const fetcher = vi.fn(async (_url: string, init?: RequestInit) => init?.method === "POST"
    ? { ok: false, status: 502 }
    : { ok: true, json: async () => ({ summary: reads++ === 0 ? failed : null }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "closed";
  selectedSummaryMeeting.value = { id: "m", mode: "live", title: "Meeting", title_source: "automatic",
    status: "completed", created_at_ms: Date.now(), transcript_version: 1,
    transcript: { segments: [] }, audio: null };
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await vi.waitFor(() => expect(root.textContent).toContain("Summary failed"));
  const button = root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!;
  expect(button.textContent).toBe("Retry");
  expect(root.textContent).toContain("The summary is unavailable.");
  expect(root.textContent).not.toContain("Finish transcription to generate a summary.");
  await act(async () => button.click());
  await vi.waitFor(() => expect(root.textContent).toContain("Summary request failed (502)"));
  expect(button.textContent).toBe("Retry");
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(reads).toBeGreaterThanOrEqual(2);
  expect(root.textContent).toContain("No saved summary yet");
  expect(button.textContent).toBe("Retry");
  expect(root.textContent).toContain("Summary request failed (502)");
  expect(fetcher.mock.calls.some(([_url, init]) => init?.method === "POST")).toBe(true);
});

it("does not carry a rolling failure into a successful final summary", async () => {
  const artifact = { state: "current", attempt_id: "final", source_version: 1,
    artifact_version: 1, error_code: null, document: { summary: "Final decision.", topics: [],
      details: [], speaker_background: [], data_references: [] } };
  const fetcher = vi.fn(async (url: string) => url.endsWith("/summary/live")
    ? { ok: false, status: 502 }
    : { ok: true, json: async () => ({ summary: artifact }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!.click());
  await vi.waitFor(() => expect(root.querySelectorAll(".summary-notice")).toHaveLength(1));
  await act(async () => { sessionStatus.value = "closed"; });
  await vi.waitFor(() => expect(root.textContent).toContain("Final decision."));
  expect(root.querySelectorAll(".summary-notice, [role='alert']")).toHaveLength(0);
  expect(root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")?.textContent).toBe("Refresh");
});
