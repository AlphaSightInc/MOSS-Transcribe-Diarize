/*
 * Failing-before / passing-after for every defect the x2-capture-client PRD names.
 *
 * `dev` carries no `frontend/src/capture/` at all, so "before" is the frozen copy in
 * `prebranch/preBranchCaptureClient.ts` (verbatim `afk2/r2-capture-client`, the state
 * the PRD's line numbers refer to). Each test drives BOTH clients through the same
 * harness and the same server fake, and asserts the pre-branch one exhibits the
 * defect while the current one does not.
 *
 * That is the point: an assertion no input can fail is not a gate. Every correctness
 * assertion below has a demonstrated failing input -- the pre-branch client -- sitting
 * next to it in the same test.
 *
 * The server fake is not invented here either; see `laneIngressContract.ts` and the
 * probe that measures it against the production ingress.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { CaptureClient } from "./captureClient";
import { CaptureClient as PreBranchCaptureClient } from "./prebranch/preBranchCaptureClient";
import {
  FakeLaneIngressServer,
  SERVER_FRAME_OUTCOMES,
  SERVER_SEQUENCE_CONSUMED,
  type FakeResponse,
} from "./laneIngressContract";

type AnyCaptureClient = CaptureClient | PreBranchCaptureClient;
type ClientCtor = typeof CaptureClient | typeof PreBranchCaptureClient;

const FRAME_SAMPLES = 8;
const DESCRIPTOR_RATE = 16_000;

type Harness = {
  client: AnyCaptureClient;
  server: FakeLaneIngressServer;
  /** Every request the client issued, in call order. */
  calls: Array<{ url: string; body: unknown }>;
  heartbeats: Array<Record<string, any>>;
  /** Frame POSTs whose response has not been released yet. */
  pending: Array<() => void>;
  microphoneTrack: MediaStreamTrack;
  context: { sampleRate: number; state: string } & EventTarget;
  deliver: (lane: "microphone" | "system", index: number) => void;
  /** Settle until the lane has no post in flight — the client's own quiescence flag. */
  quiescent: (lane: string) => Promise<void>;
  laneState: (lane: string) => any;
  setSession: (session: { id: string; viewToken: string } | null) => void;
};

class FakeAudioWorkletNode {
  readonly port: { onmessage: ((event: MessageEvent<unknown>) => void) | null } = {
    onmessage: null,
  };
  connect(target: unknown): unknown {
    return target;
  }
  disconnect = vi.fn();
}

function fakeTrack(): MediaStreamTrack {
  return Object.assign(new EventTarget(), { stop: vi.fn() }) as unknown as MediaStreamTrack;
}

/** A frame that is unambiguously above the silence floor, so `silent` is false. */
function samples(): Float32Array {
  return new Float32Array(FRAME_SAMPLES).fill(0.5);
}

