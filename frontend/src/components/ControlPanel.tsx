import { useEffect, useRef, useState } from "preact/hooks";
import { createMossSessionPoller, type MossSessionPoller } from "../api/mossPoller";
import {
  CaptureClient,
  type CaptureLane,
  type PreSessionCaptureFailure
} from "../capture/captureClient";
import { captureMeetingId, resetSessionState, sessionError, sessionStartedAt, sessionStatusLine, sessionTitle } from "../state/session";
import { bindFileUpload } from "../lib/fileUpload";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { settledSpeakerNumbers, transcriptCardSpeakerLabel } from "../lib/transcriptCards";
import { serializeTranscriptExport, triggerTranscriptExportDownload, type TranscriptExportFormat } from "../lib/transcriptExport";
import { summaryApi } from "../lib/finalSummary";
import { openMeeting } from "../api/meetings";
import { loadAppSettings, SETTINGS_CHANGED } from "../lib/settings";
import { sessionId, sessionStatus, transcript, liveLabelPolicy } from "../state/session";
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

/** Keep-list copy (plan-r3-ui §1 Q6). Nothing else is shown as status text. */
export const RECONNECTING_LINE = "Reconnecting — keep this tab open."; // K4
export const CONNECTION_LOST_LINE = "Recording stopped: connection lost."; // K5
export const GEMINI_KEY_LINE = "Enter your Gemini API key in Settings"; // K9

/**
 * K9 inline check on the I-1 fields; WP-D's `missingGeminiKey(settings, "transcription")` replaces
 * it at merge. Until the I-1 `transcription` settings exist there is nowhere to enter a key, so the
 * gate engages only once they do.
 */
