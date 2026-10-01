import { compareTranscriptOrder } from "./transcriptOrder";
import defaultPrompt from "./final-summary-prompt.txt?raw";
import { openMeeting, type Meeting } from "../api/meetings";

export interface SummaryDocument {
  summary: string;
  topics: { title: string; description: string }[];
  details: { title: string; description: string; timestamp: string }[];
  speaker_background: string[];
  data_references: { item: string; value: string; context: string }[];
}
export interface SummaryArtifact {
  state: "queued" | "generating" | "retry_wait" | "current" | "failed" | "cancelled";
  attempt_id: string;
  source_version: number;
  artifact_version: number;
  error_code: string | null;
  document: SummaryDocument | null;
  /** The name each speaker id was given to the generator under; absent on summaries saved before round 5. */
  speaker_names?: Record<string, string>;
}
export interface SummarySettings {
  endpoint: string; model: string; apiKey: string; prompt: string; language: string; timeoutSeconds: number;
}
const SETTINGS_KEY = "moss.browser-final-summary.v1";
export const SUMMARY_CHANGED = "llm_status";
export const SUMMARY_RESULT = "llm_summary_update";
export const MEETING_CREATED = "moss:meeting-created";
export const EXTERNAL_SUMMARY_MODELS = ["google/gemini-2.5-flash-lite", "google/gemini-2.5-flash"] as const;
export const RELAY_ENDPOINT = "/api/llm/chat/completions";
export interface RelayModel { id: string; upstream: string; }
export async function fetchRelayModels(fetcher: typeof fetch = fetch): Promise<RelayModel[]> {
  try {
    const response = await fetcher("/api/llm/models", { credentials: "same-origin" });
    if (!response.ok) return [];
    const result = await response.json();
    return Array.isArray(result.data) ? result.data.filter((m: RelayModel) =>
      typeof m?.id === "string" && m.id.trim() && typeof m.upstream === "string") : [];
  } catch { return []; }
}
export async function initializeRelaySettings(fetcher: typeof fetch = fetch): Promise<RelayModel[]> {
  const models = await fetchRelayModels(fetcher);
  // Existing external/disabled settings remain an explicit browser choice.
  if (models.length && window.localStorage.getItem(SETTINGS_KEY) === null) {
    saveSummarySettings({ ...defaultSettings(), endpoint: RELAY_ENDPOINT, model: models[0].id, timeoutSeconds: 200 });
  }
  return models;
}
export const RETRY_DELAYS = [60_000, 120_000, 240_000] as const;
export const defaultSettings = (): SummarySettings => ({ endpoint: "", model: "", apiKey: "", prompt: defaultPrompt, language: "", timeoutSeconds: 120 });

