// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsDialog } from "./SettingsDialog";
import { loadAppSettings } from "../lib/settings";

const root = document.createElement("div");
document.body.append(root);
let values: Map<string, string>;
let fetcher: ReturnType<typeof vi.fn>;
const descriptor = (engine_options?: unknown) => ({ ok: true, json: async () => ({ descriptor: engine_options ? { engine_options } : {} }) });

beforeEach(() => {
  values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  fetcher = vi.fn(async (url: string) => url.startsWith("/api/live/descriptor") ? descriptor() : { ok: false, status: 404, json: async () => ({}) });
  vi.stubGlobal("fetch", fetcher);
});
afterEach(() => { render(null, root); vi.unstubAllGlobals(); });

const field = <T extends Element = HTMLInputElement>(label: string) => root.querySelector<T & HTMLElement>(`[aria-label="${label}"]`);
const status = () => root.querySelector(".llm-modal-status")!.textContent;
const button = (text: string) => [...root.querySelectorAll<HTMLButtonElement>("button")].find(b => b.textContent === text)!;
async function open() {
  await act(async () => render(<SettingsDialog />, root));
  await act(async () => root.querySelector<HTMLButtonElement>(".settings-trigger")!.click());
}
async function tab(name: string) { await act(async () => button(name).click()); }
async function type(label: string, value: string) {
  await act(async () => { const input = field(label)!; (input as HTMLInputElement).value = value;
    input.dispatchEvent(new Event("input", { bubbles: true })); });
}
async function choose(label: string, value: string) {
  await act(async () => { const select = field<HTMLSelectElement>(label)!; select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true })); });
}
async function toggle(label: string) { await act(async () => field(label)!.click()); }
async function save() { await act(async () => button("Save").click()); }

