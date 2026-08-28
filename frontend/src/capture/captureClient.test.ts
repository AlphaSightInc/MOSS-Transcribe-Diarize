import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

import {
  CaptureClient,
  type CaptureDescriptor,
  type CaptureLane,
  type PreSessionCaptureFailure,
  V2_FRAME_KEYS,
  makeV2Frame,
  parseCaptureDescriptor,
  pcm16Base64,
  stopCaptureSession,
} from "./captureClient";

type TestLaneState = {
  clippedFrameRun: number;
  silentFrameRun: number;
  degradedCode: string | null;
  source: { disconnect: () => void };
  framer: { port: { onmessage: unknown }; disconnect: () => void };
  mute: { disconnect: () => void };
  tracks: { stop: () => void }[];
  trackEndedListeners: Array<{ track: EventTarget; listener: () => void }>;
  frameQueue: unknown[];
  postInFlight: boolean;
  sequence: number;
  deviceEpoch: number;
  pendingDiscontinuityEpochs: Set<number>;
  discontinuities: number;
  droppedFrames: number;
  health: "capturing" | "degraded" | "failed";
  failureCode: string | null;
};

type ActiveClient = {
  context: AudioContext | null;
  descriptor: CaptureDescriptor | null;
  session: { id: string } | null;
  heartbeatNextStartFrame: number;
  lanes: Map<string, TestLaneState>;
  stop: (deadlineSeconds: number) => Promise<void>;
  onWorkletFrame: (
    lane: CaptureLane,
    frame: { type: "frame"; lane: CaptureLane; samples: Float32Array; startFrame: number },
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
    pendingDiscontinuityEpochs: new Set(),
    discontinuities: 0,
    droppedFrames: 0,
    health: "capturing",
    failureCode: null,
    degradedCode: null,
    clippedFrameRun: 0,
    silentFrameRun: 0,
  };
}

function activeFrameClient(
  onTransportError?: (route: "frame" | "heartbeat", error: Error) => void,
): { client: ActiveClient; lane: TestLaneState } {
  const client = new CaptureClient({
    helperVersion: "test",
    onTransportError,
  });
  const active = client as unknown as ActiveClient;
  const lane = testLaneState();
  active.context = { sampleRate: 4 } as AudioContext;
  active.descriptor = {
    sampleRate: 4,
    frameSamples: 2,
    preflightStatusLines: { microphoneSilent: silentMicrophoneRemedy },
  };
  active.session = { id: "session" };
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
  session: { id: string } | null;
  heartbeatNextStartFrame: number;
  lanes: Map<CaptureLane, TestLaneState>;
  attachLane: (lane: "microphone" | "system", stream: MediaStream, tracks: MediaStreamTrack[]) => Promise<void>;
  replaceLane: (lane: CaptureLane, stream: MediaStream, tracks: MediaStreamTrack[]) => Promise<void>;
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
    sampleRate: 4,
    destination: {},
    createMediaStreamSource: () => source,
    createGain: () => mute,
  }) as unknown as AudioContext;
  const client = new CaptureClient({ helperVersion: "test" });
  const active = client as unknown as EventLaneClient;
  active.context = context;
  active.descriptor = { sampleRate: 4, frameSamples: 2 };
  active.session = { id: "session" };
  active.heartbeatNextStartFrame = Number.MAX_SAFE_INTEGER;
  const microphone = fakeTrack();
  await active.attachLane("microphone", {} as MediaStream, [microphone]);
  await active.attachLane("system", {} as MediaStream, [fakeTrack()]);
  return { client: active, microphone };
}

function deliverWorkletFrame(state: TestLaneState, frame: ReturnType<typeof workletFrame>): void {
  const onmessage = state.framer.port.onmessage as ((event: MessageEvent<unknown>) => void) | null;
  if (!onmessage) throw new Error("lane worklet is not accepting frames");
  onmessage({ data: frame } as MessageEvent<unknown>);
}

/** Push `count` frames of `samples` into a lane through its real worklet port. */
function deliverSamples(
  client: EventLaneClient,
  lane: CaptureLane,
  samples: () => Float32Array,
  count: number,
  startAt = 0,
): void {
  const state = client.lanes.get(lane);
  if (!state) throw new Error(`missing ${lane} lane`);
  for (let index = 0; index < count; index += 1) {
    deliverWorkletFrame(state, {
      type: "frame",
      lane,
      samples: samples(),
      startFrame: (startAt + index) * 2,
    } as ReturnType<typeof workletFrame>);
  }
}

