import { openMeeting, type Meeting } from "../api/meetings";
import { finalSummaryWorker, SUMMARY_CHANGED, type SummaryArtifact, type SummarySettings } from "./finalSummary";
import { loadAppSettings, type AppSettings } from "./settings";
import { requestMeetingHistoryRefresh } from "./meetingEvents";

export interface LiveSummaryResponse {
  summary: string;
  source: { committed_samples: number; text_revision_version: number };
  generated_at_ms: number;
}

function summaryBody(settings: AppSettings) {
  return { model: settings.summary.model, language: settings.summary.language, prompt: settings.summary.prompt };
}

async function postJson<T>(path: string, body: unknown, fetcher: typeof fetch): Promise<T> {
  const response = await fetcher(path, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) {
    if (response.status === 409) throw new Error("Waiting for more finished speech or a matching transcript version.");
    throw new Error(`Summary request failed (${response.status}).`);
  }
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

function externalSettings(settings: AppSettings): SummarySettings {
  return { endpoint: settings.summary.externalUrl, model: settings.summary.externalModel,
    apiKey: settings.summary.externalApiKey, language: settings.summary.language,
    timeoutSeconds: settings.summary.timeoutSeconds, prompt: settings.summary.prompt };
}

export async function finalizeMeetingSummary(meeting: Meeting, settings = loadAppSettings()): Promise<void> {
  if (meeting.status !== "completed" || settings.summary.provider === "off") return;
  if (settings.summary.provider === "external") {
    await finalSummaryWorker.enqueue(meeting, externalSettings(settings));
  } else {
    const artifact = await requestFinalSummary(meeting.id, meeting.transcript_version, settings);
    document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: { meeting_id: meeting.id, artifact } }));
  }
  requestMeetingHistoryRefresh();
}

/** A creator watches only its own meeting; the final request is made once after Stop. */
export function watchMeetingSummary(id: string): () => void {
  const settings = loadAppSettings();
  let stopped = false;
  let timer: ReturnType<typeof setTimeout>;
  const poll = async () => {
    try {
      const meeting = await openMeeting(id);
      if (stopped) return;
      requestMeetingHistoryRefresh();
      if (meeting.status === "completed") {
        stopped = true;
        await finalizeMeetingSummary(meeting, settings);
        return;
      }
      if (meeting.status !== "active") { stopped = true; return; }
      timer = setTimeout(() => void poll(), 2000);
    } catch (error) {
      if (!stopped) document.dispatchEvent(new CustomEvent(SUMMARY_CHANGED, { detail: {
        meeting_id: id, error: error instanceof Error ? error.message : "Automatic summary unavailable." } }));
      stopped = true;
    }
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); };
}
