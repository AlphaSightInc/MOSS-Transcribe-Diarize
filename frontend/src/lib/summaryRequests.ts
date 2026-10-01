import { openMeeting, type Meeting } from "../api/meetings";
import { finalSummaryWorker, SUMMARY_CHANGED, type SummaryArtifact, type SummaryDocument, type SummarySettings } from "./finalSummary";
import { loadAppSettings, summaryProviderWire, type AppSettings } from "./settings";
import { requestMeetingHistoryRefresh } from "./meetingEvents";

export interface LiveSummaryResponse {
  summary: SummaryDocument;
  source: { committed_samples: number; text_revision_version: number };
  generated_at_ms: number;
}

export const GEMINI_KEY_REQUIRED = "Enter your Gemini API key in Settings.";
const CODE_REASONS: Record<string, string> = {
  api_key_required: GEMINI_KEY_REQUIRED,
  summary_timeout: "the model did not answer in time.",
  summary_provider_error: "the model provider returned an error.",
  invalid_summary: "the model returned an unusable summary.",
  summary_in_flight: "another summary is still running.",
  summary_unavailable: "summaries are unavailable on this server.",
  // Saved artifact error codes.
  delivery_failed: "the provider could not be reached.",
  invalid_output: "the model returned an unusable summary.",
  request_rejected: "the provider rejected the request.",
  browser_worker_lost: "it was interrupted.",
  server_restarted: "it was interrupted.",
  source_changed: "the transcript changed."
};

/** A human reason for a failed summary; never a raw code. */
export function summaryFailureReason(code: string | null | undefined): string {
  return (code && CODE_REASONS[code]) || "";
}

export class SummaryRequestError extends Error {
  constructor(readonly status: number, readonly reason: string) { super(reason); }
  /** 409: the live transcript is not ready (too little finished speech); nothing was generated. */
  get notReady(): boolean { return this.status === 409; }
}

async function failure(response: Response): Promise<SummaryRequestError> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail ?? payload;
  const reason = typeof detail === "string" ? detail
    : summaryFailureReason(typeof detail?.code === "string" ? detail.code : null) || `the server answered ${response.status}.`;
  return new SummaryRequestError(response.status, reason);
}

function summaryBody(settings: AppSettings) {
  const provider = summaryProviderWire(settings);
  return { model: provider?.model ?? settings.summary.model, language: settings.summary.language,
    prompt: settings.summary.prompt, ...(provider ? { provider } : {}) };
}

async function postJson<T>(path: string, body: unknown, fetcher: typeof fetch): Promise<T> {
  const response = await fetcher(path, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw await failure(response);
  return response.json() as Promise<T>;
}

export function requestLiveSummary(id: string, settings: AppSettings, fetcher: typeof fetch = fetch): Promise<LiveSummaryResponse> {
  return postJson(`/api/meetings/${encodeURIComponent(id)}/summary/live`, summaryBody(settings), fetcher);
}

export function requestFinalSummary(id: string, version: number, settings: AppSettings,
  fetcher: typeof fetch = fetch): Promise<SummaryArtifact> {
  return postJson(`/api/meetings/${encodeURIComponent(id)}/summary/server`,
    { source_version: version, ...summaryBody(settings) }, fetcher);
}

export function externalSettings(settings: AppSettings): SummarySettings {
  return { endpoint: settings.summary.url, model: settings.summary.model,
    apiKey: settings.summary.apiKey, language: settings.summary.language,
    timeoutSeconds: settings.summary.timeoutSeconds, prompt: settings.summary.prompt };
}

/** D1 (issue #15): only the post-Stop clean-up outdates a saved summary. A speaker rename
 *  or passage correction bumps the version too, but Refresh is the user's choice there. */
export function summaryPredatesRefinement(meeting: Meeting, artifact: SummaryArtifact | null): boolean {
  if (meeting.refinement_state !== "done" || artifact == null ||
      !["current", "failed", "cancelled"].includes(artifact.state)) return false;
  // Meetings cleaned up before round 4 carry no clean-up version; keep the earlier rule for them.
  const refined = meeting.refined_version ?? meeting.transcript_version;
  return artifact.source_version < refined;
}

const FINAL_SUMMARY_ATTEMPTS = 4;
const FINAL_SUMMARY_RETRY_MS = 5000;

/** Settings are read when called, so a key or vendor entered after Start applies. */
export async function finalizeMeetingSummary(meeting: Meeting, settings = loadAppSettings()): Promise<void> {
  if (meeting.status !== "completed" || settings.summary.vendor === "off") return;
  if (settings.summary.vendor === "openai_compatible") {
    await finalSummaryWorker.enqueue(meeting, externalSettings(settings));
  } else {
    let artifact: SummaryArtifact;
    for (let attempt = 1; ; attempt++) {
      try {
        artifact = await requestFinalSummary(meeting.id, meeting.transcript_version, settings);
        break;
      } catch (cause) {
        // A rolling summary still running at Stop answers 429; it finishes within seconds.
        if (!(cause instanceof SummaryRequestError && cause.status === 429) || attempt >= FINAL_SUMMARY_ATTEMPTS) throw cause;
        await new Promise(resolve => setTimeout(resolve, FINAL_SUMMARY_RETRY_MS));
      }
    }
    document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: meeting.id, artifact } }));
  }
  requestMeetingHistoryRefresh();
}

/** A creator watches only its own meeting; the final request is made once after Stop. */
export function watchMeetingSummary(id: string): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  const poll = async () => {
    try {
      const meeting = await openMeeting(id);
      if (stopped) return;
      requestMeetingHistoryRefresh();
      if (meeting.status === "completed") {
        stopped = true;
        await finalizeMeetingSummary(meeting);
        return;
      }
      if (meeting.status !== "active") { stopped = true; return; }
      timer = setTimeout(() => void poll(), 2000);
    } catch (error) {
      if (!stopped) document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: {
        meeting_id: id, error: error instanceof SummaryRequestError ? error.reason : "the summary could not be requested." } }));
      stopped = true;
    }
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); };
}

export interface RollingLoop {
  /** Run now unless a run is in flight; the next wait is timed from this run's end. */
  now(): Promise<void>;
  /** Re-read the wait (e.g. after a settings change) relative to the last run's end. */
  reschedule(): void;
  dispose(): void;
}

/**
 * J3 rolling cadence: at most one run in flight; the next run starts `waitMs(last)` after the
 * previous run settles (success or failure). `waitMs` is read at every scheduling decision, so a
 * settings change applies without restarting; null means do not schedule (rolling off).
 */
export function createRollingLoop<Outcome>(run: () => Promise<Outcome>, // `run` reports its own failures.
  waitMs: (last: Outcome | undefined) => number | null): RollingLoop {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight: Promise<void> | null = null;
  let settledAt = Date.now();
  let last: Outcome | undefined;
  let disposed = false;
  const reschedule = () => {
    clearTimeout(timer); timer = undefined;
    if (disposed || inFlight) return;
    const wait = waitMs(last);
    if (wait === null) return;
    timer = setTimeout(() => void now(), Math.max(0, settledAt + wait - Date.now()));
  };
  const now = (): Promise<void> => {
    if (disposed) return Promise.resolve();
    if (inFlight) return inFlight;
    clearTimeout(timer); timer = undefined;
    inFlight = (async () => {
      try { last = await run(); }
      finally { settledAt = Date.now(); inFlight = null; reschedule(); }
    })();
    return inFlight;
  };
  reschedule();
  return { now, reschedule, dispose() { disposed = true; clearTimeout(timer); } };
}