export function loadSummarySettings(): SummarySettings {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SETTINGS_KEY) ?? "null");
    if (!parsed) return defaultSettings();
    return validateSettings(parsed);
  } catch { return defaultSettings(); }
}
export function validateSettings(value: SummarySettings): SummarySettings {
  for (const key of ["endpoint", "model", "apiKey", "prompt", "language"] as const) {
    if (typeof value[key] !== "string") throw new Error("Invalid browser AI setting.");
  }
  if (!Number.isFinite(value.timeoutSeconds) || value.timeoutSeconds <= 0) throw new Error("Timeout must be positive.");
  if (value.endpoint.trim() && value.endpoint.trim() !== RELAY_ENDPOINT) {
    const url = new URL(value.endpoint.trim());
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
      throw new Error("Use a trusted HTTPS provider URL without credentials, query or fragment.");
    }
    if (url.origin === location.origin) throw new Error("Use an external provider, not the MOSS server.");
  }
  return { endpoint: value.endpoint.trim(), model: value.model.trim(), apiKey: value.endpoint.trim() === RELAY_ENDPOINT ? "" : value.apiKey,
    prompt: value.prompt, language: value.language, timeoutSeconds: value.timeoutSeconds };
}
export function saveSummarySettings(value: SummarySettings): void {
  window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(validateSettings(value)));
}
export function clearSummarySettings(): void { window.localStorage.removeItem(SETTINGS_KEY); }
export function summaryEnabled(settings = loadSummarySettings()): boolean { return Boolean(settings.endpoint && settings.model); }
export function summaryUrl(endpoint: string): string {
  const base = endpoint.replace(/\/+$/, "");
  return base.endsWith("/chat/completions") ? base : `${base}${base.endsWith("/v1") ? "" : "/v1"}/chat/completions`;
}
function summaryTimestamp(seconds: number): string {
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  return [hours, minutes, whole % 60].map(value => String(value).padStart(2, "0")).join(":");
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function keys(value: Record<string, unknown>, expected: string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every(key => key in value);
}
export function validateSummary(value: unknown, duration: number): SummaryDocument {
  if (!record(value) || !keys(value, ["summary", "topics", "details", "speaker_background", "data_references"]) ||
      typeof value.summary !== "string" || !value.summary.trim()) throw new Error("Invalid final-summary shape.");
  for (const [name, fields] of [["topics", ["title", "description"]], ["details", ["title", "description", "timestamp"]],
    ["data_references", ["item", "value", "context"]]] as const) {
    const entries = value[name];
    if (!Array.isArray(entries) || !entries.every(item => record(item) && keys(item, [...fields]) && Object.values(item).every(v => typeof v === "string"))) {
      throw new Error(`Invalid ${name}.`);
    }
    if (name === "details") for (const item of entries) {
      const stamp = item.timestamp as string;
      if (!/^\d{2}:[0-5]\d:[0-5]\d$/.test(stamp)) throw new Error("Invalid detail timestamp.");
      const [h, m, s] = stamp.split(":").map(Number);
      if (h * 3600 + m * 60 + s > duration) throw new Error("Detail timestamp exceeds transcript duration.");
    }
  }
  if (!Array.isArray(value.speaker_background) || !value.speaker_background.every(v => typeof v === "string")) throw new Error("Invalid speaker background.");
  return value as unknown as SummaryDocument;
}

/** Settings > Language, or (Auto) the transcript's own language; the server's Gemini path sends the same sentence. */
export function summaryLanguageRule(language: string): string {
  const target = language.trim();
  return target ? `Write the final briefing in ${target}.`
    : "Write every string value in the transcript's dominant language; do not translate it.";
}

export function providerBody(meeting: Meeting, settings: SummarySettings): string {
  if (meeting.status !== "completed" || !meeting.transcript?.segments.some(s => s.text.trim())) throw new Error("Finalized speech is required.");
  return JSON.stringify({ model: settings.model, max_tokens: 2048, ...(settings.endpoint === RELAY_ENDPOINT ? {} : { stream: false, response_format: { type: "json_object" } }), messages: [
    { role: "system", content: `${settings.prompt}\n${summaryLanguageRule(settings.language)}` },
    { role: "user", content: JSON.stringify({ segments: [...meeting.transcript.segments].sort(compareTranscriptOrder).map(s => ({ ...(s.source_lane ? { source_lane: s.source_lane } : {}), start: summaryTimestamp(s.start), end: summaryTimestamp(s.end), speaker: s.speaker, text: s.text })) }) }
  ] });
}
function path(id: string): string { return `/api/meetings/${encodeURIComponent(id)}/summary`; }
export async function summaryApi(id: string, init?: RequestInit, attempt?: string, fetcher: typeof fetch = fetch): Promise<SummaryArtifact | null> {
  const response = await fetcher(`${path(id)}${attempt ? `/${encodeURIComponent(attempt)}` : ""}`, init);
  if (!response.ok) throw new Error(response.status === 409 ? "Another summary attempt is active or this attempt ended. Refresh; Cancel before Retry." : `Summary request failed (${response.status}).`);
  const value = await response.json();
  return init ? value as SummaryArtifact : value.summary as SummaryArtifact | null;
}
const jsonInit = (method: string, value: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
function publish(id: string, artifact: SummaryArtifact, model?: string): void {
  document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: id, artifact, ...(model ? { model } : {}) } }));
  if (artifact.state === "current") {
    document.dispatchEvent(new CustomEvent(SUMMARY_RESULT, { detail: { meeting_id: id, artifact, ...(model ? { model } : {}) } }));
    document.dispatchEvent(new Event("moss:refresh-meeting-history"));
  }
}
export function abortableWait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}

/** One serial browser worker. The server arbitrates across tabs through attempt IDs. */
export class FinalSummaryWorker {
  private tail: Promise<void> = Promise.resolve();
  private jobs = new Map<string, { attempt: SummaryArtifact; controller: AbortController }>();
  constructor(private fetcher: typeof fetch = (...args) => fetch(...args),
              private wait = abortableWait) {}

  async enqueue(meeting: Meeting, settings = loadSummarySettings()): Promise<void> {
    if (!summaryEnabled(settings)) return;
    settings = validateSettings(settings);
    const body = providerBody(meeting, settings); // Exact immutable body across delivery retries.
    const attempt = (await summaryApi(meeting.id, jsonInit("POST", { source_version: meeting.transcript_version }), undefined, this.fetcher))!;
    const controller = new AbortController();
    this.jobs.set(meeting.id, { attempt, controller });
    publish(meeting.id, attempt);
    const run = this.tail.then(() => this.run(meeting, settings, body, attempt, controller));
    this.tail = run.catch(() => undefined);
    return run;
  }

  async cancel(id: string, attempt: SummaryArtifact): Promise<void> {
    const local = this.jobs.get(id);
    if (local?.attempt.attempt_id === attempt.attempt_id) local.controller.abort();
    const cancelled = (await summaryApi(id, jsonInit("PUT", { state: "cancelled" }), attempt.attempt_id, this.fetcher))!;
    publish(id, cancelled);
  }

