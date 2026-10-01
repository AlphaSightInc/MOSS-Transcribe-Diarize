// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryStorage, storageKeys, type StorageLike } from "../lib/persistence";
import { captureMeetingId, replaceTranscript, resetSessionState, sessionError, sessionId, sessionStatus, sessionStatusLine } from "../state/session";
import { sessionStartedAt, sessionStopRequested } from "../state/session";
import { controlPanelCollapsed, selectedSummaryMeeting } from "../state/ui";

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
    setMicrophoneMuted: vi.fn(),
    // Scripted per test: the chooser's result, whether the surface carried audio, the opened device.
    requestDisplayMedia: vi.fn(),
    attachDisplayMedia: vi.fn(),
    startMicrophone: vi.fn(),
    attachSilentLane: vi.fn(),
    createSession: vi.fn().mockResolvedValue({ id: "account-live-meeting" }),
    captureOptions: null as {
      workletUrl?: string;
      onTransportError?: (route: "frame" | "heartbeat", error: Error) => void;
      onTransportRecovered?: () => void;
      onMeter?: (lane: "microphone" | "system", rms: number) => void;
      onPreflightStatus?: (statusLine: string) => void;
      onSourceStopped?: (lane: "microphone" | "system") => void;
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

vi.mock("../capture/captureClient", async importOriginal => ({
  microphoneConstraints: (await importOriginal<typeof import("../capture/captureClient")>()).microphoneConstraints,
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
    startMicrophone = vi.fn(async (...args: unknown[]) => {
      const opened = mocks.startMicrophone(...args);
      if (opened === null) return null; // no microphone, or permission denied
      this.options.onMeter?.("microphone", 0.5);
      return opened ?? args[0] ?? "default"; // the device the real client opened
    });
    requestDisplayMedia = vi.fn(() => mocks.requestDisplayMedia() ?? Promise.resolve({ getTracks: () => [] }));
    attachDisplayMedia = vi.fn(async (stream: unknown) => {
      if (mocks.attachDisplayMedia(stream) === false) return false; // shared without audio
      this.options.onMeter?.("system", 0.5);
      return true;
    });
    attachSilentLane = vi.fn(async (lane: string) => { mocks.attachSilentLane(lane); });
    replaceLane = mocks.replaceLane;
    setMicrophoneMuted = mocks.setMicrophoneMuted;
    createSession = mocks.createSession;
    close = mocks.captureClose;
    stop = mocks.captureStop;
  }
}));

import { ControlPanel, LIVE_MEETING_OBSERVE_EVENT } from "./ControlPanel";
import { App } from "../App";

