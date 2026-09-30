import { useEffect, useRef, useState } from "preact/hooks";
import { createMossSessionPoller, type MossSessionPoller } from "../api/mossPoller";
import {
  CaptureClient,
  type CaptureLane,
  type PreSessionCaptureFailure
} from "../capture/captureClient";
import { captureMeetingId, resetSessionState, sessionTitle } from "../state/session";
import { bindFileUpload } from "../lib/fileUpload";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { settledSpeakerNumbers, transcriptCardSpeakerLabel } from "../lib/transcriptCards";
import { serializeTranscriptExport, triggerTranscriptExportDownload, type TranscriptExportFormat } from "../lib/transcriptExport";
import { summaryApi } from "../lib/finalSummary";
import { openMeeting } from "../api/meetings";
import { engineSettingsFrom, loadAppSettings } from "../lib/settings";
import { sessionId, sessionNeedsReview, sessionStatus, transcript } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";
import { watchMeetingSummary } from "../lib/summaryRequests";
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

function workletUrl(): string {
  const url = document.querySelector<HTMLMetaElement>(
    'meta[name="moss-worklet-url"]'
  )?.content;
  if (!url) throw new Error("Missing live-capture worklet URL");
  return url;
}

export function ControlPanel() {
  const recovering = useRef(new Set<"capture" | "transcript">());
  const [mode, setMode] = useState<"live" | "file" | "url">("live");
  const [fileQueue, setFileQueue] = useState<string[]>([]);
  const [url, setUrl] = useState("");
  const [exportFormat, setExportFormat] = useState<TranscriptExportFormat | "audio">("md");
  const [exportError, setExportError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [audioRoute, setAudioRoute] = useState<AudioRoute>("speakers");
  const [microphones, setMicrophones] = useState<MediaDeviceInfo[]>([]);
  const [microphoneId, setMicrophoneId] = useState("");
  const [phase, setPhase] = useState<CapturePhase>("idle");
  const [connected, setConnected] = useState({ microphone: false, system: false });
  const [meters, setMeters] = useState<LaneMeters>(EMPTY_METERS);
  const [message, setMessage] = useState(
    "Live capture requires both your microphone and shared audio. Enable the microphone, then share a tab with audio."
  );
  const [setupErrors, setSetupErrors] = useState<Partial<Record<CaptureLane, string>>>({});
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
      setMessage("Both sources are receiving sound. Start capture when ready.");
    }
  };

  const reportSetupError = (lane: CaptureLane, message: string) => {
    setSetupErrors(current => ({ ...current, [lane]: message }));
    metersRef.current = EMPTY_METERS;
    setMeters(EMPTY_METERS);
    transition("error");
  };

  const reportPreSessionFailure = (failure: PreSessionCaptureFailure) => {
    setConnected({ microphone: false, system: false });
    reportSetupError(failure.lane, `${failure.lane}: ${failure.code}`);
  };

  const transportFailed = (source: "capture" | "transcript", message: string) => {
    recovering.current.add(source);
    setMessage(message === "Failed to fetch" || message === "request timed out"
      ? "Connection interrupted. Retrying automatically; keep this tab open."
      : message);
  };

  const transportRecovered = (source: "capture" | "transcript") => {
    const wasRecovering = recovering.current.delete(source);
    if (wasRecovering && recovering.current.size === 0 && phaseRef.current === "active") {
      setMessage("Connection restored. Recording microphone and shared audio.");
    }
  };

  const handleTerminal = (terminalMessage: string, clearSaved: boolean) => {
    recovering.current.clear();
    captureMeetingId.value = null;
    if (clearSaved) clearSessionReattach(sessionReattachStorage());
    pollerRef.current?.stop();
    pollerRef.current = null;
    const client = clientRef.current;
    clientRef.current = null;
    if (client) void client.close().catch(() => undefined);
    metersRef.current = EMPTY_METERS;
    setMeters(EMPTY_METERS);
    setConnected({ microphone: false, system: false });
    transition("terminal");
    setMessage(terminalMessage === "helper_lease_expired"
      ? "Recording interrupted: the connection was lost for too long. Reset capture to start again."
      : terminalMessage);
    requestMeetingHistoryRefresh();
  };

  const configureMicrophone = async () => {
    if (clientRef.current) return;
    transition("configuring");
    setMessage("Requesting microphone access...");
    const client = new CaptureClient({
      helperVersion: HELPER_VERSION,
      workletUrl: workletUrl(),
      onMeter: (lane, rms) => {
        if (clientRef.current === client && phaseRef.current !== "error") updateMeter(lane, rms);
      },
      onPreflightStatus: message => {
        if (clientRef.current === client) setMessage(message);
      },
      onPreSessionFailure: failure => {
        if (clientRef.current === client) reportPreSessionFailure(failure);
      },
      onTransportError: (_route, error) => {
        if (clientRef.current === client) transportFailed("capture", error.message);
      },
      onTransportRecovered: () => {
        if (clientRef.current === client) transportRecovered("capture");
      }
    });
    clientRef.current = client;
    try {
      await client.prepare();
      if (clientRef.current !== client) { await client.close(); return; }
      await client.startMicrophone(audioRoute === "speakers", microphoneId || undefined);
      void refreshMicrophones();
      if (clientRef.current !== client) { await client.close(); return; }
      setConnected(current => ({ ...current, microphone: true }));
      setMessage("Microphone connected. Share a browser tab, window, or screen with audio.");
    } catch (error) {
      if (clientRef.current === client) reportSetupError("microphone", errorMessage(error));
    }
  };

  const shareAudio = async () => {
    const client = clientRef.current;
    if (!client || phase === "stopping") return;
    setMessage(connected.system ? "Choose a replacement audio surface." : "Choose a surface and enable share audio.");
    try {
      const displayRequest = client.requestDisplayMedia();
      const stream = await displayRequest;
      if (clientRef.current !== client) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      if (connected.system) {
        metersRef.current = { ...metersRef.current, system: 0 };
        setMeters(metersRef.current);
        await client.replaceLane("system", stream, stream.getTracks());
      } else {
        await client.attachDisplayMedia(stream);
      }
      if (clientRef.current !== client) { await client.close(); return; }
      setConnected(current => ({ ...current, system: true }));
      setMessage("Shared audio connected. Play sound in the shared tab and speak into the microphone.");
    } catch (error) {
      if (clientRef.current !== client) return;
      if (phaseRef.current === "active") setMessage(errorMessage(error));
      else reportSetupError("system", errorMessage(error));
    }
  };

  const refreshMicrophones = async () => {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices?.();
      if (devices) setMicrophones(devices.filter(device => device.kind === "audioinput"));
    } catch { /* Browser device labels may require microphone permission. */ }
  };

  const switchMicrophone = async (deviceId = microphoneId) => {
    const client = clientRef.current;
    if (!client || phase === "stopping") return;
    setMessage("Requesting a replacement microphone...");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: audioRoute === "speakers",
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}) },
        video: false
      });
      metersRef.current = { ...metersRef.current, microphone: 0 };
      setMeters(metersRef.current);
      await client.replaceLane("microphone", stream, stream.getTracks());
      setConnected(current => ({ ...current, microphone: true }));
      setMicrophoneId(deviceId);
      void refreshMicrophones();
      setMessage("Microphone replaced. Speak to check its sound level.");
    } catch (error) {
      setMessage(errorMessage(error));
      if (phaseRef.current !== "active") transition("error");
    }
  };

  const startCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "ready") return;
    transition("configuring");
    recovering.current.clear();
    setMessage("Creating live session...");
    resetSessionState();
    sessionTitle.value = "";
    try {
      const session = await client.createSession(engineSettingsFrom(loadAppSettings()));
      watchMeetingSummary(session.id);
      saveSessionReattach(sessionReattachStorage(), {
        sessionId: session.id
      });
      const poller = createMossSessionPoller({
        sessionId: session.id,
        onError: (message) => transportFailed("transcript", message),
        onRecovered: () => {
          if (captureMeetingId.value === session.id) transportRecovered("transcript");
        },
        onTerminal(terminalMessage) {
          handleTerminal(terminalMessage, true);
        }
      });
      pollerRef.current = poller;
      captureMeetingId.value = session.id;
      transition("active");
      setMessage("Recording microphone and shared audio.");
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
    captureMeetingId.value = null;
    setMessage("Stopping capture and finalizing transcript...");
    try {
      // Five seconds bounds local frame delivery and this request's wait only.
      // A 202 leaves the existing poller running while the server finishes draining.
      await client.stop(5);
      if (phaseRef.current === "stopping") setMessage("Capture stopped. Waiting for the transcript to finish…");
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
    setConnected({ microphone: false, system: false });
    resetSessionState();
    sessionTitle.value = "";
    transition("idle");
    setSetupErrors({});
    setMessage("Live capture requires both your microphone and shared audio. Enable the microphone, then share a tab with audio.");
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
      captureMeetingId.value = null;
      document.removeEventListener(LIVE_MEETING_OBSERVE_EVENT, observeHistoryMeeting);
      pollerRef.current?.stop();
      void clientRef.current?.close().catch(() => undefined);
    };
  }, []);

  useEffect(() => {
    if (mode === "live") return;
    return bindFileUpload();
  }, [mode]);

  async function saveExport(): Promise<void> {
    const id = sessionId.value;
    if (!id) return;
    if (selectedSummaryMeeting.value?.id === id && selectedSummaryMeeting.value.refinement_state === "running") return;
    setExportError("");
    if (exportFormat === "audio") {
      try {
        const meeting = await openMeeting(id);
        if (meeting.audio?.state !== "available" && meeting.audio?.state !== "partial") {
          setExportError("Audio is unavailable for this meeting."); return;
        }
        const anchor = document.createElement("a");
        anchor.href = `/api/meetings/${encodeURIComponent(id)}/audio/download`;
        anchor.download = `meeting-${id}.mp3`;
        document.body.append(anchor); anchor.click(); anchor.remove();
      } catch (error) { setExportError(error instanceof Error ? error.message : "Audio download unavailable."); }
      return;
    }
    const turns = groupSegmentsIntoTurns(transcript.value);
    const finalized = sessionStatus.value !== "active" && sessionStatus.value !== "closing";
    const numbers = settledSpeakerNumbers(turns, finalized);
    let summary = null;
    let summaryUpdating = false;
    if (exportFormat === "md" && finalized) {
      try {
        const version = selectedSummaryMeeting.value?.id === id
          ? selectedSummaryMeeting.value.transcript_version : (await openMeeting(id)).transcript_version;
        const artifact = await summaryApi(id);
        summary = artifact?.state === "current" && artifact.source_version === version ? artifact.document : null;
        summaryUpdating = artifact != null && artifact.source_version !== version;
      }
      catch { /* A transcript remains exportable when its optional summary cannot be fetched. */ }
    }
    if (selectedSummaryMeeting.value?.id === id && selectedSummaryMeeting.value.refinement_state === "running") return;
    triggerTranscriptExportDownload(serializeTranscriptExport(exportFormat, turns,
      turn => transcriptCardSpeakerLabel(turn, numbers),
      { sessionId: id, exportedAt: new Date() }, { needsReview: sessionNeedsReview.value }, summary, summaryUpdating));
  }

  const configured = clientRef.current !== null;
  const reattached = phase === "viewing";
  const canStart = phase === "ready" && meters.microphone > 0 && meters.system > 0;
  const canReplace = phase === "ready" || phase === "active";

  const readiness = !connected.microphone
    ? "Next: enable your microphone."
    : !connected.system
      ? "Next: Share audio, choose a tab, and enable audio sharing in the browser chooser."
      : meters.microphone <= 0 && meters.system <= 0
        ? "Next: speak into your microphone and play sound in the shared tab. Both sources must register sound to start."
        : meters.microphone <= 0
          ? "Next: speak into your microphone. Shared audio is receiving sound."
          : meters.system <= 0
            ? "Next: play sound in the shared tab. Your microphone is receiving sound."
            : "Both sources are receiving sound. Start capture when ready.";

  const modeLocked = phase === "active" || phase === "stopping" || phase === "viewing" || phase === "configuring" || sessionStatus.value === "active" || sessionStatus.value === "closing";
  const exportReady = sessionId.value !== null && (exportFormat === "audio" || transcript.value.length > 0);
  const refinementRunning = selectedSummaryMeeting.value?.id === sessionId.value &&
    selectedSummaryMeeting.value.refinement_state === "running";

  return (
    <section className="control-section controls-workspace" data-mode={mode}>
      <div className="controls-scroll">
      <div className="controls-block"><span className="field-label">Mode</span>
        <div className="seg mode-tabs" role="group" aria-label="Mode">
          {(["live", "file", "url"] as const).map(choice => <button key={choice} type="button"
            className={`seg-btn${mode === choice ? " is-active" : ""}`} aria-pressed={mode === choice}
            disabled={modeLocked} onClick={() => { if (choice !== mode) setFileQueue([]); setMode(choice); }}>{choice === "url" ? "URL" : choice === "file" ? "File" : "Live"}</button>)}
        </div>
      </div>
      {mode === "live" ? <>
      <div className="controls-primary">
        {phase === "active" ? <button type="button" className="record-btn" data-action="stop" onClick={() => void stopCapture()}>Stop and finalize</button>
          : phase === "stopping" ? <button type="button" className="record-btn" disabled>Finalizing…</button>
          : phase === "viewing" || phase === "terminal" || phase === "error" ? null
          : !connected.microphone ? <button type="button" className="record-btn" disabled={phase === "configuring"} onClick={() => void configureMicrophone()}>{phase === "configuring" ? "Connecting microphone…" : "Enable microphone"}</button>
          : !connected.system ? <button type="button" className="record-btn" onClick={() => void shareAudio()}>Share audio</button>
          : <button type="button" className="record-btn" disabled={!canStart} onClick={() => void startCapture()}>Start recording</button>}
      </div>
      <div className="controls-block live-mode-section">
      <div
      className="capture-supervisor"
      data-mode="live"
      data-capture-phase={phase}
      data-observer-mode={reattached ? "read-only" : "none"}
    >
      <div className="label">Capture · Microphone + shared audio</div>
      <p className="hint">Microphone and shared audio are required. Private to this browser.</p>

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
        Speakers cancel echo; headphones preserve microphone audio.
      </p>

      <label className="field-label" htmlFor="microphone-select">Microphone</label>
      <select id="microphone-select" aria-label="Microphone" value={microphoneId}
        disabled={reattached || phase === "stopping"}
        onFocus={() => void refreshMicrophones()}
        onChange={event => { const id = event.currentTarget.value; setMicrophoneId(id);
          if (clientRef.current && connected.microphone) void switchMicrophone(id); }}>
        <option value="">System default</option>
        {microphones.map((device, index) => <option key={device.deviceId} value={device.deviceId}>
          {device.label || `Microphone ${index + 1}`}</option>)}
      </select>

      <div className="capture-meters" aria-label="Capture lane meters">
        <LaneMeter label="Microphone" value={meters.microphone} connected={connected.microphone} observer={reattached} />
        <LaneMeter label="Shared audio" value={meters.system} connected={connected.system} observer={reattached} />
      </div>

      {!reattached && (phase === "idle" || phase === "configuring" || phase === "ready") ? (
        <p className="hint" data-capture-readiness>{readiness}</p>
      ) : null}

      {phase === "configuring" || phase === "terminal" || phase === "error" ? <button type="button" className="btn" onClick={() => void resetCapture()}>Reset capture</button> : null}
      {phase === "viewing" ? <button type="button" className="btn" onClick={() => void resetCapture()}>Detach transcript</button> : null}
      {configured && connected.microphone && (phase === "configuring" || canReplace) ? (
        <div className="btn-row">
          <button type="button" className="btn" onClick={() => void switchMicrophone()}>Switch mic</button>
          {connected.system ? <button type="button" className="btn" onClick={() => void shareAudio()}>Reshare audio</button> : null}
        </div>
      ) : null}

      <p className="capture-status" role="status">{
        Object.keys(setupErrors).length > 0
          ? [setupErrors.microphone && `Microphone: ${setupErrors.microphone}`,
              setupErrors.system && `Shared audio: ${setupErrors.system}`]
              .filter(Boolean).join(". ") + ". Reset capture to try again."
          : message
      }</p>
      </div></div></> :
      <form key={mode} data-file-upload="form" className="controls-mode-form" onSubmit={event => { if (mode === "url" && !url.startsWith("https://")) event.preventDefault(); }}>
        <button type="submit" className="record-btn" disabled={mode === "file" ? fileQueue.length === 0 : !url.startsWith("https://")}>
          {mode === "file" ? "Start file transcription" : "Start URL transcription"}</button>
        <div className="controls-block">
          {mode === "file" ? <><label className="field-label" htmlFor="meeting-files">Files</label>
            <input ref={fileInputRef} id="meeting-files" name="file" type="file" multiple
              onChange={event => setFileQueue(Array.from(event.currentTarget.files ?? []).map(file => file.name))} />
            <button type="button" className="btn" disabled={!fileQueue.length} onClick={() => { if (fileInputRef.current) fileInputRef.current.value = ""; setFileQueue([]); }}>Clear queue</button>
            {fileQueue.length ? <ul>{fileQueue.map((name, index) => <li key={`${name}-${index}`}>{name}</li>)}</ul> : <p className="hint">No files added yet.</p>}</> :
            <><input name="file" type="file" multiple hidden /><label className="field-label" htmlFor="meeting-url">URL</label>
              <input id="meeting-url" name="urls" type="url" value={url} placeholder="https://example.com/audio.mp3"
                onInput={event => setUrl(event.currentTarget.value)} />
              <p className="hint">Enter an exact https:// media URL.</p></>}
          {mode === "file" && <input name="urls" value="" hidden readOnly />}
          <p data-file-upload="status" role="status" /><ul data-file-upload="results" />
        </div>
      </form>}
      </div>
      <div className="controls-block controls-export"><label className="field-label" htmlFor="meeting-export-format">Export</label>
        <div className="controls-export-row"><select id="meeting-export-format" aria-label="Export format" value={exportFormat} disabled={refinementRunning}
          onChange={event => setExportFormat(event.currentTarget.value as TranscriptExportFormat | "audio")}>
          <option value="md">Markdown (.md)</option><option value="txt">Plain text (.txt)</option>
          <option value="srt">SRT (.srt)</option><option value="vtt">VTT (.vtt)</option>
          <option value="json">JSON (.json)</option><option value="audio">Audio (.mp3)</option>
        </select><button type="button" className="btn" disabled={!exportReady || refinementRunning} onClick={() => void saveExport()}>Save</button></div>
        {refinementRunning ? <p className="hint" role="status">Export waits for transcript improvement.</p> : null}
        {exportError && <p role="alert">{exportError}</p>}
      </div>
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

function LaneMeter({ label, value, connected, observer }: { label: string; value: number; connected: boolean; observer: boolean }) {
  const level = laneMeterPercent(value);
  return (
    <div className="capture-meter">
      <span>{label}<small style={{ display: "block" }}>{observer ? "Captured in another tab" : !connected ? "Not connected" : value > 0 ? "Connected · receiving sound" : "Connected · quiet"}</small></span>
      <span className="capture-meter-track" aria-label={`${label} level ${level}%`}>
        <span style={{ width: `${level}%` }} />
      </span>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
