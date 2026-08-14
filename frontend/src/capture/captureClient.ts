export const V2_FRAME_KEYS = [
  "lane",
  "sequence",
  "capture_timestamp_ns",
  "device_epoch",
  "pcm_base64",
  "sample_count",
  "sample_rate",
  "silent",
  "discontinuity",
] as const;

export type CaptureLane = "microphone" | "system";

export type CaptureDescriptor = Readonly<{
  sampleRate: number;
  frameSamples: number;
}>;

export type V2Frame = {
  lane: CaptureLane;
  sequence: number;
  capture_timestamp_ns: number;
  device_epoch: number;
  pcm_base64: string;
  sample_count: number;
  sample_rate: number;
  silent: boolean;
  discontinuity: boolean;
};

export type CaptureSession = Readonly<{
  id: string;
  viewToken: string;
}>;

type HelperState = "starting" | "capturing" | "degraded" | "recovering" | "failed" | "stopped";

type BrowserFailureCode =
  | "browser_track_ended"
  | "browser_audio_context_suspended";

/**
 * A capture-start failure observed before a server session exists.
 *
 * The caller owns the UI retry action. These facts intentionally do not use
 * the authenticated heartbeat route because there is no session to report to.
 */
export type PreSessionCaptureFailure = Readonly<{
  lane: CaptureLane;
  code:
    | "browser_microphone_permission_denied"
    | "browser_capture_request_rejected"
    | "browser_surface_audio_missing";
}>;

type LaneHealthState = "capturing" | "degraded" | "failed";

export type CaptureClientOptions = Readonly<{
  captureBearer: string;
  helperVersion: string;
  onMeter?: (lane: CaptureLane, rms: number) => void;
  onTransportError?: (route: "frame" | "heartbeat", error: Error) => void;
  onPreSessionFailure?: (failure: PreSessionCaptureFailure) => void;
}>;

type WorkletFrame = Readonly<{
  type: "frame";
  lane: CaptureLane;
  samples: Float32Array;
  startFrame: number;
}>;

type LaneState = {
  source: MediaStreamAudioSourceNode;
  framer: AudioWorkletNode;
  mute: GainNode;
  tracks: MediaStreamTrack[];
  trackEndedListeners: Array<Readonly<{ track: MediaStreamTrack; listener: () => void }>>;
  frameQueue: WorkletFrame[];
  postInFlight: boolean;
  sequence: number;
  deviceEpoch: number;
  discontinuity: boolean;
  discontinuities: number;
  droppedFrames: number;
  health: LaneHealthState;
  failureCode: BrowserFailureCode | null;
};

const SILENCE_RMS = 1e-4;
const LANE_CAPACITY_FAILURE_CODE = "v2_lane_retention_capacity_reached";

type FramePostResult = "accepted" | "retry" | "dropped" | "recreate" | "stopped";

type FrameFailure = Readonly<{
  code: string | null;
  expectedSequence: number | null;
}>;

const DISPLAY_AUDIO_CONSTRAINTS: MediaTrackConstraints & { restrictOwnAudio: boolean } = {
  restrictOwnAudio: false,
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
};

const DISPLAY_MEDIA_OPTIONS: DisplayMediaStreamOptions & {
  systemAudio: "include";
  windowAudio: "system";
  selfBrowserSurface: "include";
  surfaceSwitching: "exclude";
  monitorTypeSurfaces: "include";
} = {
  video: true,
  audio: DISPLAY_AUDIO_CONSTRAINTS,
  systemAudio: "include",
  windowAudio: "system",
  selfBrowserSurface: "include",
  surfaceSwitching: "exclude",
  monitorTypeSurfaces: "include",
};

function positiveInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value) || (value as number) <= 0) {
    throw new Error(`${field} must be a positive integer`);
  }
  return value as number;
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

export function parseCaptureDescriptor(payload: unknown): CaptureDescriptor {
  const descriptor = record(record(payload, "descriptor response").descriptor, "descriptor");
  const bounds = record(descriptor.bounds, "descriptor.bounds");
  const sampleRate = positiveInteger(descriptor.sample_rate, "descriptor.sample_rate");
  const frameSamples = positiveInteger(descriptor.frame_samples, "descriptor.frame_samples");
  const maxFrameSamples = positiveInteger(
    bounds.max_frame_samples,
    "descriptor.bounds.max_frame_samples",
  );
  if (frameSamples > maxFrameSamples) {
    throw new Error("descriptor.frame_samples exceeds descriptor.bounds.max_frame_samples");
  }
  return Object.freeze({ sampleRate, frameSamples });
}

