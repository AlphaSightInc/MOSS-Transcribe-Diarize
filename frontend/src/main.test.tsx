// @vitest-environment jsdom

import { afterEach, expect, it, vi } from "vitest";

vi.mock("./lib/fileUpload", () => ({ bindFileUpload: vi.fn() }));
vi.mock("./App", () => ({ App: () => <div data-testid="app" /> }));
vi.mock("./components/MeetingHistory", () => ({
  MeetingHistory: () => <section data-testid="meeting-history" />
}));
vi.mock("./components/VoiceprintBank", () => ({
  VoiceprintBank: () => <section data-testid="voiceprints" />
}));
vi.mock("./lib/finalSummary", () => ({
  MEETING_CREATED: "moss:meeting-created",
  watchCreatedMeeting: vi.fn()
}));

afterEach(() => {
  document.body.replaceChildren();
});

it("removes server-rendered history fallback when the application boots", async () => {
  document.body.innerHTML = `
    <div id="meeting-history-app" data-history-root>
      <p data-history="empty">No meetings yet.</p>
    </div>
  `;

  await import("./main");

  const root = document.getElementById("meeting-history-app");
  expect(root?.querySelector('[data-history="empty"]')).toBeNull();
  expect(root?.querySelector('[data-testid="meeting-history"]')).not.toBeNull();
  expect(root?.getAttribute("data-history-boot")).toBe("ready");
});
