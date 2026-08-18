// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { storageKeys } from "../lib/persistence";

const mocks = vi.hoisted(() => {
  const poller = {
    start: vi.fn(),
    stop: vi.fn(),
    poll: vi.fn(),
    cursors: vi.fn(() => ({ version: 0, sequence: -1 }))
  };
  return { poller, createMossSessionPoller: vi.fn((_options: unknown) => poller) };
});

vi.mock("../api/mossPoller", () => ({
  createMossSessionPoller: mocks.createMossSessionPoller
}));

import { ControlPanel } from "./ControlPanel";

describe("ControlPanel reattach", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.append(root);
    window.sessionStorage.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    act(() => render(null, root));
    root.remove();
  });

  it("reattaches with only the tab-scoped view credential", async () => {
    window.sessionStorage.setItem(
      storageKeys.sessionReattach,
      JSON.stringify({ sessionId: "session-42", viewToken: "view-only" })
    );

    await act(async () => {
      render(<ControlPanel captureBearer="" onCaptureBearerChange={() => undefined} />, root);
    });

    expect(mocks.poller.start).toHaveBeenCalledOnce();
    expect(mocks.createMossSessionPoller).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: "session-42",
        accessToken: "view-only"
      })
    );
    expect(mocks.createMossSessionPoller.mock.calls[0][0]).not.toHaveProperty("terminalAccessToken");
    expect(root.querySelector('[role="status"]')?.textContent).toContain("Transcript reattached");
    const detach = [...root.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Detach transcript"
    );
    expect(detach).toBeTruthy();

    act(() => render(null, root));
    expect(mocks.poller.stop).toHaveBeenCalledOnce();
  });
});
