// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CaptureClient, type CaptureLane } from "../capture/captureClient";
import { ControlPanel } from "./ControlPanel";

vi.mock("../api/mossPoller", () => ({
  createMossSessionPoller: () => ({ start() {}, stop() {} })
}));
vi.mock("../lib/finalSummary", () => ({ watchCreatedMeeting() {} }));
// A started meeting polls for its summary; that is not what these scenarios test.
vi.mock("../lib/summaryRequests", () => ({ watchMeetingSummary: () => () => undefined }));
// These scenarios are about capture failures, so a Gemini key is present (K9 is covered elsewhere).
vi.mock("../lib/settings", async importOriginal => {
  const actual = await importOriginal<typeof import("../lib/settings")>();
  const defaults = actual.defaultAppSettings();
  return { ...actual, loadAppSettings: () => ({ ...defaults,
    transcription: { ...defaults.transcription, vendor: "gemini", apiKey: "test-key" } }) };
});

// Real ControlPanel and CaptureClient. Only browser devices, audio scheduling and
// HTTP are simulated; failures cross the same attachment/catch/cleanup boundary.
let root: HTMLDivElement;
let nodes: Map<CaptureLane, FakeWorklet>;
let contexts: FakeContext[];
let streams: FakeStream[];
let silentSources: Array<FakeNode & { offset: { value: number }; start: ReturnType<typeof vi.fn> }>;
let denyMicrophone: boolean;
let displayMode: "ok" | "cancel" | "reject" | "missing";
let sourceFails: boolean;
let workletFails: boolean;
const descriptor = { sample_rate: 16000, frame_samples: 8000, bounds: { max_frame_samples: 8000 } };
const descriptorResponse = { ok: true, status: 200,
  json: async () => ({ descriptor, preflight_status_lines: { browser_microphone_silent: "silent remedy" } }) };