describe("three tabs", () => {
  it("opens on Transcription with the Gemini defaults and no URL", async () => {
    await open();
    expect([...root.querySelectorAll('[role="tab"]')].map(t => [t.textContent, t.getAttribute("aria-selected")]))
      .toEqual([["Transcription", "true"], ["Summary", "false"], ["General", "false"]]);
    expect(field<HTMLSelectElement>("Transcription vendor")!.value).toBe("gemini");
    expect([...field<HTMLSelectElement>("Transcription vendor")!.options].map(o => o.textContent))
      .toEqual(["Gemini (AI Studio)", "OpenAI-compatible"]);
    expect(field("Transcription URL")).toBeNull();
    expect(field("Transcription model")!.value).toBe("gemini-3.5-transcribe");
    expect(field("Transcription API key")!.type).toBe("password");
    expect(field("Transcription API key")!.placeholder).toBe("Optional; server default");
    expect(field("Refresh every (s)")!.value).toBe("15");
    expect(field("Context (s)")!.value).toBe("90");
    expect(root.querySelector("p:not(.eyebrow)")).toBeNull(); // No explanatory paragraphs.
    expect(fetcher.mock.calls[0][0]).toContain("/api/live/descriptor");
  });

  it("reveals the key with the eye toggle", async () => {
    await open();
    await act(async () => root.querySelector<HTMLButtonElement>('[aria-label="Show API key"]')!.click());
    expect(field("Transcription API key")!.type).toBe("text");
  });

  it("shows URL for OpenAI-compatible, never carries a key across vendors, and restores it when switching back", async () => {
    await open();
    await type("Transcription API key", "gemini-secret");
    await choose("Transcription vendor", "openai_compatible");
    expect(field("Transcription URL")).not.toBeNull();
    expect(field("Transcription API key")!.value).toBe("");
    expect(field("Transcription API key")!.placeholder).toBe("Optional");
    expect(field("Transcription model")!.value).toBe("gpt-4o-transcribe-diarize");
    await type("Transcription URL", "http://127.0.0.1:18740/v1");
    await type("Transcription model", "whisper-1");
    await choose("Transcription vendor", "gemini");
    expect(field("Transcription API key")!.value).toBe("gemini-secret");
    expect(field("Transcription model")!.value).toBe("gemini-3.5-transcribe");
    await choose("Transcription vendor", "openai_compatible");
    expect(field("Transcription URL")!.value).toBe("http://127.0.0.1:18740/v1");
    await save();
    expect(loadAppSettings().transcription).toEqual({ vendor: "openai_compatible", url: "http://127.0.0.1:18740/v1",
      model: "whisper-1", apiKey: "", refreshSeconds: 15, contextSeconds: 90 });
    expect(root.querySelector("dialog")).toBeNull();
  });

  it("Summary tab: vendor with Off, rolling + wait, language and a short prompt", async () => {
    await open();
    await tab("Summary");
    expect([...field<HTMLSelectElement>("Summary vendor")!.options].map(o => o.textContent))
      .toEqual(["Gemini (AI Studio)", "OpenAI-compatible", "Off"]);
    expect(field("Summary model")!.value).toBe("gemini-3.8-flash");
    expect(field("Summary URL")).toBeNull();
    expect(field("Rolling summary")!.checked).toBe(true);
    expect(field("Wait after each summary (s)")!.value).toBe("20");
    expect(field<HTMLTextAreaElement>("Summary prompt")!.rows).toBe(4);
    await type("Summary API key", "k");
    await type("Wait after each summary (s)", "0");
    await type("Summary language", "French");
    await toggle("Rolling summary");
    expect(field("Wait after each summary (s)")!.disabled).toBe(true);
    await save();
    expect(loadAppSettings().summary).toMatchObject({ vendor: "gemini", apiKey: "k", waitSeconds: 0, rolling: false, language: "French" });
  });

  it("Summary Off hides the provider fields and the Test button", async () => {
    await open();
    await tab("Summary");
    await choose("Summary vendor", "off");
    expect(field("Summary model")).toBeNull();
    expect(field("Summary API key")).toBeNull();
    expect(field("Rolling summary")).toBeNull();
    expect(button("Test")).toBeUndefined();
    await save();
    expect(loadAppSettings().summary.vendor).toBe("off");
  });

  it("Settings is an icon button; Rolling summary keeps the label-above field grammar of its neighbour (P6, P8)", async () => {
    await open();
    const trigger = root.querySelector<HTMLButtonElement>(".settings-trigger")!;
    expect(trigger.classList.contains("icon-btn")).toBe(true);
    expect(trigger.textContent).toBe("");
    await tab("Summary");
    const rolling = field("Rolling summary")!.closest("label")!;
    expect(rolling.classList.contains("llm-modal-field")).toBe(true);
    expect(rolling.querySelector(".field-label")!.textContent).toBe("Rolling summary");
    expect(field("Wait after each summary (s)")!.closest("label")!.querySelector(".field-label")!.textContent)
      .toBe("Wait after each summary (s)");
  });

  it("Rolling summary needs Gemini", async () => {
    await open();
    await tab("Summary");
    await choose("Summary vendor", "openai_compatible");
    expect(field("Rolling summary")!.disabled).toBe(true);
    expect(field("Rolling summary")!.closest("label")!.title).toBe("Rolling summary needs Gemini");
    expect(field("Summary URL")).not.toBeNull();
  });

  it("General: clean-up after Stop is disabled with the reason for OpenAI-compatible transcription (J1)", async () => {
    await open();
    await tab("General");
    expect(field("Improve transcript after Stop")!.checked).toBe(true);
    await toggle("Improve transcript after Stop");
    await save();
    expect(loadAppSettings().general.cleanupAfterStop).toBe(false);
    await act(async () => root.querySelector<HTMLButtonElement>(".settings-trigger")!.click());
    await choose("Transcription vendor", "openai_compatible");
    await tab("General");
    expect(field("Improve transcript after Stop")!.disabled).toBe(true);
    expect(field("Improve transcript after Stop")!.closest("label")!.title).toBe("Not available for OpenAI-compatible transcription");
  });

  it("Cancel keeps the saved settings", async () => {
    await open();
    await type("Transcription API key", "unsaved");
    await act(async () => button("Cancel").click());
    expect(root.querySelector("dialog")).toBeNull();
    expect(loadAppSettings().transcription.apiKey).toBe("");
    expect(values.has("moss.settings.v2")).toBe(false);
  });
});