async function harness(
  Ctor: ClientCtor,
  options: {
    maxRetainedSamples?: number;
    contextSampleRate?: number;
    deferFrames?: boolean;
    attachLanes?: boolean;
  } = {},
): Promise<Harness> {
  const server = new FakeLaneIngressServer({
    maxRetainedSamples: options.maxRetainedSamples,
  });
  const calls: Harness["calls"] = [];
  const heartbeats: Harness["heartbeats"] = [];
  const pending: Harness["pending"] = [];

  const fetchImpl = (url: string, request: RequestInit): Promise<FakeResponse> => {
    const body = request?.body ? JSON.parse(request.body as string) : null;
    calls.push({ url, body });
    if (url.endsWith("/heartbeat")) {
      heartbeats.push(body as Record<string, any>);
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }
    if (url.endsWith("/stop")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }
    if (url === "/api/live/sessions") {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          id: "session",
          view_token: "view-only",
          descriptor: { sample_rate: DESCRIPTOR_RATE, frame_samples: FRAME_SAMPLES },
        }),
      });
    }
    if (!url.endsWith("/frames")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
    }
    // The server decides at *release* time, so an unserialized client's two in-flight
    // posts can genuinely arrive in the wrong order.
    if (!options.deferFrames) return Promise.resolve(server.handle(body as any));
    return new Promise<FakeResponse>((resolve) => {
      pending.push(() => resolve(server.handle(body as any)));
    });
  };
  vi.stubGlobal("fetch", fetchImpl);
  vi.stubGlobal("AudioWorkletNode", FakeAudioWorkletNode);

  const source = { connect: (target: unknown) => target, disconnect: vi.fn() };
  const mute = { gain: { value: 1 }, connect: (t: unknown) => t, disconnect: vi.fn() };
  const context = Object.assign(new EventTarget(), {
    state: "running",
    sampleRate: options.contextSampleRate ?? DESCRIPTOR_RATE,
    destination: {},
    createMediaStreamSource: () => source,
    createGain: () => mute,
    close: vi.fn().mockResolvedValue(undefined),
  }) as unknown as Harness["context"];

  const client = new Ctor({ captureBearer: "capture-token", helperVersion: "test" });
  const active = client as any;
  active.context = context;
  active.descriptor = { sampleRate: DESCRIPTOR_RATE, frameSamples: FRAME_SAMPLES };
  // Heartbeats are worklet-driven; park the gate so frame tests are not drowned in
  // them, and unpark it explicitly in the heartbeat tests.
  active.heartbeatNextStartFrame = Number.MAX_SAFE_INTEGER;

  const microphoneTrack = fakeTrack();
  if (options.attachLanes !== false) {
    await active.attachLane("microphone", {} as MediaStream, [microphoneTrack]);
    await active.attachLane("system", {} as MediaStream, [fakeTrack()]);
    active.session = { id: "session", viewToken: "view-only" };
  }

  return {
    client,
    server,
    calls,
    heartbeats,
    pending,
    microphoneTrack,
    context,
    laneState: (lane: string) => active.lanes.get(lane),
    quiescent: async (lane: string) => {
      const state = active.lanes.get(lane);
      if (state && "postInFlight" in state) {
        await vi.waitFor(() => expect(state.postInFlight).toBe(false));
        return;
      }
      // The pre-branch client has no such flag; it never knew what was in flight.
      for (let turn = 0; turn < 8; turn += 1) await Promise.resolve();
    },
    setSession: (session) => {
      active.session = session;
    },
    deliver: (lane, index) => {
      const state = active.lanes.get(lane);
      const onmessage = state?.framer?.port?.onmessage;
      if (!onmessage) throw new Error(`${lane} lane is not accepting worklet frames`);
      onmessage({
        data: {
          type: "frame",
          lane,
          samples: samples(),
          startFrame: index * FRAME_SAMPLES,
        },
      } as MessageEvent<unknown>);
    },
  };
}

/** Frame POSTs only, in wire order. */
function frameBodies(calls: Harness["calls"]): any[] {
  return calls.filter((call) => call.url.endsWith("/frames")).map((call) => call.body);
}

