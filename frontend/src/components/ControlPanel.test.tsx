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
  return {
    poller,
    createMossSessionPoller: vi.fn((_options: unknown) => poller),
    captureOptions: null as {
      authority?: string;
      captureBearer?: string;
      onPreflightStatus?: (statusLine: string) => void;
    } | null,
  };
});

vi.mock("../api/mossPoller", () => ({
  createMossSessionPoller: mocks.createMossSessionPoller
}));

vi.mock("../capture/captureClient", () => ({
  CaptureClient: class {
    constructor(options: { onPreflightStatus?: (statusLine: string) => void }) {
      mocks.captureOptions = options;
    }

    prepare = vi.fn().mockResolvedValue(undefined);
    startMicrophone = vi.fn().mockResolvedValue(undefined);
    close = vi.fn().mockResolvedValue(undefined);
  }
}));

import { ControlPanel, LIVE_MEETING_OBSERVE_EVENT } from "./ControlPanel";

describe("ControlPanel reattach", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.append(root);
    window.sessionStorage.clear();
    vi.clearAllMocks();
    mocks.captureOptions = null;
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

  it("renders the server-supplied remedy at silent-microphone preflight", async () => {
    const remedy =
      "No microphone sound was detected. In Chrome, open Settings > Privacy and security > " +
      "Site settings > Microphone and select the correct default input.";

    await act(async () => {
      render(<ControlPanel captureBearer="capture-token" onCaptureBearerChange={() => undefined} />, root);
    });
    const enableMicrophone = [...root.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Enable microphone",
    );
    if (!enableMicrophone) throw new Error("missing enable microphone button");
    await act(async () => {
      enableMicrophone.click();
    });

    act(() => mocks.captureOptions?.onPreflightStatus?.(remedy));

    expect(root.querySelector('[role="status"]')?.textContent).toBe(remedy);
  });

  it("starts Account capture without rendering or requiring a bearer", async () => {
    await act(async () => {
      render(
        <ControlPanel
          authority="account"
          captureBearer=""
          onCaptureBearerChange={() => undefined}
        />,
        root,
      );
    });
    expect(root.querySelector('[aria-label="Capture bearer"]')).toBeNull();
    const enableMicrophone = [...root.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Enable microphone",
    );
    expect(enableMicrophone?.disabled).toBe(false);
    await act(async () => enableMicrophone?.click());
    expect(mocks.captureOptions).toMatchObject({ authority: "account" });
    expect(mocks.captureOptions?.captureBearer).toBeUndefined();
  });

  it("opens an active history Meeting as an ephemeral Account observer", async () => {
    await act(async () => {
      render(
        <ControlPanel authority="account" captureBearer="" onCaptureBearerChange={() => undefined} />,
        root,
      );
    });

    act(() => {
      document.dispatchEvent(
        new CustomEvent(LIVE_MEETING_OBSERVE_EVENT, {
          detail: { meetingId: "active-live-meeting" }
        })
      );
    });

    expect(mocks.createMossSessionPoller).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: "active-live-meeting",
        authority: "account"
      })
    );
    expect(mocks.createMossSessionPoller.mock.calls[0][0]).not.toHaveProperty("accessToken");
    expect(mocks.poller.start).toHaveBeenCalledOnce();
    expect(root.querySelector('[data-capture-phase="viewing"]')).not.toBeNull();
    expect(root.querySelector('[data-observer-mode="read-only"]')).not.toBeNull();
    expect(root.querySelector('select[aria-label="Listening setup"]')).toHaveProperty("disabled", true);
    expect(root.textContent).toContain("active Live Meeting read-only");
    expect(root.textContent).not.toContain("Enable microphone");
    expect(window.sessionStorage.getItem(storageKeys.sessionReattach)).toBeNull();

    act(() => render(null, root));
    mocks.createMossSessionPoller.mockClear();
    mocks.poller.start.mockClear();
    await act(async () => {
      render(
        <ControlPanel authority="account" captureBearer="" onCaptureBearerChange={() => undefined} />,
        root,
      );
    });
    expect(mocks.createMossSessionPoller).not.toHaveBeenCalled();
    expect(root.querySelector('[data-capture-phase="idle"]')).not.toBeNull();
    expect(root.textContent).toContain("Enable microphone");
  });

  it("does not replace an originating capture page with a history observer", async () => {
    await act(async () => {
      render(
        <ControlPanel authority="account" captureBearer="" onCaptureBearerChange={() => undefined} />,
        root,
      );
    });
    const enableMicrophone = [...root.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Enable microphone"
    );
    await act(async () => enableMicrophone?.click());

    act(() => {
      document.dispatchEvent(
        new CustomEvent(LIVE_MEETING_OBSERVE_EVENT, {
          detail: { meetingId: "active-live-meeting" }
        })
      );
    });

    expect(mocks.createMossSessionPoller).not.toHaveBeenCalled();
    expect(root.querySelector('[data-capture-phase="configuring"]')).not.toBeNull();
  });
});