export function pcm16Base64(samples: Float32Array): string {
  const view = new DataView(new ArrayBuffer(samples.length * 2));
  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(index * 2, Math.round(clamped * 32767), true);
  }
  const bytes = new Uint8Array(view.buffer);
  let binary = "";
  for (let index = 0; index < bytes.length; index += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  }
  return btoa(binary);
}

export function rms(samples: Float32Array): number {
  let sum = 0;
  for (const sample of samples) sum += sample * sample;
  return Math.sqrt(sum / samples.length);
}

export function makeV2Frame(
  lane: CaptureLane,
  sequence: number,
  deviceEpoch: number,
  discontinuity: boolean,
  startFrame: number,
  samples: Float32Array,
  descriptor: CaptureDescriptor,
): V2Frame {
  if (samples.length !== descriptor.frameSamples) {
    throw new Error("worklet frame does not match descriptor.frame_samples");
  }
  return {
    lane,
    sequence,
    capture_timestamp_ns: Math.round((startFrame / descriptor.sampleRate) * 1e9),
    device_epoch: deviceEpoch,
    pcm_base64: pcm16Base64(samples),
    sample_count: samples.length,
    sample_rate: descriptor.sampleRate,
    silent: rms(samples) < SILENCE_RMS,
    discontinuity,
  };
}

/**
 * Ask the server to finish a session while its capture authority is still valid.
 *
 * `deadlineSeconds` is deliberately supplied by the caller: drain time is a
 * server-side operational policy, not a browser-capture geometry constant.
 */
export async function stopCaptureSession(
  session: CaptureSession,
  captureBearer: string,
  deadlineSeconds: number,
): Promise<void> {
  if (!Number.isFinite(deadlineSeconds) || deadlineSeconds < 0) {
    throw new Error("stop deadline must be a non-negative finite number");
  }
  const response = await fetch(`/api/live/sessions/${encodeURIComponent(session.id)}/stop`, {
    method: "POST",
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${captureBearer}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ deadline: deadlineSeconds }),
  });
  if (!response.ok) throw new Error(`session stop failed: HTTP ${response.status}`);
}

export class CaptureClient {
  private context: AudioContext | null = null;
  private descriptor: CaptureDescriptor | null = null;
  private preparation: Promise<AudioContext> | null = null;
  private session: CaptureSession | null = null;
  private readonly lanes = new Map<CaptureLane, LaneState>();
  private readonly laneHasSignal = new Set<CaptureLane>();
  private heartbeatPending: HelperState | null = null;
  private heartbeatFlush: Promise<void> | null = null;
  private heartbeatSequence = 0;
  private heartbeatMonotonicNs = 0;
  private heartbeatNextStartFrame = 0;
  private contextSuspended = false;
  private stopping = false;
  private readonly instanceId = `browser-${crypto.randomUUID()}`;
  private readonly onContextStateChange = () => this.handleContextStateChange();

  constructor(private readonly options: CaptureClientOptions) {}

  async prepare(): Promise<AudioContext> {
    if (this.context) return this.context;
    if (!this.preparation) {
      this.preparation = this.prepareContext();
    }
    return this.preparation;
  }