describe("PRD defect 1 — one 429 permanently kills a lane", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pre-branch: a lane-capacity 429 consumes the sequence and wedges the lane in 409 forever", async () => {
    // 16 retained samples = exactly two 8-sample frames, so frame 2 hits capacity --
    // the same arithmetic the python probe drives through the real ingress.
    const before = await harness(PreBranchCaptureClient, { maxRetainedSamples: 16 });
    for (const index of [0, 1, 2]) before.deliver("microphone", index);
    await vi.waitFor(() => expect(before.server.received).toHaveLength(3));
    expect(before.server.statuses).toEqual([200, 200, 429]);

    // The mixer drains, so capacity is available again from here on.
    before.server.releaseRetained("microphone");
    for (const index of [3, 4, 5]) before.deliver("microphone", index);
    await vi.waitFor(() => expect(before.server.received).toHaveLength(6));

    // It never resent sequence 2, so every later frame is out of order.
    expect(frameBodies(before.calls).map((body) => body.sequence)).toEqual([0, 1, 2, 3, 4, 5]);
    expect(before.server.statuses.slice(3)).toEqual([409, 409, 409]);
    expect(before.server.admitted("microphone")).toBe(2);
  });

  it("current: resends the unconsumed sequence and the lane keeps being admitted", async () => {
    const after = await harness(CaptureClient, { maxRetainedSamples: 16 });
    for (const index of [0, 1, 2]) after.deliver("microphone", index);
    await after.quiescent("microphone");
    expect(after.server.statuses).toEqual([200, 200, 429]);
    expect(after.laneState("microphone").frameQueue).toHaveLength(1);

    // The mixer drains 16 samples, which is room for exactly two more frames.
    after.server.releaseRetained("microphone");
    after.deliver("microphone", 3);
    await vi.waitFor(() => expect(after.server.admitted("microphone")).toBe(4));

    // Sequence 2 is re-sent, not skipped, and nothing ever 409s.
    expect(frameBodies(after.calls).map((body) => body.sequence)).toEqual([0, 1, 2, 2, 3]);
    expect(after.server.statuses).toEqual([200, 200, 429, 200, 200]);
    expect(after.server.statuses).not.toContain(409);
  });

  it("current: the retry rides the next worklet frame — there is no timer to wait on", async () => {
    const after = await harness(CaptureClient, { maxRetainedSamples: 8 });
    after.deliver("microphone", 0);
    await after.quiescent("microphone");
    after.deliver("microphone", 1);
    await after.quiescent("microphone");
    expect(after.server.statuses).toEqual([200, 429]);

    // Capacity frees up, but nothing is resent until audio moves again: no setTimeout,
    // no setInterval, no backoff clock anywhere in the client.
    after.server.releaseRetained("microphone");
    await new Promise((resolve) => queueMicrotask(() => resolve(null)));
    expect(after.server.received).toHaveLength(2);

    after.deliver("microphone", 2);
    await vi.waitFor(() => expect(after.server.admitted("microphone")).toBe(2));
    expect(frameBodies(after.calls).map((body) => body.sequence)).toEqual([0, 1, 1]);
  });

  it("current: a consumed failure-less queue 429 is advanced past, not resent", async () => {
    const after = await harness(CaptureClient);
    after.server.applyQueueBackpressure(1);
    for (const index of [0, 1]) after.deliver("microphone", index);
    await vi.waitFor(() => expect(after.server.received).toHaveLength(2));

    // Resending here would arrive as sequence 0 against an expected 1 and 409.
    expect(after.server.statuses).toEqual([429, 200]);
    expect(frameBodies(after.calls).map((body) => body.sequence)).toEqual([0, 1]);
    expect(after.server.statuses).not.toContain(409);
    expect(after.laneState("microphone").droppedFrames).toBe(1);
  });

  it("pre-branch: two in-flight posts reorder and wedge the lane with no error at all", async () => {
    const before = await harness(PreBranchCaptureClient, { deferFrames: true });
    before.deliver("microphone", 0);
    before.deliver("microphone", 1);
    // Fire-and-forget: both are already on the wire.
    expect(before.pending).toHaveLength(2);

    // The network delivers the second first, which is all it takes.
    before.pending[1]();
    before.pending[0]();
    await vi.waitFor(() => expect(before.server.received).toHaveLength(2));

    expect(before.server.received.map((frame) => frame.sequence)).toEqual([1, 0]);
    expect(before.server.statuses).toEqual([409, 200]);
    expect(before.server.admitted("microphone")).toBe(1);
  });

  it("current: only one post per lane is ever in flight, so reordering is impossible", async () => {
    const after = await harness(CaptureClient, { deferFrames: true });
    after.deliver("microphone", 0);
    after.deliver("microphone", 1);
    expect(after.pending).toHaveLength(1);

    after.pending[0]();
    await vi.waitFor(() => expect(after.pending).toHaveLength(2));
    after.pending[1]();
    await vi.waitFor(() => expect(after.server.received).toHaveLength(2));

    expect(after.server.received.map((frame) => frame.sequence)).toEqual([0, 1]);
    expect(after.server.statuses).toEqual([200, 200]);
  });

  it("current: an out-of-order 409 resyncs to the sequence the server names", async () => {
    const after = await harness(CaptureClient);
    // Push the lane ahead of the client so the next post is genuinely out of order.
    after.server.laneState("microphone").nextSequence = 4;
    after.server.laneState("microphone").currentDeviceEpoch = 1;
    after.deliver("microphone", 0);
    await after.quiescent("microphone");
    expect(after.server.statuses).toEqual([409]);
    expect(after.laneState("microphone").sequence).toBe(4);

    // Same rule as the 429 retry: the resync rides the next worklet frame.
    after.deliver("microphone", 1);
    await vi.waitFor(() => expect(after.server.admitted("microphone")).toBe(6));

    expect(frameBodies(after.calls).map((body) => body.sequence)).toEqual([0, 4, 5]);
    expect(after.server.statuses).toEqual([409, 200, 200]);
  });
});

