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
}
export interface SummarySettings {
  endpoint: string; model: string; apiKey: string; prompt: string; language: string; timeoutSeconds: number;
}
const SETTINGS_KEY = "moss.browser-final-summary.v1";
export const SUMMARY_CHANGED = "llm_status";
export const SUMMARY_RESULT = "llm_summary_update";
export const MEETING_CREATED = "moss:meeting-created";
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
  if (value.endpoint.trim()) {
    const url = new URL(value.endpoint.trim());
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
      throw new Error("Use a trusted HTTPS provider URL without credentials, query or fragment.");
    }
    if (url.origin === location.origin) throw new Error("Use an external provider, not the MOSS server.");
  }
  return { endpoint: value.endpoint.trim(), model: value.model.trim(), apiKey: value.apiKey,
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

export function providerBody(meeting: Meeting, settings: SummarySettings): string {
  if (meeting.status !== "completed" || !meeting.transcript?.segments.some(s => s.text.trim())) throw new Error("Finalized speech is required.");
  return JSON.stringify({ model: settings.model, stream: false, messages: [
    { role: "system", content: `${settings.prompt}${settings.language.trim() ? `\nWrite the final briefing in ${settings.language.trim()}.` : ""}` },
    { role: "user", content: JSON.stringify({ segments: meeting.transcript.segments.map(s => ({ start: s.start, end: s.end, speaker: s.speaker, text: s.text })) }) }
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
function publish(id: string, artifact: SummaryArtifact): void {
  document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: id, artifact } }));
  if (artifact.state === "current") {
    document.dispatchEvent(new CustomEvent(SUMMARY_RESULT, { detail: { meeting_id: id, artifact } }));
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
    const update = async (state: SummaryArtifact["state"], extra = {}) => {
      if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
      const result = (await summaryApi(meeting.id, jsonInit("PUT", { state, ...extra }), attempt.attempt_id, this.fetcher))!;
      if (signal.aborted) throw new DOMException("Cancelled", "AbortError");
      publish(meeting.id, result);
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
      for (let delivery = 0; delivery < 4; delivery++) {
        await update("generating");
        const request = new AbortController();
        const abort = () => request.abort();
        signal.addEventListener("abort", abort, { once: true });
        const timer = setTimeout(() => request.abort(), settings.timeoutSeconds * 1000);
        let content: unknown;
        let retry = false;
        let failure = "delivery_failed";
        try {
          const response = await this.fetcher(summaryUrl(settings.endpoint), {
            method: "POST", credentials: "omit", redirect: "error", referrerPolicy: "no-referrer",
            headers: { "Content-Type": "application/json", ...(settings.apiKey ? { Authorization: `Bearer ${settings.apiKey}` } : {}) },
            body, signal: request.signal
          });
          if (!response.ok) {
            retry = response.status === 408 || response.status === 429 || response.status >= 500;
            failure = retry ? "delivery_failed" : "request_rejected";
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
          await update("current", { document: result });
          return;
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
      if (optedIn) document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: id, error: "Automatic summary unavailable. Open this meeting and use Retry." } }));
      return;
    }
    timer = setTimeout(() => void poll(), 2000);
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); };
}