function transcriptionKeyMissing(settings: unknown): boolean {
  const transcription = (settings as { transcription?: { vendor?: string; apiKey?: string } }).transcription;
  return transcription !== undefined && transcription.vendor === "gemini" && !transcription.apiKey?.trim();
}

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
  // Empty unless a keep-list line applies; buttons and the top pill carry every other state.
  const [message, setMessage] = useState("");
  const [setupErrors, setSetupErrors] = useState<Partial<Record<CaptureLane, string>>>({});
  const [starting, setStarting] = useState(false);
  const [settings, setSettings] = useState(loadAppSettings);
  const clientRef = useRef<CaptureClient | null>(null);
  const pollerRef = useRef<MossSessionPoller | null>(null);
  const phaseRef = useRef<CapturePhase>("idle");
  const metersRef = useRef<LaneMeters>(EMPTY_METERS);
  const preflightLine = useRef<string | null>(null);

  const transition = (next: CapturePhase) => {
    phaseRef.current = next;
    setPhase(next);
  };

  const updateMeter = (lane: CaptureLane, rms: number) => {
    const next = { ...metersRef.current, [lane]: rms };
    metersRef.current = next;
    setMeters(next);
    // The silent-microphone remedy (K1) is stale once the microphone carries sound.
    if (lane === "microphone" && rms > 0 && preflightLine.current) {
      const stale = preflightLine.current;
      preflightLine.current = null;
      setMessage(current => current === stale ? "" : current);
    }
    if (next.microphone > 0 && next.system > 0 && phaseRef.current === "configuring") {
      transition("ready");
    }
  };

  const reportSetupError = (lane: CaptureLane, line: string, keepEarlier = false) => {
    // A classified pre-session failure precedes the raw error it rethrows; keep the classified line.
    setSetupErrors(current => keepEarlier && current[lane] ? current : { ...current, [lane]: line });
    metersRef.current = EMPTY_METERS;
    setMeters(EMPTY_METERS);
    transition("error");
  };

  const reportPreSessionFailure = (failure: PreSessionCaptureFailure) => {
    setConnected({ microphone: false, system: false });
    reportSetupError(failure.lane, preSessionLine(failure));
  };

  const transportFailed = (source: "capture" | "transcript") => {
    // Both transports retry on their own; the only useful instruction is K4.
    recovering.current.add(source);
    setMessage(RECONNECTING_LINE);
  };

  const transportRecovered = (source: "capture" | "transcript") => {
    const wasRecovering = recovering.current.delete(source);
    if (wasRecovering && recovering.current.size === 0 &&
        (phaseRef.current === "active" || phaseRef.current === "viewing")) {
      setMessage(current => current === RECONNECTING_LINE ? "" : current);
    }
  };

  const handleTerminal = (_terminalMessage: string, clearSaved: boolean) => {
    // Raw terminal reasons (interrupted_by_operator, service shutdown, …) never reach the page:
    // a clean close says nothing, anything else is K5.
    const normalClose = sessionStatus.value === "closed" && sessionError.value === null;
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
    setMessage(normalClose ? "" : CONNECTION_LOST_LINE);
    requestMeetingHistoryRefresh();
  };

  const configureMicrophone = async () => {
    if (clientRef.current) return;
    transition("configuring");
    setMessage("");
    const client = new CaptureClient({
      helperVersion: HELPER_VERSION,
      workletUrl: workletUrl(),
      onMeter: (lane, rms) => {
        if (clientRef.current === client && phaseRef.current !== "error") updateMeter(lane, rms);
      },
      onPreflightStatus: line => {
        if (clientRef.current !== client) return;
        preflightLine.current = line;
        setMessage(line);
      },
      onPreSessionFailure: failure => {
        if (clientRef.current === client) reportPreSessionFailure(failure);
      },
      onTransportError: () => {
        if (clientRef.current === client) transportFailed("capture");
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
    } catch (error) {
      if (clientRef.current === client) reportSetupError("microphone", laneFailedLine("microphone", error), true);
    }
  };

  const shareAudio = async () => {
    const client = clientRef.current;
    if (!client || phase === "stopping") return;
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
      if (phaseRef.current === "active") setMessage("");
    } catch (error) {
      if (clientRef.current !== client) return;
      // Mid-recording a stopped share is sealed at the server; only a new recording restores it.
      if (phaseRef.current === "active") {
        if (!chooserDismissed(error)) setMessage("Could not share again — stop and start a new recording.");
      } else reportSetupError("system", laneFailedLine("system", error), true);
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
      if (phaseRef.current === "active") setMessage("");
    } catch (error) {
      if (phaseRef.current === "active") {
        if (!chooserDismissed(error)) setMessage("Could not reconnect the microphone — stop and start a new recording.");
        return;
      }
      setMessage(laneFailedLine("microphone", error));
      transition("error");
    }
  };

  const startCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "ready" || transcriptionKeyMissing(loadAppSettings())) return;
    transition("configuring");
    setStarting(true);
    recovering.current.clear();
    setMessage("");
    resetSessionState();
    sessionTitle.value = "";
    try {
      const settings = loadAppSettings();
      const session = await client.createSession({ speaker_window: settings.speakerWindow,
        cleanup_after_stop: settings.cleanupAfterStop });
      watchMeetingSummary(session.id);
      saveSessionReattach(sessionReattachStorage(), {
        sessionId: session.id
      });
      sessionStartedAt.value = { sessionId: session.id, ms: Date.now() };
      const poller = createMossSessionPoller({
        sessionId: session.id,
        onError: () => transportFailed("transcript"),
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
      poller.start();
      requestMeetingHistoryRefresh();
    } catch (error) {
      transition("error");
      // Create refusals are human copy (K7, validation detail); a dropped request is not.
      setMessage(error instanceof TypeError ? "Start failed: no connection to the server." : errorMessage(error));
    } finally {
      setStarting(false);
    }
  };

  const stopCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "active") return;
    transition("stopping");
    captureMeetingId.value = null;
    setMessage("");
    try {
      // Five seconds bounds local frame delivery and this request's wait only.
      // A 202 leaves the existing poller running while the server finishes draining.
      await client.stop(5);
    } catch (error) {
      transition("error");
      setMessage(`Stop failed: ${errorMessage(error)}`);
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
    preflightLine.current = null;
    setMessage("");
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
        onError: () => transportFailed("transcript"),
        onRecovered: () => transportRecovered("transcript"),
        onTerminal(terminalMessage) {
          handleTerminal(terminalMessage, false);
        }
      });
      pollerRef.current = poller;
      transition("viewing");
      setMessage("");
      poller.start();
    };
    document.addEventListener(LIVE_MEETING_OBSERVE_EVENT, observeHistoryMeeting);

    const saved = loadSessionReattach(sessionReattachStorage());
    if (saved) {
      const poller = createMossSessionPoller({
        sessionId: saved.sessionId,
        onError: () => transportFailed("transcript"),
        onRecovered: () => transportRecovered("transcript"),
        onTerminal(terminalMessage) {
          handleTerminal(terminalMessage, true);
        }
      });
      pollerRef.current = poller;
      transition("viewing");
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

  useEffect(() => {
    const changed = () => setSettings(loadAppSettings());
    document.addEventListener(SETTINGS_CHANGED, changed);
    return () => document.removeEventListener(SETTINGS_CHANGED, changed);
  }, []);

  async function saveExport(): Promise<void> {
    const id = sessionId.value;
    if (!id) return;
    if (selectedSummaryMeeting.value?.id === id && selectedSummaryMeeting.value.refinement_state === "running") return;
    setExportError("");
    if (exportFormat === "audio") {
      try {
        const meeting = await openMeeting(id);
        if (meeting.audio?.state !== "available" && meeting.audio?.state !== "partial") {
          setExportError("Export failed: this meeting has no audio."); return;
        }
        const anchor = document.createElement("a");
        anchor.href = `/api/meetings/${encodeURIComponent(id)}/audio/download`;
        anchor.download = `meeting-${id}.mp3`;
        document.body.append(anchor); anchor.click(); anchor.remove();
      } catch (error) { setExportError(`Export failed: ${errorMessage(error)}`); }
      return;
    }
    const turns = groupSegmentsIntoTurns(transcript.value);
    const finalized = sessionStatus.value !== "active" && sessionStatus.value !== "closing";
    const numbers = settledSpeakerNumbers(turns, finalized);
    let summary = null;
    if (exportFormat === "md" && finalized) {
      try {
        const version = selectedSummaryMeeting.value?.id === id
          ? selectedSummaryMeeting.value.transcript_version : (await openMeeting(id)).transcript_version;
        const artifact = await summaryApi(id);
        summary = artifact?.state === "current" && artifact.source_version === version ? artifact.document : null;
      }
      catch { /* A transcript remains exportable when its optional summary cannot be fetched. */ }
    }
    if (selectedSummaryMeeting.value?.id === id && selectedSummaryMeeting.value.refinement_state === "running") return;
    triggerTranscriptExportDownload(serializeTranscriptExport(exportFormat, turns,
      turn => localSpeakerLabel(turn) ?? transcriptCardSpeakerLabel(turn, numbers, liveLabelPolicy.value, finalized),
      { sessionId: id, exportedAt: new Date() }, summary));
  }

  const configured = clientRef.current !== null;
  const reattached = phase === "viewing";
  const canStart = phase === "ready" && meters.microphone > 0 && meters.system > 0;
  const canReplace = phase === "ready" || phase === "active";
  const keyMissing = transcriptionKeyMissing(settings);
  // K6: a disabled Start names the source that has no sound yet.
  const silentSources = meters.microphone <= 0 && meters.system <= 0
    ? "Microphone and shared audio have no sound yet"
    : meters.microphone <= 0 ? "Microphone has no sound yet"
      : meters.system <= 0 ? "Shared audio has no sound yet" : undefined;
  const startTitle = keyMissing ? GEMINI_KEY_LINE : canStart ? undefined : silentSources;

  const setupLines = [setupErrors.microphone, setupErrors.system].filter(Boolean);
  const statusLine = setupLines.length > 0 ? setupLines.join(" ")
    : message || (phase === "active" ? sessionStatusLine.value ?? "" : "")
      || (keyMissing && (phase === "idle" || phase === "configuring" || phase === "ready") ? GEMINI_KEY_LINE : "");

  const modeLocked = phase === "active" || phase === "stopping" || phase === "viewing" || phase === "configuring" || sessionStatus.value === "active" || sessionStatus.value === "closing";
  const exportReady = sessionId.value !== null && (exportFormat === "audio" || transcript.value.length > 0);
  const refinementRunning = selectedSummaryMeeting.value?.id === sessionId.value &&
    selectedSummaryMeeting.value.refinement_state === "running";
  const urlWarning = mode === "url" && url.trim() !== "" && !url.startsWith("https://");
  const uploadReady = mode === "file" ? fileQueue.length > 0 : url.startsWith("https://");

  return (
    <div className="controls-workspace" data-mode={mode}>
      <div className="controls-scroll">
        <section className="control-section">
          <div className="label">Mode</div>
          <div className="seg mode-tabs" role="group" aria-label="Mode">
            {(["live", "file", "url"] as const).map(choice => <button key={choice} type="button"
              className={`seg-btn${mode === choice ? " is-active" : ""}`} aria-pressed={mode === choice}
              disabled={modeLocked} onClick={() => { if (choice !== mode) setFileQueue([]); setMode(choice); }}>{choice === "url" ? "URL" : choice === "file" ? "File" : "Live"}</button>)}
          </div>
        </section>

        {mode === "live" ? <>
          <section
            className="control-section capture-supervisor"
            data-mode="live"
            data-capture-phase={phase}
            data-observer-mode={reattached ? "read-only" : "none"}
          >
            {phase === "active" ? <button type="button" className="record-btn" data-action="stop" onClick={() => void stopCapture()}><StopIcon />Stop recording</button>
              : phase === "stopping" ? <button type="button" className="record-btn" data-action="stop" disabled><StopIcon />Stopping…</button>
              : phase === "viewing" || phase === "terminal" || phase === "error" ? null
              : !connected.microphone ? <button type="button" className="record-btn" disabled={phase === "configuring"} onClick={() => void configureMicrophone()}>{phase === "configuring" ? "Connecting…" : "Enable microphone"}</button>
              : !connected.system ? <button type="button" className="record-btn" onClick={() => void shareAudio()}>Share audio</button>
              : <button type="button" className="record-btn" data-action="start" disabled={!canStart || keyMissing || starting}
                  title={startTitle} onClick={() => void startCapture()}><PlayIcon />{starting ? "Starting…" : "Start recording"}</button>}

            {statusLine ? <p className="capture-status" role="status">{statusLine}</p> : null}

            {phase === "configuring" || phase === "terminal" || phase === "error" ? <button type="button" className="btn" onClick={() => void resetCapture()}>Reset</button> : null}
            {phase === "viewing" ? <button type="button" className="btn" onClick={() => void resetCapture()}>Detach</button> : null}
            {configured && connected.microphone && (phase === "configuring" || canReplace) ? (
              <div className="btn-row">
                <button type="button" className="btn" onClick={() => void switchMicrophone()}>Reconnect mic</button>
                {connected.system ? <button type="button" className="btn" onClick={() => void shareAudio()}>Share again</button> : null}
              </div>
            ) : null}
          </section>

          <section className="control-section">
            <label className="label" htmlFor="microphone-select">Microphone</label>
            <div className="field">
              <select id="microphone-select" aria-label="Microphone" value={microphoneId}
                disabled={reattached || phase === "stopping"}
                onFocus={() => void refreshMicrophones()}
                onChange={event => { const id = event.currentTarget.value; setMicrophoneId(id);
                  if (clientRef.current && connected.microphone) void switchMicrophone(id); }}>
                <option value="">System default</option>
                {microphones.map((device, index) => <option key={device.deviceId} value={device.deviceId}>
                  {device.label || `Microphone ${index + 1}`}</option>)}
              </select>
            </div>

            <label className="label" htmlFor="audio-route">Listening with</label>
            <div className="field">
              <select
                id="audio-route"
                aria-label="Listening with"
                value={audioRoute}
                disabled={reattached || phase === "stopping" || phase === "terminal"}
                onChange={(event) => setAudioRoute(event.currentTarget.value as AudioRoute)}
              >
                <option value="speakers">Speakers</option>
                <option value="headphones">Headphones</option>
              </select>
            </div>

            <div className="capture-meters" aria-label="Capture lane meters">
              <LaneMeter label="Microphone" value={meters.microphone} />
              <LaneMeter label="Shared audio" value={meters.system} />
            </div>
          </section>
        </> :
        <form key={mode} data-file-upload="form" className="controls-mode-form" onSubmit={event => { if (mode === "url" && !url.startsWith("https://")) event.preventDefault(); }}>
          <section className="control-section">
            <button type="submit" className="record-btn" data-action="start" disabled={!uploadReady || keyMissing}
              title={keyMissing ? GEMINI_KEY_LINE : undefined}>
              <PlayIcon />{mode === "file" ? "Start file transcription" : "Start URL transcription"}</button>
            {keyMissing ? <p className="capture-status">{GEMINI_KEY_LINE}</p> : null}
          </section>
          <section className="control-section">
            {mode === "file" ? <><label className="label" htmlFor="meeting-files">Files</label>
              <input ref={fileInputRef} id="meeting-files" name="file" type="file" multiple
                onChange={event => setFileQueue(Array.from(event.currentTarget.files ?? []).map(file => file.name))} />
              <button type="button" className="btn" disabled={!fileQueue.length} onClick={() => { if (fileInputRef.current) fileInputRef.current.value = ""; setFileQueue([]); }}>Clear</button>
              {fileQueue.length ? <ul className="controls-file-queue">{fileQueue.map((name, index) => <li key={`${name}-${index}`}>{name}</li>)}</ul> : null}
              <input name="urls" value="" hidden readOnly /></> :
              <><input name="file" type="file" multiple hidden /><label className="label" htmlFor="meeting-url">URL</label>
                <div className="field field--input-prompt" data-state={urlWarning ? "warning" : undefined}>
                  <input id="meeting-url" name="urls" type="url" value={url} placeholder="https://example.com/audio.mp3"
                    onInput={event => setUrl(event.currentTarget.value)} />
                </div>
                {urlWarning ? <p className="hint" data-state="warning">Use an https:// link.</p> : null}</>}
            <p data-file-upload="status" role="status" /><ul data-file-upload="results" />
          </section>
        </form>}
      </div>
      <section className="control-section controls-export">
        <label className="label" htmlFor="meeting-export-format">Export</label>
        <div className="export-row">
          <div className="field">
            <select id="meeting-export-format" aria-label="Export format" value={exportFormat} disabled={refinementRunning}
              onChange={event => setExportFormat(event.currentTarget.value as TranscriptExportFormat | "audio")}>
              <option value="md">Markdown (.md)</option><option value="txt">Plain text (.txt)</option>
              <option value="srt">SRT (.srt)</option><option value="vtt">VTT (.vtt)</option>
              <option value="json">JSON (.json)</option><option value="audio">Audio (.mp3)</option>
            </select>
          </div>
          <button type="button" className="btn" disabled={!exportReady || refinementRunning} onClick={() => void saveExport()}>
            <DownloadIcon />{refinementRunning ? "Improving…" : "Save"}</button>
        </div>
        {exportError ? <p className="hint" data-state="warning" role="alert">{exportError}</p> : null}
      </section>
    </div>
  );
}

/**
 * I-4 microphone-lane names for exports: `local-1` is "You", `local-(n+1)` is "User n" unless the
 * speaker was named. Lead: fold into WP-C's shared I-4 label mapping at merge (one rule per side).
 */
function localSpeakerLabel(turn: { speaker_entity_id: string; display_name: string }): string | null {
  const match = /^local-(\d+)$/.exec(turn.speaker_entity_id);
  if (!match) return null;
  const display = turn.display_name.trim();
  if (display && display !== turn.speaker_entity_id && !/^(Speaker|Local) \d+$/.test(display)) return null;
  const index = Number(match[1]);
  return index <= 1 ? "You" : `User ${index - 1}`;
}

/** Pre-session capture codes as keep-list lines (K3 for a stopped source; K8 otherwise). */
function preSessionLine(failure: PreSessionCaptureFailure): string {
  switch (failure.code) {
    case "browser_microphone_permission_denied": return "Microphone blocked — allow it in Chrome site settings.";
    case "browser_capture_request_rejected": return "Sharing did not start.";
    case "browser_surface_audio_missing": return "No audio in that share — choose a tab and turn on Share tab audio.";
    case "browser_track_ended": return failure.lane === "microphone" ? "Microphone stopped." : "Shared audio stopped.";
  }
}

function laneFailedLine(lane: CaptureLane, error: unknown): string {
  return `${lane === "microphone" ? "Microphone" : "Shared audio"} failed: ${errorMessage(error)}`;
}

/** Closing Chrome's chooser is a choice, not a failure. */
function chooserDismissed(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "AbortError");
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

function PlayIcon() {
  return <svg className="rec-icon rec-icon--play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>;
}

function StopIcon() {
  return <svg className="rec-icon rec-icon--stop" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>;
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