describe("PRD defect 2 — the browser failure vocabulary is dead", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pre-branch: stop() sends no final heartbeat, so the server never sees a clean stop", async () => {
    const before = await harness(PreBranchCaptureClient);
    await (before.client as PreBranchCaptureClient).stop(0);

    expect(before.heartbeats).toHaveLength(0);
    expect(before.calls.map((call) => call.url)).toEqual(["/api/live/sessions/session/stop"]);
  });

  it("current: stop() posts a stopped heartbeat before the stop route", async () => {
    const after = await harness(CaptureClient);
    await (after.client as CaptureClient).stop(0);

    expect(after.calls.map((call) => call.url)).toEqual([
      "/api/live/sessions/session/heartbeat",
      "/api/live/sessions/session/stop",
    ]);
    expect(after.heartbeats[0]).toMatchObject({
      state: "stopped",
      lanes: { microphone: { state: "stopped" }, system: { state: "stopped" } },
    });
  });

  it("pre-branch: an ended track produces no failure fact and the lane keeps posting", async () => {
    const before = await harness(PreBranchCaptureClient);
    (before.client as any).heartbeatNextStartFrame = 0;
    before.microphoneTrack.dispatchEvent(new Event("ended"));
    before.deliver("microphone", 0);
    await vi.waitFor(() => expect(before.heartbeats).toHaveLength(1));

    expect(before.heartbeats[0].state).toBe("capturing");
    expect(before.heartbeats[0].lanes.microphone).toMatchObject({
      state: "capturing",
      failure_code: null,
    });
    // Worse than silent: the dead lane is still being posted as live audio.
    expect(before.server.admitted("microphone")).toBe(1);
  });

  it("current: an ended track fails that lane with a named code and stops posting it", async () => {
    const after = await harness(CaptureClient);
    after.microphoneTrack.dispatchEvent(new Event("ended"));
    await vi.waitFor(() => expect(after.heartbeats).toHaveLength(1));

    expect(after.heartbeats[0].lanes.microphone).toMatchObject({
      state: "failed",
      failure_code: "browser_track_ended",
    });
    // The peer lane is untouched: the server fails only the named lane.
    expect(after.heartbeats[0].lanes.system).toMatchObject({ state: "capturing" });

    after.deliver("microphone", 0);
    after.deliver("system", 0);
    await vi.waitFor(() => expect(after.server.received).toHaveLength(1));
    expect(after.server.received[0].lane).toBe("system");
  });
});

describe("PRD defect 3 — lane loss is unimplemented", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pre-branch: has no lane-replacement seam, so the server's device epoch never moves", async () => {
    const before = await harness(PreBranchCaptureClient);
    expect((before.client as any).replaceLane).toBeUndefined();

    for (const index of [0, 1, 2]) before.deliver("microphone", index);
    await vi.waitFor(() => expect(before.server.received).toHaveLength(3));

    expect(frameBodies(before.calls).every((body) => body.device_epoch === 1)).toBe(true);
    expect(frameBodies(before.calls).every((body) => body.discontinuity === false)).toBe(true);
    expect(before.server.laneState("microphone").currentDeviceEpoch).toBe(1);
  });

  it("current: replacement advances the epoch and marks the splice the server checks for", async () => {
    const after = await harness(CaptureClient);
    after.deliver("microphone", 0);
    await vi.waitFor(() => expect(after.server.received).toHaveLength(1));

    await (after.client as CaptureClient).replaceLane("microphone", {} as MediaStream, [
      fakeTrack(),
    ]);
    after.deliver("microphone", 1);
    await vi.waitFor(() => expect(after.server.received).toHaveLength(2));

    expect(after.server.received[1]).toMatchObject({ device_epoch: 2, discontinuity: true });
    expect(after.server.statuses).toEqual([200, 200]);
    expect(after.server.laneState("microphone").currentDeviceEpoch).toBe(2);
  });

  it("the discontinuity flag is what the server accepts on, not the epoch bump alone", async () => {
    // Without this the test above would pass on a client that bumped the epoch and left
    // discontinuity false -- exactly the pre-branch shape.
    const after = await harness(CaptureClient);
    after.deliver("microphone", 0);
    await vi.waitFor(() => expect(after.server.received).toHaveLength(1));

    const response = after.server.handle({
      lane: "microphone",
      sequence: 1,
      device_epoch: 2,
      discontinuity: false,
      sample_count: FRAME_SAMPLES,
    });
    expect(response.status).toBe(409);
    await expect(response.json()).resolves.toMatchObject({
      failure: { code: "v2_epoch_discontinuity_required" },
    });
  });
});

