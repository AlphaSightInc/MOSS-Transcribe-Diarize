import { useEffect, useRef, useState } from "preact/hooks";
import { createMossSessionPoller, type MossSessionPoller } from "../api/mossPoller";
import {
  CaptureClient,
  type CaptureLane,
  type PreSessionCaptureFailure
} from "../capture/captureClient";
import { resetSessionState } from "../state/session";
import {
  clearSessionReattach,
  loadSessionReattach,
  saveSessionReattach,
  sessionReattachStorage
} from "../lib/persistence";
import {
  LIVE_MEETING_OBSERVE_EVENT,
  requestMeetingHistoryRefresh
} from "../lib/meetingEvents";

type CapturePhase =
  | "idle"
  | "configuring"
  | "ready"
  | "active"
  | "viewing"
  | "stopping"
  | "terminal"
  | "error";
type AudioRoute = "speakers" | "headphones";
type LaneMeters = Record<CaptureLane, number>;

const EMPTY_METERS: LaneMeters = { microphone: 0, system: 0 };
const HELPER_VERSION = "moss-web/1";
export { LIVE_MEETING_OBSERVE_EVENT } from "../lib/meetingEvents";

export function ControlPanel() {
  const [audioRoute, setAudioRoute] = useState<AudioRoute>("speakers");
  const [phase, setPhase] = useState<CapturePhase>("idle");
  const [meters, setMeters] = useState<LaneMeters>(EMPTY_METERS);
  const [message, setMessage] = useState(
    "Enable the microphone, then share system audio to start a private Live Meeting."
  );
  const clientRef = useRef<CaptureClient | null>(null);
  const pollerRef = useRef<MossSessionPoller | null>(null);
  const phaseRef = useRef<CapturePhase>("idle");
  const metersRef = useRef<LaneMeters>(EMPTY_METERS);

  const transition = (next: CapturePhase) => {
    phaseRef.current = next;
    setPhase(next);
  };

  const updateMeter = (lane: CaptureLane, rms: number) => {
    const next = { ...metersRef.current, [lane]: rms };
    metersRef.current = next;
    setMeters(next);
    if (next.microphone > 0 && next.system > 0 && phaseRef.current === "configuring") {
      transition("ready");
      setMessage("Both lanes carry audio. Start capture when ready.");
    }
  };

  const reportPreSessionFailure = (failure: PreSessionCaptureFailure) => {
    transition("error");
    setMessage(`${failure.lane}: ${failure.code}`);
  };

  const handleTerminal = (terminalMessage: string, clearSaved: boolean) => {
    if (clearSaved) clearSessionReattach(sessionReattachStorage());
    pollerRef.current?.stop();
    pollerRef.current = null;
    const client = clientRef.current;
    clientRef.current = null;
    if (client) void client.close().catch(() => undefined);
    metersRef.current = EMPTY_METERS;
    setMeters(EMPTY_METERS);
    transition("terminal");
    setMessage(terminalMessage);
    requestMeetingHistoryRefresh();
  };

  const configureMicrophone = async () => {
    if (clientRef.current) return;
    transition("configuring");
    setMessage("Requesting microphone access...");
    const client = new CaptureClient({
      helperVersion: HELPER_VERSION,
      onMeter: updateMeter,
      onPreflightStatus: setMessage,
      onPreSessionFailure: reportPreSessionFailure,
      onTransportError: (_route, error) => setMessage(error.message)
    });
    clientRef.current = client;
    try {
      await client.prepare();
      await client.startMicrophone(audioRoute === "speakers");
      setMessage("Microphone connected. Share a browser tab, window, or screen with audio.");
    } catch (error) {
      transition("error");
      setMessage(errorMessage(error));
    }
  };

  const shareAudio = async () => {
    const client = clientRef.current;
    if (!client || phase === "stopping") return;
    const displayRequest = client.requestDisplayMedia();
    setMessage(meters.system > 0 ? "Choose a replacement audio surface." : "Choose a surface and enable share audio.");
    try {
      const stream = await displayRequest;
      if (metersRef.current.system > 0) {
        metersRef.current = { ...metersRef.current, system: 0 };
        setMeters(metersRef.current);
        await client.replaceLane("system", stream, stream.getTracks());
      } else {
        await client.attachDisplayMedia(stream);
      }
      setMessage("Shared-audio lane connected; waiting for non-zero signal.");
    } catch (error) {
      setMessage(errorMessage(error));
      if (phaseRef.current !== "active") transition("error");
    }
  };

  const switchMicrophone = async () => {
    const client = clientRef.current;
    if (!client || phase === "stopping") return;
    setMessage("Requesting a replacement microphone...");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: audioRoute === "speakers" },
        video: false
      });
      metersRef.current = { ...metersRef.current, microphone: 0 };
      setMeters(metersRef.current);
      await client.replaceLane("microphone", stream, stream.getTracks());
      setMessage("Microphone replaced; waiting for non-zero signal.");
    } catch (error) {
      setMessage(errorMessage(error));
      if (phaseRef.current !== "active") transition("error");
    }
  };

  const startCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "ready") return;
    transition("configuring");
    setMessage("Creating live session...");
    resetSessionState();
    try {
      const session = await client.createSession();
      saveSessionReattach(sessionReattachStorage(), {
        sessionId: session.id
      });
      const poller = createMossSessionPoller({
        sessionId: session.id,
        onError: setMessage,
        onTerminal(terminalMessage) {
          handleTerminal(terminalMessage, true);
        }
      });
      pollerRef.current = poller;
      transition("active");
      setMessage("Capture active. Keep both lane meters moving.");
      poller.start();
      requestMeetingHistoryRefresh();
    } catch (error) {
      transition("error");
      setMessage(errorMessage(error));
    }
  };

  const stopCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "active") return;
    transition("stopping");
    setMessage("Stopping capture and finalizing transcript...");
    try {
      await client.stop(5);
    } catch (error) {
      transition("error");
      setMessage(errorMessage(error));
    }
  };

  const resetCapture = async () => {
    clearSessionReattach(sessionReattachStorage());
    pollerRef.current?.stop();
    pollerRef.current = null;
    const client = clientRef.current;
    clientRef.current = null;
    if (client) {
      try {
        await client.stop(0);
      } catch {
        // A terminal server may reject the redundant stop; local state still resets.
      }
    }
    metersRef.current = EMPTY_METERS;
    setMeters(EMPTY_METERS);
    resetSessionState();
    transition("idle");
    setMessage("Enable the microphone, then share system audio to start a private Live Meeting.");
  };

  useEffect(() => {
    const observeHistoryMeeting = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      const meetingId =
        typeof detail === "object" &&
        detail !== null &&
        "meetingId" in detail &&
        typeof detail.meetingId === "string"
          ? detail.meetingId.trim()
          : "";
      if (
        !meetingId ||
        clientRef.current !== null ||
        phaseRef.current === "active" ||
        phaseRef.current === "stopping"
      ) {
        return;
      }

      pollerRef.current?.stop();
      resetSessionState();
      const poller = createMossSessionPoller({
        sessionId: meetingId,
        onError: setMessage,
        onTerminal(terminalMessage) {
          handleTerminal(terminalMessage, false);
        }
      });
      pollerRef.current = poller;
      transition("viewing");
      setMessage("Viewing this active Live Meeting read-only. Capture remains with its original browser.");
      poller.start();
    };
    document.addEventListener(LIVE_MEETING_OBSERVE_EVENT, observeHistoryMeeting);

    const saved = loadSessionReattach(sessionReattachStorage());
    if (saved) {
      const poller = createMossSessionPoller({
        sessionId: saved.sessionId,
        onError: setMessage,
        onTerminal(terminalMessage) {
          handleTerminal(terminalMessage, true);
        }
      });
      pollerRef.current = poller;
      transition("viewing");
      setMessage("Transcript reattached. Browser capture stopped on reload.");
      poller.start();
    }

    return () => {
      document.removeEventListener(LIVE_MEETING_OBSERVE_EVENT, observeHistoryMeeting);
      pollerRef.current?.stop();
      void clientRef.current?.close().catch(() => undefined);
    };
  }, []);

  const configured = clientRef.current !== null;
  const reattached = phase === "viewing";
  const canStart = phase === "ready" && meters.microphone > 0 && meters.system > 0;
  const canReplace = phase === "ready" || phase === "active";

  return (
    <section
      className="control-section capture-supervisor"
      data-mode="live"
      data-capture-phase={phase}
      data-observer-mode={reattached ? "read-only" : "none"}
    >
      <div className="label">Capture</div>
      <p className="capture-security-note">Bound to your signed-in Account; no capture key is needed.</p>

      <label className="field-label" htmlFor="audio-route">Listening setup</label>
      <div className="field">
        <select
          id="audio-route"
          aria-label="Listening setup"
          value={audioRoute}
          disabled={reattached || phase === "stopping" || phase === "terminal"}
          onChange={(event) => setAudioRoute(event.currentTarget.value as AudioRoute)}
        >
          <option value="speakers">Speakers</option>
          <option value="headphones">Headphones</option>
        </select>
      </div>
      <p className="hint">
        Speakers enable echo cancellation; headphones preserve the microphone signal.
      </p>

      <div className="capture-meters" aria-label="Capture lane meters">
        <LaneMeter label="Microphone" value={meters.microphone} />
        <LaneMeter label="Shared audio" value={meters.system} />
      </div>

      {!configured && !reattached ? (
        <button
          type="button"
          className="record-btn"
          onClick={() => void configureMicrophone()}
        >
          <span>Enable microphone</span>
        </button>
      ) : null}

      {configured && (phase === "configuring" || canReplace) ? (
        <div className="btn-row">
          <button type="button" className="btn" onClick={() => void switchMicrophone()}>
            Switch mic
          </button>
          <button type="button" className="btn" onClick={() => void shareAudio()}>
            {meters.system > 0 ? "Reshare audio" : "Share audio"}
          </button>
        </div>
      ) : null}

      {phase === "ready" ? (
        <button type="button" className="record-btn" disabled={!canStart} onClick={() => void startCapture()}>
          <span>Start capture</span>
        </button>
      ) : null}
      {phase === "active" ? (
        <button type="button" className="record-btn" data-action="stop" onClick={() => void stopCapture()}>
          <span>Stop and finalize</span>
        </button>
      ) : null}
      {phase === "viewing" ? (
        <button type="button" className="btn" onClick={() => void resetCapture()}>
          Detach transcript
        </button>
      ) : null}
      {phase === "stopping" ? <button type="button" className="record-btn" disabled>Finalizing...</button> : null}
      {phase === "terminal" || phase === "error" ? (
        <button type="button" className="btn" onClick={() => void resetCapture()}>Reset capture</button>
      ) : null}

      <p className="capture-status" role="status">{message}</p>
    </section>
  );
}

/**
 * Map lane RMS onto the bar as decibels, not amplitude.
 *
 * A linear bar (the previous `value * 500`) drew ordinary speech at ~7% beside tab audio pegged at
 * 100%, so a perfectly healthy microphone was indistinguishable from a dead one. Measured on the
 * operator's own hardware: speech rms 1.4e-2 = -37 dBFS, tab audio rms 2.9e-1 = -11 dBFS. Hearing is
 * logarithmic, so the meter is too: -60 dBFS reads empty, 0 dBFS reads full, and those two real
 * signals land at ~38% and ~82% -- clearly distinct, and neither one pegged.
 */
export function laneMeterPercent(value: number): number {
  if (!(value > 0)) return 0;
  const db = 20 * Math.log10(value);
  return Math.min(100, Math.max(0, Math.round(((db + 60) / 60) * 100)));
}

function LaneMeter({ label, value }: { label: string; value: number }) {
  const level = laneMeterPercent(value);
  return (
    <div className="capture-meter">
      <span>{label}</span>
      <span className="capture-meter-track" aria-label={`${label} level ${level}%`}>
        <span style={{ width: `${level}%` }} />
      </span>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
