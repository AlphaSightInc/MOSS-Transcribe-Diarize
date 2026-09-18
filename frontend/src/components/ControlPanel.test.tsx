// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { storageKeys } from "../lib/persistence";
import { captureMeetingId } from "../state/session";

const mocks = vi.hoisted(() => {
  const poller = {
    start: vi.fn(),
    stop: vi.fn(),
    poll: vi.fn(),
    cursors: vi.fn(() => ({ version: 0, sequence: -1 }))
  };
  return {
    poller,
    pollerOptions: null as { onTerminal?: (message: string) => void; onError?: (message: string) => void; onRecovered?: () => void } | null,
    createMossSessionPoller: vi.fn((options: { onTerminal?: (message: string) => void; onError?: (message: string) => void; onRecovered?: () => void }) => {
      mocks.pollerOptions = options;
      return poller;
    }),
    captureClose: vi.fn().mockResolvedValue(undefined),
    captureStop: vi.fn().mockResolvedValue(undefined),
    replaceLane: vi.fn().mockResolvedValue(undefined),
    createSession: vi.fn().mockResolvedValue({ id: "account-live-meeting" }),
    captureOptions: null as {
      workletUrl?: string;
      onTransportError?: (route: "frame" | "heartbeat", error: Error) => void;
      onTransportRecovered?: () => void;
      onMeter?: (lane: "microphone" | "system", rms: number) => void;
      onPreflightStatus?: (statusLine: string) => void;
    } | null,
  };
});

vi.mock("../api/mossPoller", () => ({
  createMossSessionPoller: mocks.createMossSessionPoller
}));

vi.mock("../capture/captureClient", () => ({
  CaptureClient: class {
    options: {
      workletUrl?: string;
      onTransportError?: (route: "frame" | "heartbeat", error: Error) => void;
      onTransportRecovered?: () => void;
      onMeter?: (lane: "microphone" | "system", rms: number) => void;
      onPreflightStatus?: (statusLine: string) => void;
    };

    constructor(options: {
      workletUrl?: string;
      onTransportError?: (route: "frame" | "heartbeat", error: Error) => void;
      onTransportRecovered?: () => void;
      onMeter?: (lane: "microphone" | "system", rms: number) => void;
      onPreflightStatus?: (statusLine: string) => void;
    }) {
      mocks.captureOptions = options;
      this.options = options;
    }

    prepare = vi.fn().mockResolvedValue(undefined);
    startMicrophone = vi.fn(async () => this.options.onMeter?.("microphone", 0.5));
    requestDisplayMedia = vi.fn().mockResolvedValue({ getTracks: () => [] });
    attachDisplayMedia = vi.fn(async () => this.options.onMeter?.("system", 0.5));
    replaceLane = mocks.replaceLane;
    createSession = mocks.createSession;
    close = mocks.captureClose;
    stop = mocks.captureStop;
  }
}));

import { ControlPanel, LIVE_MEETING_OBSERVE_EVENT } from "./ControlPanel";

