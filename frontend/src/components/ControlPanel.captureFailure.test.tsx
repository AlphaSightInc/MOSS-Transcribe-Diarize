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

async function resetAfterFailure(message: string) {
  expect(phase()).toBe("error");
  expect(status()).toBe(message);
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
  await resetAfterFailure(`${failure} attachment failed`);
});
it.each(["source", "worklet"])("F4/5 cleans acquired microphone after %s failure and Reset", async failure => {
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await click("Enable microphone");
  await resetAfterFailure(`${failure} attachment failed`);
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
  await resetAfterFailure("capture AudioContext is not running");
});
it.each(["source", "worklet"])("F4/9 cleans replacement microphone and both old lanes after %s failure and Reset", async failure => {
  await ready();
  sourceFails = failure === "source"; workletFails = failure === "worklet";
  await click("Switch mic");
  await resetAfterFailure(`${failure} attachment failed`);
});
it("denied microphone recovers without reload", async () => {
  denyMicrophone = true; await click("Enable microphone");
  await resetAfterFailure("microphone denied");
  denyMicrophone = false; await ready();
});
it("cancelled picker recovers without reload", async () => {
  await click("Enable microphone"); displayMode = "reject"; await click("Share audio");
  await resetAfterFailure("chooser rejected");
  displayMode = "ok"; await ready();
});