class FakeTrack extends EventTarget {
  stop = vi.fn();
}
class FakeStream {
  /** `audio` is empty for a surface shared without audio: it still has its video track to stop. */
  constructor(readonly tracks = [new FakeTrack()], readonly audio = tracks) { streams.push(this); }
  getTracks() { return this.tracks; }
  getAudioTracks() { return this.audio; }
}
class FakeNode {
  port: { onmessage: ((event: { data: unknown }) => void) | null; postMessage: ReturnType<typeof vi.fn> } =
    { onmessage: null, postMessage: vi.fn() };
  connect(target: unknown) { return target; }
  disconnect = vi.fn();
}
class FakeContext extends EventTarget {
  state = "running";
  sampleRate = 16000;
  destination = {};
  audioWorklet = { addModule: async () => {} };
  constructor() { super(); contexts.push(this); }
  async resume() {}
  async close() { this.state = "closed"; }
  createMediaStreamSource() {
    if (sourceFails) throw new Error("source attachment failed");
    return new FakeNode();
  }
  // The source of a lane that is not recorded: zeros on the context clock.
  createConstantSource() {
    const node = Object.assign(new FakeNode(), { offset: { value: 1 }, start: vi.fn() });
    silentSources.push(node);
    return node;
  }
  createGain() { return Object.assign(new FakeNode(), { gain: { value: 1 } }); }
}
class FakeWorklet extends FakeNode {
  // Like lane-framer.js, a muted worklet frames zeros (captureClient.test covers the real one).
  muted: boolean;
  constructor(_context: unknown, _name: string, options: { processorOptions: { lane: CaptureLane; muted?: boolean } }) {
    super(); if (workletFails) throw new Error("worklet attachment failed"); nodes.set(options.processorOptions.lane, this);
    this.muted = options.processorOptions.muted === true;
    this.port.postMessage.mockImplementation((message: { type?: string; muted?: boolean }) => {
      if (message.type === "mute") this.muted = message.muted === true;
    });
  }
}
let nextStartFrame: Record<CaptureLane, number>;
function feed(lane: CaptureLane, level: number) {
  const node = nodes.get(lane);
  if (!node) return;
  const startFrame = nextStartFrame[lane];
  nextStartFrame[lane] += 8000;
  node.port.onmessage?.({ data: {
    type: "frame", lane, samples: new Float32Array(8000).fill(node.muted ? 0 : level), startFrame
  } });
}
function posted(route: "frames" | "heartbeat") {
  return vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith(`/${route}`))
    .map(([, request]) => JSON.parse((request as RequestInit).body as string));
}
function postedFrames(lane: CaptureLane) { return posted("frames").filter(frame => frame.lane === lane); }
function reportedSilentMicrophone() {
  return posted("heartbeat").some(beat => beat.lanes.microphone.failure_code === "browser_microphone_silent");
}
function sessionCreates() { return vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/live/sessions").length; }
function phase() { return root.querySelector("[data-capture-phase]")?.getAttribute("data-capture-phase"); }
function status() { return root.querySelector("[role=status]")?.textContent; }
function meters() { return [...root.querySelectorAll(".capture-meter-track")].map(node => node.getAttribute("aria-label")); }
function button(label: string) {
  return [...root.querySelectorAll("button")].find(node => node.textContent?.trim() === label);
}
function box(label: string) {
  return [...root.querySelectorAll<HTMLLabelElement>("label.check-row")]
    .find(row => row.textContent?.trim() === label)!.querySelector<HTMLInputElement>("input")!;
}
const media = () => vi.mocked(navigator.mediaDevices);
async function settle(action: () => void = () => undefined) {
  await act(async () => { action(); await new Promise(resolve => setTimeout(resolve, 0)); });
}
async function click(label: string) {
  await act(async () => {
    expect(button(label)).toBeTruthy();
    button(label)!.click();
    // Event handler intentionally returns void; let its asynchronous chain settle.
    await new Promise(resolve => setTimeout(resolve, 0));
  });
}
async function untick(label: string) { await act(async () => box(label).click()); }
/** Pick a microphone in the dropdown, the only switch control. */
async function chooseMicrophone(deviceId: string) {
  const select = root.querySelector<HTMLSelectElement>("#microphone-select")!;
  await act(async () => {
    select.value = deviceId;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise(resolve => setTimeout(resolve, 0));
  });
}
/** One click on Start, through to a running recording. */
async function record() {
  await click("Start recording");
  expect(phase()).toBe("active");
}
/** Everything a Start opened is released: contexts closed, tracks stopped, no frame handlers. */
function expectReleased() {
  expect(contexts.every(context => context.state === "closed")).toBe(true);
  expect(streams.every(stream => stream.getTracks().every(track => track.stop.mock.calls.length > 0))).toBe(true);
  expect([...nodes.values()].filter(node => node.port.onmessage)).toHaveLength(0);
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
beforeEach(async () => {
  nodes = new Map(); contexts = []; streams = []; silentSources = [];
  nextStartFrame = { microphone: 8000, system: 8000 };
  denyMicrophone = false; displayMode = "ok"; sourceFails = false; workletFails = false;
  window.sessionStorage.clear();
  document.head.innerHTML = '<meta name="moss-worklet-url" content="/static/worklets/lane-framer.js?v=review">';
  vi.stubGlobal("AudioContext", FakeContext);
  vi.stubGlobal("AudioWorkletNode", FakeWorklet);
  vi.stubGlobal("MediaStream", FakeStream);
  vi.stubGlobal("navigator", { mediaDevices: {
    getUserMedia: vi.fn(async () => {
      if (denyMicrophone) throw new DOMException("Permission denied", "NotAllowedError");
      return new FakeStream();
    }),
    getDisplayMedia: vi.fn(async () => {
      // Closing Chrome's picker rejects with NotAllowedError; anything else is a real failure.
      if (displayMode === "cancel") throw new DOMException("Permission denied", "NotAllowedError");
      if (displayMode === "reject") throw new Error("chooser rejected");
      return displayMode === "missing" ? new FakeStream([new FakeTrack()], []) : new FakeStream();
    }),
    enumerateDevices: vi.fn(async () => [{ kind: "audioinput", deviceId: "usb", label: "USB mic" }])
  } });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url.includes("/descriptor") ? descriptorResponse
    : { ok: true, status: 200, json: async () => ({ id: "probe", descriptor }) }));
  root = document.createElement("div"); document.body.append(root);
  await act(async () => render(<ControlPanel />, root));
});
afterEach(async () => {
  await act(async () => render(null, root)); root.remove();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

// One click, three source choices.
it("asks for the share picker inside the click, before the microphone, and records both sources", async () => {
  await act(async () => {
    button("Start recording")!.click();
    // Synchronous: Chrome's picker needs the click's user activation.
    expect(media().getDisplayMedia).toHaveBeenCalledOnce();
    expect(media().getUserMedia).not.toHaveBeenCalled();
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  expect(phase()).toBe("active");
  expect(media().getDisplayMedia.mock.invocationCallOrder[0]).toBeLessThan(media().getUserMedia.mock.invocationCallOrder[0]);
  // Echo cancellation is always on; there is no listening-route question.
  expect(media().getUserMedia).toHaveBeenCalledWith({ audio: { echoCancellation: true, noiseSuppression: false,
    autoGainControl: false, deviceId: { exact: "usb" } }, video: false });
  expect(sessionCreates()).toBe(1);
  expect(silentSources).toHaveLength(0);
  expect(status()).toBeUndefined();
  await settle(() => { feed("microphone", .02); feed("system", .3); });
  expect(meters()).toEqual(["System Sound Output level 83%", "Microphone level 43%"]);
  await vi.waitFor(() => expect(postedFrames("system")).toHaveLength(1));
  expect(postedFrames("system")[0]).toMatchObject({ sequence: 0, silent: false });
  expect(postedFrames("microphone")[0]).toMatchObject({ sequence: 0, silent: false });
});
it("starts with silence on both recorded sources: neither has to carry sound", async () => {
  await record();
  // The person may start recording first and play the audio afterwards.
  await settle(() => { feed("microphone", 0); feed("system", 0); });
  expect(status()).toBeUndefined();
  await vi.waitFor(() => expect(postedFrames("system")).toHaveLength(1));
  expect(postedFrames("system")[0]).toMatchObject({ silent: true });
  expect(postedFrames("microphone")[0]).toMatchObject({ silent: true });
});
it("system sound only: an unticked microphone opens no device, sends a silent lane and never raises K1", async () => {
  await untick("Microphone");
  await record();
  expect(media().getUserMedia).not.toHaveBeenCalled();
  expect(streams).toHaveLength(2); // the shared surface and its audio-only lane stream
  expect(silentSources).toHaveLength(1);
  expect(silentSources[0].offset.value).toBe(0);
  expect(silentSources[0].start).toHaveBeenCalledOnce();
  // 25 frames x 0.5 s is past the 10 s silent-microphone window.
  await settle(() => { for (let frame = 0; frame < 25; frame += 1) { feed("microphone", 0); feed("system", .3); } });
  await vi.waitFor(() => expect(postedFrames("microphone")).toHaveLength(25));
  expect(postedFrames("microphone").map(frame => frame.sequence)).toEqual([...Array(25).keys()]);
  expect(postedFrames("microphone").every(frame => frame.silent && frame.device_epoch === 1 && !frame.discontinuity)).toBe(true);
  // Frame for frame on the recorded lane's clock.
  await vi.waitFor(() => expect(postedFrames("system")).toHaveLength(25));
  expect(postedFrames("microphone").map(frame => frame.capture_timestamp_ns))
    .toEqual(postedFrames("system").map(frame => frame.capture_timestamp_ns));
  expect(reportedSilentMicrophone()).toBe(false);
  expect(posted("heartbeat").every(beat => beat.state === "capturing" && beat.lanes.microphone.state === "capturing")).toBe(true);
  expect(status()).toBeUndefined();
  expect(meters()).toEqual(["System Sound Output level 83%"]);
  expect(button("Mute mic")).toBeUndefined();
  expect([box("System Sound Output").disabled, box("Microphone").disabled]).toEqual([true, true]);
});
it("microphone only: no share picker, a silent system lane and no stopped-share line", async () => {
  await untick("System Sound Output");
  await record();
  expect(media().getDisplayMedia).not.toHaveBeenCalled();
  expect(silentSources).toHaveLength(1);
  await settle(() => { for (let frame = 0; frame < 25; frame += 1) { feed("microphone", .02); feed("system", 0); } });
  await vi.waitFor(() => expect(postedFrames("system")).toHaveLength(25));
  expect(postedFrames("system").every(frame => frame.silent)).toBe(true);
  expect(posted("heartbeat").every(beat => beat.state === "capturing" && beat.lanes.system.state === "capturing"
    && beat.lanes.system.failure_code === null)).toBe(true);
  expect(status()).toBeUndefined();
  expect(meters()).toEqual(["Microphone level 43%"]);
  expect(button("Mute mic")).toBeTruthy();
  expect(button("Share again")).toBeUndefined();
});
it("control: a recorded microphone that stays silent does raise K1", async () => {
  await record();
  await settle(() => { for (let frame = 0; frame < 20; frame += 1) feed("microphone", 0); });
  await vi.waitFor(() => expect(reportedSilentMicrophone()).toBe(true));
});

// Q16: what one Start click could not record.
it("(a) a denied microphone starts system sound only, unticks Microphone and says so", async () => {
  denyMicrophone = true;
  await record();
  expect(status()).toBe("Microphone unavailable");
  expect([box("System Sound Output").checked, box("Microphone").checked]).toEqual([true, false]);
  expect(sessionCreates()).toBe(1);
  expect(silentSources).toHaveLength(1);
  // The share stays open and recorded.
  expect(streams[0].getTracks()[0].stop).not.toHaveBeenCalled();
  await settle(() => { for (let frame = 0; frame < 25; frame += 1) { feed("microphone", 0); feed("system", .3); } });
  await vi.waitFor(() => expect(postedFrames("microphone")).toHaveLength(25));
  expect(reportedSilentMicrophone()).toBe(false);
  expect(status()).toBe("Microphone unavailable");
  expect(button("Mute mic")).toBeUndefined();
});
it("(b) a closed picker starts nothing, says nothing, and the next click works", async () => {
  displayMode = "cancel";
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBeUndefined();
  expect(button("Reset")).toBeUndefined();
  expect(media().getUserMedia).not.toHaveBeenCalled();
  expect(sessionCreates()).toBe(0);
  expectReleased();
  expect([box("System Sound Output").checked, box("Microphone").checked]).toEqual([true, true]);
  displayMode = "ok";
  await record();
});
it("a share that fails for another reason starts nothing and names the reason", async () => {
  displayMode = "reject";
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe("System sound output failed: chooser rejected");
  expect(media().getUserMedia).not.toHaveBeenCalled();
  expectReleased();
});
it("(c) a surface shared without audio starts the microphone only and says so", async () => {
  displayMode = "missing";
  await record();
  expect(status()).toBe("System sound output not shared");
  // The surface is released; the microphone is recorded; the system lane is silent.
  expect(streams[0].getTracks()[0].stop).toHaveBeenCalledOnce();
  expect(silentSources).toHaveLength(1);
  expect(sessionCreates()).toBe(1);
  await settle(() => { feed("microphone", .02); feed("system", 0); });
  expect(meters()).toEqual(["Microphone level 43%"]);
  expect([box("System Sound Output").checked, box("Microphone").checked]).toEqual([false, true]);
  expect(button("Share again")).toBeUndefined();
});
it.each(["unticked", "denied"])("(c) a surface without audio and a microphone %s starts nothing and tells how to share audio", async microphone => {
  displayMode = "missing";
  if (microphone === "unticked") await untick("Microphone"); else denyMicrophone = true;
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe("No audio was shared — turn on “Also share audio” in Chrome’s picker");
  expect(sessionCreates()).toBe(0);
  expect(silentSources).toHaveLength(0);
  expectReleased();
  expect(button("Start recording")?.disabled).toBe(false);
  displayMode = "ok"; denyMicrophone = false;
  await record();
});
it("a denied microphone as the only source starts nothing, unticks it and disables Start", async () => {
  await untick("System Sound Output");
  denyMicrophone = true;
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe("Microphone unavailable");
  expect(sessionCreates()).toBe(0);
  expectReleased();
  expect(button("Start recording")?.disabled).toBe(true);
  expect(button("Start recording")?.title).toBe("Tick System Sound Output or Microphone.");
});

// Attachment failures: everything a Start opened is released without Reset.
it.each(["source", "worklet"])("F4/4 releases the acquired share after %s failure", async failure => {
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe(`System sound output failed: ${failure} attachment failed`);
  expect(media().getUserMedia).not.toHaveBeenCalled();
  expectReleased();
});
it.each(["source", "worklet"])("F4/5 releases the attached share and the acquired microphone after %s failure", async failure => {
  const open = media().getUserMedia.getMockImplementation()!;
  media().getUserMedia.mockImplementation(async constraints => {
    sourceFails = failure === "source"; workletFails = failure === "worklet";
    return open(constraints);
  });
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe(`Microphone failed: ${failure} attachment failed`);
  expect(streams.length).toBeGreaterThanOrEqual(3);
  expectReleased();
});
it("F4/6 catches synchronous chooser errors in the user gesture", async () => {
  const request = vi.spyOn(CaptureClient.prototype, "requestDisplayMedia").mockImplementation(() => {
    throw new Error("display capture is not supported");
  });
  await act(async () => {
    button("Start recording")!.click();
    expect(request).toHaveBeenCalledOnce();
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  expect(phase()).toBe("idle");
  expect(status()).toBe("System sound output failed: display capture is not supported");
  expectReleased();
});
it.each(["source", "worklet"])("F4/9 a microphone switch that fails mid-recording after %s failure keeps the recording and releases the replacement", async failure => {
  await record();
  const running = streams.at(-1)!;
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await chooseMicrophone("usb");
  expect(phase()).toBe("active");
  expect(status()).toBe("Could not switch the microphone — stop and start a new recording.");
  expect(streams.at(-1)!.getTracks()[0].stop).toHaveBeenCalled();
  expect(running.getTracks()[0].stop).not.toHaveBeenCalled();
});
it("a muted microphone sends silence without the silent-microphone remedy", async () => {
  await record();
  await settle(() => { feed("microphone", .02); feed("system", .3); });
  expect(button("Reconnect mic")).toBeUndefined();
  const microphone = nodes.get("microphone")!;
  await click("Mute mic");
  expect(microphone.port.postMessage).toHaveBeenLastCalledWith({ type: "mute", muted: true });
  // The muted worklet delivers zeros; 25 frames x 0.5 s is past the 10 s silence window.
  await settle(() => { for (let frame = 0; frame < 25; frame += 1) feed("microphone", .02); });
  await vi.waitFor(() => expect(postedFrames("microphone")).toHaveLength(26));
  expect(postedFrames("microphone").slice(1).every(frame => frame.silent && frame.device_epoch === 1)).toBe(true);
  expect(reportedSilentMicrophone()).toBe(false);
  expect(status()).toBeUndefined();
  expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeTruthy();
  // Muted is not unticked: the lane stays a recorded source.
  expect([box("Microphone").checked, box("Microphone").disabled]).toEqual([true, true]);

  await click("Unmute mic");
  expect(microphone.port.postMessage).toHaveBeenLastCalledWith({ type: "mute", muted: false });
  expect(button("Mute mic")?.querySelector("svg")?.getAttribute("data-icon")).toBe("mic");
  await settle(() => feed("microphone", .02));
  await vi.waitFor(() => expect(postedFrames("microphone")).toHaveLength(27));
  expect(postedFrames("microphone")[26]).toMatchObject({ sequence: 26, silent: false, device_epoch: 1, discontinuity: false });
  expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeNull();
  // Control: the same silence unmuted is a real fault and is reported.
  await settle(() => { for (let frame = 0; frame < 20; frame += 1) feed("microphone", 0); });
  await vi.waitFor(() => expect(reportedSilentMicrophone()).toBe(true));
});
it.each(["system", "microphone"] as const)("K3: a recorded %s that stops mid-recording goes silent, never failed, and Stop goes through", async lane => {
  await record();
  await settle(() => { feed("microphone", .02); feed("system", .3); feed("microphone", .02); feed("system", .3); });
  await vi.waitFor(() => expect(postedFrames(lane)).toHaveLength(2));
  const framer = nodes.get(lane)!;
  // The real event: Chrome's "Stop sharing", or an unplugged microphone.
  const track = streams[lane === "system" ? 0 : 2].getTracks()[0];
  await settle(() => track.dispatchEvent(new Event("ended")));
  expect(status()).toBe(lane === "system" ? "System sound output stopped." : "Microphone stopped.");
  expect(phase()).toBe("active");
  expect(button(lane === "system" ? "Share again" : "Mute mic")).toBeUndefined();
  expect(button(lane === "system" ? "Mute mic" : "Share again")).toBeTruthy();
  expect(meters()).toEqual([lane === "system" ? "Microphone level 43%" : "System Sound Output level 83%"]);
  expect(box(lane === "system" ? "System Sound Output" : "Microphone").checked).toBe(false);
  expect(track.stop).toHaveBeenCalled();
  // Zeros now feed the lane's own framer, and its frames continue the same sequence and clock.
  expect(silentSources).toHaveLength(1);
  expect(nodes.get(lane)).toBe(framer);
  await settle(() => { for (let frame = 0; frame < 25; frame += 1) { feed(lane, 0); feed(lane === "system" ? "microphone" : "system", .02); } });
  await vi.waitFor(() => expect(postedFrames(lane)).toHaveLength(27));
  expect(postedFrames(lane).map(frame => frame.sequence)).toEqual([...Array(27).keys()]);
  expect(postedFrames(lane).every(frame => frame.device_epoch === 1 && !frame.discontinuity)).toBe(true);
  expect(postedFrames(lane).map(frame => frame.capture_timestamp_ns))
    .toEqual(postedFrames(lane === "system" ? "microphone" : "system").map(frame => frame.capture_timestamp_ns));
  // The server's failed-lane rule never sees a failed lane, and a stopped microphone raises no K1.
  expect(posted("heartbeat").every(beat => beat.state === "capturing"
    && beat.lanes.system.state === "capturing" && beat.lanes.microphone.state === "capturing"
    && beat.lanes.system.failure_code === null && beat.lanes.microphone.failure_code === null)).toBe(true);
  expect(status()).toBe(lane === "system" ? "System sound output stopped." : "Microphone stopped.");

  await click("Stop recording");
  expect(phase()).toBe("stopping");
  expect(posted("heartbeat").at(-1)).toMatchObject({ state: "stopped" });
  expect(vi.mocked(fetch).mock.calls.some(([url]) => url === "/api/live/sessions/probe/stop")).toBe(true);
  expect(status()).toBeUndefined();
});

// Ordering regressions (WP27), for the one-click flow.
it.each(["descriptor", "microphone"] as const)("pending %s shows Starting… with Reset, then records", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else media().getUserMedia.mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Start recording");
  expect(phase()).toBe("configuring");
  expect(button("Starting…")?.disabled).toBe(true);
  expect(button("Reset")).toBeTruthy();
  expect([box("System Sound Output").disabled, box("Microphone").disabled]).toEqual([true, true]);
  expect(sessionCreates()).toBe(0);
  await settle(() => gate.resolve(pending === "descriptor"
    ? descriptorResponse as unknown as Response : new FakeStream() as unknown as MediaStream));
  expect(phase()).toBe("active");
  expect(status()).toBeUndefined();
});
it("a server that cannot be reached starts nothing and releases the share", async () => {
  vi.mocked(fetch).mockImplementationOnce(async () => { throw new TypeError("Failed to fetch"); });
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe("Start failed: no connection to the server.");
  expect(media().getUserMedia).not.toHaveBeenCalled();
  expectReleased();
  await record();
});
it("a refused meeting starts nothing and releases both sources", async () => {
  vi.mocked(fetch).mockImplementation(async (url: string | URL | Request) => String(url).includes("/descriptor")
    ? descriptorResponse as unknown as Response
    : { ok: false, status: 409, json: async () => ({ detail: { code: "live_capacity_full" } }) } as unknown as Response);
  await click("Start recording");
  expect(phase()).toBe("idle");
  expect(status()).toBe("Two meetings are already recording — stop one first.");
  expectReleased();
});
it.each(["descriptor", "microphone"] as const)("Reset before pending %s resolves cannot revive capture", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else media().getUserMedia.mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Start recording");
  await click("Reset");
  expect(phase()).toBe("idle");
  await settle(() => gate.resolve(pending === "descriptor"
    ? descriptorResponse as unknown as Response : new FakeStream() as unknown as MediaStream));
  expect(phase()).toBe("idle");
  expect(status()).toBeUndefined();
  expect(sessionCreates()).toBe(0);
  expect(streams.length).toBeGreaterThan(0);
  expectReleased();
});
it.each(["descriptor", "microphone"] as const)("an old %s rejection after Reset cannot disturb a fresh recording", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else media().getUserMedia.mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Start recording"); await click("Reset");
  await record();
  await settle(() => gate.reject(new Error("old microphone denied")));
  expect(phase()).toBe("active");
  expect(status()).toBeUndefined();
  expect([box("System Sound Output").checked, box("Microphone").checked]).toEqual([true, true]);
});
it.each(["success", "cancel"] as const)("Reset while the picker is open handles a late %s", async outcome => {
  const chooser = deferred<MediaStream>();
  media().getDisplayMedia.mockImplementationOnce(() => chooser.promise);
  await click("Start recording");
  expect(phase()).toBe("configuring");
  await click("Reset");
  await settle(() => outcome === "success" ? chooser.resolve(new FakeStream() as unknown as MediaStream)
    : chooser.reject(new DOMException("Permission denied", "NotAllowedError")));
  expect(phase()).toBe("idle"); expect(status()).toBeUndefined();
  expect(media().getUserMedia).not.toHaveBeenCalled();
  expectReleased();
});
it.each(["microphone", "system"] as const)("a %s that stops before the meeting exists starts nothing (K3) and permits retry", async lane => {
  // The meeting is slow to appear; the source ends in that window.
  const created = deferred<Response>();
  const answer = vi.mocked(fetch).getMockImplementation()!;
  vi.mocked(fetch).mockImplementation((url, request) =>
    url === "/api/live/sessions" && sessionCreates() === 1 ? created.promise : answer(url, request));
  await click("Start recording");
  expect(phase()).toBe("configuring");
  const track = streams[lane === "system" ? 0 : 2].getTracks()[0];
  await settle(() => track.dispatchEvent(new Event("ended")));
  expect(phase()).toBe("idle");
  // K3: the stopped source by name; the raw browser_track_ended code never reaches the page.
  expect(status()).toBe(lane === "microphone" ? "Microphone stopped." : "System sound output stopped.");
  expect(meters()).toEqual([]);
  expectReleased();
  // The meeting that was created after all is ended at the server, not left to its lease.
  await settle(() => created.resolve({ ok: true, status: 200, json: async () => ({ id: "late", descriptor }) } as Response));
  await vi.waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => url === "/api/live/sessions/late/stop")).toBe(true));
  expect(phase()).toBe("idle");
  await record();
});
