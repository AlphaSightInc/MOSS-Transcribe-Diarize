// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import descriptor from "../test-fixtures/gemini-live-9fb217f4/descriptor.json";
import liveSummary from "../test-fixtures/gemini-live-9fb217f4/live-summary.json";
import serverSummary from "../test-fixtures/gemini-live-9fb217f4/server-summary.json";
import meetingDetail from "../test-fixtures/gemini-live-9fb217f4/meeting-detail.json";
import { SettingsDialog } from "../components/SettingsDialog";
import { SummaryPane } from "../components/SummaryPane";
import { defaultAppSettings } from "../lib/settings";
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

it("reads transcription options from the captured descriptor envelope", async () => {
  browserStorage();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => descriptor }));
  await act(async () => render(<SettingsDialog />, root));
  await act(async () => root.querySelector<HTMLButtonElement>(".settings-trigger")!.click());
  await vi.waitFor(() => expect(root.querySelector<HTMLSelectElement>('[aria-label="Speaker window"]')).not.toBeNull());
  expect(root.querySelector<HTMLSelectElement>('[aria-label="Speaker window"]')?.value)
    .toBe(descriptor.descriptor.engine_options.default_speaker_window);
  expect(root.querySelector<HTMLInputElement>('.settings-checkbox input')?.checked)
    .toBe(descriptor.descriptor.engine_options.cleanup_after_stop.default);
});

it("renders the captured live-summary document as visible theme text", async () => {
  browserStorage();
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => liveSummary }));
  sessionId.value = meetingDetail.id; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!.click());
  await vi.waitFor(() => expect(root.textContent).toContain(liveSummary.summary.summary));
  expect(root.querySelector(".summary-content p")?.textContent).toBe(liveSummary.summary.summary);
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