describe("validation", () => {
  it.each([
    ["Refresh every (s)", "4", "Refresh every must be 5–60 seconds."],
    ["Refresh every (s)", "61", "Refresh every must be 5–60 seconds."],
    ["Refresh every (s)", "", "Refresh every must be 5–60 seconds."],
    ["Context (s)", "89", "Context must be 90–300 seconds."],
    ["Context (s)", "301", "Context must be 90–300 seconds."],
    ["Context (s)", "12.5", "Context must be 90–300 seconds."]
  ])("rejects %s = %j and stays open", async (label, value, message) => {
    await open();
    await type(label, value);
    await save();
    expect(status()).toBe(message);
    expect(root.querySelector("dialog")).not.toBeNull();
    expect(values.has("moss.settings.v2")).toBe(false);
  });

  it("uses descriptor bounds (I-3) when present", async () => {
    fetcher.mockImplementation(async () => descriptor({ transcription_vendors: ["gemini", "openai_compatible"],
      default_model: "gemini-3.5-transcribe", refresh_seconds: { min: 10, max: 30, default: 15 },
      context_seconds: { min: 120, max: 240, default: 120 }, cleanup_after_stop: { available: true, default: true } }));
    await open();
    await vi.waitFor(() => expect(field("Refresh every (s)")!.max).toBe("30"));
    await type("Refresh every (s)", "45");
    await save();
    expect(status()).toBe("Refresh every must be 10–30 seconds.");
    await type("Refresh every (s)", "30");
    await save();
    expect(status()).toBe("Context must be 120–240 seconds.");
  });

  it("switches to the tab that holds the problem", async () => {
    await open();
    await tab("Summary");
    await choose("Summary vendor", "openai_compatible");
    await type("Summary model", "gpt");
    await type("Summary URL", "http://insecure.example/v1");
    await tab("General");
    await save();
    expect(root.querySelector('[role="tab"][aria-selected="true"]')!.textContent).toBe("Summary");
    expect(status()).toBe("Use a trusted HTTPS provider URL without credentials, query or fragment.");
    await type("Wait after each summary (s)", "-1");
    await type("Summary URL", "https://api.example/v1");
    await save();
    expect(status()).toBe("Wait after each summary must be 0 seconds or more.");
  });

  it("requires a URL for OpenAI-compatible transcription", async () => {
    await open();
    await choose("Transcription vendor", "openai_compatible");
    await type("Transcription model", "whisper-1");
    await save();
    expect(status()).toBe("Enter the transcription URL (http or https).");
  });
});

describe("Test button", () => {
  it("tests the server fallback when the Gemini key is empty", async () => {
    await open();
    await act(async () => button("Test").click());
    expect(fetcher.mock.calls.some(([url]) => url === "/api/providers/test")).toBe(true);
    const [, init] = fetcher.mock.calls.find(([url]) => url === "/api/providers/test")!;
    expect(JSON.parse(init.body).api_key).toBeNull();
  });

  it("posts the tab's provider to /api/providers/test and shows Testing…, ok and the returned detail", async () => {
    let answer!: (value: unknown) => void;
    fetcher.mockImplementation(async (url: string) => url === "/api/providers/test"
      ? new Promise(resolve => { answer = resolve; }) : descriptor());
    await open();
    await type("Transcription API key", "k");
    await act(async () => button("Test").click());
    expect(button("Testing…").disabled).toBe(true);
    expect(button("Save").disabled).toBe(true);
    const [, init] = fetcher.mock.calls.find(([url]) => url === "/api/providers/test")!;
    expect(JSON.parse(init.body)).toEqual({ purpose: "transcription", vendor: "gemini", url: null,
      model: "gemini-3.5-transcribe", api_key: "k" });
    await act(async () => answer({ ok: true, json: async () => ({ ok: true }) }));
    await vi.waitFor(() => expect(status()).toBe("Connection OK"));
    expect(root.querySelector(".llm-modal-status")!.getAttribute("data-tone")).toBe("success");
    expect(button("Test").disabled).toBe(false);

    await tab("Summary");
    expect(status()).toBe("");
    await type("Summary API key", "bad");
    fetcher.mockImplementation(async () => ({ ok: true, json: async () => ({ ok: false, detail: "The API key was rejected." }) }));
    await act(async () => button("Test").click());
    await vi.waitFor(() => expect(status()).toBe("The API key was rejected."));
    expect(root.querySelector(".llm-modal-status")!.getAttribute("data-tone")).toBe("error");
    expect(JSON.parse(fetcher.mock.calls.at(-1)![1].body)).toMatchObject({ purpose: "summary", vendor: "gemini", api_key: "bad" });
  });

  it("tests an OpenAI-compatible summary provider from this browser, as it is used", async () => {
    await open();
    await tab("Summary");
    await choose("Summary vendor", "openai_compatible");
    await type("Summary URL", "https://api.example/v1");
    await type("Summary model", "gpt-x");
    await type("Summary API key", "sk");
    fetcher.mockImplementation(async () => ({ ok: true, json: async () => ({ data: [{ id: "other" }] }) }));
    await act(async () => button("Test").click());
    await vi.waitFor(() => expect(status()).toBe("The provider does not list this model."));
    const [url, init] = fetcher.mock.calls.at(-1)!;
    expect(url).toBe("https://api.example/v1/models");
    expect(init).toMatchObject({ credentials: "omit", headers: { Authorization: "Bearer sk" } });
    fetcher.mockImplementation(async () => ({ ok: true, json: async () => ({ data: [{ id: "gpt-x" }] }) }));
    await act(async () => button("Test").click());
    await vi.waitFor(() => expect(status()).toBe("Connection OK"));
    fetcher.mockImplementation(async () => { throw new TypeError("Failed to fetch"); });
    await act(async () => button("Test").click());
    await vi.waitFor(() => expect(status()).toBe("Could not reach the provider from this browser."));
  });
});