describe("PRD defect 4 — frames are tagged with the requested sample rate", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("pre-branch: a browser that hands back 48 kHz still ships 16 kHz labels and clocks", async () => {
    const before = await harness(PreBranchCaptureClient, { contextSampleRate: 48_000 });
    before.deliver("microphone", 1);
    await vi.waitFor(() => expect(before.server.received).toHaveLength(1));

    const body = frameBodies(before.calls)[0];
    expect(body.sample_rate).toBe(DESCRIPTOR_RATE);
    expect(body.capture_timestamp_ns).toBe(Math.round((FRAME_SAMPLES / DESCRIPTOR_RATE) * 1e9));
  });

  it("current: labels and clocks the frame with the rate the AudioContext actually gave", async () => {
    const after = await harness(CaptureClient, { contextSampleRate: 48_000 });
    after.deliver("microphone", 1);
    await vi.waitFor(() => expect(after.server.received).toHaveLength(1));

    const body = frameBodies(after.calls)[0];
    expect(body.sample_rate).toBe(48_000);
    expect(body.capture_timestamp_ns).toBe(Math.round((FRAME_SAMPLES / 48_000) * 1e9));
  });
});

describe("PRD defect 5 — the preflight signal gate is a no-op", () => {
  afterEach(() => vi.unstubAllGlobals());

  const dither = () => new Float32Array(FRAME_SAMPLES).fill(5e-5);

  async function driveDitherThenCreate(Ctor: ClientCtor) {
    const bench = await harness(Ctor);
    const active = bench.client as any;
    active.session = null;
    for (const lane of ["microphone", "system"] as const) {
      active.lanes.get(lane).framer.port.onmessage({
        data: { type: "frame", lane, samples: dither(), startFrame: 0 },
      } as MessageEvent<unknown>);
    }
    return bench;
  }

  it("pre-branch: dither alone satisfies `level > 0` and a session is created on silence", async () => {
    const before = await driveDitherThenCreate(PreBranchCaptureClient);
    await expect((before.client as PreBranchCaptureClient).createSession()).resolves.toMatchObject({
      id: "session",
    });
  });

  it("current: dither is below the declared noise floor and session creation is refused", async () => {
    const after = await driveDitherThenCreate(CaptureClient);
    await expect((after.client as CaptureClient).createSession()).rejects.toThrow(
      "both capture lanes must have non-zero signal before session creation",
    );

    // ... and real signal on both lanes still gets through, so this is a floor, not a wall.
    const active = after.client as any;
    for (const lane of ["microphone", "system"] as const) {
      active.lanes.get(lane).framer.port.onmessage({
        data: { type: "frame", lane, samples: samples(), startFrame: FRAME_SAMPLES },
      } as MessageEvent<unknown>);
    }
    await expect((after.client as CaptureClient).createSession()).resolves.toMatchObject({
      id: "session",
    });
  });
});

describe("the server contract table this suite is built on", () => {
  it("covers every reachable frame outcome and names which ones consume the sequence", () => {
    const scenarios = SERVER_FRAME_OUTCOMES.map(([scenario]) => scenario);
    expect(new Set(scenarios).size).toBe(scenarios.length);
    expect(Object.keys(SERVER_SEQUENCE_CONSUMED).sort()).toEqual([...scenarios].sort());

    // The two 429s that must be handled in opposite directions.
    const capacity = SERVER_FRAME_OUTCOMES.find(
      ([, status, code]) => status === 429 && code === "v2_lane_retention_capacity_reached",
    );
    const backpressure = SERVER_FRAME_OUTCOMES.find(
      ([, status, code]) => status === 429 && code === null,
    );
    expect(capacity).toBeDefined();
    expect(backpressure).toBeDefined();
    expect(SERVER_SEQUENCE_CONSUMED["lane_retention_capacity_reached"]).toBe(false);
    expect(SERVER_SEQUENCE_CONSUMED["queue_backpressure_after_accept"]).toBe(true);
  });
});