describe("ControlPanel reattach", () => {
  let root: HTMLDivElement;
  let workletMeta: HTMLMetaElement;

  beforeEach(() => {
    workletMeta = document.createElement("meta");
    workletMeta.name = "moss-worklet-url";
    workletMeta.content = "/static/worklets/lane-framer.js?v=" + "a".repeat(64);
    document.head.append(workletMeta);
    root = document.createElement("div");
    document.body.append(root);
    window.sessionStorage.clear();
    vi.clearAllMocks();
    mocks.captureOptions = null;
    mocks.pollerOptions = null;
  });

  afterEach(() => {
    act(() => render(null, root));
    root.remove();
    workletMeta.remove();
  });

  it("reattaches read-only with only the Account Meeting ID", async () => {
    window.sessionStorage.setItem(
      storageKeys.sessionReattach,
      JSON.stringify({ sessionId: "session-42" })
    );

    await act(async () => {
      render(<ControlPanel />, root);
    });

    expect(mocks.poller.start).toHaveBeenCalledOnce();
    expect(captureMeetingId.value).toBeNull();
    expect(mocks.createMossSessionPoller).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: "session-42"
      })
    );
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
      render(<ControlPanel />, root);
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

  it("distinguishes connections from sound and never enables microphone-only Start", async () => {
    await act(async () => render(<ControlPanel />, root));
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    expect(root.textContent).toContain("Microphone-only capture is not available");
    expect(root.textContent).toContain("Not connected");
    await act(async () => button("Enable microphone")!.click());
    await vi.waitFor(() => expect(root.textContent).toContain("Connected · receiving sound"));
    expect(root.querySelector('[data-capture-readiness]')?.textContent).toContain("Share audio");
    expect(button("Start capture")).toBeUndefined();
    act(() => mocks.captureOptions!.onMeter!("microphone", 0));
    expect(root.textContent).toContain("Connected · quiet");
    await act(async () => button("Share audio")!.click());
    await vi.waitFor(() => expect(root.querySelector('[data-capture-readiness]')?.textContent).toContain("speak into your microphone"));
    expect(button("Start capture")).toBeUndefined();
    act(() => mocks.captureOptions!.onMeter!("microphone", .5));
    expect(button("Start capture")!.disabled).toBe(false);
    act(() => mocks.captureOptions!.onMeter!("system", 0));
    expect(button("Start capture")!.disabled).toBe(true);
    expect(root.querySelector('[data-capture-readiness]')?.textContent).toContain("play sound in the shared tab");
    await act(async () => button("Reshare audio")!.click());
    expect(mocks.replaceLane).toHaveBeenCalledWith("system", expect.anything(), expect.any(Array));
    expect(mocks.createSession).not.toHaveBeenCalled();
  });

  it("starts Account capture without rendering or requiring another credential", async () => {
    await act(async () => {
      render(<ControlPanel />, root);
    });
    expect(root.querySelector('input[type="password"]')).toBeNull();
    const enableMicrophone = [...root.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Enable microphone",
    );
    expect(enableMicrophone?.disabled).toBe(false);
    await act(async () => enableMicrophone?.click());
    expect(mocks.captureOptions).toMatchObject({ workletUrl: workletMeta.content });
  });

  it("opens an active history Meeting as an ephemeral Account observer", async () => {
    await act(async () => {
      render(<ControlPanel />, root);
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
        sessionId: "active-live-meeting"
      })
    );
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
      render(<ControlPanel />, root);
    });
    expect(mocks.createMossSessionPoller).not.toHaveBeenCalled();
    expect(root.querySelector('[data-capture-phase="idle"]')).not.toBeNull();
    expect(root.textContent).toContain("Enable microphone");
  });

  it("does not replace an originating capture page with a history observer", async () => {
    await act(async () => {
      render(<ControlPanel />, root);
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

  it("clears network warnings only after capture and polling recover, never after terminal", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    await act(async () => button("Enable microphone")?.click());
    await act(async () => button("Share audio")?.click());
    await act(async () => button("Start capture")?.click());
    act(() => {
      mocks.captureOptions?.onTransportError?.("frame", new TypeError("Failed to fetch"));
      mocks.pollerOptions?.onError?.("Failed to fetch");
    });
    expect(root.textContent).toContain("Retrying automatically");
    act(() => mocks.pollerOptions?.onRecovered?.());
    expect(root.textContent).toContain("Retrying automatically");
    act(() => mocks.captureOptions?.onTransportRecovered?.());
    expect(root.textContent).toContain("Connection restored. Recording microphone and shared audio.");
    act(() => mocks.pollerOptions?.onTerminal?.("helper_lease_expired"));
    act(() => { mocks.captureOptions?.onTransportRecovered?.(); mocks.pollerOptions?.onRecovered?.(); });
    expect(root.textContent).toContain("Recording interrupted: the connection was lost for too long. Reset capture to start again.");
    expect(root.textContent).not.toContain("Connection restored");
  });

  it("keeps polling while an accepted Stop is still draining", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    await act(async () => button("Enable microphone")?.click());
    await act(async () => button("Share audio")?.click());
    await act(async () => button("Start capture")?.click());
    await act(async () => button("Stop and finalize")?.click());
    expect(mocks.captureStop).toHaveBeenCalledWith(5);
    expect(root.querySelector('[data-capture-phase="stopping"]')).not.toBeNull();
    expect(mocks.poller.stop).not.toHaveBeenCalled();
    expect(root.textContent).toContain("Waiting for the transcript to finish");
    await act(async () => mocks.pollerOptions?.onTerminal?.("Transcript finalized."));
    expect(root.querySelector('[data-capture-phase="terminal"]')).not.toBeNull();
  });

  it.each(["Sign in required.", "helper_lease_expired", "canonical decode failed"])("stops without automatically recreating a terminal capture: %s", async (reason) => {
    await act(async () => {
      render(<ControlPanel />, root);
    });
    const button = (label: string) =>
      [...root.querySelectorAll("button")].find(
        (candidate) => candidate.textContent?.trim() === label,
      );

    await act(async () => button("Enable microphone")?.click());
    await act(async () => button("Share audio")?.click());
    await act(async () => button("Start capture")?.click());
    expect(root.querySelector('[data-capture-phase="active"]')).not.toBeNull();
    expect(captureMeetingId.value).toBe("account-live-meeting");
    expect(mocks.poller.start).toHaveBeenCalledOnce();

    await act(async () => mocks.pollerOptions?.onTerminal?.(reason));
    await act(async () => { await Promise.resolve(); });
    expect(mocks.createSession).toHaveBeenCalledTimes(1);

    expect(mocks.captureClose).toHaveBeenCalledOnce();
    expect(captureMeetingId.value).toBeNull();
    expect(mocks.poller.stop).toHaveBeenCalledOnce();
    expect(root.querySelector('[data-capture-phase="terminal"]')).not.toBeNull();
    expect(root.querySelector('[role="status"]')?.textContent).toBe(reason === "helper_lease_expired"
      ? "Recording interrupted: the connection was lost for too long. Reset capture to start again."
      : reason);
    expect(button("Stop and finalize")).toBeUndefined();
    expect(button("Reset capture")).toBeTruthy();
  });
});
