// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { validateSummary } from "./finalSummary";
import {
  DEFAULT_SUMMARY_PROMPT, defaultAppSettings, engineSettingsFrom, loadAppSettings, missingGeminiKey, saveAppSettings,
  SETTINGS_CHANGED, summaryProviderWire, transcriptionWire, type AppSettings
} from "./settings";

let values: Map<string, string>;
beforeEach(() => {
  values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key) });
});

const OLD_DEFAULT_PROMPT = "Create the sole final briefing for a thoughtful reader who will not read the transcript.\n\nGOAL\n…";
const v1 = (patch: Record<string, unknown> = {}, summary: Record<string, unknown> = {}) => JSON.stringify({
  speakerWindow: "balanced", cleanupAfterStop: true, ...patch,
  summary: { provider: "built-in", model: "gemini-3.5-flash", externalUrl: "", externalModel: "", externalApiKey: "",
    language: "French", intervalSeconds: 120, timeoutSeconds: 90, prompt: OLD_DEFAULT_PROMPT, ...summary } });
const settingsWith = (edit: (settings: AppSettings) => void) => { const settings = defaultAppSettings(); edit(settings); return settings; };

describe("I-1 schema", () => {
  it("defaults to Gemini for both tabs with the documented seconds", () => {
    expect(loadAppSettings()).toEqual({
      transcription: { vendor: "gemini", url: "", model: "gemini-3.5-transcribe", apiKey: "", refreshSeconds: 15, contextSeconds: 90 },
      summary: { vendor: "gemini", url: "", model: "gemini-3.5-flash-lite", apiKey: "", rolling: true, waitSeconds: 60,
        language: "", timeoutSeconds: 120, prompt: DEFAULT_SUMMARY_PROMPT },
      general: { cleanupAfterStop: true }
    });
  });

  it("persists under moss.settings.v2, announces the change, and stores an unedited prompt empty", () => {
    const changed = vi.fn();
    document.addEventListener(SETTINGS_CHANGED, changed);
    saveAppSettings(settingsWith(s => { s.transcription.apiKey = "key"; s.summary.vendor = "off"; s.summary.waitSeconds = 0; }));
    document.removeEventListener(SETTINGS_CHANGED, changed);
    expect(changed).toHaveBeenCalledOnce();
    expect(JSON.parse(values.get("moss.settings.v2")!).summary.prompt).toBe("");
    expect(loadAppSettings()).toMatchObject({ transcription: { apiKey: "key" },
      summary: { vendor: "off", waitSeconds: 0, prompt: DEFAULT_SUMMARY_PROMPT } });
    saveAppSettings(settingsWith(s => { s.summary.prompt = "Custom"; }));
    expect(loadAppSettings().summary.prompt).toBe("Custom");
  });

  it("falls back per field on malformed values", () => {
    values.set("moss.settings.v2", JSON.stringify({ transcription: { vendor: "moss", refreshSeconds: "15", contextSeconds: 12.5 },
      summary: { vendor: "external", waitSeconds: -1, rolling: "yes" }, general: null }));
    expect(loadAppSettings()).toEqual(defaultAppSettings());
    values.set("moss.settings.v2", "{broken");
    expect(loadAppSettings()).toEqual(defaultAppSettings());
  });
});

describe("migration to v2", () => {
  it.each([
    ["balanced", 15, 90], ["economy", 30, 90], ["max", 15, 180]
  ])("maps the %s speaker window to (%i, %i) and keeps built-in as Gemini with an empty key", (speakerWindow, refresh, context) => {
    values.set("moss.settings.v1", v1({ speakerWindow, cleanupAfterStop: false }));
    expect(loadAppSettings()).toEqual({
      transcription: { vendor: "gemini", url: "", model: "gemini-3.5-transcribe", apiKey: "", refreshSeconds: refresh, contextSeconds: context },
      summary: { vendor: "gemini", url: "", model: "gemini-3.5-flash", apiKey: "", rolling: true, waitSeconds: 120,
        language: "French", timeoutSeconds: 90, prompt: DEFAULT_SUMMARY_PROMPT },
      general: { cleanupAfterStop: false }
    });
    expect(values.has("moss.settings.v1")).toBe(false);
    expect(values.has("moss.settings.v2")).toBe(true);
  });

  it("carries an external provider as OpenAI-compatible and interval 0 as rolling off", () => {
    values.set("moss.settings.v1", v1({}, { provider: "external", externalUrl: "https://example.com/v1", externalModel: "m",
      externalApiKey: "k", intervalSeconds: 0, prompt: "Custom prompt" }));
    expect(loadAppSettings().summary).toEqual({ vendor: "openai_compatible", url: "https://example.com/v1", model: "m",
      apiKey: "k", rolling: false, waitSeconds: 60, language: "French", timeoutSeconds: 90, prompt: "Custom prompt" });
  });

  it("keeps summaries off", () => {
    values.set("moss.settings.v1", v1({}, { provider: "off" }));
    expect(loadAppSettings().summary.vendor).toBe("off");
  });

  it("migrates the older browser-only summary settings once", () => {
    values.set("moss.browser-final-summary.v1", JSON.stringify({ endpoint: "https://example.com/v1", model: "m",
      apiKey: "k", prompt: "Custom", language: "French", timeoutSeconds: 80 }));
    expect(loadAppSettings().summary).toMatchObject({ vendor: "openai_compatible", url: "https://example.com/v1",
      model: "m", apiKey: "k", prompt: "Custom", language: "French", timeoutSeconds: 80, rolling: true });
    expect(values.has("moss.browser-final-summary.v1")).toBe(false);
    values.clear();
    values.set("moss.browser-final-summary.v1", JSON.stringify({ endpoint: "", model: "", apiKey: "", prompt: OLD_DEFAULT_PROMPT,
      language: "", timeoutSeconds: 120 }));
    expect(loadAppSettings().summary).toMatchObject({ vendor: "off", model: "gemini-3.5-flash-lite", prompt: DEFAULT_SUMMARY_PROMPT });
  });
});

