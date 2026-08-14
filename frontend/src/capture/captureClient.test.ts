import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

import {
  CaptureClient,
  type PreSessionCaptureFailure,
  V2_FRAME_KEYS,
  makeV2Frame,
  parseCaptureDescriptor,
  pcm16Base64,
  stopCaptureSession,
} from "./captureClient";

type TestLaneState = {
  source: { disconnect: () => void };
  framer: { port: { onmessage: unknown }; disconnect: () => void };
  mute: { disconnect: () => void };
  tracks: { stop: () => void }[];
  trackEndedListeners: Array<{ track: EventTarget; listener: () => void }>;
  frameQueue: unknown[];
  postInFlight: boolean;
  sequence: number;
  deviceEpoch: number;
  discontinuity: boolean;
  discontinuities: number;
  droppedFrames: number;
  health: "capturing" | "degraded" | "failed";
  failureCode: string | null;
};

type ActiveClient = {
  descriptor: { sampleRate: number; frameSamples: number } | null;
  session: { id: string; viewToken: string } | null;
  heartbeatNextStartFrame: number;
  lanes: Map<string, TestLaneState>;
  stop: (deadlineSeconds: number) => Promise<void>;
  onWorkletFrame: (
    lane: "microphone",
    frame: { type: "frame"; lane: "microphone"; samples: Float32Array; startFrame: number },
  ) => void;
};

function testLaneState(): TestLaneState {
  return {
    source: { disconnect: vi.fn() },
    framer: { port: { onmessage: null }, disconnect: vi.fn() },
    mute: { disconnect: vi.fn() },
    tracks: [],
    trackEndedListeners: [],
    frameQueue: [],
    postInFlight: false,
    sequence: 0,
    deviceEpoch: 1,
    discontinuity: false,
    discontinuities: 0,
    droppedFrames: 0,
    health: "capturing",
    failureCode: null,
  };
}

function activeFrameClient(): { client: ActiveClient; lane: TestLaneState } {
  const client = new CaptureClient({ captureBearer: "capture-token", helperVersion: "test" });
  const active = client as unknown as ActiveClient;
  const lane = testLaneState();
  active.descriptor = { sampleRate: 4, frameSamples: 2 };
  active.session = { id: "session", viewToken: "view-only" };
  active.heartbeatNextStartFrame = Number.MAX_SAFE_INTEGER;
  active.lanes.set("microphone", lane);
  return { client: active, lane };
}

type PreSessionClient = {
  context: AudioContext | null;
  descriptor: { sampleRate: number; frameSamples: number } | null;
  lanes: Map<string, TestLaneState>;
  startMicrophone: (echoCancellation: boolean) => Promise<void>;
  requestDisplayMedia: () => Promise<MediaStream>;
  attachDisplayMedia: (stream: MediaStream) => Promise<void>;
};

function preSessionClient(onPreSessionFailure: (failure: PreSessionCaptureFailure) => void): {
  client: PreSessionClient;
  context: { close: ReturnType<typeof vi.fn> };
} {
  const context = Object.assign(new EventTarget(), {
    state: "running" as AudioContextState,
    resume: vi.fn().mockResolvedValue(undefined),
    close: vi.fn().mockResolvedValue(undefined),
  });
  const client = new CaptureClient({
    captureBearer: "capture-token",
    helperVersion: "test",
    onPreSessionFailure,
  });
  const active = client as unknown as PreSessionClient;
  active.context = context as unknown as AudioContext;
  active.descriptor = { sampleRate: 4, frameSamples: 2 };
  return { client: active, context };
}

function workletFrame(startFrame: number) {
  return {
    type: "frame" as const,
    lane: "microphone" as const,
    samples: new Float32Array([0.5, -0.5]),
    startFrame,
  };
}

function postedSequences(fetchSpy: ReturnType<typeof vi.fn>): number[] {
  return fetchSpy.mock.calls.map(([, request]) =>
    JSON.parse((request as RequestInit).body as string).sequence,
  );
}