  async startMicrophone(echoCancellation: boolean): Promise<void> {
    if (this.lanes.has("microphone")) throw new Error("microphone lane is already active");
    const context = await this.prepare();
    await context.resume();
    if (context.state !== "running") throw new Error("capture AudioContext did not start");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
    } catch (error) {
      await this.failBeforeSession("microphone", "browser_microphone_permission_denied");
      throw error;
    }
    await this.attachLane("microphone", stream, stream.getTracks());
  }

  // Call this directly from the display button's click handler. It intentionally
  // does not await preparation or any other work before requesting the chooser.
  requestDisplayMedia(): Promise<MediaStream> {
    if (!this.lanes.has("microphone")) throw new Error("start microphone before display capture");
    if (this.context?.state !== "running") throw new Error("capture AudioContext is not running");
    return navigator.mediaDevices.getDisplayMedia(DISPLAY_MEDIA_OPTIONS).catch(async (error) => {
      await this.failBeforeSession("system", "browser_capture_request_rejected");
      throw error;
    });
  }

  async attachDisplayMedia(stream: MediaStream): Promise<void> {
    if (this.lanes.has("system")) throw new Error("system lane is already active");
    const audioTrack = stream.getAudioTracks()[0];
    if (!audioTrack) {
      stream.getTracks().forEach((track) => track.stop());
      await this.failBeforeSession("system", "browser_surface_audio_missing");
      throw new Error("selected display surface supplied no audio track");
    }
    await this.attachLane("system", new MediaStream([audioTrack]), stream.getTracks());
  }

  /**
   * Create a server session after both lanes have proved they carry signal.
   *
   * A terminal frame conflict clears only the delivery state, so callers can
   * invoke this again without rebuilding the browser's capture graph.
   */
  async createSession(): Promise<CaptureSession> {
    if (this.session) return this.session;
    if (!this.laneHasSignal.has("microphone") || !this.laneHasSignal.has("system")) {
      throw new Error("both capture lanes must have non-zero signal before session creation");
    }
    const descriptor = await this.requireDescriptor();
    const response = await fetch("/api/live/sessions", {
      method: "POST",
      cache: "no-store",
      headers: { Authorization: `Bearer ${this.options.captureBearer}` },
    });
    if (!response.ok) throw new Error(`session create failed: HTTP ${response.status}`);
    const payload = record(await response.json(), "session response");
    const id = payload.id;
    const viewToken = payload.view_token;
    if (typeof id !== "string" || !id || typeof viewToken !== "string" || !viewToken) {
      throw new Error("session response is missing credentials");
    }
    const serverDescriptor = record(payload.descriptor, "session descriptor");
    if (
      serverDescriptor.sample_rate !== descriptor.sampleRate ||
      serverDescriptor.frame_samples !== descriptor.frameSamples
    ) {
      throw new Error("session descriptor differs from preflight descriptor");
    }
    this.session = Object.freeze({ id, viewToken });
    return this.session;
  }

  async stop(deadlineSeconds: number): Promise<void> {
    const session = this.session;
    if (!session) {
      await this.close();
      return;
    }
    this.stopping = true;
    await this.scheduleHeartbeat("stopped");
    await stopCaptureSession(session, this.options.captureBearer, deadlineSeconds);
    await this.close();
  }

  async close(): Promise<void> {
    for (const state of this.lanes.values()) {
      state.framer.port.onmessage = null;
      for (const { track, listener } of state.trackEndedListeners) {
        track.removeEventListener("ended", listener);
      }
      state.source.disconnect();
      state.framer.disconnect();
      state.mute.disconnect();
      state.tracks.forEach((track) => track.stop());
    }
    this.lanes.clear();
    this.laneHasSignal.clear();
    this.session = null;
    this.heartbeatPending = null;
    this.contextSuspended = false;
    this.stopping = false;
    const context = this.context;
    this.context = null;
    this.preparation = null;
    this.descriptor = null;
    if (context) {
      context.removeEventListener("statechange", this.onContextStateChange);
      await context.close();
    }
  }

  private async prepareContext(): Promise<AudioContext> {
    try {
      const response = await fetch(
        "/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2",
        { cache: "no-store" },
      );
      if (!response.ok) throw new Error(`descriptor request failed: HTTP ${response.status}`);
      this.descriptor = parseCaptureDescriptor(await response.json());
      const context = new AudioContext({ sampleRate: this.descriptor.sampleRate });
      await context.audioWorklet.addModule("/worklets/lane-framer.js");
      context.addEventListener("statechange", this.onContextStateChange);
      this.context = context;
      return context;
    } catch (error) {
      this.preparation = null;
      throw error;
    }
  }

  private async requireDescriptor(): Promise<CaptureDescriptor> {
    await this.prepare();
    if (!this.descriptor) throw new Error("capture descriptor is unavailable");
    return this.descriptor;
  }

  private async failBeforeSession(
    lane: CaptureLane,
    code: PreSessionCaptureFailure["code"],
  ): Promise<void> {
    try {
      this.options.onPreSessionFailure?.({ lane, code });
    } finally {
      await this.close();
    }
  }

  private async attachLane(
    lane: CaptureLane,
    stream: MediaStream,
    tracks: MediaStreamTrack[],
  ): Promise<void> {
    if (this.lanes.has(lane)) throw new Error(`${lane} lane is already active`);
    const [context, descriptor] = await Promise.all([this.prepare(), this.requireDescriptor()]);
    const source = context.createMediaStreamSource(stream);
    const framer = new AudioWorkletNode(context, "lane-framer", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      processorOptions: { lane, frameSamples: descriptor.frameSamples },
    });
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(framer).connect(mute).connect(context.destination);
    const state: LaneState = {
      source,
      framer,
      mute,
      tracks,
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
    for (const track of tracks) {
      const listener = () => this.markLaneFailed(lane, "browser_track_ended");
      track.addEventListener("ended", listener);
      state.trackEndedListeners.push({ track, listener });
    }
    this.lanes.set(lane, state);
    framer.port.onmessage = (event: MessageEvent<unknown>) => {
      const frame = event.data as Partial<WorkletFrame>;
      if (
        frame.type !== "frame" ||
        frame.lane !== lane ||
        !(frame.samples instanceof Float32Array) ||
        !Number.isInteger(frame.startFrame)
      ) {
        return;
      }
      this.onWorkletFrame(lane, frame as WorkletFrame);
    };
  }

  private onWorkletFrame(lane: CaptureLane, workletFrame: WorkletFrame): void {
    const state = this.lanes.get(lane);
    const descriptor = this.descriptor;
    if (!state || !descriptor) return;

    const level = rms(workletFrame.samples);
    if (level > 0) this.laneHasSignal.add(lane);
    this.options.onMeter?.(lane, level);
    if (!this.session || this.stopping || state.health === "failed") return;

    this.queueHeartbeat(workletFrame);
    state.frameQueue.push(workletFrame);
    if (!state.postInFlight) void this.flushFrameQueue(state);
  }

  private async flushFrameQueue(state: LaneState): Promise<void> {
    state.postInFlight = true;
    try {
      while (state.frameQueue.length > 0 && this.session && state.health !== "failed") {
        const descriptor = this.descriptor;
        if (!descriptor) return;
        const workletFrame = state.frameQueue[0];
        const frame = makeV2Frame(
          workletFrame.lane,
          state.sequence,
          state.deviceEpoch,
          state.discontinuity,
          workletFrame.startFrame,
          workletFrame.samples,
          descriptor,
        );
        const result = await this.postFrame(frame, state);
        if (result === "retry" || result === "recreate" || result === "stopped") return;

        state.frameQueue.shift();
        state.sequence += 1;
        state.discontinuity = false;
        if (result === "dropped") state.droppedFrames += 1;
      }
    } finally {
      state.postInFlight = false;
    }
  }

  private async postFrame(frame: V2Frame, state: LaneState): Promise<FramePostResult> {
    const session = this.session;
    if (!session) return "dropped";
    try {
      const response = await fetch(`/api/live/sessions/${encodeURIComponent(session.id)}/frames`, {
        method: "POST",
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${this.options.captureBearer}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(frame),
      });
      if (response.ok) return "accepted";
      const failure = await this.frameFailure(response);
      if (response.status === 429 && failure.code === LANE_CAPACITY_FAILURE_CODE) {
        return "retry";
      }
      if (
        response.status === 409 &&
        failure.code === "v2_out_of_order_frame" &&
        failure.expectedSequence !== null
      ) {
        state.sequence = failure.expectedSequence;
        return "retry";
      }
      const error = new Error(`frame POST failed: HTTP ${response.status}`);
      if (response.status === 409) {
        this.resetSessionForRecreation();
        this.reportTransportError("frame", error);
        return "recreate";
      }
      if (response.status === 400) {
        this.reportTransportError("frame", error);
        void this.close().catch((closeError) => this.reportTransportError("frame", closeError));
        return "stopped";
      }
      throw error;
    } catch (caught) {
      this.reportTransportError("frame", caught);
      return "dropped";
    }
  }

  private async frameFailure(response: Response): Promise<FrameFailure> {
    try {
      const payload = await response.json();
      if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
        return { code: null, expectedSequence: null };
      }
      const failure = (payload as Record<string, unknown>).failure;
      if (failure === null || typeof failure !== "object" || Array.isArray(failure)) {
        return { code: null, expectedSequence: null };
      }
      const fields = failure as Record<string, unknown>;
      return {
        code: typeof fields.code === "string" ? fields.code : null,
        expectedSequence:
          Number.isInteger(fields.expected_sequence) && (fields.expected_sequence as number) >= 0
            ? (fields.expected_sequence as number)
            : null,
      };
    } catch {
      return { code: null, expectedSequence: null };
    }
  }

  private resetSessionForRecreation(): void {
    this.session = null;
    this.heartbeatPending = null;
    this.heartbeatSequence = 0;
    this.heartbeatMonotonicNs = 0;
    this.heartbeatNextStartFrame = 0;
    for (const state of this.lanes.values()) {
      state.frameQueue.length = 0;
      state.sequence = 0;
    }
  }

  private queueHeartbeat(workletFrame: WorkletFrame): void {
    if (this.stopping) return;
    if (workletFrame.startFrame < this.heartbeatNextStartFrame) return;
    const descriptor = this.descriptor;
    if (!descriptor) return;
    this.heartbeatNextStartFrame = workletFrame.startFrame + descriptor.frameSamples;
    void this.scheduleHeartbeat(this.heartbeatState());
  }

  private scheduleHeartbeat(state: HelperState): Promise<void> {
    if (!this.session || (this.stopping && state !== "stopped")) return Promise.resolve();
    if (this.heartbeatPending !== "stopped") this.heartbeatPending = state;
    if (!this.heartbeatFlush) {
      this.heartbeatFlush = this.flushHeartbeat().finally(() => {
        this.heartbeatFlush = null;
      });
    }
    return this.heartbeatFlush;
  }

  private async flushHeartbeat(): Promise<void> {
    try {
      while (this.heartbeatPending && this.session) {
        const state = this.heartbeatPending;
        this.heartbeatPending = null;
        const session = this.session;
        const sentMonotonicNs = Math.max(
          this.heartbeatMonotonicNs + 1,
          Math.round(performance.now() * 1e6),
        );
        this.heartbeatMonotonicNs = sentMonotonicNs;
        const response = await fetch(
          `/api/live/sessions/${encodeURIComponent(session.id)}/heartbeat`,
          {
            method: "POST",
            cache: "no-store",
            headers: {
              Authorization: `Bearer ${this.options.captureBearer}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              schema: "moss-live-helper-health.v1",
              instance_id: this.instanceId,
              sequence: this.heartbeatSequence,
              sent_monotonic_ns: sentMonotonicNs,
              helper_version: this.options.helperVersion,
              state,
              lanes: {
                system: this.heartbeatLane("system", state),
                microphone: this.heartbeatLane("microphone", state),
              },
            }),
          },
        );
        this.heartbeatSequence += 1;
        if (!response.ok) throw new Error(`heartbeat POST failed: HTTP ${response.status}`);
      }
    } catch (caught) {
      this.reportTransportError("heartbeat", caught);
    }
  }

  private heartbeatState(): HelperState {
    const states = [...this.lanes.values()];
    if (states.length > 0 && states.every((state) => state.health === "failed")) return "failed";
    if (this.contextSuspended || states.some((state) => state.health === "degraded")) {
      return "degraded";
    }
    return "capturing";
  }

  private heartbeatLane(lane: CaptureLane, heartbeatState: HelperState) {
    const state = this.lanes.get(lane);
    if (heartbeatState === "stopped") {
      return {
        state: "stopped",
        device_epoch: state?.deviceEpoch ?? 0,
        dropped_frames: state?.droppedFrames ?? 0,
        discontinuities: state?.discontinuities ?? 0,
        failure_code: null,
      };
    }
    if (this.contextSuspended && state?.health !== "failed") {
      return {
        state: "degraded",
        device_epoch: state?.deviceEpoch ?? 0,
        dropped_frames: state?.droppedFrames ?? 0,
        discontinuities: state?.discontinuities ?? 0,
        failure_code: "browser_audio_context_suspended",
      };
    }
    return {
      state: state?.health ?? "capturing",
      device_epoch: state?.deviceEpoch ?? 0,
      dropped_frames: state?.droppedFrames ?? 0,
      discontinuities: state?.discontinuities ?? 0,
      failure_code: state?.failureCode ?? null,
    };
  }

  private handleContextStateChange(): void {
    const context = this.context;
    if (!context) return;
    const wasSuspended = this.contextSuspended;
    this.contextSuspended = context.state !== "running" && context.state !== "closed";
    if (this.contextSuspended !== wasSuspended) {
      void this.scheduleHeartbeat(this.heartbeatState());
    }
  }

  private markLaneFailed(lane: CaptureLane, failureCode: BrowserFailureCode): void {
    const state = this.lanes.get(lane);
    if (!state || state.health === "failed") return;
    state.health = "failed";
    state.failureCode = failureCode;
    state.frameQueue.length = 0;
    void this.scheduleHeartbeat(this.heartbeatState());
  }

  private reportTransportError(route: "frame" | "heartbeat", caught: unknown): void {
    const error = caught instanceof Error ? caught : new Error(String(caught));
    this.options.onTransportError?.(route, error);
  }
}
