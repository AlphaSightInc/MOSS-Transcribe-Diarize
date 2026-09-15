// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { Meeting } from "../api/meetings";
import {
  FinalSummaryWorker, defaultSettings, loadSummarySettings, saveSummarySettings,
  clearSummarySettings, summaryEnabled, providerBody, validateSummary, validateSettings,
  watchCreatedMeeting, abortableWait, type SummaryArtifact, RELAY_ENDPOINT, initializeRelaySettings, SUMMARY_CHANGED
} from "./finalSummary";

const result = { summary: "Grounded", topics: [{ title: "Title", description: "Reason" }], details: [{ title: "Evidence", description: "Fact", timestamp: "00:00:04" }], speaker_background: [], data_references: [] };
const meeting = (id = "private-meeting-A"): Meeting => ({ id, mode: "file", title: "PRIVATE TITLE", title_source: "automatic", status: "completed", created_at_ms: 0,
  transcript: { segments: [{ id: "private-segment", speaker_entity_id: "private-canonical", start: 0, end: 4, speaker: "Alex", text: `ONLY ${id === "private-meeting-A" ? "A" : "B"} TRANSCRIPT` }] }, transcript_version: 3, audio: null });
const settings = () => ({ ...defaultSettings(), endpoint: "https://provider.test/v1", model: "MY MODEL", apiKey: "MY SECRET", prompt: "MY PROMPT", language: "English" });
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const answer = () => response({ choices: [{ message: { content: JSON.stringify(result) } }] });

function harness(provider: (url: string, init: RequestInit) => Promise<Response>) {
  const artifacts = new Map<string, SummaryArtifact>();
  const mossCalls: { url: string; init?: RequestInit }[] = [];
  let attempts = 0;
  const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("https://provider.test") || url === RELAY_ENDPOINT) return provider(url, init!);
    if (url === "/api/llm/models") return response({ data: [{ id: "primary", upstream: "macstudio" }, { id: "fallback", upstream: "rtx4090" }] });
    mossCalls.push({ url, init });
    const id = url.split("/")[3];
    const body = JSON.parse(String(init?.body ?? "null"));
    if (init?.method === "POST") {
      const value: SummaryArtifact = { state: "queued", document: null, attempt_id: `attempt-${++attempts}`, source_version: body.source_version, artifact_version: attempts, error_code: null };
      artifacts.set(id, value); return response(value);
    }
    if (init?.method === "PUT") {
      const current = artifacts.get(id)!;
      if (url.split("/").at(-1) !== current.attempt_id || ["current", "cancelled", "failed"].includes(current.state)) return response({}, 409);
      const allowed: Record<string, string[]> = { queued: ["generating", "failed", "cancelled"], generating: ["retry_wait", "current", "failed", "cancelled"], retry_wait: ["generating", "failed", "cancelled"] };
      if (!allowed[current.state]?.includes(body.state)) return response({}, 409);
      const value = { ...current, ...body };
      artifacts.set(id, value); return response(value);
    }
    return response({ summary: artifacts.get(id) ?? null });
  });
  return { fetcher, artifacts, mossCalls };
}

beforeEach(() => {
  const data = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value), removeItem: (key: string) => data.delete(key) });
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("keeps settings local, blank disables, rejects own-origin/provider URL credentials", () => {
  expect(summaryEnabled()).toBe(false);
  saveSummarySettings(settings()); expect(loadSummarySettings()).toEqual(settings());
  clearSummarySettings(); expect(summaryEnabled()).toBe(false);
  for (const endpoint of [location.origin, "https://user:pass@provider.test", "https://provider.test?key=secret", "http://provider.test"]) {
    expect(() => validateSettings({ ...settings(), endpoint })).toThrow();
  }
});

it("sends only projected final transcript and browser parameters, never meeting IDs/history/audio", () => {
  const body = providerBody(meeting(), settings());
  expect(JSON.parse(body)).toMatchObject({ max_tokens: 2048, stream: false, response_format: { type: "json_object" } });
  expect(body).toContain("ONLY A TRANSCRIPT"); expect(body).toContain("MY MODEL"); expect(body).toContain("MY PROMPT");
  for (const forbidden of ["MY SECRET", "private-meeting", "private-segment", "private-canonical", "PRIVATE TITLE", "audio", "ONLY B TRANSCRIPT"]) expect(body).not.toContain(forbidden);
  expect(() => providerBody({ ...meeting(), status: "active" }, settings())).toThrow();
});

it("formats every provider segment timestamp as floored HH:MM:SS, including hours", () => {
  const source = meeting();
  const segment = source.transcript!.segments[0];
  const timed = { ...source, transcript: { segments: [
    { ...segment, start: 3.87, end: 59.64 },
    { ...segment, start: 98.16, end: 3661.99 },
  ] } };
  for (const endpoint of [settings().endpoint, RELAY_ENDPOINT]) {
    const body = JSON.parse(providerBody(timed, { ...settings(), endpoint }));
    const payload = JSON.parse(body.messages[1].content);
    expect(payload.segments.map(({ start, end }: { start: string; end: string }) => [start, end])).toEqual([
      ["00:00:03", "00:00:59"],
      ["00:01:38", "01:01:01"],
    ]);
  }
});

