// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { CaptureClient, type CaptureLane, type PreSessionCaptureFailure } from "../capture/captureClient";
import { ControlPanel } from "./ControlPanel";

vi.mock("../api/mossPoller", () => ({
  createMossSessionPoller: () => ({ start() {}, stop() {} })
}));
vi.mock("../lib/finalSummary", () => ({ watchCreatedMeeting() {} }));

// Real ControlPanel and CaptureClient. Only browser devices, audio scheduling and
// HTTP are simulated; failures cross the same attachment/catch/cleanup boundary.
let root: HTMLDivElement;
let nodes: Map<CaptureLane, FakeNode>;
let contexts: FakeContext[];
let streams: FakeStream[];
let denyMicrophone: boolean;
let displayMode: "ok" | "reject" | "missing";
let sourceFails: boolean;
let workletFails: boolean;
const descriptor = { sample_rate: 16000, frame_samples: 8000, bounds: { max_frame_samples: 8000 } };
class FakeTrack extends EventTarget {
  stop = vi.fn();
}
class FakeStream {
  constructor(readonly tracks = [new FakeTrack()]) { streams.push(this); }
  getTracks() { return this.tracks; }
  getAudioTracks() { return this.tracks; }
}
class FakeNode {
  port: { onmessage: ((event: { data: unknown }) => void) | null } = { onmessage: null };
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
  createGain() { return Object.assign(new FakeNode(), { gain: { value: 1 } }); }
}
class FakeWorklet extends FakeNode {
  constructor(_context: unknown, _name: string, options: { processorOptions: { lane: CaptureLane } }) {
    super(); if (workletFails) throw new Error("worklet attachment failed"); nodes.set(options.processorOptions.lane, this);
  }
}
function feed(lane: CaptureLane, level: number) {
  nodes.get(lane)?.port.onmessage?.({ data: {
    type: "frame", lane, samples: new Float32Array(8000).fill(level), startFrame: 8000
  } });
}
function phase() { return root.querySelector("[data-capture-phase]")?.getAttribute("data-capture-phase"); }
function status() { return root.querySelector("[role=status]")?.textContent; }
function button(label: string) {
  return [...root.querySelectorAll("button")].find(node => node.textContent?.trim() === label);
}
async function click(label: string) {
  await act(async () => {
    expect(button(label)).toBeTruthy();
    button(label)!.click();
    // Event handler intentionally returns void; let its asynchronous chain settle.
    await new Promise(resolve => setTimeout(resolve, 0));
  });
}
async function ready() {
  await click("Enable microphone");
  await click("Share audio");
  await act(async () => { feed("microphone", .02); feed("system", .3); });
  expect(phase()).toBe("ready");
}
beforeEach(async () => {
  nodes = new Map(); contexts = []; streams = [];
  denyMicrophone = false; displayMode = "ok"; sourceFails = false; workletFails = false;
  window.sessionStorage.clear();
  document.head.innerHTML = '<meta name="moss-worklet-url" content="/static/worklets/lane-framer.js?v=review">';
  vi.stubGlobal("AudioContext", FakeContext);
  vi.stubGlobal("AudioWorkletNode", FakeWorklet);
  vi.stubGlobal("MediaStream", FakeStream);
  vi.stubGlobal("navigator", { mediaDevices: {
    getUserMedia: vi.fn(async () => {
      if (denyMicrophone) throw new Error("microphone denied");
      return new FakeStream();
    }),
    getDisplayMedia: vi.fn(async () => {
      if (displayMode === "reject") throw new Error("chooser rejected");
      return new FakeStream(displayMode === "missing" ? [] : undefined);
    })
  } });
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: true, status: 200,
    json: async () => url.includes("/descriptor")
      ? { descriptor, preflight_status_lines: { browser_microphone_silent: "silent remedy" } }
      : { id: "probe", descriptor }
  })));
  root = document.createElement("div"); document.body.append(root);
  await act(async () => render(<ControlPanel />, root));
});
afterEach(async () => {
  await act(async () => render(null, root)); root.remove();
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

async function resetAfterFailure(message: string, lane?: CaptureLane) {
  expect(phase()).toBe("error");
  expect(status()).toBe(lane
    ? `${lane === "microphone" ? "Microphone" : "Shared audio"}: ${message}. Reset capture to try again.`
    : message);
  expect(button("Reset capture")).toBeTruthy();
  await click("Reset capture");
  expect(phase()).toBe("idle");
  expect(contexts.every(context => context.state === "closed")).toBe(true);
  expect(streams.every(stream => stream.getTracks().every(track => track.stop.mock.calls.length > 0))).toBe(true);
  expect([...nodes.values()].filter(node => node.port.onmessage)).toHaveLength(0);
}
it.each(["source", "worklet"])("F4/4 cleans acquired display and existing microphone after %s failure and Reset", async failure => {
  await click("Enable microphone");
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await click("Share audio");
  await resetAfterFailure(`${failure} attachment failed`, "system");
});
it.each(["source", "worklet"])("F4/5 cleans acquired microphone after %s failure and Reset", async failure => {
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await click("Enable microphone");
  await resetAfterFailure(`${failure} attachment failed`, "microphone");
});
it("F4/6 catches synchronous chooser errors in the user gesture", async () => {
  await click("Enable microphone");
  const request = vi.spyOn(CaptureClient.prototype, "requestDisplayMedia").mockImplementation(() => {
    throw new Error("capture AudioContext is not running");
  });
  await act(async () => {
    button("Share audio")!.click();
    expect(request).toHaveBeenCalledOnce();
    await new Promise(resolve => setTimeout(resolve, 0));
  });
  await resetAfterFailure("capture AudioContext is not running", "system");
});
it.each(["source", "worklet"])("F4/9 cleans replacement microphone and both old lanes after %s failure and Reset", async failure => {
  await ready();
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await click("Switch mic");
  await resetAfterFailure(`${failure} attachment failed`);
});
it("denied microphone recovers without reload", async () => {
  denyMicrophone = true; await click("Enable microphone");
  await resetAfterFailure("microphone denied", "microphone");
  denyMicrophone = false; await ready();
});
it("cancelled picker recovers without reload", async () => {
  await click("Enable microphone"); displayMode = "reject"; await click("Share audio");
  await resetAfterFailure("chooser rejected", "system");
  displayMode = "ok"; await ready();
});

// WP27 ordering regressions absorbed from the measured logic prototype.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function settle(action: () => void) {
  await act(async () => { action(); await new Promise(resolve => setTimeout(resolve, 0)); });
}
function snapshot(step: string) {
  process.stdout.write(JSON.stringify({ step, phase: phase(), status: status(),
    reset: !!button("Reset capture"),
    meters: [...root.querySelectorAll(".capture-meter-track")].map(n => n.getAttribute("aria-label")),
    connected: [...root.querySelectorAll(".capture-meter small")].map(n => n.textContent),
    tracks: streams.flatMap(s => s.getTracks().map(t => t.stop.mock.calls.length)),
    contexts: contexts.map(c => c.state),
    handlers: [...nodes.values()].filter(n => n.port.onmessage).length,
    chooserCalls: vi.mocked(navigator.mediaDevices.getDisplayMedia).mock.calls.length }) + "\n");
}
async function assertReset() {
  expect(button("Reset capture")).toBeTruthy();
  await click("Reset capture"); snapshot("reset");
  expect(phase()).toBe("idle");
  expect(contexts.every(c => c.state === "closed")).toBe(true);
  expect(streams.every(s => s.getTracks().every(t => t.stop.mock.calls.length > 0))).toBe(true);
  expect([...nodes.values()].filter(n => n.port.onmessage)).toHaveLength(0);
  expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeTruthy();
  expect(root.querySelector('[aria-label="Shared audio level 0%"]')).toBeTruthy();
}
it.each(["descriptor", "microphone"] as const)("early Share while %s pending retains explanation after success", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Enable microphone"); snapshot(`${pending} pending`);
  await click("Share audio"); snapshot("early share rejected");
  expect(vi.mocked(navigator.mediaDevices.getDisplayMedia)).not.toHaveBeenCalled();
  await settle(() => gate.resolve(pending === "descriptor"
    ? { ok: true, json: async () => ({ descriptor, preflight_status_lines: { browser_microphone_silent: "silent remedy" } }) } as Response : new FakeStream() as unknown as MediaStream));
  snapshot("microphone succeeded");
  expect(nodes.has("microphone")).toBe(true);
  expect(status()).not.toContain("Microphone:");
  expect(status()).toContain("start microphone before display capture");
  expect(status()).toContain("Shared audio");
  expect(status()).toContain("Reset capture");
  await settle(() => feed("microphone", .02)); snapshot("late meter");
  expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeTruthy();
  await assertReset();
});
it.each(["descriptor", "microphone"] as const)("early Share while %s pending retains both failures", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Enable microphone"); snapshot(`${pending} pending`);
  await click("Share audio"); snapshot("early share rejected");
  await settle(() => gate.reject(new Error("microphone preparation denied"))); snapshot("microphone failed");
  expect(status()).toContain("start microphone before display capture");
  expect(status()).toContain("microphone preparation denied");
  expect(status()).toContain("Microphone"); expect(status()).toContain("Shared audio");
  expect(status()).toContain("Reset capture");
  await assertReset();
});
it.each(["descriptor", "microphone"] as const)("Reset before pending %s resolves cannot revive capture", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Enable microphone"); await click("Share audio");
  await click("Reset capture"); snapshot("reset while pending");
  await settle(() => gate.resolve(pending === "descriptor"
    ? { ok: true, json: async () => ({ descriptor, preflight_status_lines: { browser_microphone_silent: "silent remedy" } }) } as Response : new FakeStream() as unknown as MediaStream)); snapshot("old setup settled");
  expect(contexts.length).toBeGreaterThan(0);
  expect(phase()).toBe("idle");
  expect(status()).toContain("Live capture requires both");
  expect(contexts.every(c => c.state === "closed")).toBe(true);
  expect(streams.every(s => s.getTracks().every(t => t.stop.mock.calls.length > 0))).toBe(true);
  expect([...nodes.values()].filter(n => n.port.onmessage)).toHaveLength(0);
});
it.each(["reject", "missing"] as const)("admitted Share %s clears meters and explains recovery", async mode => {
  await click("Enable microphone"); await settle(() => feed("microphone", .02)); snapshot("mic receiving");
  displayMode = mode; await click("Share audio"); snapshot(`share ${mode}`);
  expect(status()).toContain("Shared audio"); expect(status()).toContain("Reset capture");
  expect(status()).toContain(mode === "reject" ? "chooser rejected" : "selected display surface supplied no audio track");
  expect(root.querySelector('[aria-label="Microphone level 0%"]')).toBeTruthy();
  await assertReset();
  displayMode = "ok"; await ready(); snapshot("retry ready");
});
it("mic failure before Share removes Share and offers Reset", async () => {
  denyMicrophone = true; await click("Enable microphone"); snapshot("mic denied first");
  expect(button("Share audio")).toBeUndefined();
  expect(status()).toContain("Microphone"); expect(status()).toContain("microphone denied");
  expect(status()).toContain("Reset capture"); await assertReset();
});
it("successful setup still becomes ready only after both lanes have sound", async () => {
  await click("Enable microphone"); await click("Share audio"); snapshot("both attached");
  expect(phase()).toBe("configuring");
  await settle(() => feed("microphone", .02)); snapshot("mic sound"); expect(phase()).toBe("configuring");
  await settle(() => feed("system", .3)); snapshot("both sound"); expect(phase()).toBe("ready");
  expect(status()).toBe("Both sources are receiving sound. Start capture when ready.");
});