  private async run(meeting: Meeting, settings: SummarySettings, body: string, attempt: SummaryArtifact, controller: AbortController): Promise<void> {
    const signal = controller.signal;
    const update = async (state: SummaryArtifact["state"], extra = {}, model?: string) => {
      if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
      const result = (await summaryApi(meeting.id, jsonInit("PUT", { state, ...extra }), attempt.attempt_id, this.fetcher))!;
      if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
      publish(meeting.id, result, model);
    };
    // Same-workspace tabs can cancel a worker while its provider request is pending.
    let checking = false;
    const monitor = setInterval(async () => {
      if (checking || signal.aborted) return;
      checking = true;
      try {
        const current = await summaryApi(meeting.id, undefined, undefined, this.fetcher);
        if (!current || current.attempt_id !== attempt.attempt_id || !["queued", "generating", "retry_wait"].includes(current.state)) controller.abort();
      } catch { controller.abort(); }
      finally { checking = false; }
    }, 2000);
    try {
      const relay = settings.endpoint === RELAY_ENDPOINT;
      const models = relay ? await fetchRelayModels(this.fetcher) : [];
      const index = models.findIndex(model => model.id === settings.model);
      const fallback = index >= 0 ? models[index + 1]?.id : undefined;
      let model = settings.model;
      for (let delivery = 0; delivery < (relay ? 2 : 4); delivery++) {
        // Relay fallback stays in the same generating attempt; no duplicate state transition.
        if (!relay || delivery === 0) await update("generating", {}, model);
        const request = new AbortController();
        const abort = () => request.abort();
        signal.addEventListener("abort", abort, { once: true });
        const timer = setTimeout(() => request.abort(), settings.timeoutSeconds * 1000);
        let content: unknown;
        let retry = false;
        let relayFallback = false;
        let failure = "delivery_failed";
        try {
          const response = await this.fetcher(summaryUrl(settings.endpoint), {
            method: "POST", credentials: relay ? "same-origin" : "omit", redirect: "error", referrerPolicy: "no-referrer",
            headers: { "Content-Type": "application/json", ...(!relay && settings.apiKey ? { Authorization: `Bearer ${settings.apiKey}` } : {}) },
            body: relay ? JSON.stringify({ ...JSON.parse(body), model }) : body, signal: request.signal
          });
          if (!response.ok) {
            retry = response.status === 408 || response.status === 429 || response.status >= 500;
            failure = retry ? "delivery_failed" : "request_rejected";
            if (relay && response.status === 502) {
              const error = await response.json().catch(() => ({}));
              relayFallback = ["empty_content", "upstream_error", "upstream_unreachable"].includes(error.detail);
            }
          } else {
            try { content = (await response.json()).choices?.[0]?.message?.content; }
            catch { failure = request.signal.aborted ? "delivery_failed" : "invalid_output"; retry = request.signal.aborted; }
            if (typeof content !== "string" && !retry) failure = "invalid_output";
          }
        } catch { retry = true; }
        finally { clearTimeout(timer); signal.removeEventListener("abort", abort); }
        if (signal.aborted) return;
        if (typeof content === "string") {
          let result: SummaryDocument;
          try {
            result = validateSummary(JSON.parse(content), Math.max(0, ...meeting.transcript!.segments.map(s => s.end)));
          } catch { await update("failed", { error_code: "invalid_output" }); return; }
          await update("current", { document: result }, model);
          return;
        }
        if (relay) {
          if (delivery === 0 && fallback && relayFallback) { model = fallback; continue; }
          await update("failed", { error_code: failure }, model); return;
        }
        if (!retry || delivery === 3) { await update("failed", { error_code: failure }); return; }
        await update("retry_wait");
        await this.wait(RETRY_DELAYS[delivery], signal);
      }
    } finally {
      clearInterval(monitor);
      if (this.jobs.get(meeting.id)?.attempt.attempt_id === attempt.attempt_id) this.jobs.delete(meeting.id);
    }
  }
}

export const finalSummaryWorker = new FinalSummaryWorker();

/** Called only by creating pages; opening history never registers a worker. */
export function watchCreatedMeeting(id: string, refreshHistory = false): () => void {
  const optedIn = summaryEnabled();
  if (!optedIn && !refreshHistory) return () => undefined;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  const poll = async () => {
    try {
      const meeting = await openMeeting(id);
      if (stopped) return;
      if (refreshHistory) document.dispatchEvent(new Event("moss:refresh-meeting-history"));
      if (meeting.status === "completed") {
        stopped = true;
        if (optedIn) await finalSummaryWorker.enqueue(meeting);
        return;
      }
      if (meeting.status !== "active") return;
    } catch {
      // No automatic inference retry after an unknown admission/persistence outcome.
      if (optedIn) document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: id, error: "Automatic summary unavailable. Open this meeting to try generating a summary again." } }));
      return;
    }
    timer = setTimeout(() => void poll(), 2000);
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); };
}