/** Both samples encode to full scale, so the whole frame is clipped. */
const fullScale = () => new Float32Array([1, -1]);
const clean = () => new Float32Array([0.5, -0.5]);
const silent = () => new Float32Array([0, 0]);
const silentMicrophoneRemedy =
  "No microphone sound was detected. In Chrome, open Settings > Privacy and security > " +
  "Site settings > Microphone and select the correct default input.";

function heartbeatBodies(fetchSpy: ReturnType<typeof vi.fn>): Array<Record<string, any>> {
  return fetchSpy.mock.calls
    .filter(([url]) => String(url).endsWith("/heartbeat"))
    .map(([, request]) => JSON.parse((request as RequestInit).body as string));
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
      preflight_status_lines: { browser_microphone_silent: silentMicrophoneRemedy },
    });
    expect(descriptor.preflightStatusLines.microphoneSilent).toBe(silentMicrophoneRemedy);
    const frame = makeV2Frame(
      "system",
      9,
      2,
      true,
      4,
      new Float32Array([1, -1, 0, 0.5]),
      descriptor,
      48_000,
    );

    expect(Object.keys(frame).sort()).toEqual([...V2_FRAME_KEYS].sort());
    expect(frame).toMatchObject({
      lane: "system",
      sequence: 9,
      device_epoch: 2,
      discontinuity: true,
      sample_count: 4,
      sample_rate: 48_000,
      capture_timestamp_ns: 83_333,
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
      preflight_status_lines: { browser_microphone_silent: silentMicrophoneRemedy },
    });

    expect(() =>
      makeV2Frame("microphone", 0, 1, false, 0, new Float32Array(3), descriptor, 16_000),
    ).toThrow("worklet frame does not match descriptor.frame_samples");
  });

  it("encodes clamped signed little-endian PCM16", () => {
    const bytes = Uint8Array.from(atob(pcm16Base64(new Float32Array([-2, 2]))), (byte) =>
      byte.charCodeAt(0),
    );

    expect(Array.from(new Int16Array(bytes.buffer))).toEqual([-32767, 32767]);
  });

  it("labels a frame and its clock with the actual AudioContext rate", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = activeFrameClient();
    client.context = { sampleRate: 8 } as AudioContext;

    client.onWorkletFrame("microphone", workletFrame(2));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce());

    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toMatchObject({ sample_rate: 8, capture_timestamp_ns: 250_000_000 });
  });

  it("requires signal above the declared preflight noise floor before creating a session", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "session",
        descriptor: { sample_rate: 4, frame_samples: 2 },
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = activeFrameClient();
    client.session = null;
    client.lanes.set("system", testLaneState());

    client.onWorkletFrame("microphone", {
      ...workletFrame(0),
      samples: new Float32Array([5e-5, -5e-5]),
    });
    client.onWorkletFrame("system", {
      ...workletFrame(0),
      lane: "system",
      samples: new Float32Array([0.5, -0.5]),
    });

    await expect((client as unknown as CaptureClient).createSession()).rejects.toThrow(
      "both capture lanes must have non-zero signal before session creation",
    );
    expect(fetchSpy).not.toHaveBeenCalled();

    client.onWorkletFrame("microphone", {
      ...workletFrame(2),
      samples: new Float32Array([2e-4, -2e-4]),
    });
    await expect((client as unknown as CaptureClient).createSession()).resolves.toMatchObject({
      id: "session",
    });
    expect(fetchSpy.mock.calls.map(([url]) => url)).toEqual([
      "/api/live/sessions",
      "/api/live/sessions/session/heartbeat",
    ]);
  });

  it("stops through the authenticated server route before local capture teardown", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ helperVersion: "test" });
    const clientState = client as unknown as {
      session: { id: string } | null;
    };
    clientState.session = { id: "session/with space" };

    await client.stop(1.25);

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy).toHaveBeenLastCalledWith(
      "/api/live/sessions/session%2Fwith%20space/stop",
      {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        signal: expect.any(AbortSignal),
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ deadline: 1.25 }),
      },
    );
    expect(clientState.session).toBeNull();
  });

  it("uses the signed-in Account cookie without another client credential", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({
        id: "account-meeting",
        descriptor: { sample_rate: 4, frame_samples: 2 },
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ helperVersion: "test" });
    const active = client as unknown as ActiveClient;
    active.context = { sampleRate: 4 } as AudioContext;
    active.descriptor = {
      sampleRate: 4,
      frameSamples: 2,
      preflightStatusLines: { microphoneSilent: silentMicrophoneRemedy },
    };
    active.session = null;
    active.lanes.set("microphone", testLaneState());
    active.lanes.set("system", testLaneState());
    active.onWorkletFrame("microphone", workletFrame(0));
    active.onWorkletFrame("system", { ...workletFrame(0), lane: "system" });

    await expect(client.createSession()).resolves.toEqual({ id: "account-meeting" });
    expect(fetchSpy.mock.calls[0]).toEqual([
      "/api/live/sessions",
      expect.objectContaining({ credentials: "same-origin" }),
    ]);
    expect((fetchSpy.mock.calls[0][1] as RequestInit).headers).toBeUndefined();
  });

  it("rejects an invalid stop deadline before issuing a request", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    await expect(
      stopCaptureSession({ id: "session" }, -1),
    ).rejects.toThrow("stop deadline must be a non-negative finite number");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("posts a final stopped heartbeat without a recurring timer loop", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ helperVersion: "test" });
    const active = client as unknown as ActiveClient;
    active.session = { id: "session/with space" };

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
    expect(source).not.toMatch(/\bsetInterval\b/);
    expect(source.match(/\bsetTimeout\b/g)).toHaveLength(1);
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

  it("preserves queued-source epochs and marks the first replacement frame discontinuous", async () => {
    let resolveFirst!: (response: { ok: boolean; status: number }) => void;
    const firstResponse = new Promise<{ ok: boolean; status: number }>((resolve) => {
      resolveFirst = resolve;
    });
    const fetchSpy = vi.fn().mockReturnValueOnce(firstResponse).mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, microphone } = await eventLaneClient();
    const initial = client.lanes.get("microphone");
    if (!initial) throw new Error("missing microphone lane");
    const initialFramer = initial.framer;

    deliverWorkletFrame(initial, workletFrame(0));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce());
    deliverWorkletFrame(initial, workletFrame(2));

    const replacementTrack = fakeTrack();
    await client.replaceLane("microphone", {} as MediaStream, [replacementTrack]);
    const replacement = client.lanes.get("microphone");
    if (!replacement) throw new Error("missing replacement microphone lane");
    expect(initialFramer.port.onmessage).toBeNull();
    expect(microphone.stop).toHaveBeenCalledOnce();
    expect(replacement.deviceEpoch).toBe(2);
    expect(replacement.discontinuities).toBe(1);

    deliverWorkletFrame(replacement, workletFrame(4));
    resolveFirst({ ok: true, status: 200 });
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(3));

    const bodies = fetchSpy.mock.calls.map(([, request]) =>
      JSON.parse((request as RequestInit).body as string),
    );
    expect(bodies).toMatchObject([
      { sequence: 0, device_epoch: 1, discontinuity: false },
      { sequence: 1, device_epoch: 1, discontinuity: false },
      { sequence: 2, device_epoch: 2, discontinuity: true },
    ]);
  });

  it("replays identical PCM and sequence after an unconfirmed frame delivery", async () => {
    const transportError = new Error("connection reset");
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, status: 200 })
      .mockRejectedValueOnce(transportError)
      .mockResolvedValueOnce({ ok: true, status: 200 })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = await eventLaneClient();
    const initial = client.lanes.get("microphone");
    if (!initial) throw new Error("missing microphone lane");

    deliverWorkletFrame(initial, workletFrame(0));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledOnce());
    await client.replaceLane("microphone", {} as MediaStream, [fakeTrack()]);
    const replacement = client.lanes.get("microphone");
    if (!replacement) throw new Error("missing replacement microphone lane");

    deliverWorkletFrame(replacement, workletFrame(2));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    await vi.waitFor(() => expect(replacement.postInFlight).toBe(false));
    deliverWorkletFrame(replacement, workletFrame(4));
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(4));

    const bodies = fetchSpy.mock.calls.map(([, request]) =>
      JSON.parse((request as RequestInit).body as string),
    );
    expect(bodies).toMatchObject([
      { sequence: 0, device_epoch: 1, discontinuity: false },
      { sequence: 1, device_epoch: 2, discontinuity: true },
      { sequence: 1, device_epoch: 2, discontinuity: true },
      { sequence: 2, device_epoch: 2, discontinuity: false },
    ]);
    expect(replacement.droppedFrames).toBe(0);
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
        preflight_status_lines: { browser_microphone_silent: silentMicrophoneRemedy },
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ helperVersion: "test" });
    const active = client as unknown as { session: { id: string } | null };
    const context = (await client.prepare()) as unknown as FakeAudioContext;
    expect(context.audioWorklet.addModule).toHaveBeenCalledWith("/static/worklets/lane-framer.js");
    active.session = { id: "session" };

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

  it("keeps an active session and both lanes when the Reshare chooser is cancelled", async () => {
    const onPreSessionFailure = vi.fn<(failure: PreSessionCaptureFailure) => void>();
    const displayError = new DOMException("dismissed", "NotAllowedError");
    const display = preSessionClient(onPreSessionFailure);
    display.client.lanes.set("microphone", testLaneState());
    display.client.lanes.set("system", testLaneState());
    (display.client as unknown as { session: { id: string } | null }).session = {
      id: "active-session",
    };
    vi.stubGlobal("navigator", {
      mediaDevices: { getDisplayMedia: vi.fn().mockRejectedValue(displayError) },
    });

    await expect(display.client.requestDisplayMedia()).rejects.toBe(displayError);

    expect(display.context.close).not.toHaveBeenCalled();
    expect(display.client.lanes.size).toBe(2);
    expect(onPreSessionFailure).not.toHaveBeenCalled();
  });

  it("closes local media even when terminal Stop is rejected", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 409 }));
    const { client } = activeFrameClient();
    (client as unknown as { scheduleHeartbeat: (state: string) => Promise<void> }).scheduleHeartbeat = vi
      .fn()
      .mockResolvedValue(undefined);
    const close = vi.spyOn(client as unknown as CaptureClient, "close").mockResolvedValue(undefined);

    await expect(client.stop(0)).rejects.toThrow("session stop failed: HTTP 409");

    expect(close).toHaveBeenCalledOnce();
  });

  it("reconciles an uncertain final frame before Stop closes local media", async () => {
    const fetchSpy = vi
      .fn()
      .mockRejectedValueOnce(new Error("connection reset"))
      .mockResolvedValueOnce({ ok: true, status: 200 })
      .mockResolvedValueOnce({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();
    (client as unknown as { scheduleHeartbeat: (state: string) => Promise<void> }).scheduleHeartbeat = vi
      .fn()
      .mockResolvedValue(undefined);
    const close = vi.spyOn(client as unknown as CaptureClient, "close").mockResolvedValue(undefined);

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));
    expect(lane.frameQueue).toHaveLength(1);

    await client.stop(1);

    const frameBodies = fetchSpy.mock.calls.slice(0, 2).map(([, request]) =>
      JSON.parse((request as RequestInit).body as string),
    );
    expect(frameBodies).toMatchObject([{ sequence: 0 }, { sequence: 0 }]);
    expect(lane.frameQueue).toHaveLength(0);
    expect(close).toHaveBeenCalledOnce();
  });

  it("aborts a hanging final frame, attempts Stop, and closes local media", async () => {
    let frameSignal: AbortSignal | null = null;
    const fetchSpy = vi.fn((url: string, request: RequestInit) => {
      if (url.endsWith("/frames")) {
        frameSignal = request.signal as AbortSignal;
        return new Promise((_resolve, reject) => {
          frameSignal?.addEventListener("abort", () => reject(frameSignal?.reason), { once: true });
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = activeFrameClient();
    (client as unknown as { scheduleHeartbeat: (state: string) => Promise<void> }).scheduleHeartbeat = vi
      .fn()
      .mockResolvedValue(undefined);
    const close = vi.spyOn(client as unknown as CaptureClient, "close").mockResolvedValue(undefined);

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(frameSignal).not.toBeNull());

    await expect(client.stop(0.01)).rejects.toThrow("capture frame delivery deadline expired");

    expect((frameSignal as unknown as AbortSignal).aborted).toBe(true);
    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toContain(
      "/api/live/sessions/session/stop",
    );
    expect(close).toHaveBeenCalledOnce();
  });

  it("aborts a pre-existing hanging heartbeat before the final heartbeat and Stop", async () => {
    let firstHeartbeatSignal: AbortSignal | null = null;
    let heartbeatCalls = 0;
    const fetchSpy = vi.fn((url: string, request: RequestInit) => {
      if (url.endsWith("/heartbeat") && heartbeatCalls++ === 0) {
        firstHeartbeatSignal = request.signal as AbortSignal;
        return new Promise((_resolve, reject) => {
          firstHeartbeatSignal?.addEventListener(
            "abort",
            () => reject(firstHeartbeatSignal?.reason),
            { once: true },
          );
        });
      }
      return Promise.resolve({ ok: true, status: 200 });
    });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ helperVersion: "test" });
    const active = client as unknown as {
      session: { id: string } | null;
      scheduleHeartbeat: (state: string) => Promise<void>;
    };
    active.session = { id: "session" };
    const close = vi.spyOn(client, "close").mockResolvedValue(undefined);

    void active.scheduleHeartbeat("capturing");
    await vi.waitFor(() => expect(firstHeartbeatSignal).not.toBeNull());
    await client.stop(0);

    expect((firstHeartbeatSignal as unknown as AbortSignal).aborted).toBe(true);
    expect(fetchSpy.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/live/sessions/session/heartbeat",
      "/api/live/sessions/session/heartbeat",
      "/api/live/sessions/session/stop",
    ]);
    expect(close).toHaveBeenCalledOnce();
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

  it("closes local tracks and helper state on revoked Account frame 401 without retry", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Sign in required." }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    const onTransportError = vi.fn();
    const { client, lane } = activeFrameClient(onTransportError);
    const context = Object.assign(new EventTarget(), {
      sampleRate: 4,
      close: vi.fn().mockResolvedValue(undefined),
    });
    const track = Object.assign(new EventTarget(), { stop: vi.fn() });
    client.context = context as unknown as AudioContext;
    lane.tracks = [track];

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(context.close).toHaveBeenCalledOnce());

    expect(track.stop).toHaveBeenCalledOnce();
    expect(client.session).toBeNull();
    expect(client.lanes.size).toBe(0);
    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(onTransportError).toHaveBeenCalledWith(
      "frame",
      expect.objectContaining({ message: "frame POST failed: HTTP 401" }),
    );
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

  it("reports the server-authored terminal 409 line instead of a bare HTTP status", async () => {
    const onTransportError = vi.fn();
    const fetchSpy = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({
        detail: "canonical decode failed: OSError: decoder device became unavailable",
        failure: { code: "canonical_decode_failed" },
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient(onTransportError);

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));

    expect(client.session).toBeNull();
    expect(onTransportError).toHaveBeenCalledWith(
      "frame",
      expect.objectContaining({ message: "canonical decode failed: OSError: decoder device became unavailable" }),
    );
  });

  it("keeps Account-cookie capture publishing when Chrome backgrounds the tab", async () => {
    vi.stubGlobal("document", { visibilityState: "hidden" });
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, request] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/live/sessions/session/frames");
    expect(request.headers).toEqual({ "Content-Type": "application/json" });
    expect(lane.sequence).toBe(1);
    expect(client.session).toEqual({ id: "session" });
  });

  it("stops local capture on a frame that can never fit the server queue", async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ failure: { code: "frame_work_exceeds_queue_capacity" } }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, lane } = activeFrameClient();

    client.onWorkletFrame("microphone", workletFrame(0));
    await vi.waitFor(() => expect(lane.postInFlight).toBe(false));

    expect(client.session).toBeNull();
    expect((client as unknown as { lanes: Map<string, unknown> }).lanes.size).toBe(0);
  });

  it("sends a heartbeat scheduled at any microtask offset after the previous one", async () => {
    // Regression: clearing the in-flight flag from a `.finally()` on the returned
    // promise leaves a one-microtask window where the drain loop has stopped but the
    // flag still says it is running. A schedule landing there was silently dropped.
    const dropped: number[] = [];
    for (let turns = 0; turns < 6; turns += 1) {
      const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
      vi.stubGlobal("fetch", fetchSpy);
      const client = new CaptureClient({ helperVersion: "test" });
      const active = client as unknown as {
        session: { id: string } | null;
        scheduleHeartbeat: (state: string) => Promise<void>;
      };
      active.session = { id: "session" };

      void active.scheduleHeartbeat("degraded");
      for (let turn = 0; turn < turns; turn += 1) await Promise.resolve();
      void active.scheduleHeartbeat("capturing");
      await vi.waitFor(() => expect(fetchSpy.mock.calls.length).toBeGreaterThanOrEqual(1));
      await new Promise((resolve) => setTimeout(resolve, 5));

      const states = heartbeatBodies(fetchSpy).map((body) => body.state);
      if (!states.includes("capturing")) dropped.push(turns);
      vi.unstubAllGlobals();
    }
    expect(dropped).toEqual([]);
  });

  it("still posts the final stopped heartbeat when stop() lands in that window", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({ helperVersion: "test" });
    const active = client as unknown as {
      session: { id: string } | null;
      scheduleHeartbeat: (state: string) => Promise<void>;
    };
    active.session = { id: "session" };

    void active.scheduleHeartbeat("capturing");
    await Promise.resolve(); // the exact offset that used to swallow the next schedule
    await client.stop(0);

    const urls = fetchSpy.mock.calls.map(([url]) => String(url));
    expect(urls.at(-1)).toBe("/api/live/sessions/session/stop");
    expect(heartbeatBodies(fetchSpy).map((body) => body.state)).toContain("stopped");
    // Sequence numbers must still be strictly increasing; the server rejects a regression.
    const sequences = heartbeatBodies(fetchSpy).map((body) => body.sequence);
    expect(sequences).toEqual([...sequences].sort((a, b) => a - b));
    expect(new Set(sequences).size).toBe(sequences.length);
  });

  it("reports sustained full-scale audio as a degraded lane, and clears it on recovery", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = await eventLaneClient();

    // Three clipped frames is 1.5 s: a transient, below the measured sustained window.
    deliverSamples(client, "system", fullScale, 3);
    await vi.waitFor(() => expect(client.lanes.get("system")?.clippedFrameRun).toBe(3));
    expect(heartbeatBodies(fetchSpy)).toHaveLength(0);

    // The fourth crosses it.
    deliverSamples(client, "system", fullScale, 1, 3);
    await vi.waitFor(() => expect(heartbeatBodies(fetchSpy)).toHaveLength(1));
    expect(heartbeatBodies(fetchSpy)[0]).toMatchObject({
      state: "degraded",
      lanes: {
        system: { state: "degraded", failure_code: "browser_sustained_clipping" },
        microphone: { state: "capturing", failure_code: null },
      },
    });

    // Recoverable, unlike a failed lane: clean audio clears it.
    deliverSamples(client, "system", clean, 1, 4);
    await vi.waitFor(() => expect(heartbeatBodies(fetchSpy)).toHaveLength(2));
    expect(heartbeatBodies(fetchSpy)[1]).toMatchObject({
      state: "capturing",
      lanes: { system: { state: "capturing", failure_code: null } },
    });
  });

  it("names the silent-microphone remedy only for the microphone lane", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client } = await eventLaneClient();

    // A quiet system lane is the normal state of a meeting nobody is sharing sound into.
    deliverSamples(client, "system", silent, 40);
    await vi.waitFor(() => expect(client.lanes.get("system")?.silentFrameRun).toBe(40));
    expect(heartbeatBodies(fetchSpy)).toHaveLength(0);

    deliverSamples(client, "microphone", silent, 19);
    await vi.waitFor(() => expect(client.lanes.get("microphone")?.silentFrameRun).toBe(19));
    expect(heartbeatBodies(fetchSpy)).toHaveLength(0);

    deliverSamples(client, "microphone", silent, 1, 19);
    await vi.waitFor(() => expect(heartbeatBodies(fetchSpy)).toHaveLength(1));
    expect(heartbeatBodies(fetchSpy)[0]).toMatchObject({
      state: "degraded",
      lanes: {
        microphone: { state: "degraded", failure_code: "browser_microphone_silent" },
        system: { state: "capturing", failure_code: null },
      },
    });

    deliverSamples(client, "microphone", clean, 1, 20);
    await vi.waitFor(() => expect(heartbeatBodies(fetchSpy)).toHaveLength(2));
    expect(heartbeatBodies(fetchSpy)[1].lanes.microphone).toMatchObject({
      state: "capturing",
      failure_code: null,
    });
  });

  it("reports the silent-microphone remedy and refuses a session for a lane that never produced any signal", async () => {
    const onPreflightStatus = vi.fn<(statusLine: string) => void>();
    const client = new CaptureClient({
      helperVersion: "test",
      onPreflightStatus,
    });
    const active = client as unknown as ActiveClient;
    active.context = { sampleRate: 4 } as AudioContext;
    active.descriptor = {
      sampleRate: 4,
      frameSamples: 2,
      preflightStatusLines: { microphoneSilent: silentMicrophoneRemedy },
    };
    active.session = null;
    active.lanes.set("microphone", testLaneState());
    active.lanes.set("system", testLaneState());

    for (let index = 0; index < 20; index += 1) {
      active.onWorkletFrame("microphone", {
        type: "frame",
        lane: "microphone",
        samples: silent(),
        startFrame: index * 2,
      });
    }
    await vi.waitFor(() => expect(onPreflightStatus).toHaveBeenCalledWith(silentMicrophoneRemedy));
    // This lane never produced a single non-silent frame, so the sticky signal gate refuses it --
    // that is the precondition charter section 4 actually states, and it stays enforced.
    await expect(client.createSession()).rejects.toThrow(
      "both capture lanes must have non-zero signal before session creation",
    );
  });

  it("starts a session for a lane that HAS proven signal and then went quiet, while still surfacing the remedy", async () => {
    // Charter section 4's precondition is that both lanes have SHOWN non-zero signal, which is the
    // sticky laneHasSignal gate. Live silence is a health condition, not a precondition: an operator
    // choosing a tab and ticking "share tab audio" is naturally quiet for well over ten seconds, and
    // with echoCancellation on Chrome emits exact zeros in that gap. Blocking there refuses a healthy
    // microphone and nothing transcribes at all.
    const onPreflightStatus = vi.fn<(statusLine: string) => void>();
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "session",
        descriptor: { sample_rate: 4, frame_samples: 2 },
      }),
    });
    vi.stubGlobal("fetch", fetchSpy);
    const client = new CaptureClient({
      helperVersion: "test",
      onPreflightStatus,
    });
    const active = client as unknown as ActiveClient;
    active.context = { sampleRate: 4 } as AudioContext;
    active.descriptor = {
      sampleRate: 4,
      frameSamples: 2,
      preflightStatusLines: { microphoneSilent: silentMicrophoneRemedy },
    };
    active.session = null;
    active.lanes.set("microphone", testLaneState());
    active.lanes.set("system", testLaneState());

    // both lanes prove signal once -- the operator spoke and the tab played
    active.onWorkletFrame("microphone", {
      type: "frame",
      lane: "microphone",
      samples: clean(),
      startFrame: 0,
    });
    active.onWorkletFrame("system", {
      type: "frame",
      lane: "system",
      samples: clean(),
      startFrame: 0,
    });

    // then the operator stops talking while arranging the share
    for (let index = 1; index <= 20; index += 1) {
      active.onWorkletFrame("microphone", {
        type: "frame",
        lane: "microphone",
        samples: silent(),
        startFrame: index * 2,
      });
    }

    // the remedy must still reach the operator ...
    await vi.waitFor(() => expect(onPreflightStatus).toHaveBeenCalledWith(silentMicrophoneRemedy));
    // ... but it must not prevent the meeting from starting
    await expect(client.createSession()).resolves.toMatchObject({ id: "session" });
  });

  it("never reports a metered condition as `failed`, which would seal the lane server-side", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetchSpy);
    const { client, microphone } = await eventLaneClient();

    // Both lanes in their worst metered state at once. If either reported `failed`,
    // LiveHelperFailureCoordinator would call fail_lane on it; if both did, the whole
    // session would be torn down as helper_all_lanes_failed.
    deliverSamples(client, "system", fullScale, 8);
    deliverSamples(client, "microphone", silent, 24);
    await vi.waitFor(() => expect(heartbeatBodies(fetchSpy).length).toBeGreaterThanOrEqual(2));

    const latest = heartbeatBodies(fetchSpy).at(-1)!;
    expect(latest.state).toBe("degraded");
    expect(latest.lanes.system.state).toBe("degraded");
    expect(latest.lanes.microphone.state).toBe("degraded");
    for (const body of heartbeatBodies(fetchSpy)) {
      expect(body.state).not.toBe("failed");
      expect(body.lanes.system.state).not.toBe("failed");
      expect(body.lanes.microphone.state).not.toBe("failed");
    }

    // A really-gone track still latches failed, and outranks the metered reason. Driven
    // by the real event, not by calling the transition.
    microphone.dispatchEvent(new Event("ended"));
    await vi.waitFor(() => expect(heartbeatBodies(fetchSpy).at(-1)!.lanes.microphone.state).toBe("failed"));
    expect(heartbeatBodies(fetchSpy).at(-1)!.lanes.microphone.failure_code).toBe(
      "browser_track_ended",
    );
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
