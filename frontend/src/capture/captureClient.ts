/**
 * Browser capture client for the live v2 lane path.
 *
 * ## Mounting it
 *
 * One Start click does all of it (round 5, docs/plan-r5-start-flow.md). `getDisplayMedia()`
 * needs that click's user activation, so it is requested first, with nothing awaited before
 * it; the microphone follows. The server session must not exist until both lanes are
 * attached, so a source that is not recorded -- unticked, or unavailable -- gets a silent
 * lane instead. Neither lane needs sound yet: audio may start after the meeting does.
 *
 *   const client = new CaptureClient({ helperVersion, workletUrl, onMeter, ... });
 *   // ... in the Start click handler, with no await before it (system sound ticked):
 *   const stream = await client.requestDisplayMedia();
 *   await client.attachDisplayMedia(stream);     // false: the surface carried no audio
 *   await client.startMicrophone(deviceId);      // null: no microphone, or permission denied
 *   await client.attachSilentLane(lane);         // for each source that is not recorded
 *   // ... both lanes are attached; `createSession` refuses otherwise:
 *   const session = await client.createSession();
 *   // ... capture now runs on its own, driven by worklet frames. Then:
 *   await client.stop(deadlineSeconds);
 *
 * Nothing is polled. Frames, heartbeats and retries are all driven by AudioWorklet port
 * messages. The sole clock is a one-shot shutdown deadline that cancels stuck network I/O;
 * no recurring capture or retry loop exists.
 *
 * ## What the caller must handle
 *
 * - `onMeter(lane, rms)` fires once per worklet frame per recorded lane, for the level
 *   meters. It gates nothing: a quiet or muted lane still starts a meeting.
 * - `onPreSessionFailure(failure)` fires when a source's track ends before a session
 *   exists, so there is no authenticated heartbeat to carry it. The client has already
 *   torn its capture graph down when this fires; the retry is a new Start click. A
 *   cancelled picker, a surface without audio and an unavailable microphone are results
 *   of the calls above, not failures: the caller decides what still starts.
 * - `onTransportError(route, error)` is advisory. The client has already decided what to
 *   do about the response by the time this fires.
 * - A frame 409 that is not a sequence conflict clears the session and returns the client
 *   to a state where `createSession()` can be called again WITHOUT rebuilding the audio
 *   graph. A 400 is a client bug: the client stops capture locally and does not retry.
 * - `replaceLane(lane, stream, tracks)` advances `device_epoch` for a chosen device
 *   switch; explicit session adoption takes the server-supplied resume epoch.
 * - `onSourceStopped(lane)` fires when a recorded source's track ends during a session
 *   (Chrome's "Stop sharing", an unplugged microphone). The lane is never reported
 *   `failed` -- the server would seal it and could not close the meeting cleanly. It goes
 *   silent on its own framer instead, so the meeting records on and Stop completes.
 *
 * Lane health reaches the operator only through the heartbeat, and the server turns it
 * into one `capture_phase` + one `status_line` on the snapshot route. The caller renders
 * that string; it does not need to know these codes -- except for the pre-session
 * one, which never reaches the server and so has no server-side copy.
 */
import type { EngineSettingsWire } from "../lib/settings";
import { displaySurfaceOf, rememberCaptureSurface, type CaptureSurface } from "../lib/captureSurface";
import { chooseMicrophone, DEFAULT_MICROPHONE_ID } from "./microphoneChoice";

export const V2_FRAME_KEYS = [
  "lane",
  "sequence",
  "capture_timestamp_ns",
  "capture_end_timestamp_ns",
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
  preflightStatusLines: Readonly<{
    microphoneSilent: string;
  }>;
}>;

export type V2Frame = {
  lane: CaptureLane;
  sequence: number;
  capture_timestamp_ns: number;
  capture_end_timestamp_ns: number;
  device_epoch: number;
  pcm_base64: string;
  sample_count: number;
  sample_rate: number;
  silent: boolean;
  discontinuity: boolean;
};

export type CaptureSession = Readonly<{
  id: string;
  instanceId?: string;
}>;

/** The helper states this client reports: it never reports itself or a lane as `failed`. */
type HelperState = "capturing" | "degraded" | "stopped";

/** A recorded source's track ended. It reaches the caller, never the heartbeat. */
type BrowserFailureCode = "browser_track_ended";

/**
 * Non-terminal lane conditions. These ride `state: "degraded"`, never `"failed"`.
 *
 * That distinction is load-bearing rather than cosmetic:
 * `LiveHelperFailureCoordinator.observe` calls `LiveV2Session.fail_lane` for every lane
 * a heartbeat reports as `failed`, which permanently seals it, and a heartbeat whose
 * lanes are all `failed` tears the whole session down. "Your microphone is too loud"
 * must not end a meeting.
 */
type BrowserDegradedCode =
  | "browser_audio_context_suspended"
  | "browser_sustained_clipping"
  | "browser_microphone_silent";

/** Every `browser_*` code this client can put on the wire. */
export type BrowserCaptureCode = BrowserDegradedCode;

/**
 * A source that stopped after it was attached and before a server session exists.
 *
 * The caller owns the UI retry action. This fact intentionally does not use
 * the authenticated heartbeat route because there is no session to report to.
 */
export type PreSessionCaptureFailure = Readonly<{
  lane: CaptureLane;
  code: BrowserFailureCode;
}>;

type LaneHealthState = "capturing" | "degraded";

export type CaptureClientOptions = Readonly<{
  helperVersion: string;
  workletUrl: string;
  onMeter?: (lane: CaptureLane, rms: number) => void;
  onPreflightStatus?: (statusLine: string) => void;
  onTransportError?: (route: "frame" | "heartbeat", error: Error) => void;
  /** Fires once all previously failing frame lanes/heartbeat have succeeded. */
  onTransportRecovered?: () => void;
  onPreSessionFailure?: (failure: PreSessionCaptureFailure) => void;
  /** A recorded source stopped during a session; its lane now sends silence. */
  onSourceStopped?: (lane: CaptureLane) => void;
  onCaptureReplaced?: () => void;
}>;

