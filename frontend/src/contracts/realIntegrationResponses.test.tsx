// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import descriptor from "../test-fixtures/gemini-live-9fb217f4/descriptor.json";
import liveSummary from "../test-fixtures/gemini-live-9fb217f4/live-summary.json";
import serverSummary from "../test-fixtures/gemini-live-9fb217f4/server-summary.json";
import meetingDetail from "../test-fixtures/gemini-live-9fb217f4/meeting-detail.json";
import { readEngineOptions, SettingsDialog } from "../components/SettingsDialog";
import { SummaryPane } from "../components/SummaryPane";
import { defaultAppSettings, saveAppSettings } from "../lib/settings";
import { requestFinalSummary } from "../lib/summaryRequests";
import { openMeeting } from "../api/meetings";
import { sessionId, sessionStatus } from "../state/session";

const root = document.createElement("div"); document.body.append(root);
afterEach(() => { render(null, root); sessionId.value = null; sessionStatus.value = "idle";
  vi.unstubAllGlobals(); });

function browserStorage() {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key) });
}

it("keeps the documented fallback bounds for the captured round-2 descriptor (no I-3 seconds)", async () => {
  browserStorage();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => descriptor }));
  expect(readEngineOptions(descriptor)).toMatchObject({ vendors: ["gemini", "openai_compatible"],
    refresh: { min: 5, max: 60 }, context: { min: 90, max: 300 },
    cleanupAvailable: descriptor.descriptor.engine_options.cleanup_after_stop.available });
  await act(async () => render(<SettingsDialog />, root));
  await act(async () => root.querySelector<HTMLButtonElement>(".settings-trigger")!.click());
  expect(root.querySelector<HTMLInputElement>('[aria-label="Refresh every (s)"]')?.value).toBe("15");
  expect(root.querySelector<HTMLInputElement>('[aria-label="Context (s)"]')?.value).toBe("90");
});

it("renders the captured live-summary document with its theme", async () => {
  browserStorage();
  saveAppSettings({ ...defaultAppSettings(), summary: { ...defaultAppSettings().summary, apiKey: "key" } });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => liveSummary }));
  sessionId.value = meetingDetail.id; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!.click());
  await vi.waitFor(() => expect(root.textContent).toContain(liveSummary.summary.summary));
  expect(root.querySelector(".summary-content h3")?.textContent).toBe(liveSummary.summary.summary);
});

it("parses the captured final-summary response at the saved version", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => serverSummary });
  const artifact = await requestFinalSummary(meetingDetail.id, meetingDetail.transcript_version,
    defaultAppSettings(), fetcher);
  expect(artifact.state).toBe("current");
  expect(artifact.source_version).toBe(meetingDetail.transcript_version);
  expect(artifact.document?.summary).toBe(serverSummary.document.summary);
});

it("parses the captured completed meeting with refinement state", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => meetingDetail });
  const meeting = await openMeeting(meetingDetail.id, fetcher);
  expect(meeting.status).toBe("completed");
  expect(meeting.refinement_state).toBe("done");
  expect(meeting.transcript_version).toBe(serverSummary.source_version);
  expect(meeting.transcript?.segments.length).toBeGreaterThan(0);
});
