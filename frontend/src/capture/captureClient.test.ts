import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CaptureClient,
  V2_FRAME_KEYS,
  makeV2Frame,
  parseCaptureDescriptor,
  pcm16Base64,
  stopCaptureSession,
} from "./captureClient";

type TestLaneState = {
  frameQueue: unknown[];
  postInFlight: boolean;
  sequence: number;
  deviceEpoch: number;
  discontinuity: boolean;
  discontinuities: number;
  droppedFrames: number;
};

type ActiveClient = {
  descriptor: { sampleRate: number; frameSamples: number } | null;
  session: { id: string; viewToken: string } | null;
  heartbeatNextStartFrame: number;
  lanes: Map<string, TestLaneState>;
  onWorkletFrame: (
    lane: "microphone",
    frame: { type: "frame"; lane: "microphone"; samples: Float32Array; startFrame: number },
  ) => void;
};

function activeFrameClient(): { client: ActiveClient; lane: TestLaneState } {
  const client = new CaptureClient({ captureBearer: "capture-token", helperVersion: "test" });
  const active = client as unknown as ActiveClient;
  const lane: TestLaneState = {
    frameQueue: [],
    postInFlight: false,
    sequence: 0,
    deviceEpoch: 1,
    discontinuity: false,
    discontinuities: 0,
    droppedFrames: 0,
  };
  active.descriptor = { sampleRate: 4, frameSamples: 2 };
  active.session = { id: "session", viewToken: "view-only" };
  active.heartbeatNextStartFrame = Number.MAX_SAFE_INTEGER;
  active.lanes.set("microphone", lane);
  return { client: active, lane };
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

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy).toHaveBeenCalledWith(
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
});