type EventLaneClient = {
  context: AudioContext | null;
  descriptor: { sampleRate: number; frameSamples: number } | null;
  session: { id: string; viewToken: string } | null;
  attachLane: (lane: "microphone" | "system", stream: MediaStream, tracks: MediaStreamTrack[]) => Promise<void>;
};

class FakeAudioWorkletNode {
  readonly port: { onmessage: unknown } = { onmessage: null };

  connect(target: unknown): unknown {
    return target;
  }

  disconnect = vi.fn();
}

function fakeTrack(): MediaStreamTrack {
  return Object.assign(new EventTarget(), { stop: vi.fn() }) as unknown as MediaStreamTrack;
}

async function eventLaneClient(): Promise<{ client: EventLaneClient; microphone: MediaStreamTrack }> {
  vi.stubGlobal("AudioWorkletNode", FakeAudioWorkletNode);
  const source = { connect: (target: unknown) => target, disconnect: vi.fn() };
  const mute = {
    gain: { value: 1 },
    connect: (target: unknown) => target,
    disconnect: vi.fn(),
  };
  const context = Object.assign(new EventTarget(), {
    state: "running",
    destination: {},
    createMediaStreamSource: () => source,
    createGain: () => mute,
  }) as unknown as AudioContext;
  const client = new CaptureClient({ captureBearer: "capture-token", helperVersion: "test" });
  const active = client as unknown as EventLaneClient;
  active.context = context;
  active.descriptor = { sampleRate: 4, frameSamples: 2 };
  active.session = { id: "session", viewToken: "view-only" };
  const microphone = fakeTrack();
  await active.attachLane("microphone", {} as MediaStream, [microphone]);
  await active.attachLane("system", {} as MediaStream, [fakeTrack()]);
  return { client: active, microphone };
}