describe("ControlPanel reattach", () => {
  let root: HTMLDivElement;
  let workletMeta: HTMLMetaElement;
  let storage: StorageLike;

  beforeEach(() => {
    workletMeta = document.createElement("meta");
    workletMeta.name = "moss-worklet-url";
    workletMeta.content = "/static/worklets/lane-framer.js?v=" + "a".repeat(64);
    document.head.append(workletMeta);
    root = document.createElement("div");
    document.body.append(root);
    window.sessionStorage.clear();
    // Node's own non-functional localStorage shadows jsdom's here; use a working one.
    storage = createMemoryStorage();
    vi.stubGlobal("localStorage", storage);
    vi.resetAllMocks();
    mocks.createMossSessionPoller.mockImplementation(options => { mocks.pollerOptions = options; return mocks.poller; });
    mocks.poller.cursors.mockReturnValue({ version: 0, sequence: -1 });
    for (const settled of [mocks.captureClose, mocks.captureStop, mocks.replaceLane]) settled.mockResolvedValue(undefined);
    mocks.createSession.mockResolvedValue({ id: "account-live-meeting" });
    mocks.apiKey = "test-key";
    mocks.captureOptions = null;
    mocks.pollerOptions = null;
  });

  afterEach(() => {
    act(() => render(null, root));
    resetSessionState();
    sessionStartedAt.value = null;
    sessionStopRequested.value = null;
    selectedSummaryMeeting.value = null;
    vi.unstubAllGlobals();
    root.remove();
    workletMeta.remove();
  });

  it("offers only Markdown, Text and Audio exports (#11)", () => {
    act(() => { render(<ControlPanel />, root); });
    const options = [...root.querySelectorAll<HTMLOptionElement>('[aria-label="Export format"] option')];
    expect(options.map(option => [option.value, option.textContent])).toEqual([
      ["md", "Markdown (.md)"], ["txt", "Text (.txt)"], ["audio", "Audio (.mp3)"]]);
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
    // After a reload the top pill counts from the meeting's real start, not from the reload (#14).
    const createdAtMs = Date.now() - 25 * 60_000;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => ({ ok: true, status: 200, json: async () => (
      url === "/api/meetings/session-42" ? { id: "session-42", mode: "live", title: "Meeting", title_source: "automatic",
        status: "active", created_at_ms: createdAtMs, transcript: { segments: [] }, transcript_version: 0, audio: null }
        : {}) })));

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
    await vi.waitFor(() => expect(sessionStartedAt.value).toEqual({ sessionId: "session-42", ms: createdAtMs }));

    act(() => render(null, root));
    expect(mocks.poller.stop).toHaveBeenCalledOnce();
  });

  const button = (label: string) => [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === label);
  const box = (label: string) => [...root.querySelectorAll<HTMLLabelElement>("label.check-row")]
    .find(row => row.textContent?.trim() === label)!.querySelector<HTMLInputElement>("input")!;
  const status = () => root.querySelector('[role="status"]')?.textContent ?? null;
  const phase = () => root.querySelector("[data-capture-phase]")?.getAttribute("data-capture-phase");
  const meters = () => [...root.querySelectorAll(".capture-meter-track")].map(node => node.getAttribute("aria-label"));
  /** One click on Start, settled: the recording runs, or the Start was abandoned. */
  async function clickStart() {
    await act(async () => button("Start recording")!.click());
    await vi.waitFor(() => expect(button("Starting…")).toBeUndefined());
  }
  async function startRecording() {
    await clickStart();
    expect(button("Stop recording")).toBeTruthy();
  }
  const callOrder = (mock: ReturnType<typeof vi.fn>) => mock.mock.invocationCallOrder[0];

  describe("one-click Start (round 5)", () => {
    it("starts with both sources in one click: the picker first, then the microphone, then the meeting", async () => {
      await act(async () => render(<ControlPanel />, root));
      // No setup prose, hints or separate source buttons: Start is the only action.
      expect(status()).toBeNull();
      for (const removed of ["Enable microphone", "Share audio", "Listening with", "Headphones", "required",
        "Private to this browser", "Speakers cancel echo", "Not connected", "Next:"]) {
        expect(root.textContent).not.toContain(removed);
      }
      expect(root.querySelector('[aria-label="Listening with"]')).toBeNull();
      expect(button("Mute mic")).toBeUndefined();
      expect(meters()).toEqual([]);
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, true]);
      expect(button("Start recording")!.disabled).toBe(false);
      expect(button("Start recording")!.hasAttribute("title")).toBe(false);

      act(() => { sessionId.value = "meeting-on-screen"; });
      await startRecording();
      // The page now shows the new meeting, not the one that was on screen.
      expect(sessionId.value).toBe("account-live-meeting");
      expect(callOrder(mocks.requestDisplayMedia)).toBeLessThan(callOrder(mocks.startMicrophone));
      expect(callOrder(mocks.startMicrophone)).toBeLessThan(callOrder(mocks.createSession));
      expect(mocks.attachSilentLane).not.toHaveBeenCalled();
      expect(mocks.createSession).toHaveBeenCalledOnce();
      expect(status()).toBeNull();

      // Locked while recording; a level for each recorded source; Mute beside Share again.
      expect([box("System sound").disabled, box("Microphone").disabled]).toEqual([true, true]);
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, true]);
      expect(meters()).toEqual(["System sound level 90%", "Microphone level 90%"]);
      expect(button("Mute mic")?.parentElement?.classList.contains("btn-row")).toBe(true);
      await act(async () => button("Share again")!.click());
      expect(mocks.replaceLane).toHaveBeenCalledWith("system", expect.anything(), expect.any(Array));
      expect(mocks.createSession).toHaveBeenCalledOnce();
    });

    it("records system sound only when Microphone is unticked: no microphone request, a silent lane, no Mute", async () => {
      await act(async () => render(<ControlPanel />, root));
      await act(async () => box("Microphone").click());
      await startRecording();
      expect(mocks.requestDisplayMedia).toHaveBeenCalledOnce();
      expect(mocks.startMicrophone).not.toHaveBeenCalled();
      expect(mocks.attachSilentLane.mock.calls).toEqual([["microphone"]]);
      expect(button("Mute mic")).toBeUndefined();
      expect(button("Unmute mic")).toBeUndefined();
      expect(button("Share again")).toBeTruthy();
      expect(meters()).toEqual(["System sound level 90%"]);
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, false]);
      expect(status()).toBeNull();
    });

    it("records the microphone only when System sound is unticked: no share picker, a silent lane", async () => {
      await act(async () => render(<ControlPanel />, root));
      await act(async () => box("System sound").click());
      await startRecording();
      expect(mocks.requestDisplayMedia).not.toHaveBeenCalled();
      expect(mocks.attachDisplayMedia).not.toHaveBeenCalled();
      expect(mocks.startMicrophone).toHaveBeenCalledOnce();
      expect(mocks.attachSilentLane.mock.calls).toEqual([["system"]]);
      expect(button("Mute mic")).toBeTruthy();
      expect(button("Share again")).toBeUndefined();
      expect(meters()).toEqual(["Microphone level 90%"]);
      expect(status()).toBeNull();
    });

    it("(a) records system sound only when the microphone is unavailable, unticks it and says so", async () => {
      mocks.startMicrophone.mockReturnValue(null);
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      expect(mocks.attachSilentLane.mock.calls).toEqual([["microphone"]]);
      expect(mocks.createSession).toHaveBeenCalledOnce();
      expect(status()).toBe("Microphone unavailable");
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, false]);
      expect(button("Mute mic")).toBeUndefined();
      expect(meters()).toEqual(["System sound level 90%"]);
      // A line that asks for action outranks the note, which returns once it clears.
      act(() => { sessionStatusLine.value = "System sound too loud — lower it."; });
      expect(status()).toBe("System sound too loud — lower it.");
      act(() => { sessionStatusLine.value = ""; });
      expect(status()).toBe("Microphone unavailable");
      // The box stays unticked for the next Start, in this browser.
      expect(JSON.parse(storage.getItem(storageKeys.captureSources)!)).toEqual({ system: true, microphone: false });
      await act(async () => button("Stop recording")!.click());
      expect(status()).toBeNull();
    });

    it("(b) starts nothing and says nothing when the share picker is closed", async () => {
      mocks.requestDisplayMedia.mockReturnValue(Promise.reject(new DOMException("Permission denied", "NotAllowedError")));
      await act(async () => { sessionId.value = "meeting-on-screen"; render(<ControlPanel />, root); });
      await clickStart();
      expect(phase()).toBe("idle");
      expect(status()).toBeNull();
      expect(button("Start recording")!.disabled).toBe(false);
      expect(button("Reset")).toBeUndefined();
      expect(mocks.startMicrophone).not.toHaveBeenCalled();
      expect(mocks.attachSilentLane).not.toHaveBeenCalled();
      expect(mocks.createSession).not.toHaveBeenCalled();
      expect(mocks.captureClose).toHaveBeenCalledOnce();
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, true]);
      // The meeting that was on screen is still there: nothing was reset.
      expect(sessionId.value).toBe("meeting-on-screen");
    });

    it("(c) records the microphone only when the surface was shared without audio, and says so", async () => {
      mocks.attachDisplayMedia.mockReturnValue(false);
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      expect(mocks.startMicrophone).toHaveBeenCalledOnce();
      expect(mocks.attachSilentLane.mock.calls).toEqual([["system"]]);
      expect(status()).toBe("System sound not shared");
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([false, true]);
      expect(button("Share again")).toBeUndefined();
      expect(button("Mute mic")).toBeTruthy();
      expect(meters()).toEqual(["Microphone level 90%"]);
      // The choice itself is untouched: the next Start asks for system sound again.
      await act(async () => { sessionStatus.value = "closed"; sessionError.value = null;
        mocks.pollerOptions?.onTerminal?.("Audio capture stopped."); });
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, true]);
      expect([box("System sound").disabled, box("Microphone").disabled]).toEqual([false, false]);
      expect(storage.getItem(storageKeys.captureSources)).toBeNull();
    });

    it.each([
      { microphone: "unticked" }, { microphone: "unavailable" }
    ])("(c) starts nothing and tells how to share audio when there is no microphone either ($microphone)", async ({ microphone }) => {
      mocks.attachDisplayMedia.mockReturnValue(false);
      mocks.startMicrophone.mockReturnValue(null);
      await act(async () => render(<ControlPanel />, root));
      if (microphone === "unticked") await act(async () => box("Microphone").click());
      await clickStart();
      expect(phase()).toBe("idle");
      expect(status()).toBe("No audio was shared — turn on “Also share audio” in Chrome’s picker");
      expect(mocks.createSession).not.toHaveBeenCalled();
      expect(mocks.attachSilentLane).not.toHaveBeenCalled();
      expect(mocks.captureClose).toHaveBeenCalledOnce();
      expect(button("Start recording")!.disabled).toBe(false);
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, microphone === "unavailable"]);
    });

    it("starts nothing when the microphone is the only source and is unavailable", async () => {
      mocks.startMicrophone.mockReturnValue(null);
      await act(async () => render(<ControlPanel />, root));
      await act(async () => box("System sound").click());
      await clickStart();
      expect(phase()).toBe("idle");
      expect(status()).toBe("Microphone unavailable");
      expect(mocks.createSession).not.toHaveBeenCalled();
      expect(mocks.captureClose).toHaveBeenCalledOnce();
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([false, false]);
      expect(button("Start recording")!.disabled).toBe(true);
    });

    it("disables Start with a tooltip only while both boxes are unticked", async () => {
      await act(async () => render(<ControlPanel />, root));
      await act(async () => box("System sound").click());
      expect(button("Start recording")!.disabled).toBe(false);
      await act(async () => box("Microphone").click());
      expect(button("Start recording")!.disabled).toBe(true);
      expect(button("Start recording")!.title).toBe("Tick System sound or Microphone.");
      await act(async () => button("Start recording")!.click());
      expect(mocks.captureOptions).toBeNull();
      await act(async () => box("System sound").click());
      expect(button("Start recording")!.disabled).toBe(false);
      expect(button("Start recording")!.title).toBe("");
    });

    it("remembers the ticked sources in this browser, and works when storage is blocked", async () => {
      await act(async () => render(<ControlPanel />, root));
      await act(async () => box("Microphone").click());
      expect(JSON.parse(storage.getItem(storageKeys.captureSources)!)).toEqual({ system: true, microphone: false });
      act(() => render(null, root));
      await act(async () => render(<ControlPanel />, root));
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, false]);

      act(() => render(null, root));
      const blocked = () => { throw new DOMException("blocked", "SecurityError"); };
      vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked, removeItem: blocked });
      await act(async () => render(<ControlPanel />, root));
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, true]);
      await act(async () => box("System sound").click());
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([false, true]);
    });

    it("returns to ready with the refusal when the meeting cannot be created, releasing the sources", async () => {
      mocks.createSession.mockRejectedValueOnce(new Error("Two meetings are already recording — stop one first."));
      await act(async () => { sessionId.value = "meeting-on-screen"; render(<ControlPanel />, root); });
      await clickStart();
      expect(phase()).toBe("idle");
      expect(sessionId.value).toBe("meeting-on-screen");
      expect(status()).toBe("Two meetings are already recording — stop one first.");
      expect(mocks.captureClose).toHaveBeenCalledOnce();
      expect(button("Start recording")!.disabled).toBe(false);
      expect(meters()).toEqual([]);
      // The next Start clears the line.
      await startRecording();
      expect(status()).toBeNull();
    });

    it("Reset while the picker is open retires the Start and stops a share that arrives late", async () => {
      let share!: (stream: unknown) => void;
      mocks.requestDisplayMedia.mockReturnValue(new Promise(resolve => { share = resolve; }));
      await act(async () => { sessionId.value = "meeting-on-screen"; render(<ControlPanel />, root); });
      await act(async () => button("Start recording")!.click());
      expect(phase()).toBe("configuring");
      expect(button("Starting…")?.disabled).toBe(true);
      expect([box("System sound").disabled, box("Microphone").disabled]).toEqual([true, true]);
      // Reset exists only here, and only cancels the pending Start: the meeting on screen stays.
      await act(async () => button("Reset")!.click());
      expect(phase()).toBe("idle");
      expect(button("Reset")).toBeUndefined();
      expect(sessionId.value).toBe("meeting-on-screen");
      const track = { stop: vi.fn() };
      await act(async () => { share({ getTracks: () => [track] }); await new Promise(resolve => setTimeout(resolve, 0)); });
      expect(track.stop).toHaveBeenCalled();
      expect(mocks.startMicrophone).not.toHaveBeenCalled();
      expect(mocks.createSession).not.toHaveBeenCalled();
      expect(phase()).toBe("idle");
      expect(button("Start recording")!.disabled).toBe(false);
    });
  });

  describe("no Reset between recordings (round 5, D5)", () => {
    const finish = (status: "closed" | "failed" = "closed") => act(async () => {
      sessionStatus.value = status; sessionError.value = status === "closed" ? null : "lost";
      mocks.pollerOptions?.onTerminal?.(status === "closed" ? "Audio capture stopped." : "lost");
    });

    it("offers Start as soon as a recording has finished, keeps the finished meeting until the next one exists", async () => {
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      await act(async () => button("Stop recording")!.click());
      await finish();
      expect(phase()).toBe("terminal");
      expect(button("Reset")).toBeUndefined();
      expect(button("Start recording")?.disabled).toBe(false);
      expect([box("System sound").disabled, box("Microphone").disabled]).toEqual([false, false]);
      expect(sessionId.value).toBe("account-live-meeting");

      // A second Start whose picker is closed changes nothing: the finished meeting stays on screen.
      mocks.requestDisplayMedia.mockReturnValueOnce(Promise.reject(new DOMException("Permission denied", "NotAllowedError")));
      await clickStart();
      expect(phase()).toBe("idle");
      expect(sessionId.value).toBe("account-live-meeting");
      expect(mocks.createSession).toHaveBeenCalledOnce();

      // The next Start that succeeds replaces it, with no Reset click in between.
      mocks.createSession.mockResolvedValueOnce({ id: "second-meeting" });
      await startRecording();
      expect(mocks.createSession).toHaveBeenCalledTimes(2);
      expect(sessionId.value).toBe("second-meeting");
      expect(captureMeetingId.value).toBe("second-meeting");
      expect(status()).toBeNull();
    });

    it("offers Start after a recording was lost (K5), and the line goes when Start is clicked", async () => {
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      await finish("failed");
      expect(status()).toBe("Recording stopped: connection lost.");
      expect(button("Reset")).toBeUndefined();
      await startRecording();
      expect(status()).toBeNull();
      expect(mocks.createSession).toHaveBeenCalledTimes(2);
    });

    it("offers Start after a Stop that failed, and that Start retires the old poller", async () => {
      mocks.captureStop.mockRejectedValueOnce(new Error("HTTP 500"));
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      await act(async () => button("Stop recording")!.click());
      expect(phase()).toBe("error");
      expect(status()).toBe("Stop failed: HTTP 500");
      expect(button("Reset")).toBeUndefined();
      expect(mocks.poller.stop).not.toHaveBeenCalled();
      await startRecording();
      expect(mocks.poller.stop).toHaveBeenCalledOnce();
      expect(mocks.captureClose).toHaveBeenCalledOnce();
      expect(mocks.createSession).toHaveBeenCalledTimes(2);
      expect(status()).toBeNull();
    });
  });

  describe("a recorded source that stops mid-recording (K3)", () => {
    it("system sound: says so, drops its level and Share again, and Stop completes normally", async () => {
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      act(() => mocks.captureOptions!.onSourceStopped!("system"));
      expect(status()).toBe("System sound stopped.");
      expect(phase()).toBe("active");
      expect(button("Share again")).toBeUndefined();
      expect(button("Mute mic")).toBeTruthy();
      expect(meters()).toEqual(["Microphone level 90%"]);
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([false, true]);
      // A late level from the stopped lane is not shown.
      act(() => mocks.captureOptions!.onMeter!("system", .5));
      expect(meters()).toEqual(["Microphone level 90%"]);
      // The choice for the next recording is untouched.
      expect(storage.getItem(storageKeys.captureSources)).toBeNull();

      await act(async () => button("Stop recording")!.click());
      expect(mocks.captureStop).toHaveBeenCalledWith(5);
      expect(status()).toBeNull();
      await act(async () => { sessionStatus.value = "closed"; sessionError.value = null;
        mocks.pollerOptions?.onTerminal?.("Audio capture stopped."); });
      expect(phase()).toBe("terminal");
      expect(status()).toBeNull();
      expect([box("System sound").checked, box("Microphone").checked]).toEqual([true, true]);
    });

    it("microphone: says so and drops Mute and its level; with both stopped the recording goes on until Stop", async () => {
      await act(async () => render(<ControlPanel />, root));
      await startRecording();
      await act(async () => button("Mute mic")!.click());
      act(() => mocks.captureOptions!.onSourceStopped!("microphone"));
      expect(status()).toBe("Microphone stopped.");
      expect(button("Mute mic")).toBeUndefined();
      expect(button("Unmute mic")).toBeUndefined();
      expect(button("Share again")).toBeTruthy();
      expect(meters()).toEqual(["System sound level 90%"]);
      // A line that asks for action outranks it, then it returns.
      act(() => { sessionStatusLine.value = "System sound too loud — lower it."; });
      expect(status()).toBe("System sound too loud — lower it.");
      act(() => { sessionStatusLine.value = ""; });
      expect(status()).toBe("Microphone stopped.");

      act(() => mocks.captureOptions!.onSourceStopped!("system"));
      expect(status()).toBe("System sound stopped.");
      expect(meters()).toEqual([]);
      expect(button("Share again")).toBeUndefined();
      expect(phase()).toBe("active");
      expect(button("Stop recording")?.disabled).toBe(false);
    });
  });

  it("renders the server-supplied remedy at silent-microphone preflight until the microphone has sound", async () => {
    const remedy = "No microphone sound — check the input in Chrome site settings.";
    // The meeting is slow to appear, so the microphone's first 10 s pass before a session exists.
    mocks.createSession.mockImplementationOnce(() => new Promise(() => undefined));
    await act(async () => { render(<ControlPanel />, root); });
    await act(async () => button("Start recording")!.click());
    await vi.waitFor(() => expect(mocks.createSession).toHaveBeenCalled());

    act(() => mocks.captureOptions?.onMeter?.("microphone", 0));
    act(() => mocks.captureOptions?.onPreflightStatus?.(remedy));

    expect(status()).toBe(remedy);
    act(() => mocks.captureOptions?.onMeter?.("microphone", 0.02));
    expect(status()).toBeNull();
  });

  it("allows the server Gemini fallback when the browser key is blank", async () => {
    mocks.apiKey = "";
    await act(async () => render(<ControlPanel />, root));
    await act(async () => button("URL")!.click());
    const url = root.querySelector<HTMLInputElement>("#meeting-url")!;
    await act(async () => { url.value = "https://example.com/a.mp3"; url.dispatchEvent(new Event("input", { bubbles: true })); });
    expect(button("Start URL transcription")!.disabled).toBe(false);
    expect(root.textContent).not.toContain("Enter your Gemini API key");
  });

  it("explains a non-https URL instead of silently disabling Start", async () => {
    await act(async () => render(<ControlPanel />, root));
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
    expect(button("Start recording")?.disabled).toBe(false);
    await startRecording();
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
    // Read-only: the source boxes are locked and there is nothing to start.
    expect([box("System sound").disabled, box("Microphone").disabled]).toEqual([true, true]);
    expect(root.textContent).not.toContain("read-only");
    expect(button("Start recording")).toBeUndefined();
    expect(button("Mute mic")).toBeUndefined();
    expect(window.sessionStorage.getItem(storageKeys.sessionReattach)).toBeNull();

    act(() => render(null, root));
    mocks.createMossSessionPoller.mockClear();
    mocks.poller.start.mockClear();
    await act(async () => {
      render(<ControlPanel />, root);
    });
    expect(mocks.createMossSessionPoller).not.toHaveBeenCalled();
    expect(root.querySelector('[data-capture-phase="idle"]')).not.toBeNull();
    expect(button("Start recording")?.disabled).toBe(false);
  });

  it("does not replace an originating capture page with a history observer", async () => {
    mocks.createSession.mockImplementationOnce(() => new Promise(() => undefined));
    await act(async () => {
      render(<ControlPanel />, root);
    });
    await act(async () => button("Start recording")!.click());

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
    await startRecording();
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
    expect(button("Reset")).toBeUndefined();
    expect(button("Start recording")?.disabled).toBe(false);
  });

  it("shows a keep-list capture line from the server only while this tab records", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    await startRecording();
    act(() => { sessionStatusLine.value = "Microphone too loud — lower it."; });
    expect(status()).toBe("Microphone too loud — lower it.");
    act(() => { sessionStatusLine.value = ""; });
    expect(status()).toBeNull();
  });

  it("opens a collapsed Controls rail when a keep-list line needs the operator (#8)", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    await startRecording();
    act(() => { controlPanelCollapsed.value = true; });
    act(() => { sessionStatusLine.value = "Microphone too loud — lower it."; });
    expect(controlPanelCollapsed.value).toBe(false);
    // Once open, the operator may collapse it again over the same line.
    act(() => { controlPanelCollapsed.value = true; });
    expect(controlPanelCollapsed.value).toBe(true);
    act(() => { mocks.captureOptions?.onTransportError?.("frame", new TypeError("Failed to fetch")); });
    expect(controlPanelCollapsed.value).toBe(false);
    controlPanelCollapsed.value = false;
    sessionStatusLine.value = "";
  });

  it("opens a collapsed Controls rail for a Start line too (#8)", async () => {
    mocks.startMicrophone.mockReturnValue(null);
    await act(async () => { render(<ControlPanel />, root); });
    act(() => { controlPanelCollapsed.value = true; });
    await startRecording();
    expect(status()).toBe("Microphone unavailable");
    expect(controlPanelCollapsed.value).toBe(false);
  });

  // r4 F3: the top pill follows the Start click, not the first poll that reports the meeting.
  it.each([
    { outcome: "created", pill: "Recording 0:00" },
    { outcome: "refused", pill: "Standby" }
  ])("reads Starting… from the Start click, then $pill when the meeting is $outcome", async ({ outcome, pill }) => {
    let settle!: () => void;
    mocks.createSession.mockImplementationOnce(() => new Promise((resolve, reject) => {
      settle = () => outcome === "created" ? resolve({ id: "account-live-meeting" })
        : reject(new Error("Two meetings are already recording — stop one first."));
    }));
    await act(async () => { render(<App />, root); });
    const topPill = () => root.querySelector(".top-status")?.textContent;
    expect(topPill()).toBe("Standby");
    await act(async () => button("Start recording")?.click());
    expect(topPill()).toBe("Starting…");
    await vi.waitFor(() => expect(mocks.createSession).toHaveBeenCalled());
    expect(topPill()).toBe("Starting…");
    await act(async () => settle());
    await vi.waitFor(() => expect(topPill()).toBe(pill));
    if (outcome === "created") {
      expect(button("Stop recording")).toBeTruthy();
      expect(sessionStatus.value).toBe("active");
    } else {
      expect(button("Start recording")?.disabled).toBe(false);
    }
  });

  it("returns the top pill to Standby when the share picker is closed", async () => {
    let cancel!: (error: Error) => void;
    mocks.requestDisplayMedia.mockReturnValue(new Promise((_resolve, reject) => { cancel = reject; }));
    await act(async () => { render(<App />, root); });
    const topPill = () => root.querySelector(".top-status")?.textContent;
    await act(async () => button("Start recording")?.click());
    expect(topPill()).toBe("Starting…");
    await act(async () => cancel(new DOMException("Permission denied", "NotAllowedError")));
    await vi.waitFor(() => expect(topPill()).toBe("Standby"));
  });

  it("keeps polling while an accepted Stop is still draining", async () => {
    await act(async () => { render(<ControlPanel />, root); });
    await startRecording();
    await act(async () => button("Stop recording")?.click());
    expect(mocks.captureStop).toHaveBeenCalledWith(5);
    // The top pill stops counting at the click, before the server reports anything (#14).
    expect(sessionStopRequested.value).toBe("account-live-meeting");
    expect(root.querySelector('[data-capture-phase="stopping"]')).not.toBeNull();
    expect(mocks.poller.stop).not.toHaveBeenCalled();
    expect(button("Stopping…")?.disabled).toBe(true);
    expect(status()).toBeNull();
    // Still locked on the sources this recording took.
    expect([box("System sound").disabled, box("Microphone").disabled]).toEqual([true, true]);
    // The poller publishes the clean close before calling back; a normal Stop says nothing.
    await act(async () => { sessionStatus.value = "closed"; sessionError.value = null;
      mocks.pollerOptions?.onTerminal?.("Audio capture stopped."); });
    expect(root.querySelector('[data-capture-phase="terminal"]')).not.toBeNull();
    expect(status()).toBeNull();
  });

  it.each(["Sign in required.", "helper_lease_expired", "canonical decode failed", "interrupted_by_operator", "service shutdown"])("stops without automatically recreating a terminal capture: %s", async (reason) => {
    await act(async () => {
      render(<ControlPanel />, root);
    });

    await startRecording();
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
    expect(status()).toBe("Recording stopped: connection lost.");
    expect(button("Stop recording")).toBeUndefined();
    expect(button("Reset")).toBeUndefined();
    expect(button("Start recording")?.disabled).toBe(false);
    expect(mocks.createSession).toHaveBeenCalledTimes(1);
  });

  describe("microphone dropdown and Mute mic", () => {
    const select = () => root.querySelector<HTMLSelectElement>("#microphone-select")!;
    const choose = (deviceId: string) => act(async () => {
      select().value = deviceId;
      select().dispatchEvent(new Event("change", { bubbles: true }));
    });
    const replacement = { getTracks: () => ["replacement-track"] };
    let getUserMedia: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      getUserMedia = vi.fn(async () => replacement);
      vi.stubGlobal("navigator", { mediaDevices: { getUserMedia, enumerateDevices: vi.fn(async () => [
        { kind: "audioinput", deviceId: "desk", label: "Desk mic" },
        { kind: "audioinput", deviceId: "usb", label: "USB mic" },
        { kind: "videoinput", deviceId: "cam", label: "Camera" }
      ]) } });
    });

    async function recordWithDeskMic() {
      await act(async () => render(<ControlPanel />, root));
      // The dropdown appears once Chrome names the microphones.
      await vi.waitFor(() => expect(select()).toBeTruthy());
      await choose("desk");
      await startRecording();
    }

    it("sits under the Microphone box, only while it is ticked", async () => {
      await act(async () => render(<ControlPanel />, root));
      await vi.waitFor(() => expect(select()).toBeTruthy());
      expect(select().closest(".capture-sources")).not.toBeNull();
      expect(box("Microphone").closest(".source-row")!.nextElementSibling).toBe(select().parentElement);
      await act(async () => box("Microphone").click());
      expect(select()).toBeNull();
      await act(async () => box("Microphone").click());
      expect(select()).toBeTruthy();
    });

    it("picks the device Start opens, then switches the recorded microphone as soon as the dropdown changes", async () => {
      await act(async () => render(<ControlPanel />, root));
      await vi.waitFor(() => expect(select()).toBeTruthy());
      // Before Start a pick opens nothing.
      await choose("desk");
      expect(getUserMedia).not.toHaveBeenCalled();
      expect(mocks.captureOptions).toBeNull();
      await startRecording();
      expect(mocks.startMicrophone).toHaveBeenCalledWith("desk");
      expect(getUserMedia).not.toHaveBeenCalled();
      expect(button("Reconnect mic")).toBeUndefined();
      expect(button("Switch mic")).toBeUndefined();

      await choose("usb");
      await vi.waitFor(() => expect(mocks.replaceLane).toHaveBeenCalledWith("microphone", replacement, ["replacement-track"]));
      // The same request as the first microphone: echo cancellation always on.
      expect(getUserMedia).toHaveBeenCalledWith({ audio: { echoCancellation: true, noiseSuppression: false,
        autoGainControl: false, deviceId: { exact: "usb" } }, video: false });
      expect(select().value).toBe("usb");
      expect(mocks.createSession).toHaveBeenCalledOnce();
    });

    it("keeps the running microphone and its dropdown entry when a switch fails mid-recording", async () => {
      await recordWithDeskMic();
      getUserMedia.mockRejectedValueOnce(new DOMException("Requested device not found", "NotFoundError"));
      await choose("usb");
      await vi.waitFor(() => expect(select().value).toBe("desk"));
      expect(mocks.replaceLane).not.toHaveBeenCalled();
      expect(status()).toBe("Could not switch the microphone — stop and start a new recording.");
      expect(root.querySelector('[data-capture-phase="active"]')).not.toBeNull();
    });

    const micIcon = (label: string) => button(label)?.querySelector("svg")?.getAttribute("data-icon");

    it("offers Mute only in a recording that takes the microphone; it mutes without stopping the lane", async () => {
      await act(async () => render(<ControlPanel />, root));
      expect(button("Mute mic")).toBeUndefined();
      await startRecording();
      const mute = button("Mute mic")!;
      expect(mute.parentElement?.classList.contains("btn-row")).toBe(true);
      expect(mute.className).toBe("btn ghost");
      expect(mute.getAttribute("aria-pressed")).toBe("false");
      expect(micIcon("Mute mic")).toBe("mic");

      await act(async () => mute.click());
      expect(mocks.setMicrophoneMuted).toHaveBeenLastCalledWith(true);
      const unmute = button("Unmute mic")!;
      expect(unmute.getAttribute("aria-pressed")).toBe("true");
      expect(unmute.classList.contains("is-active")).toBe(true);
      expect(micIcon("Unmute mic")).toBe("mic-off");
      // The worklet's last pre-mute frame may still carry a level; the meter shows none.
      act(() => mocks.captureOptions!.onMeter!("microphone", .5));
      expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeTruthy();
      // Muted is not unticked: the box stays ticked and locked.
      expect([box("Microphone").checked, box("Microphone").disabled]).toEqual([true, true]);

      await act(async () => unmute.click());
      expect(mocks.setMicrophoneMuted).toHaveBeenLastCalledWith(false);
      expect(micIcon("Mute mic")).toBe("mic");
      act(() => mocks.captureOptions!.onMeter!("microphone", .5));
      expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeNull();

      // Mute only flips the lane: no replacement, no restart, no new session.
      await act(async () => button("Mute mic")!.click());
      expect(button("Stop recording")).toBeTruthy();
      expect(mocks.replaceLane).not.toHaveBeenCalled();
      expect(mocks.captureStop).not.toHaveBeenCalled();
      expect(mocks.createSession).toHaveBeenCalledOnce();

      // A new recording after the meeting ends starts unmuted.
      await act(async () => { sessionStatus.value = "failed"; sessionError.value = "lost";
        mocks.pollerOptions?.onTerminal?.("lost"); });
      expect(button("Unmute mic")).toBeUndefined();
      await startRecording();
      expect(button("Mute mic")?.getAttribute("aria-pressed")).toBe("false");
      expect(button("Unmute mic")).toBeUndefined();
    });

    it("drops the silent-microphone remedy (K1) once the microphone is muted on purpose", async () => {
      const remedy = "No microphone sound — check the input in Chrome site settings.";
      let created!: (session: { id: string }) => void;
      mocks.createSession.mockImplementationOnce(() => new Promise(resolve => { created = resolve; }));
      await act(async () => render(<ControlPanel />, root));
      await act(async () => button("Start recording")!.click());
      await vi.waitFor(() => expect(mocks.createSession).toHaveBeenCalled());
      act(() => mocks.captureOptions!.onMeter!("microphone", 0));
      act(() => mocks.captureOptions!.onPreflightStatus!(remedy));
      await act(async () => created({ id: "account-live-meeting" }));
      await vi.waitFor(() => expect(button("Mute mic")).toBeTruthy());
      expect(status()).toBe(remedy);
      await act(async () => button("Mute mic")!.click());
      expect(status()).toBeNull();
    });
  });

  describe("microphone choice (issue #2)", () => {
    // Chrome on macOS, measured shapes: a "default" alias labelled after its device and sharing its group id.
    type Device = { kind: "audioinput"; deviceId: string; groupId: string; label: string };
    const device = (deviceId: string, label: string): Device => ({ kind: "audioinput", deviceId, groupId: `g-${deviceId}`, label });
    const defaultIs = (target: Device): Device => ({ ...target, deviceId: "default", label: `Default - ${target.label}` });
    const iphone = device("phone", "Gao’s iPhone Microphone");
    const builtIn = device("builtin", "MacBook Pro Microphone (Built-in)");
    const airPods = device("airpods", "AirPods (Bluetooth)");
    const hidden = [{ kind: "audioinput", deviceId: "", groupId: "", label: "" }];
    const replacement = { getTracks: () => ["replacement-track"] };
    const select = () => root.querySelector<HTMLSelectElement>("#microphone-select");
    const optionLabels = () => [...select()!.options].map(option => option.textContent);
    const shownLabel = () => select()!.selectedOptions[0]?.textContent;
    let devices: unknown[];
    let media: EventTarget & { getUserMedia: ReturnType<typeof vi.fn>; enumerateDevices: ReturnType<typeof vi.fn> };

    beforeEach(() => {
      media = Object.assign(new EventTarget(), {
        getUserMedia: vi.fn(async () => replacement),
        enumerateDevices: vi.fn(async () => devices)
      });
      vi.stubGlobal("navigator", { mediaDevices: media });
    });

    async function plug(next: Device[]) {
      devices = next;
      await act(async () => { media.dispatchEvent(new Event("devicechange")); });
    }

    it("hides the dropdown until Chrome names the microphones, then shows the one opened, not an iPhone default", async () => {
      devices = hidden;
      await act(async () => render(<ControlPanel />, root));
      expect(select()).toBeNull();
      expect(root.textContent).not.toContain("System default");

      // The real client reveals the devices with Chrome's default alias and opens the rule's choice.
      mocks.startMicrophone.mockImplementationOnce(() => {
        devices = [defaultIs(iphone), iphone, builtIn];
        return "builtin";
      });
      await startRecording();
      expect(mocks.startMicrophone).toHaveBeenCalledWith(undefined);
      await vi.waitFor(() => expect(select()).not.toBeNull());
      expect(select()!.value).toBe("builtin");
      expect(shownLabel()).toBe("MacBook Pro Microphone (Built-in)");
      expect(optionLabels()).toEqual(["Gao’s iPhone Microphone", "MacBook Pro Microphone (Built-in)"]);
    });

    it("names the device Start will open once permission is known, and honours an explicit iPhone pick", async () => {
      devices = [defaultIs(iphone), iphone, builtIn, airPods];
      await act(async () => render(<ControlPanel />, root));
      await vi.waitFor(() => expect(select()).not.toBeNull());
      expect(shownLabel()).toBe("AirPods (Bluetooth)");

      await act(async () => {
        select()!.value = "phone";
        select()!.dispatchEvent(new Event("change", { bubbles: true }));
      });
      await startRecording();
      expect(mocks.startMicrophone).toHaveBeenCalledWith("phone");
      await vi.waitFor(() => expect(select()!.value).toBe("phone"));
    });

    it("follows the system default before Start, never to an iPhone, and never switches a recording", async () => {
      devices = [defaultIs(builtIn), builtIn, iphone];
      await act(async () => render(<ControlPanel />, root));
      await vi.waitFor(() => expect(select()?.value).toBe("builtin"));

      // An iPhone taking the default is skipped; nothing is opened before Start.
      await plug([defaultIs(iphone), builtIn, iphone]);
      await vi.waitFor(() => expect(optionLabels()).toHaveLength(2));
      expect(select()!.value).toBe("builtin");
      await plug([defaultIs(airPods), builtIn, iphone, airPods]);
      await vi.waitFor(() => expect(select()!.value).toBe("airpods"));
      expect(media.getUserMedia).not.toHaveBeenCalled();

      await startRecording();
      expect(mocks.startMicrophone).toHaveBeenCalledWith("airpods");
      await plug([defaultIs(builtIn), builtIn, iphone]);
      await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
      expect(mocks.replaceLane).not.toHaveBeenCalled();
      expect(media.getUserMedia).not.toHaveBeenCalled();
      expect(root.querySelector('[data-capture-phase="active"]')).not.toBeNull();
    });
  });
});
