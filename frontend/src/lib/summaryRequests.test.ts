// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defaultAppSettings, saveAppSettings, type AppSettings } from "./settings";
import { SUMMARY_CHANGED } from "./finalSummary";
import { createRollingLoop, requestFinalSummary, requestLiveSummary, summaryPredatesRefinement, SummaryRequestError, watchMeetingSummary } from "./summaryRequests";

beforeEach(() => {
  vi.restoreAllMocks();
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

const settingsWith = (edit: (settings: AppSettings) => void) => { const settings = defaultAppSettings(); edit(settings); return settings; };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("summary request bodies (I-2)", () => {
  it("adds the Gemini provider with the browser key to live requests", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ summary: {}, source: { committed_samples: 1, text_revision_version: 1 }, generated_at_ms: 1 }));
    const settings = settingsWith(s => { s.summary.language = "French"; s.summary.apiKey = "k"; s.summary.model = "gemini-3.5-flash"; });
    await requestLiveSummary("m", settings, fetcher);
    expect(fetcher.mock.calls[0][0]).toBe("/api/meetings/m/summary/live");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ model: "gemini-3.5-flash", language: "French",
      prompt: settings.summary.prompt, provider: { vendor: "gemini", model: "gemini-3.5-flash", api_key: "k" } });
  });

  it("finalizes at the authoritative transcript version", async () => {
    const fetcher = vi.fn().mockResolvedValue(json({ state: "current" }));
    await requestFinalSummary("m", 7, defaultAppSettings(), fetcher);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ source_version: 7, model: "gemini-3.8-flash",
      language: "", prompt: defaultAppSettings().summary.prompt,
      provider: { vendor: "gemini", model: "gemini-3.8-flash", api_key: null } });
  });

  it.each([
    [409, { detail: "At least 40 transcript words are required." }, "At least 40 transcript words are required.", true],
    [400, { detail: { code: "api_key_required" } }, "Enter your Gemini API key in Settings.", false],
    [502, { detail: { code: "summary_provider_error" } }, "the model provider returned an error.", false],
    [504, { detail: { code: "summary_timeout" } }, "the model did not answer in time.", false],
    [500, null, "the server answered 500.", false]
  ])("turns HTTP %i into a human reason", async (status, body, reason, notReady) => {
    const fetcher = vi.fn().mockResolvedValue(body === null ? new Response("oops", { status }) : json(body, status));
    const failure = await requestLiveSummary("m", defaultAppSettings(), fetcher).catch(error => error);
    expect(failure).toBeInstanceOf(SummaryRequestError);
    expect(failure.reason).toBe(reason);
    expect(failure.notReady).toBe(notReady);
  });
});

describe("watchMeetingSummary", () => {
  it("reads settings when the meeting completes, so a key entered during the meeting is used", async () => {
    vi.useFakeTimers();
    const posts: RequestInit[] = [];
    let reads = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/summary/server")) { posts.push(init!); return json({ state: "current" }); }
      return json({ id: "m", mode: "live", title: "M", title_source: "automatic", status: ++reads > 1 ? "completed" : "active",
        created_at_ms: 1, transcript_version: 3, transcript: { segments: [] }, audio: null });
    }));
    const artifacts = vi.fn();
    document.addEventListener(SUMMARY_CHANGED, artifacts);
    const stop = watchMeetingSummary("m");
    await vi.advanceTimersByTimeAsync(0);
    saveAppSettings(settingsWith(s => { s.summary.apiKey = "typed-later"; }));
    await vi.advanceTimersByTimeAsync(2000);
    stop();
    document.removeEventListener(SUMMARY_CHANGED, artifacts);
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0].body as string)).toMatchObject({ source_version: 3, provider: { api_key: "typed-later" } });
    expect(artifacts).toHaveBeenCalledOnce();
  });

  it("requests a Gemini summary with a blank key for the server fallback", async () => {
    const fetcher = vi.fn(async (_url: string, _init?: RequestInit) => json({ id: "m", mode: "live", title: "M", title_source: "automatic", status: "completed",
      created_at_ms: 1, transcript_version: 1, transcript: { segments: [] }, audio: null }));
    vi.stubGlobal("fetch", fetcher);
    watchMeetingSummary("m");
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalled());
    await new Promise(resolve => setTimeout(resolve, 0));
    const summary = fetcher.mock.calls.find(([url]) => String(url).includes("/summary"));
    expect(summary).toBeDefined();
    expect(JSON.parse(summary![1]!.body as string).provider.api_key).toBeNull();
  });
});