it("validates exact raw shape and timestamp bounds without repair or digit coverage", () => {
  expect(validateSummary(result, 4)).toEqual(result);
  for (const value of [ { ...result, extra: "no" }, { ...result, summary: " " }, { ...result, topics: {} },
    { ...result, details: [{ ...result.details[0], timestamp: "00:00:05" }] },
    { ...result, details: [{ ...result.details[0], timestamp: "00:60:00" }] }, { ...result, speaker_background: [{}] } ]) {
    expect(() => validateSummary(value, 4)).toThrow();
  }
});

it("retries exactly four identical deliveries at 60/120/240 seconds, without leaking configuration to MOSS", async () => {
  const external: { url: string; init: RequestInit }[] = [];
  const h = harness(async (url, init) => { external.push({ url, init }); return response({}, 503); });
  const waits: number[] = [];
  await new FinalSummaryWorker(h.fetcher, async ms => { waits.push(ms); }).enqueue(meeting(), settings());
  expect(external).toHaveLength(4); expect(waits).toEqual([60_000, 120_000, 240_000]);
  expect(new Set(external.map(call => call.init.body)).size).toBe(1);
  expect(external[0].init).toMatchObject({ credentials: "omit", redirect: "error", referrerPolicy: "no-referrer", headers: { Authorization: "Bearer MY SECRET" } });
  expect(h.artifacts.get(meeting().id)?.state).toBe("failed");
  const moss = JSON.stringify(h.mossCalls);
  for (const forbidden of ["MY MODEL", "MY SECRET", "MY PROMPT", "provider.test", "English"]) expect(moss).not.toContain(forbidden);
});

it.each(["malformed", "fenced", "missing", "http400"])("fails %s without repair", async kind => {
  let count = 0;
  const h = harness(async () => { count++; return kind === "http400" ? response({}, 400)
    : response({ choices: [{ message: { content: kind === "malformed" ? "{" : kind === "fenced" ? `\x60\x60\x60json\n${JSON.stringify(result)}\n\x60\x60\x60` : {} } }] }); });
  await new FinalSummaryWorker(h.fetcher).enqueue(meeting(), settings());
  expect(count).toBe(1); expect(h.artifacts.get(meeting().id)?.state).toBe("failed");
});

it("serializes two ready meetings and keeps their requests separate", async () => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const bodies: string[] = [];
  const h = harness(async (_url, init) => { bodies.push(String(init.body)); if (bodies.length === 1) await held; return answer(); });
  const worker = new FinalSummaryWorker(h.fetcher);
  const a = worker.enqueue(meeting(), settings());
  const b = worker.enqueue(meeting("private-meeting-B"), settings());
  await vi.waitFor(() => expect(bodies).toHaveLength(1));
  expect(h.artifacts.get("private-meeting-B")?.state).toBe("queued");
  release(); await Promise.all([a, b]);
  expect(bodies).toHaveLength(2);
  expect(bodies[0]).not.toContain("ONLY B TRANSCRIPT"); expect(bodies[1]).not.toContain("ONLY A TRANSCRIPT");
  expect([...h.artifacts.values()].every(a => a.state === "current")).toBe(true);
});

it("cancels pending provider work and rejects a late response", async () => {
  let externalSignal: AbortSignal | undefined;
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const h = harness(async (_url, init) => { externalSignal = init.signal as AbortSignal; await held; return answer(); });
  const worker = new FinalSummaryWorker(h.fetcher);
  const task = worker.enqueue(meeting(), settings());
  await vi.waitFor(() => expect(externalSignal).toBeDefined());
  await worker.cancel(meeting().id, h.artifacts.get(meeting().id)!);
  expect(externalSignal?.aborted).toBe(true);
  release(); await task;
  expect(h.artifacts.get(meeting().id)?.state).toBe("cancelled");
  expect(h.artifacts.get(meeting().id)?.document).toBeNull();
});

it("does not dispatch externally when Cancel wins during the generating response", async () => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const external = vi.fn(async () => answer());
  const h = harness(external);
  let generating = false;
  const fetcher: typeof fetch = async (url, init) => {
    const response = await h.fetcher(url, init);
    if (init?.method === "PUT" && JSON.parse(String(init.body)).state === "generating") {
      generating = true; await held;
    }
    return response;
  };
  const worker = new FinalSummaryWorker(fetcher);
  const task = worker.enqueue(meeting(), settings()).catch(() => undefined);
  await vi.waitFor(() => expect(generating).toBe(true));
  await worker.cancel(meeting().id, h.artifacts.get(meeting().id)!);
  release(); await task;
  expect(external).not.toHaveBeenCalled();
  expect(h.artifacts.get(meeting().id)?.state).toBe("cancelled");
});