describe("browser capture frame contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses descriptor geometry and emits exactly the nine v2 frame keys", () => {
    const descriptor = parseCaptureDescriptor({
      descriptor: {
        sample_rate: 24_000,
        frame_samples: 4,
        bounds: { max_frame_samples: 8 },
      },
    });
    const frame = makeV2Frame(
      "system",
      9,
      2,
      true,
      4,
      new Float32Array([1, -1, 0, 0.5]),
      descriptor,
    );

    expect(Object.keys(frame).sort()).toEqual([...V2_FRAME_KEYS].sort());
    expect(frame).toMatchObject({
      lane: "system",
      sequence: 9,
      device_epoch: 2,
      discontinuity: true,
      sample_count: 4,
      sample_rate: 24_000,
      capture_timestamp_ns: 166_667,
    });
    expect(Array.from(new Int16Array(Uint8Array.from(atob(frame.pcm_base64), (byte) => byte.charCodeAt(0)).buffer))).toEqual([
      32767,
      -32767,
      0,
      16384,
    ]);
  });

  it("rejects a worklet frame whose geometry differs from the descriptor", () => {
    const descriptor = parseCaptureDescriptor({
      descriptor: {
        sample_rate: 16_000,
        frame_samples: 4,
        bounds: { max_frame_samples: 4 },
      },
    });

    expect(() =>
      makeV2Frame("microphone", 0, 1, false, 0, new Float32Array(3), descriptor),
    ).toThrow("worklet frame does not match descriptor.frame_samples");
  });

  it("encodes clamped signed little-endian PCM16", () => {
    const bytes = Uint8Array.from(atob(pcm16Base64(new Float32Array([-2, 2]))), (byte) =>
      byte.charCodeAt(0),
    );

    expect(Array.from(new Int16Array(bytes.buffer))).toEqual([-32767, 32767]);
  });

  it("stops through the authenticated server route before local capture teardown", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({
      captureBearer: "capture-token",
      helperVersion: "test",
    });
    const clientState = client as unknown as {
      session: { id: string; viewToken: string } | null;
    };
    clientState.session = { id: "session/with space", viewToken: "view-only" };

    await client.stop(1.25);

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy).toHaveBeenLastCalledWith(
      "/api/live/sessions/session%2Fwith%20space/stop",
      {
        method: "POST",
        cache: "no-store",
        headers: {
          Authorization: "Bearer capture-token",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ deadline: 1.25 }),
      },
    );
    expect(clientState.session).toBeNull();
  });

  it("rejects an invalid stop deadline before issuing a request", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    await expect(
      stopCaptureSession({ id: "session", viewToken: "view" }, "capture-token", -1),
    ).rejects.toThrow("stop deadline must be a non-negative finite number");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("posts a final stopped heartbeat before stopping and rejects timer-based heartbeats", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ captureBearer: "capture-token", helperVersion: "test" });
    const active = client as unknown as ActiveClient;
    active.session = { id: "session/with space", viewToken: "view-only" };

    await active.stop(0);

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const [heartbeatUrl, heartbeatRequest] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(heartbeatUrl).toBe("/api/live/sessions/session%2Fwith%20space/heartbeat");
    expect(JSON.parse(heartbeatRequest.body as string)).toMatchObject({
      state: "stopped",
      lanes: {
        microphone: { state: "stopped", failure_code: null },
        system: { state: "stopped", failure_code: null },
      },
    });
    expect(fetchSpy.mock.calls[1][0]).toBe("/api/live/sessions/session%2Fwith%20space/stop");

    const source = readFileSync(new URL("./captureClient.ts", import.meta.url), "utf8");
    expect(source).not.toMatch(/\b(?:setInterval|setTimeout)\b/);
  });

  it("reports a real track ended event as a failed lane while its peer keeps capture alive", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { microphone } = await eventLaneClient();

    microphone.dispatchEvent(new Event("ended"));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce());

    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toMatchObject({
      state: "capturing",
      lanes: {
        microphone: { state: "failed", failure_code: "browser_track_ended" },
        system: { state: "capturing", failure_code: null },
      },
    });
  });

  it("reports a suspended AudioContext from its real statechange event", async () => {
    class FakeAudioContext extends EventTarget {
      sampleRate = 4;
      state: AudioContextState = "running";
      destination = {} as AudioDestinationNode;
      audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) } as AudioWorklet;
      close = vi.fn().mockResolvedValue(undefined);
    }

    vi.stubGlobal("AudioContext", FakeAudioContext);
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        descriptor: {
          sample_rate: 4,
          frame_samples: 2,
          bounds: { max_frame_samples: 2 },
        },
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ captureBearer: "capture-token", helperVersion: "test" });
    const active = client as unknown as { session: { id: string; viewToken: string } | null };
    const context = (await client.prepare()) as unknown as FakeAudioContext;
    active.session = { id: "session", viewToken: "view-only" };

    context.state = "suspended";
    context.dispatchEvent(new Event("statechange"));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

    const body = JSON.parse((fetchSpy.mock.calls[1][1] as RequestInit).body as string);
    expect(body).toMatchObject({
      state: "degraded",
      lanes: {
        microphone: { state: "degraded", failure_code: "browser_audio_context_suspended" },
        system: { state: "degraded", failure_code: "browser_audio_context_suspended" },
      },
    });
  });

  it("reports and tears down real pre-session capture failures without a heartbeat", async () => {
    const onPreSessionFailure = vi.fn<(failure: PreSessionCaptureFailure) => void>();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const microphoneError = new DOMException("denied", "NotAllowedError");
    const microphone = preSessionClient(onPreSessionFailure);
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(microphoneError) },
    });

    await expect(microphone.client.startMicrophone(false)).rejects.toBe(microphoneError);
    expect(microphone.context.close).toHaveBeenCalledOnce();

    const displayError = new DOMException("dismissed", "NotAllowedError");
    const display = preSessionClient(onPreSessionFailure);
    display.client.lanes.set("microphone", testLaneState());
    vi.stubGlobal("navigator", {
      mediaDevices: { getDisplayMedia: vi.fn().mockRejectedValue(displayError) },
    });

    await expect(display.client.requestDisplayMedia()).rejects.toBe(displayError);
    expect(display.context.close).toHaveBeenCalledOnce();

    const missingAudio = preSessionClient(onPreSessionFailure);
    missingAudio.client.lanes.set("microphone", testLaneState());
    const videoTrack = { stop: vi.fn() } as unknown as MediaStreamTrack;
    const noAudioSurface = {
      getAudioTracks: () => [],
      getTracks: () => [videoTrack],
    } as unknown as MediaStream;

    await expect(missingAudio.client.attachDisplayMedia(noAudioSurface)).rejects.toThrow(
      "selected display surface supplied no audio track",
    );
    expect(videoTrack.stop).toHaveBeenCalledOnce();
    expect(missingAudio.context.close).toHaveBeenCalledOnce();
    expect(onPreSessionFailure).toHaveBeenNthCalledWith(1, {
      lane: "microphone",
      code: "browser_microphone_permission_denied",
    });
    expect(onPreSessionFailure).toHaveBeenNthCalledWith(2, {
      lane: "system",
      code: "browser_capture_request_rejected",
    });
    expect(onPreSessionFailure).toHaveBeenNthCalledWith(3, {
      lane: "system",
      code: "browser_surface_audio_missing",
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("serializes worklet frame POSTs within a lane", async () => {
    let resolveFirst!: (response: { ok: boolean; status: number }) => void;
    const firstResponse = new Promise<{ ok: boolean; status: number }>((resolve) => {
      resolveFirst = resolve;
    });
    const fetchSpy = vi
      .fn()
      .mockReturnValueOnce(firstResponse)
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    client.onWorkletFrame("microphone", workletFrame(2));

    expect(fetchSpy).toHaveBeenCalledOnce();
    resolveFirst({ ok: true, status: 200 });
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

    expect(postedSequences(fetchSpy)).toEqual([0, 1]);
  });

  it("retries the same sequence after an unconsumed lane-capacity 429", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ failure: { code: "v2_lane_retention_capacity_reached" } }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200 })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));
    expect(lane.sequence).toBe(0);
    expect(lane.frameQueue).toHaveLength(1);

    client.onWorkletFrame("microphone", workletFrame(2));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3));

    expect(postedSequences(fetchSpy)).toEqual([0, 0, 1]);
    expect(lane.droppedFrames).toBe(0);
  });

  it("advances after a consumed failure-less queue 429 instead of retrying it", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({ detail: "inference queue is full" }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));
    expect(lane.sequence).toBe(1);
    expect(lane.frameQueue).toHaveLength(0);
    expect(lane.droppedFrames).toBe(1);

    client.onWorkletFrame("microphone", workletFrame(2));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));

    expect(postedSequences(fetchSpy)).toEqual([0, 1]);
  });

  it("resyncs the queue head to the server's expected sequence after an out-of-order 409", async () => {
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 409,
        json: async () => ({
          failure: { code: "v2_out_of_order_frame", expected_sequence: 5 },
        }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200 })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));
    expect(lane.sequence).toBe(5);
    expect(lane.frameQueue).toHaveLength(1);

    client.onWorkletFrame("microphone", workletFrame(2));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3));

    expect(postedSequences(fetchSpy)).toEqual([0, 5, 6]);
  });

  it("clears local session delivery state after a terminal 409 so the caller can recreate it", async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ failure: { code: "v2_stop_accounting_mismatch" } }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));

    expect(client.session).toBeNull();
    expect(lane.sequence).toBe(0);
    expect(lane.frameQueue).toHaveLength(0);
  });

  it("stops local capture instead of sending another frame after a malformed-frame 400", async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(client.session).toBeNull());

    expect(client.lanes).toHaveLength(0);
    client.onWorkletFrame("microphone", workletFrame(2));
    expect(fetchSpy).toHaveBeenCalledOnce();
  });
});