type WorkletFrame = Readonly<{
  type: "frame";
  lane: CaptureLane;
  samples: Float32Array;
  startFrame: number;
}>;

type QueuedFrame = Readonly<{
  workletFrame: WorkletFrame;
  deviceEpoch: number;
}>;

type LaneState = {
  /** A source that is not recorded has no stream: its lane frames zeros (`attachSilentLane`). */
  silent: boolean;
  source: AudioNode;
  framer: AudioWorkletNode;
  mute: GainNode;
  tracks: MediaStreamTrack[];
  trackEndedListeners: Array<Readonly<{ track: MediaStreamTrack; listener: () => void }>>;
  frameQueue: QueuedFrame[];
  postInFlight: boolean;
  postFlush: Promise<void> | null;
  sequence: number;
  deviceEpoch: number;
  pendingDiscontinuityEpochs: Set<number>;
  discontinuities: number;
  droppedFrames: number;
  health: LaneHealthState;
  degradedCode: BrowserDegradedCode | null;
  clippedFrameRun: number;
  silentFrameRun: number;
};

const SILENCE_RMS = 1e-4;
const LANE_CAPACITY_FAILURE_CODE = "v2_lane_retention_capacity_reached";
const TERMINAL_REQUEST_TIMEOUT_MS = 1_000;
/**
 * A frame or heartbeat POST unanswered this long is abandoned and retried (frames replay the
 * same payload and sequence). A request stuck on a dead connection otherwise never settles:
 * its lane sends nothing more and no heartbeat leaves, so the helper lease interrupts a
 * meeting whose network has already come back.
 */
const CAPTURE_REQUEST_TIMEOUT_MS = 10_000;

function requestDeadline(timeoutMs: number): Readonly<{ signal: AbortSignal; cancel: () => void }> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(
    () => controller.abort(new DOMException("capture request deadline expired", "TimeoutError")),
    timeoutMs,
  );
  return {
    signal: controller.signal,
    cancel: () => globalThis.clearTimeout(timeoutId),
  };
}

/** Release Chrome's network loader before any caller can ignore a response body. */
async function captureFetch(input: string, init: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  if (!response.body) return response;
  const body = await response.arrayBuffer();
  // Keep status and error JSON available without retaining the network-backed stream.
  return new Response(body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
  });
}

/**
 * Capture-health thresholds. Measured, not chosen -- re-run
 * the retained capture-health threshold measurement,
 * which frames the tree's real 16 kHz meeting audio at the production descriptor
 * geometry and fails if these numbers stop separating the corpora.
 *
 * At native gain that corpus produces ZERO full-scale samples across 238 frames; gained
 * until the encoder pins, it produces runs of 19-50 clipped frames. Real speech pauses
 * run at most 3 frames below the silence floor, while a lane that genuinely delivers
 * nothing runs 120+.
 */
/** A sample is clipped only if `pcm16Base64` will encode it to exactly +/-32767. */
const CLIPPED_SAMPLE_MAGNITUDE = 32766.5 / 32767;
/** Share of a frame's samples at full scale before the frame counts as clipped. */
const CLIPPED_FRAME_FRACTION = 0.01;
/** Consecutive clipped frames that make it "sustained" (4 x 500 ms = 2 s). */
const SUSTAINED_CLIPPING_FRAMES = 4;
/** Consecutive silent microphone frames before naming the Chrome input remedy (10 s). */
const SILENT_MICROPHONE_FRAMES = 20;

type FramePostResult =
  | "accepted"
  | "retry"
  | "dropped"
  | "recreate"
  | "stopped";

