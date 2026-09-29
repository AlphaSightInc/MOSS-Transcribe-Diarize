// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
import { defaultAppSettings } from "./settings";
import { requestLiveSummary, requestFinalSummary } from "./summaryRequests";

beforeEach(() => vi.restoreAllMocks());

it("requests an ephemeral live summary with browser model, language and prompt", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ summary: "Now", source: {
    committed_samples: 100, text_revision_version: 2 }, generated_at_ms: 10 }) });
  const settings = defaultAppSettings(); settings.summary.language = "French";
  await requestLiveSummary("m", settings, fetcher);
  expect(fetcher).toHaveBeenCalledWith("/api/meetings/m/summary/live", expect.objectContaining({
    method: "POST", body: JSON.stringify({ model: "gemini-3.5-flash-lite", language: "French", prompt: settings.summary.prompt })
  }));
});

it("finalizes at the authoritative transcript version", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ state: "current" }) });
  await requestFinalSummary("m", 7, defaultAppSettings(), fetcher);
  expect(fetcher).toHaveBeenCalledWith("/api/meetings/m/summary/server", expect.objectContaining({
    body: JSON.stringify({ source_version: 7, model: "gemini-3.5-flash-lite", language: "", prompt: defaultAppSettings().summary.prompt })
  }));
});
