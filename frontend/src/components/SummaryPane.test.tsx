// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, expect, it, vi } from "vitest";
import { SummaryPane } from "./SummaryPane";
import { sessionId, sessionStatus } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";

const root = document.createElement("div"); document.body.append(root);
afterEach(() => { render(null, root); sessionId.value = null; sessionStatus.value = "idle"; selectedSummaryMeeting.value = null; vi.unstubAllGlobals(); });

it("renders a rolling summary from the frozen live response", async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ summary: "The team agreed.",
    source: { committed_samples: 48000, text_revision_version: 4 }, generated_at_ms: Date.now() }) });
  vi.stubGlobal("fetch", fetcher);
  sessionId.value = "m"; sessionStatus.value = "active";
  await act(async () => render(<SummaryPane hidden={false} />, root));
  await act(async () => root.querySelector<HTMLButtonElement>("button[data-summary-refresh]")!.click());
  await vi.waitFor(() => expect(root.textContent).toContain("The team agreed."));
  expect(fetcher.mock.calls[0][0]).toBe("/api/meetings/m/summary/live");
});