it("cancels scheduled retries without another provider call", async () => {
  const h = harness(async () => response({}, 429));
  const waiting = vi.fn(abortableWait);
  const worker = new FinalSummaryWorker(h.fetcher, waiting);
  const task = worker.enqueue(meeting(), settings()).catch(() => undefined);
  await vi.waitFor(() => expect(waiting).toHaveBeenCalledTimes(1));
  await worker.cancel(meeting().id, h.artifacts.get(meeting().id)!);
  await task;
  expect(h.fetcher.mock.calls.filter(call => String(call[0]).startsWith("https:"))).toHaveLength(1);
});

it("never starts a browser watcher while settings are blank", () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  watchCreatedMeeting("history-id")();
  expect(fetcher).not.toHaveBeenCalled();
});


it("allows only the exact same-origin relay endpoint and never stores a relay key", () => {
  expect(validateSettings({ ...settings(), endpoint: RELAY_ENDPOINT }).apiKey).toBe("");
  for (const endpoint of ["/api/other", "//elsewhere.test/api/llm/chat/completions", RELAY_ENDPOINT + "?url=evil"]) {
    expect(() => validateSettings({ ...settings(), endpoint })).toThrow();
  }
  const body = JSON.parse(providerBody(meeting(), { ...settings(), endpoint: RELAY_ENDPOINT }));
  expect(Object.keys(body).sort()).toEqual(["max_tokens", "messages", "model"]);
  expect(body.max_tokens).toBe(2048);
  expect(body.response_format).toBeUndefined();
});

it("defaults fresh settings to the first relay model but preserves explicit external settings", async () => {
  const fetcher = vi.fn(async () => response({ data: [{ id: "primary", upstream: "macstudio" }] }));
  await initializeRelaySettings(fetcher);
  expect(loadSummarySettings()).toMatchObject({ endpoint: RELAY_ENDPOINT, model: "primary", apiKey: "", timeoutSeconds: 200 });
  saveSummarySettings(settings());
  await initializeRelaySettings(fetcher);
  expect(loadSummarySettings()).toEqual(settings());
});

it.each(["empty_content", "upstream_unreachable", "upstream_error"])("falls back once on relay %s and names the successful model", async reason => {
  const calls: { body: Record<string, unknown>; init: RequestInit }[] = [];
  const events: unknown[] = [];
  const listener = (event: Event) => events.push((event as CustomEvent).detail);
  document.addEventListener(SUMMARY_CHANGED, listener);
  const h = harness(async (_url, init) => {
    calls.push({ body: JSON.parse(String(init.body)), init });
    return calls.length === 1 ? response({ detail: reason }, 502) : answer();
  });
  const wait = vi.fn();
  try {
    await new FinalSummaryWorker(h.fetcher, wait).enqueue(meeting(), { ...settings(), endpoint: RELAY_ENDPOINT, model: "primary" });
    expect(calls.map(c => c.body.model)).toEqual(["primary", "fallback"]);
    expect(calls[0].body.messages).toEqual(calls[1].body.messages);
    expect(calls[0].init.credentials).toBe("same-origin");
    expect(calls[0].init.headers).toEqual({ "Content-Type": "application/json" });
    expect(wait).not.toHaveBeenCalled();
    expect(h.artifacts.get(meeting().id)?.state).toBe("current");
    expect(events).toContainEqual(expect.objectContaining({ model: "fallback", artifact: expect.objectContaining({ state: "current" }) }));
    expect(JSON.stringify(h.mossCalls)).not.toContain("fallback"); // Model stays out of durable summary updates.
  } finally { document.removeEventListener(SUMMARY_CHANGED, listener); }
});

it("stops after the relay fallback fails, without four delivery retry rounds", async () => {
  let calls = 0;
  const h = harness(async () => { calls++; return response({ detail: "empty_content" }, 502); });
  const wait = vi.fn();
  await new FinalSummaryWorker(h.fetcher, wait).enqueue(meeting(), { ...settings(), endpoint: RELAY_ENDPOINT, model: "primary" });
  expect(calls).toBe(2); expect(wait).not.toHaveBeenCalled();
  expect(h.artifacts.get(meeting().id)?.state).toBe("failed");
});

it.each([404, 401, 400])("does not switch relay models for HTTP %s", async status => {
  let calls = 0;
  const h = harness(async () => { calls++; return response({ detail: "unknown_model" }, status); });
  await new FinalSummaryWorker(h.fetcher).enqueue(meeting(), { ...settings(), endpoint: RELAY_ENDPOINT, model: "primary" });
  expect(calls).toBe(1);
});