type FrameFailure = Readonly<{
  code: string | null;
  detail: string | null;
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

function nonEmptyString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

function record(value: unknown, field: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

/**
 * The one microphone request, for the first acquisition and for every device switch: echo
 * cancellation is always on (round 5, Q17: no listening-route question; its cost to a voice heard
 * through headphones is unmeasured); the browser's noise suppression and gain control stay off.
 * It always names its device exactly: left to choose, Chrome follows its own device ranking and
 * wakes a nearby iPhone (issue #2).
 */
export function microphoneConstraints(deviceId: string, echoCancellation = true): MediaStreamConstraints {
  return {
    audio: {
      echoCancellation,
      noiseSuppression: false,
      autoGainControl: false,
      deviceId: { exact: deviceId },
    },
    video: false,
  };
}

/** Zeros on the context's own clock: the source of a lane that is not recorded. */
function zeroSource(context: AudioContext): ConstantSourceNode {
  const zeros = context.createConstantSource();
  zeros.offset.value = 0;
  zeros.start();
  return zeros;
}

export function parseCaptureDescriptor(payload: unknown): CaptureDescriptor {
  const response = record(payload, "descriptor response");
  const descriptor = record(response.descriptor, "descriptor");
  const bounds = record(descriptor.bounds, "descriptor.bounds");
  const preflightStatusLines = record(
    response.preflight_status_lines,
    "preflight_status_lines",
  );
  const sampleRate = positiveInteger(descriptor.sample_rate, "descriptor.sample_rate");
  const frameSamples = positiveInteger(descriptor.frame_samples, "descriptor.frame_samples");
  const maxFrameSamples = positiveInteger(
    bounds.max_frame_samples,
    "descriptor.bounds.max_frame_samples",
  );
  if (frameSamples > maxFrameSamples) {
    throw new Error("descriptor.frame_samples exceeds descriptor.bounds.max_frame_samples");
  }
  return Object.freeze({
    sampleRate,
    frameSamples,
    preflightStatusLines: Object.freeze({
      microphoneSilent: nonEmptyString(
        preflightStatusLines.browser_microphone_silent,
        "preflight_status_lines.browser_microphone_silent",
      ),
    }),
  });
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

/**
 * Share of a frame that will reach the server pinned at full scale.
 *
 * Measured on the encoded value rather than on some float headroom figure, because
 * full-scale PCM is exactly what the attended run observed on the loopback lane
 * (`docs/research-chrome-capture-mvp-2026-08-03.md`).
 */
export function clippedFraction(samples: Float32Array): number {
  let clipped = 0;
  for (const sample of samples) {
    if (Math.abs(sample) >= CLIPPED_SAMPLE_MAGNITUDE) clipped += 1;
  }
  return clipped / samples.length;
}

export function makeV2Frame(
  lane: CaptureLane,
  sequence: number,
  deviceEpoch: number,
  discontinuity: boolean,
  startFrame: number,
  samples: Float32Array,
  descriptor: CaptureDescriptor,
  captureSampleRate: number,
): V2Frame {
  if (samples.length !== descriptor.frameSamples) {
    throw new Error("worklet frame does not match descriptor.frame_samples");
  }
  positiveInteger(captureSampleRate, "AudioContext.sampleRate");
  return {
    lane,
    sequence,
    capture_timestamp_ns: Math.round((startFrame / captureSampleRate) * 1e9),
    capture_end_timestamp_ns: Math.round(((startFrame + samples.length) / captureSampleRate) * 1e9),
    device_epoch: deviceEpoch,
    pcm_base64: pcm16Base64(samples),
    sample_count: samples.length,
    sample_rate: captureSampleRate,
    silent: rms(samples) < SILENCE_RMS,
    discontinuity,
  };
}

/**
 * Ask the server to finish a session while its capture authority is still valid.
 *
 * `deadlineSeconds` is deliberately supplied by the caller: drain time is a
 * bounded wait for server completion, not a deadline that cancels server work.
 */
export async function stopCaptureSession(
  session: CaptureSession,
  deadlineSeconds: number,
  signal?: AbortSignal,
): Promise<void> {
  if (!Number.isFinite(deadlineSeconds) || deadlineSeconds < 0) {
    throw new Error("stop deadline must be a non-negative finite number");
  }
  const request: RequestInit = {
    method: "POST",
    cache: "no-store",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(session.instanceId ? { "X-Moss-Capture-Instance": session.instanceId } : {}) },
    body: JSON.stringify({ deadline: deadlineSeconds }),
  };
  if (signal) request.signal = signal;
  const response = await captureFetch(`/api/live/sessions/${encodeURIComponent(session.id)}/stop`, request);
  if (response.status === 202) {
    const pending = await response.json();
    if (pending?.code !== "stop_in_progress" || pending?.retryable !== true) {
      throw new Error("session stop returned an invalid pending response");
    }
    // Capture closes locally; the existing session poller waits for finalization.
    return;
  }
  if (!response.ok) throw await captureResponseError(response, "session stop");
}

export class CaptureResponseError extends Error {
  constructor(readonly code: string | null, message: string) { super(message); }
}

async function captureResponseError(response: Response, route: string): Promise<CaptureResponseError> {
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail ?? payload;
  return new CaptureResponseError(payload?.code ?? detail?.code ?? payload?.failure?.code ?? null,
    typeof detail === "string" ? detail : `${route} failed: HTTP ${response.status}`);
}

export async function abortCaptureSession(session: CaptureSession, reason: string): Promise<void> {
  const response = await captureFetch(`/api/live/sessions/${encodeURIComponent(session.id)}/abort`, {
    method: "POST", cache: "no-store", credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(session.instanceId ? { "X-Moss-Capture-Instance": session.instanceId } : {}) },
    body: JSON.stringify({ reason }),
  });
  if (!response.ok) throw await captureResponseError(response, "session abort");
}

export class CaptureClient {
  private context: AudioContext | null = null;
  private descriptor: CaptureDescriptor | null = null;
  private preparation: Promise<AudioContext> | null = null;
  private session: CaptureSession | null = null;
  // Chrome's share choice for the system lane; stored per meeting for row source labels (J5).
  private displaySurface: CaptureSurface | null = null;
  private readonly lanes = new Map<CaptureLane, LaneState>();
  private failedTransports = new Set<CaptureLane | "heartbeat">();
  private heartbeatPending: HelperState | null = null;
  private heartbeatFlush: Promise<void> | null = null;
  private heartbeatFlushing = false;
  private heartbeatSequence = 0;
  private heartbeatMonotonicNs = 0;
  private heartbeatNextStartFrame = 0;
  private contextSuspended = false;
  private stopping = false;
  private microphoneMuted = false;
  private captureOffsetNs = 0;
  private replaced = false;
  get captureInstanceId(): string { return this.instanceId; }
  get captureShareKind(): string | null { return this.displaySurface; }
  private frameDeadlineSignal: AbortSignal | null = null;
  private readonly requestControllers = new Set<AbortController>();
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

  /**
   * Open the microphone lane on `deviceId` and resolve with the device id it opened, or with
   * null when no microphone can be opened (none present, or permission denied). Nothing else is
   * torn down then: the caller records the other source and gives this lane silence.
   *
   * With no `deviceId` the caller could not name one because Chrome still hides the devices.
   * Opening Chrome's default alias once grants the permission that reveals them; the lane then
   * opens the device `chooseMicrophone` names, so an iPhone default is skipped from the start.
   */
  async startMicrophone(deviceId?: string, echoCancellation = true): Promise<string | null> {
    if (this.lanes.has("microphone")) throw new Error("microphone lane is already active");
    let stream: MediaStream;
    let opened = deviceId;
    try {
      if (!opened) {
        const permission = await navigator.mediaDevices.getUserMedia(microphoneConstraints(DEFAULT_MICROPHONE_ID));
        permission.getTracks().forEach(track => track.stop());
        opened = chooseMicrophone(await navigator.mediaDevices.enumerateDevices()) ?? DEFAULT_MICROPHONE_ID;
      }
      stream = await navigator.mediaDevices.getUserMedia(microphoneConstraints(opened, echoCancellation));
    } catch {
      return null;
    }
    await this.attachLane("microphone", stream, stream.getTracks());
    return stream.getTracks().find(track => track.kind === "audio")?.getSettings().deviceId || opened;
  }

  /**
   * Give a source that is not recorded its lane. The server needs both lanes attached; this one
   * is fed zeros by a constant source through the same framer on the same AudioContext clock,
   * so its frames, sequence numbers and timestamps run exactly like a recorded lane's (measured:
   * docs/design-capture-setup.md, Silent lane). It opens no device, has no track to end, and is
   * never metered: its silence is intended, so it raises no `browser_microphone_silent` (K1).
   */
  async attachSilentLane(lane: CaptureLane): Promise<void> {
    await this.prepare();
    await this.attachLane(lane, null, []);
  }

  /**
   * Mute or unmute the microphone lane without stopping it.
   *
   * The worklet keeps framing every input sample and zeroes them while muted, so frames,
   * sequence numbers, timestamps and `device_epoch` continue unchanged and the server accounts
   * the muted time as silence; nothing is restarted. A replacement microphone inherits the
   * state. Muted silence is intentional, so it never raises `browser_microphone_silent` (K1).
   */
  setMicrophoneMuted(muted: boolean): void {
    this.microphoneMuted = muted;
    this.lanes.get("microphone")?.framer.port.postMessage({ type: "mute", muted });
  }

  // Call this directly from the click handler, before anything is awaited: Chrome's chooser
  // needs the click's user activation. It needs no AudioContext and no other lane. A rejection
  // (the chooser was closed) tears nothing down; the caller decides what it means.
  requestDisplayMedia(): Promise<MediaStream> {
    // Keep the capture tab active after the chooser. On macOS, moving native
    // focus to the shared tab can make the next chooser reject as backgrounded
    // even when document.hasFocus() is true. Controllers are single-request objects.
    type FocusController = { setFocusBehavior(behavior: "focus-capturing-application"): void };
    const Controller = (globalThis as typeof globalThis & {
      CaptureController?: { new(): FocusController; prototype: FocusController };
    }).CaptureController;
    const options: DisplayMediaStreamOptions & { controller?: FocusController } = { ...DISPLAY_MEDIA_OPTIONS };
    if (typeof Controller?.prototype.setFocusBehavior === "function") {
      options.controller = new Controller();
      options.controller.setFocusBehavior("focus-capturing-application");
    }
    return navigator.mediaDevices.getDisplayMedia(options);
  }

  /**
   * Attach the shared surface as the system lane. Resolves false, with the surface's tracks
   * stopped and nothing else torn down, when it was shared without audio.
   */
  async attachDisplayMedia(stream: MediaStream): Promise<boolean> {
    if (this.lanes.has("system")) throw new Error("system lane is already active");
    const audioTrack = stream.getAudioTracks()[0];
    // An ended track (sharing stopped before the lane existed) would frame silence as a recorded source.
    if (!audioTrack || audioTrack.readyState === "ended") {
      stream.getTracks().forEach((track) => track.stop());
      return false;
    }
    await this.runningContext();
    await this.attachLane("system", new MediaStream([audioTrack]), stream.getTracks());
    this.displaySurface = displaySurfaceOf(stream);
    return true;
  }

  /**
   * Swap a lane's source for a caller-acquired replacement stream.
   *
   * The caller must acquire browser media through its required user gesture.
   * Queued frames keep their source epoch; the first replacement frame carries
   * the incremented epoch and an explicit discontinuity.
   */
  async replaceLane(
    lane: CaptureLane,
    stream: MediaStream,
    tracks: MediaStreamTrack[],
  ): Promise<void> {
    const state = this.lanes.get(lane);
    if (!state) {
      // Own the caller's freshly acquired tracks here too, or a refused switch keeps the device open.
      tracks.forEach(track => track.stop());
      throw new Error(`${lane} lane is not active`);
    }
    const { source, framer, mute } = await this.createLaneGraph(lane, stream, tracks);

    this.detachLaneResources(state);
    state.silent = false;
    state.source = source;
    state.framer = framer;
    state.mute = mute;
    state.tracks = tracks;
    state.trackEndedListeners = [];
    state.deviceEpoch += 1;
    state.pendingDiscontinuityEpochs.add(state.deviceEpoch);
    state.discontinuities += 1;
    state.health = "capturing";
    // A new source starts with a clean health history; the old device's clipping or
    // silence says nothing about this one.
    state.degradedCode = null;
    state.clippedFrameRun = 0;
    state.silentFrameRun = 0;
    this.observeLaneTracks(lane, state);
    this.observeLaneFrames(lane, state);
    if (lane === "system") {
      this.displaySurface = displaySurfaceOf(stream);
      if (this.session) rememberCaptureSurface(this.session.id, this.displaySurface);
    }
  }

  /**
   * Create a server session once both lanes are attached.
   *
   * A terminal frame conflict clears only the delivery state, so callers can
   * invoke this again without rebuilding the browser's capture graph.
   */
  async createSession(engineSettings?: EngineSettingsWire): Promise<CaptureSession> {
    if (this.replaced) throw new Error("capture replaced; view meeting");
    if (this.session) return this.session;
    // Start needs both lanes attached, not sound on either (user decision, round 4): the person
    // may start recording first and play the audio afterwards. A source that is not recorded has
    // a silent lane (round 5). A recorded lane exists only while its track is live -- an ended
    // track tears the capture down before this point (browser_track_ended). Silence stays a
    // health condition (K1), never a precondition.
    if (!this.lanes.has("microphone") || !this.lanes.has("system")) {
      throw new Error("both capture lanes must be attached before session creation");
    }
    const descriptor = await this.requireDescriptor();
    const response = await captureFetch("/api/live/sessions", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      ...(engineSettings ? { headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ engine_settings: engineSettings }) } : {}),
    });
    if (!response.ok) {
      const failure = response.status === 409 || response.status === 400
        ? await response.json().catch(() => null)
        : null;
      const detail = failure !== null && typeof failure === "object" && !Array.isArray(failure)
        ? (failure as Record<string, unknown>).detail ?? failure
        : null;
      const code = detail !== null && typeof detail === "object" && !Array.isArray(detail)
        ? (detail as Record<string, unknown>).code
        : null;
      if (code === "live_capacity_full") {
        throw new Error(
          "Two meetings are already recording — stop one first.",
        );
      }
      // I-2: a missing Gemini key is typed; other invalid engine settings carry a human detail.
      if (code === "api_key_required") throw new Error("Enter your Gemini API key in Settings.");
      if (response.status === 400 && typeof detail === "string" && detail) throw new Error(detail);
      throw new Error(`session create failed: HTTP ${response.status}`);
    }
    const payload = record(await response.json(), "session response");
    const id = payload.id;
    if (typeof id !== "string" || !id) {
      throw new Error("session response is missing its Meeting ID");
    }
    const serverDescriptor = record(payload.descriptor, "session descriptor");
    if (
      serverDescriptor.sample_rate !== descriptor.sampleRate ||
      serverDescriptor.frame_samples !== descriptor.frameSamples
    ) {
      throw new Error("session descriptor differs from preflight descriptor");
    }
    this.session = Object.freeze({ id });
    rememberCaptureSurface(id, this.displaySurface);
    // Establish the server-owned loss detector before returning control to the page. A reload or
    // close may happen before the next worklet frame; without this initial heartbeat no lease
    // exists to interrupt the now-orphaned Meeting.
    await this.scheduleHeartbeat("capturing");
    return this.session;
  }

  /** Adopt server cursors before any frame or heartbeat is allowed to leave. */
  async resumeSession(id: string, expectedInstanceId: string | null, automatic: boolean): Promise<CaptureSession> {
    if (this.replaced) throw new Error("capture replaced; view meeting");
    if (!this.lanes.has("microphone") || !this.lanes.has("system")) throw new Error("both capture lanes must be attached before resume");
    const path = `/api/live/sessions/${encodeURIComponent(id)}/resume`;
    const request: RequestInit = {
      method: "POST", cache: "no-store", credentials: "same-origin", headers: this.requestHeaders(true),
      body: JSON.stringify({ expected_instance_id: expectedInstanceId, instance_id: this.instanceId, automatic }),
    };
    let response: Response;
    try { response = await this.fetchRequest(path, request); }
    catch (error) {
      if (!this.context || !(error instanceof TypeError || (error instanceof DOMException && error.name === "TimeoutError"))) throw error;
      // The measured lost-response protocol repeats the same old->new pair, never a new writer.
      response = await this.fetchRequest(path, request);
    }
    if (!response.ok) throw await captureResponseError(response, "session resume");
    const state = await response.json();
    const descriptor = await this.requireDescriptor();
    if (state.descriptor.sample_rate !== descriptor.sampleRate || state.descriptor.frame_samples !== descriptor.frameSamples)
      throw new Error("resume descriptor differs from preflight descriptor");
    // Receipt anchors the new context; all subsequent start AND end times share this offset.
    this.captureOffsetNs = state.capture_now_ns - Math.round(this.context!.currentTime * 1e9);
    this.heartbeatSequence = state.heartbeat_next_sequence;
    this.heartbeatMonotonicNs = state.heartbeat_next_monotonic_ns - 1;
    for (const [lane, value] of this.lanes) {
      value.sequence = state.lanes[lane].next_sequence;
      value.deviceEpoch = state.lanes[lane].resume_device_epoch;
      value.pendingDiscontinuityEpochs.add(value.deviceEpoch);
      value.frameQueue = [];
    }
    this.session = Object.freeze({ id });
    await this.scheduleHeartbeat(this.heartbeatState());
    return this.session!;
  }

  private async captureReplaced(): Promise<void> {
    if (this.replaced) return;
    this.replaced = true;
    await this.close();
    this.options.onCaptureReplaced?.();
  }

  async abort(reason: string): Promise<void> {
    const session = this.session;
    try {
      if (session) await abortCaptureSession({ ...session, instanceId: this.instanceId }, reason);
    } catch (error) {
      if (error instanceof CaptureResponseError && error.code === "capture_replaced") await this.captureReplaced();
      throw error;
    } finally { await this.close(); }
  }

  async stop(deadlineSeconds: number): Promise<void> {
    if (!Number.isFinite(deadlineSeconds) || deadlineSeconds < 0) {
      throw new Error("stop deadline must be a non-negative finite number");
    }
    const session = this.session;
    if (!session) {
      await this.close();
      return;
    }
    this.stopping = true;
    let deliveryFailure: unknown = null;
    let remainingDeadline = deadlineSeconds;
    const drainDeadline = requestDeadline(Math.max(1, Math.ceil(deadlineSeconds * 1_000)));
    const drainSignal = drainDeadline.signal;
    const abortDrainRequests = () => this.abortRequests(drainSignal.reason);
    drainSignal.addEventListener("abort", abortDrainRequests, { once: true });
    this.frameDeadlineSignal = drainSignal;
    try {
      try {
        remainingDeadline = await this.drainFrameQueues(deadlineSeconds);
      } catch (error) {
        deliveryFailure = error;
        remainingDeadline = 0;
      }
      this.frameDeadlineSignal = null;
      drainSignal.removeEventListener("abort", abortDrainRequests);
      drainDeadline.cancel();
      this.abortRequests(new DOMException("capture stopping", "AbortError"));
      if (this.heartbeatFlush) await this.heartbeatFlush;
      const heartbeatDeadline = requestDeadline(TERMINAL_REQUEST_TIMEOUT_MS);
      try {
        await this.scheduleHeartbeat("stopped", heartbeatDeadline.signal);
      } finally {
        heartbeatDeadline.cancel();
      }
      const stopDeadline = requestDeadline(Math.ceil(remainingDeadline * 1_000) + TERMINAL_REQUEST_TIMEOUT_MS);
      try {
        await stopCaptureSession(
          { ...session, instanceId: this.instanceId },
          remainingDeadline,
          stopDeadline.signal,
        );
      } finally {
        stopDeadline.cancel();
      }
      if (deliveryFailure) throw deliveryFailure;
    } catch (error) {
      if (error instanceof CaptureResponseError && error.code === "capture_replaced") await this.captureReplaced();
      throw error;
    } finally {
      this.frameDeadlineSignal = null;
      drainSignal.removeEventListener("abort", abortDrainRequests);
      drainDeadline.cancel();
      await this.close();
    }
  }

  async close(): Promise<void> {
    this.abortRequests(new DOMException("capture closed", "AbortError"));
    for (const state of this.lanes.values()) {
      this.detachLaneResources(state);
    }
    this.lanes.clear();
    this.failedTransports.clear();
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
      const response = await captureFetch(
        "/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2",
        { cache: "no-store", credentials: "same-origin" },
      );
      if (!response.ok) throw new Error(`descriptor request failed: HTTP ${response.status}`);
      this.descriptor = parseCaptureDescriptor(await response.json());
      const context = new AudioContext({ sampleRate: this.descriptor.sampleRate });
      await context.audioWorklet.addModule(this.options.workletUrl);
      context.addEventListener("statechange", this.onContextStateChange);
      this.context = context;
      this.contextSuspended = context.state === "suspended";
      return context;
    } catch (error) {
      this.preparation = null;
      throw error;
    }
  }

  private async runningContext(): Promise<AudioContext> {
    const context = await this.prepare();
    await context.resume();
    if (context.state !== "running") throw new Error("capture AudioContext did not start");
    return context;
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

  // Own acquired tracks immediately: attachment can fail before a LaneState exists.
  // With no stream the lane is silent: a constant source of zeros drives the same framer.
  private async createLaneGraph(
    lane: CaptureLane,
    stream: MediaStream | null,
    tracks: MediaStreamTrack[],
  ): Promise<{ source: AudioNode; framer: AudioWorkletNode; mute: GainNode }> {
    let source: AudioNode | undefined;
    let framer: AudioWorkletNode | undefined;
    let mute: GainNode | undefined;
    try {
      const [context, descriptor] = await Promise.all([this.prepare(), this.requireDescriptor()]);
      // Chrome permits gestureless AudioContext playback once microphone capture is active.
      if (stream && context.state === "suspended") await this.runningContext();
      source = stream ? context.createMediaStreamSource(stream) : zeroSource(context);
      framer = new AudioWorkletNode(context, "lane-framer", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        processorOptions: {
          lane,
          frameSamples: descriptor.frameSamples,
          muted: lane === "microphone" && this.microphoneMuted,
        },
      });
      mute = context.createGain();
      mute.gain.value = 0;
      source.connect(framer).connect(mute).connect(context.destination);
      return { source, framer, mute };
    } catch (error) {
      source?.disconnect();
      framer?.disconnect();
      mute?.disconnect();
      tracks.forEach(track => track.stop());
      throw error;
    }
  }

  private async attachLane(
    lane: CaptureLane,
    stream: MediaStream | null,
    tracks: MediaStreamTrack[],
  ): Promise<void> {
    if (this.lanes.has(lane)) throw new Error(`${lane} lane is already active`);
    const { source, framer, mute } = await this.createLaneGraph(lane, stream, tracks);
    const state: LaneState = {
      silent: stream === null,
      source,
      framer,
      mute,
      tracks,
      trackEndedListeners: [],
      frameQueue: [],
      postInFlight: false,
      postFlush: null,
      sequence: 0,
      deviceEpoch: 1,
      pendingDiscontinuityEpochs: new Set(),
      discontinuities: 0,
      droppedFrames: 0,
      health: "capturing",
      degradedCode: null,
      clippedFrameRun: 0,
      silentFrameRun: 0,
    };
    this.observeLaneTracks(lane, state);
    this.lanes.set(lane, state);
    this.observeLaneFrames(lane, state);
  }

  private detachLaneResources(state: LaneState): void {
    state.framer.port.onmessage = null;
    for (const { track, listener } of state.trackEndedListeners) {
      track.removeEventListener("ended", listener);
    }
    state.source.disconnect();
    state.framer.disconnect();
    state.mute.disconnect();
    state.tracks.forEach((track) => track.stop());
  }

  private observeLaneTracks(lane: CaptureLane, state: LaneState): void {
    for (const track of state.tracks) {
      const listener = () => this.sourceEnded(lane);
      track.addEventListener("ended", listener);
      state.trackEndedListeners.push({ track, listener });
    }
  }

  private observeLaneFrames(lane: CaptureLane, state: LaneState): void {
    state.framer.port.onmessage = (event: MessageEvent<unknown>) => {
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

    if (!state.silent) {
      const level = rms(workletFrame.samples);
      this.options.onMeter?.(lane, level);
      // Health is metered before the delivery gate so a lane that is clipping or dead
      // during preflight is already in that state when the first heartbeat goes out.
      this.meterLaneHealth(lane, state, level, workletFrame.samples);
    }
    if (!this.session || this.stopping) return;

    this.queueHeartbeat(workletFrame);
    state.frameQueue.push({ workletFrame, deviceEpoch: state.deviceEpoch });
    if (!state.postInFlight) state.postFlush = this.flushFrameQueue(state);
  }

  private async flushFrameQueue(state: LaneState): Promise<void> {
    state.postInFlight = true;
    try {
      while (state.frameQueue.length > 0 && this.session) {
        const descriptor = this.descriptor;
        const context = this.context;
        if (!descriptor || !context) return;
        const queuedFrame = state.frameQueue[0];
        const { workletFrame, deviceEpoch } = queuedFrame;
        const discontinuity = state.pendingDiscontinuityEpochs.has(deviceEpoch);
        const frame = makeV2Frame(
          workletFrame.lane,
          state.sequence,
          deviceEpoch,
          discontinuity,
          workletFrame.startFrame,
          workletFrame.samples,
          descriptor,
          context.sampleRate,
        );
        frame.capture_timestamp_ns += this.captureOffsetNs;
        frame.capture_end_timestamp_ns += this.captureOffsetNs;
        const result = await this.postFrame(frame, state);
        if (result === "retry" || result === "recreate" || result === "stopped") return;

        state.frameQueue.shift();
        state.sequence += 1;
        if (discontinuity) state.pendingDiscontinuityEpochs.delete(deviceEpoch);
        if (result === "dropped") state.droppedFrames += 1;
      }
    } finally {
      state.postInFlight = false;
      state.postFlush = null;
    }
  }

  private async postFrame(frame: V2Frame, state: LaneState): Promise<FramePostResult> {
    const session = this.session;
    if (!session) return "dropped";
    let response: Response;
    try {
      response = await this.fetchRequest(`/api/live/sessions/${encodeURIComponent(session.id)}/frames`, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: this.requestHeaders(true),
        body: JSON.stringify(frame),
      }, this.frameDeadlineSignal ?? undefined);
    } catch (caught) {
      this.reportTransportError("frame", caught, frame.lane);
      // No response means the server may have admitted the frame. Retain the exact
      // payload and sequence so its idempotent replay contract resolves ambiguity.
      return "retry";
    }
    if (response.ok) {
      this.transportRecovered(frame.lane);
      return "accepted";
    }
    const failure = await this.frameFailure(response);
    if (response.status === 409 && failure.code === "capture_replaced") {
      await this.captureReplaced();
      return "stopped";
    }
    if (response.status === 429 && failure.code === LANE_CAPACITY_FAILURE_CODE) return "retry";
    if (response.status === 429) return "dropped";
    if (response.status === 409 && failure.code === "frame_work_exceeds_queue_capacity") {
      const error = new Error("capture frame exceeds server queue capacity");
      this.reportTransportError("frame", error, frame.lane);
      try {
        await this.close();
      } catch (closeError) {
        this.reportTransportError("frame", closeError, frame.lane);
      }
      return "stopped";
    }
    if (
      response.status === 409 &&
      failure.code === "v2_out_of_order_frame" &&
      failure.expectedSequence !== null
    ) {
      state.sequence = failure.expectedSequence;
      return "retry";
    }
    const error = new Error(
      response.status === 409 && failure.detail !== null
        ? failure.detail
        : `frame POST failed: HTTP ${response.status}`,
    );
    if (response.status === 409) {
      this.resetSessionForRecreation();
      this.reportTransportError("frame", error, frame.lane);
      return "recreate";
    }
    if (response.status >= 500) {
      this.reportTransportError("frame", error, frame.lane);
      return "retry";
    }
    this.reportTransportError("frame", error, frame.lane);
    try {
      await this.close();
    } catch (closeError) {
      this.reportTransportError("frame", closeError, frame.lane);
    }
    return "stopped";
  }

  private async drainFrameQueues(deadlineSeconds: number): Promise<number> {
    const deadlineMs = Date.now() + deadlineSeconds * 1000;
    while ([...this.lanes.values()].some((state) => state.frameQueue.length > 0 || state.postInFlight)) {
      const inFlight = [...this.lanes.values()].flatMap((state) =>
        state.postFlush ? [state.postFlush] : [],
      );
      if (inFlight.length > 0) await Promise.allSettled(inFlight);
      for (const state of this.lanes.values()) {
        if (!state.postInFlight && state.frameQueue.length > 0) {
          state.postFlush = this.flushFrameQueue(state);
          await state.postFlush;
        }
      }
      if (![...this.lanes.values()].some((state) => state.frameQueue.length > 0 || state.postInFlight)) break;
      if (Date.now() >= deadlineMs) throw new Error("capture frame delivery deadline expired");
    }
    return Math.max(0, (deadlineMs - Date.now()) / 1000);
  }

  private async frameFailure(response: Response): Promise<FrameFailure> {
    try {
      const payload = await response.json();
      if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
        return { code: null, detail: null, expectedSequence: null };
      }
      const responsePayload = payload as Record<string, unknown>;
      const responseDetail = responsePayload.detail;
      const failure = responsePayload.failure;
      if (failure === null || typeof failure !== "object" || Array.isArray(failure)) {
        return {
          code: typeof responsePayload.code === "string" ? responsePayload.code : typeof (responseDetail as Record<string, unknown> | null)?.code === "string" ? (responseDetail as Record<string, string>).code : null,
          detail: typeof responseDetail === "string" && responseDetail.trim() ? responseDetail : null,
          expectedSequence: null,
        };
      }
      const fields = failure as Record<string, unknown>;
      return {
        code: typeof fields.code === "string" ? fields.code : null,
        detail:
          typeof responseDetail === "string" && responseDetail.trim()
            ? responseDetail
            : typeof fields.message === "string" && fields.message.trim()
              ? fields.message
              : null,
        expectedSequence:
          Number.isInteger(fields.expected_sequence) && (fields.expected_sequence as number) >= 0
            ? (fields.expected_sequence as number)
            : null,
      };
    } catch {
      return { code: null, detail: null, expectedSequence: null };
    }
  }

  private resetSessionForRecreation(): void {
    this.failedTransports.clear();
    this.session = null;
    this.heartbeatPending = null;
    this.heartbeatSequence = 0;
    this.heartbeatMonotonicNs = 0;
    this.heartbeatNextStartFrame = 0;
    for (const state of this.lanes.values()) {
      state.frameQueue.length = 0;
      state.sequence = 0;
      state.pendingDiscontinuityEpochs.clear();
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

  private scheduleHeartbeat(state: HelperState, signal?: AbortSignal): Promise<void> {
    if (!this.session || (this.stopping && state !== "stopped")) return Promise.resolve();
    if (this.heartbeatPending !== "stopped") this.heartbeatPending = state;
    // `heartbeatFlushing` is cleared inside the flush itself, in the same synchronous
    // step the drain loop exits in. Clearing it from a `.finally()` on the returned
    // promise instead leaves a one-microtask window in which the loop has already
    // stopped but the flag still says a flush is running: a schedule landing there sets
    // `heartbeatPending` and starts nothing, and that heartbeat is never sent. The
    // worst case is `stop()`, which awaits this and would otherwise walk past its final
    // `stopped` heartbeat -- the one fact the server turns into "Audio capture stopped."
    if (!this.heartbeatFlushing) {
      this.heartbeatFlushing = true;
      this.heartbeatFlush = this.flushHeartbeat(signal);
    }
    return this.heartbeatFlush ?? Promise.resolve();
  }

  private async flushHeartbeat(signal?: AbortSignal): Promise<void> {
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
        const response = await this.fetchRequest(
          `/api/live/sessions/${encodeURIComponent(session.id)}/heartbeat`,
          {
            method: "POST",
            cache: "no-store",
            credentials: "same-origin",
            headers: this.requestHeaders(true),
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
          signal,
        );
        this.heartbeatSequence += 1;
        if (!response.ok) {
          const error = await captureResponseError(response, "heartbeat POST");
          if (error.code === "capture_replaced") { await this.captureReplaced(); return; }
          throw error;
        }
        this.transportRecovered("heartbeat");
      }
    } catch (caught) {
      this.reportTransportError("heartbeat", caught);
    } finally {
      this.heartbeatFlushing = false;
    }
  }

  private async fetchRequest(
    input: string,
    init: RequestInit,
    deadlineSignal?: AbortSignal,
  ): Promise<Response> {
    if (deadlineSignal?.aborted) {
      throw deadlineSignal.reason ?? new DOMException("capture request deadline expired", "TimeoutError");
    }
    const controller = new AbortController();
    const abort = () => controller.abort(deadlineSignal?.reason);
    deadlineSignal?.addEventListener("abort", abort, { once: true });
    const timeout = requestDeadline(CAPTURE_REQUEST_TIMEOUT_MS);
    const expire = () => controller.abort(timeout.signal.reason);
    timeout.signal.addEventListener("abort", expire, { once: true });
    this.requestControllers.add(controller);
    try {
      return await captureFetch(input, { ...init, signal: controller.signal });
    } finally {
      timeout.cancel();
      timeout.signal.removeEventListener("abort", expire);
      this.requestControllers.delete(controller);
      deadlineSignal?.removeEventListener("abort", abort);
    }
  }

  private abortRequests(reason?: unknown): void {
    for (const controller of this.requestControllers) controller.abort(reason);
  }

  private requestHeaders(json = false): Record<string, string> {
    const headers: Record<string, string> = { "X-Moss-Capture-Instance": this.instanceId };
    if (json) headers["Content-Type"] = "application/json";
    return headers;
  }

  private heartbeatState(): HelperState {
    const states = [...this.lanes.values()];
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
    if (this.contextSuspended) {
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
      failure_code: state?.degradedCode ?? null,
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

  /**
   * A recorded source's track ended: Chrome's "Stop sharing", an unplugged microphone.
   *
   * Before a session exists nothing starts. During one the lane goes silent rather than
   * `failed`: a failed lane is sealed by the server, which then ends the meeting as failed
   * instead of completing it at Stop. Zeros join the lane's own framer before the ended source
   * leaves it, so the framer never sees an empty input and its sequence numbers and timestamps
   * continue; frames already queued are still delivered.
   */
  private sourceEnded(lane: CaptureLane): void {
    const state = this.lanes.get(lane);
    if (!state || state.silent) return;
    const context = this.context;
    if (!this.session || !context) {
      void this.failBeforeSession(lane, "browser_track_ended");
      return;
    }
    const zeros = zeroSource(context);
    zeros.connect(state.framer);
    for (const { track, listener } of state.trackEndedListeners) {
      track.removeEventListener("ended", listener);
    }
    state.source.disconnect();
    state.tracks.forEach((track) => track.stop());
    state.silent = true;
    state.source = zeros;
    state.tracks = [];
    state.trackEndedListeners = [];
    state.clippedFrameRun = 0;
    state.silentFrameRun = 0;
    if (state.degradedCode !== null) {
      // The stopped source's clipping or silence is not a condition of the silent lane.
      state.degradedCode = null;
      state.health = "capturing";
      void this.scheduleHeartbeat(this.heartbeatState());
    }
    this.options.onSourceStopped?.(lane);
  }

  /**
   * Turn worklet frames into the two metered lane conditions the charter requires.
   *
   * Both are *recoverable*: they set `degraded`, and they clear themselves when the
   * audio recovers. Neither is ever reported as `failed`, which the server treats as a
   * permanent seal on the lane.
   *
   * Silence is only ever reported for the microphone. A quiet system lane is the
   * normal state of a meeting where nobody is sharing sound, and the server's copy for
   * `browser_microphone_silent` names a Chrome microphone setting. A muted microphone is
   * silent on purpose and never counts toward it.
   */
  private meterLaneHealth(
    lane: CaptureLane,
    state: LaneState,
    level: number,
    samples: Float32Array,
  ): void {
    state.clippedFrameRun =
      clippedFraction(samples) >= CLIPPED_FRAME_FRACTION ? state.clippedFrameRun + 1 : 0;
    const muted = lane === "microphone" && this.microphoneMuted;
    state.silentFrameRun = level < SILENCE_RMS && !muted ? state.silentFrameRun + 1 : 0;

    let degraded: BrowserDegradedCode | null = null;
    if (state.clippedFrameRun >= SUSTAINED_CLIPPING_FRAMES) {
      degraded = "browser_sustained_clipping";
    } else if (lane === "microphone" && state.silentFrameRun >= SILENT_MICROPHONE_FRAMES) {
      degraded = "browser_microphone_silent";
    }
    if (degraded === state.degradedCode) return;

    state.degradedCode = degraded;
    state.health = degraded === null ? "capturing" : "degraded";
    if (!this.session && degraded === "browser_microphone_silent") {
      this.options.onPreflightStatus?.(this.requirePreflightStatusLine("microphoneSilent"));
    }
    // A condition that just started or just cleared is news; send it now rather than
    // waiting for the next rate-limited worklet heartbeat.
    void this.scheduleHeartbeat(this.heartbeatState());
  }

  private requirePreflightStatusLine(kind: "microphoneSilent"): string {
    const descriptor = this.descriptor;
    if (!descriptor) throw new Error("capture descriptor is unavailable");
    return descriptor.preflightStatusLines[kind];
  }

  private transportRecovered(path: CaptureLane | "heartbeat"): void {
    if (this.failedTransports.delete(path) && this.failedTransports.size === 0 && this.session && !this.stopping) {
      this.options.onTransportRecovered?.();
    }
  }

  private reportTransportError(route: "frame" | "heartbeat", caught: unknown, lane?: CaptureLane): void {
    if (this.session && !this.stopping) {
      if (route === "heartbeat") this.failedTransports.add("heartbeat");
      else if (lane) this.failedTransports.add(lane);
    }
    const error = caught instanceof Error ? caught : new Error(String(caught));
    this.options.onTransportError?.(route, error);
  }
}