it.each(["descriptor", "microphone"] as const)("old %s rejection after Reset cannot overwrite a fresh ready setup", async pending => {
  const gate = deferred<Response | MediaStream>();
  if (pending === "descriptor") vi.mocked(fetch).mockImplementationOnce(() => gate.promise as Promise<Response>);
  else vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementationOnce(() => gate.promise as Promise<MediaStream>);
  await click("Enable microphone"); await click("Share audio"); await click("Reset capture");
  await ready();
  await settle(() => gate.reject(new Error("old microphone denied"))); snapshot("retired rejection after fresh ready");
  expect(phase()).toBe("ready");
  expect(status()).toBe("Both sources are receiving sound. Start capture when ready.");
  expect(button("Reset capture")).toBeUndefined();
});
it.each(["success", "reject"] as const)("Reset while chooser pending handles late %s", async outcome => {
  await click("Enable microphone");
  const chooser = deferred<MediaStream>();
  vi.mocked(navigator.mediaDevices.getDisplayMedia).mockImplementationOnce(() => chooser.promise);
  await click("Share audio");
  // A second Share can fail while the first request is pending (for example,
  // the browser rejects a concurrent chooser). Both are real client requests.
  displayMode = "reject";
  await click("Share audio");
  snapshot("second chooser rejected with first pending");
  await click("Reset capture");
  await settle(() => outcome === "success" ? chooser.resolve(new FakeStream() as unknown as MediaStream)
    : chooser.reject(new Error("chooser cancelled")));
  snapshot("late chooser settled");
  expect(phase()).toBe("idle"); expect(status()).toContain("Live capture requires both");
  expect(contexts.every(c => c.state === "closed")).toBe(true);
  expect(streams.every(s => s.getTracks().every(t => t.stop.mock.calls.length > 0))).toBe(true);
});
