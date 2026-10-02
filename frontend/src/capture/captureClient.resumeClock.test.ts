// P74 review F2: a chunk the worklet began before adoption must never be sent after a resume.
import { afterEach, describe, expect, it, vi } from "vitest";
import { CaptureClient } from "./captureClient";

function lane() {
  return {
    silent: true, source: { disconnect() {} }, framer: { port: { onmessage: null }, disconnect() {} },
    mute: { disconnect() {} }, tracks: [], trackEndedListeners: [], frameQueue: [], postInFlight: false,
    postFlush: null, sequence: 0, deviceEpoch: 0, pendingDiscontinuityEpochs: new Set(), discontinuities: 0,
    droppedFrames: 0, health: "capturing", degradedCode: null, clippedFrameRun: 0, silentFrameRun: 0,
  };
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("resumed capture clock", () => {
  it("drops the chunk begun before adoption and starts at or after the lane's accepted end", async () => {
    const client: any = new CaptureClient({ helperVersion: "test", workletUrl: "/worklet" });
    client.context = { currentTime: 2.4, sampleRate: 16000, state: "running", removeEventListener() {}, close: vi.fn(async () => {}) };
    client.descriptor = { sampleRate: 16000, frameSamples: 8000, preflightStatusLines: { microphoneSilent: "" } };
    client.heartbeatNextStartFrame = Infinity;
    client.lanes.set("system", lane());
    client.lanes.set("microphone", lane());
    const lastAcceptedEndNs = 4_000_000_000;
    const state = {
      descriptor: { sample_rate: 16000, frame_samples: 8000 }, capture_now_ns: 4_100_000_000,
      heartbeat_next_sequence: 2, heartbeat_next_monotonic_ns: 2,
      lanes: { system: { next_sequence: 8, resume_device_epoch: 1 }, microphone: { next_sequence: 8, resume_device_epoch: 1 } },
    };
    const frames: any[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: any) => {
      if (url.endsWith("/resume")) return new Response(JSON.stringify(state));
      if (url.endsWith("/frames")) { frames.push(JSON.parse(init.body)); return new Response("{}"); }
      return new Response("{}");
    }));
    vi.spyOn(performance, "now").mockReturnValue(1000);
    await client.resumeSession("m", "old", false, Promise.resolve());

    // The worklet had 0.4 s buffered at adoption (context time 2.4 s): its chunk starts at 2.0 s.
    client.onWorkletFrame("system", { type: "frame", lane: "system", samples: new Float32Array(8000), startFrame: 32000 });
    // The next chunk starts after adoption.
    client.onWorkletFrame("system", { type: "frame", lane: "system", samples: new Float32Array(8000), startFrame: 40000 });
    await vi.waitFor(() => expect(frames).toHaveLength(1));

    expect(frames[0].sequence).toBe(8);
    expect(frames[0].discontinuity).toBe(true);
    expect(frames[0].capture_timestamp_ns).toBe(4_200_000_000);
    expect(frames[0].capture_timestamp_ns).toBeGreaterThanOrEqual(lastAcceptedEndNs);
    expect(frames[0].capture_end_timestamp_ns).toBe(4_700_000_000);
    expect(client.context).not.toBeNull(); // capture stays open
  });
});
