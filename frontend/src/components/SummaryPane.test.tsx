// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SummaryPane } from "./SummaryPane";
import { defaultAppSettings, saveAppSettings, type AppSettings } from "../lib/settings";
import { sessionId, sessionStatus } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";

const root = document.createElement("div"); document.body.append(root);
const rollingDocument = (summary: string) => ({ summary, topics: [], details: [],
  speaker_background: [], data_references: [] });
const live = (summary: string) => ({ ok: true, json: async () => ({ summary: rollingDocument(summary),
  source: { committed_samples: 48000, text_revision_version: 4 }, generated_at_ms: Date.now() }) });
const refresh = () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!;
const REMOVED = ["next in", "Waiting for first update", "Rolling summary is off", "Open a meeting to see its summary",
  "Summary will appear", "Finish transcription", "The summary is unavailable", "No saved summary yet", "Summary ready",
  "Retrying at the next interval"];

function configure(edit: (settings: AppSettings) => void = () => undefined) {
  const settings = defaultAppSettings();
  settings.summary.apiKey = "key";
  edit(settings);
  saveAppSettings(settings);
}
beforeEach(() => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  configure();
});
afterEach(() => {
  for (const text of REMOVED) expect(root.textContent).not.toContain(text);
  render(null, root); sessionId.value = null; sessionStatus.value = "idle"; selectedSummaryMeeting.value = null;
  vi.unstubAllGlobals(); vi.useRealTimers();
});

it("renders a rolling summary from the frozen live response with only 'Updated Ns ago'", async () => {
  const fetcher = vi.fn().mockResolvedValue(live("The team agreed."));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  expect(root.querySelector('[role="status"]')).toBeNull();
  await act(async () => refresh().click());
  await vi.waitFor(() => expect(root.textContent).toContain("The team agreed."));
  expect(fetcher.mock.calls[0][0]).toBe("/api/meetings/m/summary/live");
  expect(root.querySelector('[role="status"]')?.textContent).toMatch(/^Updated \d+s ago$/);
});

it("shows the whole rolling document while live, not only its theme (#6)", async () => {
  const summary = { summary: "Theme line.", topics: [{ title: "Pricing", description: "Price is what you pay." }],
    details: [{ title: "Graham", description: "The first book.", timestamp: "00:01:00" }],
    speaker_background: ["Speaker 2: investor"], data_references: [{ item: "Coupon", value: "5%", context: "A bond." }] };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ summary,
    source: { committed_samples: 48000, text_revision_version: 4 }, generated_at_ms: Date.now() }) }));
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => refresh().click());
  await vi.waitFor(() => expect(root.textContent).toContain("Theme line."));
  for (const text of ["Pricing", "Price is what you pay.", "00:01:00 · Graham", "Speaker 2: investor", "Coupon: 5%"])
    expect(root.textContent).toContain(text);
  // Only the saved final summary carries the final marker.
  expect(root.querySelector("[data-final-summary]")).toBeNull();
});

it("allows a blank browser key to use the server summary fallback", async () => {
  configure(settings => { settings.summary.apiKey = ""; });
  const fetcher = vi.fn().mockResolvedValue(live("never"));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  expect(refresh().disabled).toBe(false);
  await act(async () => refresh().click());
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetcher.mock.calls[0][1].body).provider.api_key).toBeNull();
});

it("disables Refresh with the reason when summaries are off or not Gemini during a meeting", async () => {
  configure(settings => { settings.summary.vendor = "off"; });
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  expect(refresh().disabled).toBe(true);
  expect(refresh().title).toBe("Summary is off in Settings");
  await act(async () => configure(settings => { settings.summary.vendor = "openai_compatible"; }));
  expect(refresh().title).toBe("Rolling summary needs Gemini");
  await act(async () => configure());
  expect(refresh().disabled).toBe(false);
});

it("waits after each request finishes, shows 'Summary failed' + Retry, and keeps the last summary", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn()
    .mockResolvedValueOnce(live("The first good update."))
    .mockResolvedValueOnce({ ok: false, status: 502, json: async () => ({ detail: { code: "summary_provider_error" } }) })
    .mockResolvedValueOnce(live("The recovered update."));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  // Default wait: 20 s after the previous request settles (#10).
  await act(async () => { await vi.advanceTimersByTimeAsync(19_999); });
  expect(fetcher).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(root.textContent).toContain("The first good update.");
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(root.textContent).toContain("The first good update.");
  expect(root.querySelector('[role="alert"]')?.textContent).toBe("Summary failed — the model provider returned an error.");
  expect(refresh().textContent).toBe("Retry");
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(root.textContent).toContain("The recovered update.");
  expect(root.querySelector('[role="alert"]')).toBeNull();
  expect(refresh().textContent).toBe("Refresh");
});