describe("I-2 wire builders", () => {
  it("sends Gemini transcription with no URL and a null key when empty", () => {
    expect(transcriptionWire(defaultAppSettings())).toEqual({ vendor: "gemini", url: null, model: "gemini-3.5-transcribe", api_key: null });
    const typed = settingsWith(s => { s.transcription.apiKey = " key "; s.transcription.url = "https://ignored"; s.transcription.model = " "; });
    expect(transcriptionWire(typed)).toEqual({ vendor: "gemini", url: null, model: "gemini-3.5-transcribe", api_key: "key" });
  });

  it("builds the live create body; clean-up is never requested for OpenAI-compatible transcription", () => {
    const gemini = settingsWith(s => { s.transcription.apiKey = "key"; s.transcription.refreshSeconds = 20; s.transcription.contextSeconds = 120; });
    expect(engineSettingsFrom(gemini)).toEqual({ transcription: { vendor: "gemini", url: null, model: "gemini-3.5-transcribe", api_key: "key" },
      refresh_seconds: 20, context_seconds: 120, cleanup_after_stop: true });
    const openai = settingsWith(s => { s.transcription = { ...s.transcription, vendor: "openai_compatible",
      url: " http://127.0.0.1:18740/v1 ", model: "whisper-1", apiKey: "" }; });
    expect(engineSettingsFrom(openai)).toEqual({ transcription: { vendor: "openai_compatible", url: "http://127.0.0.1:18740/v1",
      model: "whisper-1", api_key: null }, refresh_seconds: 15, context_seconds: 90, cleanup_after_stop: false });
  });

  it("adds a server summary provider only for Gemini", () => {
    expect(summaryProviderWire(settingsWith(s => { s.summary.apiKey = "k"; })))
      .toEqual({ vendor: "gemini", model: "gemini-3.5-flash-lite", api_key: "k" });
    expect(summaryProviderWire(defaultAppSettings())?.api_key).toBeNull();
    expect(summaryProviderWire(settingsWith(s => { s.summary.vendor = "openai_compatible"; }))).toBeNull();
    expect(summaryProviderWire(settingsWith(s => { s.summary.vendor = "off"; }))).toBeNull();
  });

  it("reports a missing Gemini key per purpose", () => {
    const settings = settingsWith(s => { s.transcription.apiKey = "key"; });
    expect(missingGeminiKey(settings, "transcription")).toBe(false);
    expect(missingGeminiKey(settings, "summary")).toBe(true);
    settings.summary.apiKey = "  ";
    expect(missingGeminiKey(settings, "summary")).toBe(true);
    settings.summary.vendor = "openai_compatible";
    expect(missingGeminiKey(settings, "summary")).toBe(false);
    settings.transcription = { ...settings.transcription, vendor: "openai_compatible", apiKey: "" };
    expect(missingGeminiKey(settings, "transcription")).toBe(false);
  });
});

describe("J4 default prompt", () => {
  it("is a few lines whose JSON example is exactly the five-section contract the validators accept", () => {
    expect(DEFAULT_SUMMARY_PROMPT.trim().split("\n").length).toBeLessThanOrEqual(10);
    expect(DEFAULT_SUMMARY_PROMPT.length).toBeLessThan(1500);
    const start = DEFAULT_SUMMARY_PROMPT.indexOf('{"summary"');
    const example = JSON.parse(DEFAULT_SUMMARY_PROMPT.slice(start, DEFAULT_SUMMARY_PROMPT.lastIndexOf("]}") + 2));
    expect(Object.keys(example)).toEqual(["summary", "topics", "details", "speaker_background", "data_references"]);
    expect(Object.keys(example.topics[0])).toEqual(["title", "description"]);
    expect(Object.keys(example.details[0])).toEqual(["title", "description", "timestamp"]);
    expect(example.details[0].timestamp).toBe("HH:MM:SS");
    expect(typeof example.speaker_background[0]).toBe("string");
    expect(Object.keys(example.data_references[0])).toEqual(["item", "value", "context"]);
    example.details[0].timestamp = "00:00:05";
    expect(() => validateSummary(example, 10)).not.toThrow();
  });
});
