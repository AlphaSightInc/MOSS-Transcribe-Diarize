// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { storageKeys } from "../lib/persistence";
import { captureMeetingId, replaceTranscript, resetSessionState, sessionError, sessionId, sessionStatus, sessionStatusLine } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";

const mocks = vi.hoisted(() => {
  const poller = {
    start: vi.fn(),
    stop: vi.fn(),
    poll: vi.fn(),
    cursors: vi.fn(() => ({ version: 0, sequence: -1 }))
  };
  return {
    poller,
    apiKey: "test-key",
    exportDownload: vi.fn(),
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
// K9 reads the I-1 transcription settings; the key is scripted per test.
vi.mock("../lib/settings", async importOriginal => {
  const actual = await importOriginal<typeof import("../lib/settings")>();
  return { ...actual, loadAppSettings: () => {
    const defaults = actual.defaultAppSettings() as ReturnType<typeof actual.defaultAppSettings> & { transcription?: object };
    return { ...defaults, transcription: { ...defaults.transcription, vendor: "gemini", apiKey: mocks.apiKey } };
  } };
});
vi.mock("../lib/transcriptExport", async importOriginal => ({
  ...await importOriginal<typeof import("../lib/transcriptExport")>(),
  triggerTranscriptExportDownload: mocks.exportDownload
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
    mocks.apiKey = "test-key";
    mocks.captureOptions = null;
    mocks.pollerOptions = null;
  });

  afterEach(() => {
    act(() => render(null, root));
    resetSessionState();
    selectedSummaryMeeting.value = null;
    vi.unstubAllGlobals();
    root.remove();
    workletMeta.remove();
  });

  it("holds transcript and audio export while refinement runs, then restores Save", async () => {
    const meeting = { id: "refining", mode: "live" as const, title: "Meeting", title_source: "automatic" as const,
      status: "completed" as const, created_at_ms: Date.now(), transcript_version: 1,
      refinement_state: "running" as const, transcript: { segments: [] }, audio: null };
    act(() => {
      sessionId.value = meeting.id;
      sessionStatus.value = "closed";
      selectedSummaryMeeting.value = meeting;
      replaceTranscript([{ start: 0, end: 1, text: "Live words", speaker: "S01", speaker_entity_id: "S01",
        display_name: "Alex", state: "final" }]);
      render(<ControlPanel />, root);
    });
    const format = root.querySelector<HTMLSelectElement>('[aria-label="Export format"]')!;
    const save = root.querySelector<HTMLButtonElement>(".controls-export button")!;
    expect(format.disabled).toBe(true);
    expect(save.disabled).toBe(true);
    // The state lives on the control: no separate "Export waits…" sentence.
    expect(save.textContent).toBe("Improving…");
    expect(root.textContent).not.toContain("Export waits");
    act(() => { selectedSummaryMeeting.value = { ...meeting, refinement_state: "done", transcript_version: 2 }; });
    expect(format.disabled).toBe(false);
    expect(save.disabled).toBe(false);
    expect(save.textContent).toBe("Save");
  });

  it.each([1, 2])("exports transcript version 2 with summary version %i only when matching", async sourceVersion => {
    const meeting = { id: "export", mode: "live" as const, title: "Meeting", title_source: "automatic" as const,
      status: "completed" as const, created_at_ms: Date.now(), transcript_version: 2,
      refinement_state: "done" as const, transcript: { segments: [] }, audio: null };
    const artifact = { state: "current", attempt_id: "saved", source_version: sourceVersion,
      artifact_version: 1, error_code: null, document: { summary: "Saved summary", topics: [],
        details: [], speaker_background: [], data_references: [] } };
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ summary: artifact }) })));
    act(() => {
      sessionId.value = meeting.id;
      sessionStatus.value = "closed";
      selectedSummaryMeeting.value = meeting;
      replaceTranscript([{ start: 0, end: 1, text: "Improved words", speaker: "S01", speaker_entity_id: "S01",
        display_name: "Alex", state: "final" }]);
      render(<ControlPanel />, root);
    });
    await act(async () => root.querySelector<HTMLButtonElement>(".controls-export button")!.click());
    await vi.waitFor(() => expect(mocks.exportDownload).toHaveBeenCalledOnce());
    const content = mocks.exportDownload.mock.calls[0][0].content as string;
    expect(content).toContain("Improved words");
    expect(content.includes("Saved summary")).toBe(sourceVersion === 2);
    expect(content).not.toContain("summary is being updated");
  });

  it("exports microphone-lane speakers with the I-4 names", async () => {
    act(() => {
      sessionId.value = "local-names";
      sessionStatus.value = "closed";
      replaceTranscript([
        { start: 0, end: 1, text: "Mine", speaker: "local-1", speaker_entity_id: "local-1", display_name: "local-1", state: "final" },
        { start: 1, end: 2, text: "Theirs", speaker: "local-3", speaker_entity_id: "local-3", display_name: "Speaker 2", state: "final" },
        { start: 2, end: 3, text: "Named", speaker: "local-2", speaker_entity_id: "local-2", display_name: "Priya", state: "final" }
      ]);
      render(<ControlPanel />, root);
    });
    act(() => { const select = root.querySelector<HTMLSelectElement>('[aria-label="Export format"]')!;
      select.value = "txt"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    await act(async () => root.querySelector<HTMLButtonElement>(".controls-export button")!.click());
    const content = mocks.exportDownload.mock.calls[0][0].content as string;
    expect(content).toContain("] You:\nMine");
    expect(content).toContain("] User 2:\nTheirs");
    expect(content).toContain("] Priya:\nNamed");
    expect(content).not.toContain("Local 0");
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
    // Buttons carry the state: no "Transcript reattached…" sentence.
    expect(root.querySelector('[role="status"]')).toBeNull();
    const detach = [...root.querySelectorAll("button")].find(
      (button) => button.textContent?.trim() === "Detach"
    );
    expect(detach).toBeTruthy();

    act(() => render(null, root));
    expect(mocks.poller.stop).toHaveBeenCalledOnce();
  });

  it("renders the server-supplied remedy at silent-microphone preflight until the microphone has sound", async () => {
    const remedy = "No microphone sound — check the input in Chrome site settings.";

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

    act(() => mocks.captureOptions?.onMeter?.("microphone", 0));
    act(() => mocks.captureOptions?.onPreflightStatus?.(remedy));

    expect(root.querySelector('[role="status"]')?.textContent).toBe(remedy);
    act(() => mocks.captureOptions?.onMeter?.("microphone", 0.02));
    expect(root.querySelector('[role="status"]')).toBeNull();
  });

  it("distinguishes connections from sound and names the silent source on disabled Start (K6)", async () => {
    await act(async () => render(<ControlPanel />, root));
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    // No setup prose, "Next:" hints or meter sub-labels: the next button is the instruction.
    expect(root.querySelector('[role="status"]')).toBeNull();
    for (const removed of ["required", "Private to this browser", "Speakers cancel echo", "Not connected", "Next:"]) {
      expect(root.textContent).not.toContain(removed);
    }
    await act(async () => button("Enable microphone")!.click());
    await vi.waitFor(() => expect(button("Share audio")).toBeTruthy());
    expect(button("Start recording")).toBeUndefined();
    expect(button("Share audio")?.classList.contains("record-btn")).toBe(true);
    act(() => mocks.captureOptions!.onMeter!("microphone", 0));
    await act(async () => button("Share audio")!.click());
    await vi.waitFor(() => expect(button("Start recording")).toBeTruthy());
    expect(button("Start recording")!.disabled).toBe(true);
    expect(button("Start recording")!.title).toBe("Microphone has no sound yet");
    act(() => mocks.captureOptions!.onMeter!("microphone", .5));
    expect(button("Start recording")!.disabled).toBe(false);
    expect(button("Start recording")!.title).toBe("");
    act(() => mocks.captureOptions!.onMeter!("system", 0));
    expect(button("Start recording")!.disabled).toBe(true);
    expect(button("Start recording")!.title).toBe("Shared audio has no sound yet");
    act(() => mocks.captureOptions!.onMeter!("microphone", 0));
    expect(button("Start recording")!.title).toBe("Microphone and shared audio have no sound yet");
    await act(async () => button("Share again")!.click());
    expect(mocks.replaceLane).toHaveBeenCalledWith("system", expect.anything(), expect.any(Array));
    expect(mocks.createSession).not.toHaveBeenCalled();
    expect(root.querySelector('[role="status"]')).toBeNull();
  });

  it("blocks Start without a Gemini key and says where to enter it (K9)", async () => {
    mocks.apiKey = "";
    await act(async () => render(<ControlPanel />, root));
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    expect(root.querySelector('[role="status"]')?.textContent).toBe("Enter your Gemini API key in Settings");
    await act(async () => button("Enable microphone")!.click());
    await vi.waitFor(() => expect(button("Share audio")).toBeTruthy());
    await act(async () => button("Share audio")!.click());
    await vi.waitFor(() => expect(button("Start recording")).toBeTruthy());
    expect(button("Start recording")!.disabled).toBe(true);
    expect(button("Start recording")!.title).toBe("Enter your Gemini API key in Settings");
    await act(async () => button("Start recording")!.click());
    expect(mocks.createSession).not.toHaveBeenCalled();

    for (const [mode, label] of [["File", "Start file transcription"], ["URL", "Start URL transcription"]] as const) {
      await act(async () => button(mode)!.click());
      const start = button(label)!;
      expect(start.disabled).toBe(true);
      expect(start.title).toBe("Enter your Gemini API key in Settings");
      expect(root.textContent).toContain("Enter your Gemini API key in Settings");
      await act(async () => button("Live")!.click());
    }

    mocks.apiKey = "entered";
    await act(async () => { document.dispatchEvent(new Event("moss:settings-changed")); });
    await act(async () => button("URL")!.click());
    const url = root.querySelector<HTMLInputElement>("#meeting-url")!;
    await act(async () => { url.value = "https://example.com/a.mp3"; url.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(button("Start URL transcription")!.disabled).toBe(false);
    expect(root.textContent).not.toContain("Enter your Gemini API key");
  });

  it("explains a non-https URL instead of silently disabling Start", async () => {
    await act(async () => render(<ControlPanel />, root));
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    await act(async () => button("URL")!.click());
    expect(root.textContent).not.toContain("Enter an exact https://");
    const url = root.querySelector<HTMLInputElement>("#meeting-url")!;
    await act(async () => { url.value = "http://example.com/a.mp3"; url.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(button("Start URL transcription")!.disabled).toBe(true);
    expect(root.textContent).toContain("Use an https:// link.");
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
    expect(root.querySelector('select[aria-label="Listening with"]')).toHaveProperty("disabled", true);
    expect(root.textContent).not.toContain("read-only");
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
    await vi.waitFor(() => expect(button("Share audio")).toBeTruthy());
    await act(async () => button("Share audio")?.click());
    await vi.waitFor(() => expect(button("Start recording")?.disabled).toBe(false));
    await act(async () => button("Start recording")?.click());
    const status = () => root.querySelector('[role="status"]')?.textContent ?? null;
    expect(status()).toBeNull();
    act(() => {
      mocks.captureOptions?.onTransportError?.("frame", new TypeError("Failed to fetch"));
      mocks.pollerOptions?.onError?.("HTTP 502");
    });
    expect(status()).toBe("Reconnecting — keep this tab open.");
    act(() => mocks.pollerOptions?.onRecovered?.());
    expect(status()).toBe("Reconnecting — keep this tab open.");
    act(() => mocks.captureOptions?.onTransportRecovered?.());
    expect(status()).toBeNull();
    act(() => mocks.pollerOptions?.onTerminal?.("helper_lease_expired"));
    act(() => { mocks.captureOptions?.onTransportRecovered?.(); mocks.pollerOptions?.onRecovered?.(); });
    expect(status()).toBe("Recording stopped: connection lost.");
    expect(button("Reset")).toBeTruthy();
  });

  it("shows a keep-list capture line from the server only while this tab records", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    await act(async () => button("Enable microphone")?.click());
    await vi.waitFor(() => expect(button("Share audio")).toBeTruthy());
    await act(async () => button("Share audio")?.click());
    await vi.waitFor(() => expect(button("Start recording")?.disabled).toBe(false));
    await act(async () => button("Start recording")?.click());
    act(() => { sessionStatusLine.value = "Microphone too loud — lower it."; });
    expect(root.querySelector('[role="status"]')?.textContent).toBe("Microphone too loud — lower it.");
    act(() => { sessionStatusLine.value = ""; });
    expect(root.querySelector('[role="status"]')).toBeNull();
  });

  it("keeps polling while an accepted Stop is still draining", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
    await act(async () => button("Enable microphone")?.click());
    await vi.waitFor(() => expect(button("Share audio")).toBeTruthy());
    await act(async () => button("Share audio")?.click());
    await vi.waitFor(() => expect(button("Start recording")?.disabled).toBe(false));
    await act(async () => button("Start recording")?.click());
    await act(async () => button("Stop recording")?.click());
    expect(mocks.captureStop).toHaveBeenCalledWith(5);
    expect(root.querySelector('[data-capture-phase="stopping"]')).not.toBeNull();
    expect(mocks.poller.stop).not.toHaveBeenCalled();
    expect(button("Stopping…")?.disabled).toBe(true);
    expect(root.querySelector('[role="status"]')).toBeNull();
    // The poller publishes the clean close before calling back; a normal Stop says nothing.
    await act(async () => { sessionStatus.value = "closed"; sessionError.value = null;
      mocks.pollerOptions?.onTerminal?.("Audio capture stopped."); });
    expect(root.querySelector('[data-capture-phase="terminal"]')).not.toBeNull();
    expect(root.querySelector('[role="status"]')).toBeNull();
  });

  it.each(["Sign in required.", "helper_lease_expired", "canonical decode failed", "interrupted_by_operator", "service shutdown"])("stops without automatically recreating a terminal capture: %s", async (reason) => {
    await act(async () => {
      render(<ControlPanel />, root);
    });
    const button = (label: string) =>
      [...root.querySelectorAll("button")].find(
        (candidate) => candidate.textContent?.trim() === label,
      );

    await act(async () => button("Enable microphone")?.click());
    await vi.waitFor(() => expect(button("Share audio")).toBeTruthy());
    await act(async () => button("Share audio")?.click());
    await vi.waitFor(() => expect(button("Start recording")?.disabled).toBe(false));
    await act(async () => button("Start recording")?.click());
    expect(root.querySelector('[data-capture-phase="active"]')).not.toBeNull();
    expect(captureMeetingId.value).toBe("account-live-meeting");
    expect(mocks.poller.start).toHaveBeenCalledOnce();

    await act(async () => { sessionStatus.value = "failed"; sessionError.value = reason;
      mocks.pollerOptions?.onTerminal?.(reason); });
    await act(async () => { await Promise.resolve(); });
    expect(mocks.createSession).toHaveBeenCalledTimes(1);

    expect(mocks.captureClose).toHaveBeenCalledOnce();
    expect(captureMeetingId.value).toBeNull();
    expect(mocks.poller.stop).toHaveBeenCalledOnce();
    expect(root.querySelector('[data-capture-phase="terminal"]')).not.toBeNull();
    // Raw reasons and codes never reach the page: every abnormal end is K5.
    expect(root.querySelector('[role="status"]')?.textContent).toBe("Recording stopped: connection lost.");
    expect(button("Stop recording")).toBeUndefined();
    expect(button("Reset")).toBeTruthy();
  });
});