it("keeps too-little-speech refusals silent and retries them no sooner than the transcript refresh", async () => {
  vi.useFakeTimers();
  configure(settings => { settings.summary.waitSeconds = 0; settings.transcription.refreshSeconds = 15; });
  const notReady = { ok: false, status: 409, json: async () => ({ detail: "At least 40 transcript words are required." }) };
  const fetcher = vi.fn().mockResolvedValueOnce(notReady).mockResolvedValueOnce(notReady).mockResolvedValue(live("Ready now."));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(root.querySelector('[role="alert"]')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(14_999); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(15_001); });
  expect(fetcher).toHaveBeenCalledTimes(3);
  expect(root.textContent).toContain("Ready now.");
  // After a real summary, 0 means back-to-back again.
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(fetcher.mock.calls.length).toBeGreaterThan(3);
});

it("shows the reason when the user asked and there is too little speech", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409,
    json: async () => ({ detail: "At least 40 transcript words are required." }) }));
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => refresh().click());
  await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent)
    .toBe("Summary failed — At least 40 transcript words are required."));
});

it("sends no rolling requests when Rolling summary is unchecked, but Refresh still works", async () => {
  vi.useFakeTimers();
  configure(settings => { settings.summary.rolling = false; });
  const fetcher = vi.fn().mockResolvedValue(live("On demand."));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => { await vi.advanceTimersByTimeAsync(600_000); });
  expect(fetcher).not.toHaveBeenCalled();
  await act(async () => refresh().click());
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(root.textContent).toContain("On demand.");
  await act(async () => { await vi.advanceTimersByTimeAsync(600_000); });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("applies a changed wait, model, prompt and language to the next request without restarting", async () => {
  vi.useFakeTimers();
  const fetcher = vi.fn(async (_url: string, _init?: RequestInit) => live("Updated"));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
  await act(async () => configure(settings => { settings.summary.waitSeconds = 20; settings.summary.model = "gemini-3.5-flash";
    settings.summary.prompt = "New prompt"; settings.summary.language = "French"; }));
  await act(async () => { await vi.advanceTimersByTimeAsync(9_999); });
  expect(fetcher).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(JSON.parse(fetcher.mock.calls[0][1]!.body as string)).toEqual({ model: "gemini-3.5-flash", prompt: "New prompt",
    language: "French", provider: { vendor: "gemini", model: "gemini-3.5-flash", api_key: "key" } });
});

it("offers Retry when a final summary artifact or request fails", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  const failed = { state: "failed", attempt_id: "attempt", source_version: 1,
    artifact_version: 0, error_code: "delivery_failed", document: null };
  let reads = 0;
  const fetcher = vi.fn(async (_url: string, init?: RequestInit) => init?.method === "POST"
    ? { ok: false, status: 502, json: async () => ({}) }
    : { ok: true, json: async () => ({ summary: reads++ === 0 ? failed : null }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "closed";
  selectedSummaryMeeting.value = { id: "m", mode: "live", title: "Meeting", title_source: "automatic",
    status: "completed", created_at_ms: Date.now(), transcript_version: 1,
    transcript: { segments: [] }, audio: null };
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent)
    .toBe("Summary failed — the provider could not be reached."));
  const button = refresh();
  expect(button.textContent).toBe("Retry");
  await act(async () => button.click());
  await vi.waitFor(() => expect(root.textContent).toContain("Summary failed — the server answered 502."));
  expect(button.textContent).toBe("Retry");
  await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
  expect(reads).toBeGreaterThanOrEqual(2);
  expect(button.textContent).toBe("Retry");
  expect(root.textContent).toContain("Summary failed — the server answered 502.");
  expect(fetcher.mock.calls.some(([_url, init]) => init?.method === "POST")).toBe(true);
});

it("does not carry a rolling failure into a successful final summary", async () => {
  const artifact = { state: "current", attempt_id: "final", source_version: 1,
    artifact_version: 1, error_code: null, document: { summary: "Final decision.", topics: [],
      details: [], speaker_background: [], data_references: [] } };
  const fetcher = vi.fn(async (url: string) => url.endsWith("/summary/live")
    ? { ok: false, status: 502, json: async () => ({}) }
    : { ok: true, json: async () => ({ summary: artifact }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => refresh().click());
  await vi.waitFor(() => expect(root.querySelectorAll('[role="alert"]')).toHaveLength(1));
  await act(async () => { sessionStatus.value = "closed"; });
  await vi.waitFor(() => expect(root.textContent).toContain("Final decision."));
  expect(root.querySelectorAll(".summary-notice, [role='alert']")).toHaveLength(0);
  expect(refresh().textContent).toBe("Refresh");
});

it("regenerates an existing Gemini summary when refinement raises the transcript version", async () => {
  const document = (summary: string) => ({ summary, topics: [], details: [], speaker_background: [], data_references: [] });
  const old = { state: "current", attempt_id: "old", source_version: 1, artifact_version: 1,
    error_code: null, document: document("Old summary") };
  const improved = { ...old, attempt_id: "improved", source_version: 2, artifact_version: 2,
    document: document("Improved summary") };
  const fetcher = vi.fn(async (url: string, _init?: RequestInit) => url.endsWith("/summary/server")
    ? { ok: true, json: async () => improved }
    : { ok: true, json: async () => ({ summary: old }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "closed";
  selectedSummaryMeeting.value = { id: "m", mode: "live", title: "Meeting", title_source: "automatic",
    status: "completed", created_at_ms: Date.now(), transcript_version: 1, refinement_state: "running",
    transcript: { segments: [] }, audio: null };
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await vi.waitFor(() => expect(root.textContent).toContain("Old summary"));
  await act(async () => { selectedSummaryMeeting.value = { ...selectedSummaryMeeting.value!,
    transcript_version: 2, refinement_state: "done", refined_version: 2 }; });
  await vi.waitFor(() => expect(fetcher.mock.calls.some(([url]) => url.endsWith("/summary/server"))).toBe(true));
  const body = JSON.parse(fetcher.mock.calls.find(([url]) => url.endsWith("/summary/server"))![1]!.body as string);
  expect(body.source_version).toBe(2);
  expect(body.provider).toEqual({ vendor: "gemini", model: "gemini-3.8-flash", api_key: "key" });
  await vi.waitFor(() => expect(root.textContent).toContain("Improved summary"));
  expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/summary/server"))).toHaveLength(1);
});

it.each([
  { state: "failed", error_code: "delivery_failed" },
  { state: "failed", error_code: "source_changed" },
  { state: "cancelled", error_code: null }
])("regenerates an older terminal $state artifact ($error_code) after refinement", async ({ state, error_code }) => {
  const old = { state, attempt_id: "old", source_version: 1, artifact_version: 1,
    error_code, document: null };
  const improved = { ...old, state: "current", source_version: 2,
    document: { summary: "Improved summary", topics: [], details: [], speaker_background: [], data_references: [] } };
  const fetcher = vi.fn(async (url: string) => url.endsWith("/summary/server")
    ? { ok: true, json: async () => improved }
    : { ok: true, json: async () => ({ summary: old }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "closed";
  selectedSummaryMeeting.value = { id: "m", mode: "live", title: "Meeting", title_source: "automatic",
    status: "completed", created_at_ms: Date.now(), transcript_version: 2, refinement_state: "done", refined_version: 2,
    transcript: { segments: [] }, audio: null };
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await vi.waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/summary/server"))).toHaveLength(1));
  await vi.waitFor(() => expect(root.textContent).toContain("Improved summary"));
});

it("drops a late rolling response after switching meetings", async () => {
  let finishOld!: (response: unknown) => void;
  const oldResponse = new Promise(resolve => { finishOld = resolve; });
  const fetcher = vi.fn((url: string) => url.includes("/old/") ? oldResponse : Promise.resolve(live("New meeting summary")));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "old"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => refresh().click());
  await act(async () => { sessionId.value = "new"; });
  await act(async () => refresh().click());
  await vi.waitFor(() => expect(root.textContent).toContain("New meeting summary"));
  await act(async () => finishOld(live("Old meeting summary")));
  expect(root.textContent).toContain("New meeting summary");
  expect(root.textContent).not.toContain("Old meeting summary");
});

it("offers Update summary for a stale OpenAI-compatible artifact without sending automatically", async () => {
  configure(settings => { settings.summary = { ...settings.summary, vendor: "openai_compatible", url: "https://example.com/v1",
    model: "m", apiKey: "" }; });
  const old = { state: "current", attempt_id: "old", source_version: 1, artifact_version: 1,
    error_code: null, document: { summary: "Older summary", topics: [], details: [],
      speaker_background: [], data_references: [] } };
  const fetcher = vi.fn(async (_url: string) => ({ ok: true, json: async () => ({ summary: old }) }));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "closed";
  selectedSummaryMeeting.value = { id: "m", mode: "live", title: "Meeting", title_source: "automatic",
    status: "completed", created_at_ms: Date.now(), transcript_version: 2, refinement_state: "done", refined_version: 2,
    transcript: { segments: [] }, audio: null };
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await vi.waitFor(() => expect(refresh().textContent).toBe("Update summary"));
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/summary/server"))).toBe(false);
});

it.each([1, 3])("sends no summary request after %i speaker rename(s) of a cleaned-up meeting (D1, #15)", async renames => {
  const current = { state: "current", attempt_id: "a", source_version: 2, artifact_version: 1, error_code: null,
    document: { summary: "Clean-up summary", topics: [], details: [], speaker_background: [], data_references: [] } };
  const fetcher = vi.fn(async (_url: string) => ({ ok: true, json: async () => ({ summary: current }) }));
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "closed";
  selectedSummaryMeeting.value = { id: "m", mode: "live", title: "Meeting", title_source: "automatic",
    status: "completed", created_at_ms: Date.now(), transcript_version: 2, refinement_state: "done", refined_version: 2,
    transcript: { segments: [] }, audio: null };
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await vi.waitFor(() => expect(root.textContent).toContain("Clean-up summary"));
  for (let version = 3; version < 3 + renames; version += 1) {
    // Each rename's history refresh delivers the same meeting at a higher version.
    await act(async () => { selectedSummaryMeeting.value = { ...selectedSummaryMeeting.value!, transcript_version: version }; });
  }
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 50)); });
  expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/summary/server"))).toHaveLength(0);
  expect(refresh().textContent).toBe("Refresh");
  expect(root.textContent).not.toContain("Summary failed");
});