describe("summaryPredatesRefinement", () => {
  const artifact = (source_version: number) => ({ state: "current", source_version }) as never;
  const meeting = (extra: Record<string, unknown>) => ({ refinement_state: "done", transcript_version: 7, ...extra }) as never;
  it("compares with the clean-up version, so later renames do not make the summary stale", () => {
    expect(summaryPredatesRefinement(meeting({ refined_version: 5 }), artifact(5))).toBe(false);
    expect(summaryPredatesRefinement(meeting({ refined_version: 5 }), artifact(4))).toBe(true);
  });
  it("keeps the earlier rule for meetings cleaned up before the clean-up version was recorded", () => {
    expect(summaryPredatesRefinement(meeting({}), artifact(6))).toBe(true);
    expect(summaryPredatesRefinement(meeting({}), artifact(7))).toBe(false);
  });
});

describe("J3 rolling loop", () => {
  const deferred = () => { let resolve!: () => void; const promise = new Promise<void>(done => { resolve = done; }); return { promise, resolve }; };

  it("times each wait from the previous run's end and never overlaps", async () => {
    vi.useFakeTimers();
    const runs: number[] = [];
    let pending = deferred();
    const run = vi.fn(async () => { runs.push(Date.now()); await pending.promise; return "ok"; });
    const loop = createRollingLoop(run, () => 60_000);
    const start = Date.now();
    await vi.advanceTimersByTimeAsync(59_999);
    expect(run).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(1);
    // The request takes 25 s; a manual trigger meanwhile joins it instead of overlapping.
    await vi.advanceTimersByTimeAsync(10_000);
    void loop.now();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(run).toHaveBeenCalledTimes(1);
    const first = pending; pending = deferred(); first.resolve();
    await vi.advanceTimersByTimeAsync(0);
    const finished = Date.now();
    await vi.advanceTimersByTimeAsync(59_999);
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(2);
    expect(runs).toEqual([start + 60_000, finished + 60_000]);
    loop.dispose();
  });

  it("counts a failed run's end the same way", async () => {
    vi.useFakeTimers();
    const run = vi.fn(async () => { await new Promise(resolve => setTimeout(resolve, 5_000)); return "failed"; });
    const loop = createRollingLoop(run, () => 30_000);
    await vi.advanceTimersByTimeAsync(30_000 + 5_000 + 29_999);
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(2);
    loop.dispose();
  });

  it("with 0 starts the next run right after the previous one finishes", async () => {
    vi.useFakeTimers();
    let inFlight = 0, maxInFlight = 0;
    const run = vi.fn(async () => {
      inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise(resolve => setTimeout(resolve, 3_000));
      inFlight--; return "ok";
    });
    const loop = createRollingLoop(run, () => 0);
    await vi.advanceTimersByTimeAsync(7_000); // Runs at 0, 3 and 6 s; the third is in flight.
    expect(run).toHaveBeenCalledTimes(3);
    expect(maxInFlight).toBe(1);
    loop.dispose();
    await vi.advanceTimersByTimeAsync(9_000);
    expect(run).toHaveBeenCalledTimes(3);
    expect(inFlight).toBe(0);
  });

  it("picks up a changed wait relative to the last end, and null stops scheduling", async () => {
    vi.useFakeTimers();
    let wait: number | null = 300_000;
    const run = vi.fn(async () => "ok");
    const loop = createRollingLoop(run, () => wait);
    await vi.advanceTimersByTimeAsync(20_000);
    wait = 30_000; loop.reschedule();
    await vi.advanceTimersByTimeAsync(9_999);
    expect(run).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(1);
    wait = null; loop.reschedule();
    await vi.advanceTimersByTimeAsync(600_000);
    expect(run).toHaveBeenCalledTimes(1);
    await loop.now();
    expect(run).toHaveBeenCalledTimes(2);
    wait = 0; loop.reschedule();
    await vi.advanceTimersByTimeAsync(0);
    expect(run.mock.calls.length).toBeGreaterThan(2);
    loop.dispose();
  });

  it("passes the last outcome to the wait", async () => {
    vi.useFakeTimers();
    const outcomes = ["not_ready", "ok"];
    const run = vi.fn(async () => outcomes.shift() ?? "ok");
    const waitMs = vi.fn((last: string | undefined) => last === "not_ready" ? 15_000 : 1_000);
    const loop = createRollingLoop(run, waitMs);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(14_999);
    expect(run).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(run).toHaveBeenCalledTimes(2);
    expect(waitMs.mock.calls.map(([last]) => last)).toEqual([undefined, "not_ready", "ok"]);
    loop.dispose();
  });
});
