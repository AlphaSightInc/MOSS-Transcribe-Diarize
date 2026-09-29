// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defaultAppSettings, loadAppSettings, saveAppSettings } from "./settings";

beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key) });
});

describe("browser settings", () => {
  it("starts with Gemini summaries and balanced windows, then persists one browser choice", () => {
    expect(loadAppSettings()).toMatchObject({ speakerWindow: "balanced", cleanupAfterStop: false,
      summary: { provider: "built-in", model: "gemini-3.5-flash-lite", intervalSeconds: 60 } });
    saveAppSettings({ ...defaultAppSettings(), speakerWindow: "economy", summary: { ...defaultAppSettings().summary, provider: "off" } });
    expect(loadAppSettings().speakerWindow).toBe("economy");
    expect(loadAppSettings().summary.provider).toBe("off");
  });

  it("migrates a configured external provider once", () => {
    localStorage.setItem("moss.browser-final-summary.v1", JSON.stringify({ endpoint: "https://example.com/v1", model: "m",
      apiKey: "k", prompt: "Custom", language: "French", timeoutSeconds: 80 }));
    expect(loadAppSettings().summary).toMatchObject({ provider: "external", externalUrl: "https://example.com/v1",
      externalModel: "m", externalApiKey: "k", prompt: "Custom", language: "French", timeoutSeconds: 80 });
    expect(localStorage.getItem("moss.browser-final-summary.v1")).toBeNull();
  });
});
