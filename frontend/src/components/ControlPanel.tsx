import { useEffect, useRef, useState } from "preact/hooks";
import { createMossSessionPoller, type MossSessionPoller } from "../api/mossPoller";
import {
  CaptureClient,
  microphoneConstraints,
  type CaptureLane,
  type PreSessionCaptureFailure
} from "../capture/captureClient";
import { chooseMicrophone, microphoneOptions } from "../capture/microphoneChoice";
import { captureMeetingId, resetSessionState, sessionError, sessionStartedAt, sessionStatusLine, sessionTitle } from "../state/session";
import { bindFileUpload } from "../lib/fileUpload";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { settledSpeakerNumbers, transcriptCardSpeakerLabel } from "../lib/transcriptCards";
import { serializeTranscriptExport, triggerTranscriptExportDownload, type TranscriptExportFormat } from "../lib/transcriptExport";
import { summaryApi } from "../lib/finalSummary";
import { openMeeting } from "../api/meetings";
import { engineSettingsFrom, loadAppSettings } from "../lib/settings";
import { sessionId, sessionStarting, sessionStatus, sessionStopRequested, transcript } from "../state/session";
import { dispatchWsEvent } from "../api/ws";
import { controlPanelCollapsed, selectedSummaryMeeting } from "../state/ui";
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
  // The person's dropdown pick ("" = none yet) and the device the running lane opened.
  const [microphoneId, setMicrophoneId] = useState("");
  const [openMicrophoneId, setOpenMicrophoneId] = useState("");
  const openMicrophone = useRef("");
  const [micMuted, setMicMuted] = useState(false);
  const [phase, setPhase] = useState<CapturePhase>("idle");
  const [connected, setConnected] = useState({ microphone: false, system: false });
  const [meters, setMeters] = useState<LaneMeters>(EMPTY_METERS);
  // Empty unless a keep-list line applies; buttons and the top pill carry every other state.
  const [message, setMessage] = useState("");
  const [setupErrors, setSetupErrors] = useState<Partial<Record<CaptureLane, string>>>({});
  const [starting, setStarting] = useState(false);
  const clientRef = useRef<CaptureClient | null>(null);
  const pollerRef = useRef<MossSessionPoller | null>(null);
  const phaseRef = useRef<CapturePhase>("idle");
  const metersRef = useRef<LaneMeters>(EMPTY_METERS);
  const preflightLine = useRef<string | null>(null);

  const transition = (next: CapturePhase) => {
    phaseRef.current = next;
    setPhase(next);
  };

  const microphoneOpened = (deviceId: string) => {
    openMicrophone.current = deviceId;
    setOpenMicrophoneId(deviceId);
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
    setMicMuted(false);
    transition("terminal");
    setMessage(normalClose ? "" : CONNECTION_LOST_LINE);
    requestMeetingHistoryRefresh();
  };

  const configureMicrophone = async () => {
    if (clientRef.current) return;
    transition("configuring");
    setMessage("");
    setMicMuted(false);
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
      const devices = await refreshMicrophones();
      await client.prepare();
      if (clientRef.current !== client) { await client.close(); return; }
      // Unnamed only while Chrome hides the devices; the client then names the device itself.
      microphoneOpened(await client.startMicrophone(audioRoute === "speakers",
        chooseMicrophone(devices, microphoneId) ?? undefined));
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
      // Both sources attached is all Start needs: neither has to carry sound yet, since the
      // person may start recording first and play the audio afterwards.
      if (!connected.system && phaseRef.current === "configuring") transition("ready");
      if (phaseRef.current === "active") setMessage("");
    } catch (error) {
      if (clientRef.current !== client) return;
      // Mid-recording a stopped share is sealed at the server; only a new recording restores it.
      if (phaseRef.current === "active") {
        if (!chooserDismissed(error)) setMessage("Could not share again — stop and start a new recording.");
      } else reportSetupError("system", laneFailedLine("system", error), true);
    }
  };

  const refreshMicrophones = async (): Promise<MediaDeviceInfo[]> => {
    try {
      const inputs = ((await navigator.mediaDevices?.enumerateDevices?.()) ?? [])
        .filter(device => device.kind === "audioinput");
      setMicrophones(inputs);
      return inputs;
    } catch { return []; }
  };

  // A dropdown pick, or the system default moving during setup, replaces the running microphone
  // in place (same lane, next device epoch).
  const switchMicrophone = async (deviceId: string, picked: boolean) => {
    const client = clientRef.current;
    if (!client || phase === "stopping") return;
    const previousId = microphoneId;
    try {
      const stream = await navigator.mediaDevices.getUserMedia(
        microphoneConstraints(audioRoute === "speakers", deviceId));
      metersRef.current = { ...metersRef.current, microphone: 0 };
      setMeters(metersRef.current);
      await client.replaceLane("microphone", stream, stream.getTracks());
      setConnected(current => ({ ...current, microphone: true }));
      microphoneOpened(deviceId);
      void refreshMicrophones();
      if (phaseRef.current === "active") setMessage("");
    } catch (error) {
      // An automatic switch that fails leaves the running microphone as it was.
      if (!picked) return;
      if (phaseRef.current === "active") {
        // The running microphone is untouched, so the dropdown goes back to it.
        setMicrophoneId(previousId);
        if (!chooserDismissed(error)) setMessage("Could not switch the microphone — stop and start a new recording.");
        return;
      }
      setMessage(laneFailedLine("microphone", error));
      transition("error");
    }
  };

  // Plugging headphones in or out moves the system default. Setup follows it; a recording keeps
  // its microphone until the person picks another, so nothing changes under them mid-meeting.
  const followMicrophones = async () => {
    const devices = await refreshMicrophones();
    const settingUp = (phaseRef.current === "configuring" && !starting) || phaseRef.current === "ready";
    if (!clientRef.current || !connected.microphone || !settingUp) return;
    const next = chooseMicrophone(devices, microphoneId, openMicrophone.current);
    if (next && next !== openMicrophone.current) await switchMicrophone(next, false);
  };
  const deviceChange = useRef(followMicrophones);
  deviceChange.current = followMicrophones;

  // Muting keeps the lane running and sends silence; the server keeps accounting the time.
  const toggleMicMute = () => {
    const client = clientRef.current;
    if (!client) return;
    const next = !micMuted;
    client.setMicrophoneMuted(next);
    setMicMuted(next);
    if (next && preflightLine.current) {
      // "No microphone sound" (K1) is not the reason once the microphone is muted on purpose.
      const stale = preflightLine.current;
      preflightLine.current = null;
      setMessage(current => current === stale ? "" : current);
    }
  };

  const startCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "ready") return;
    transition("configuring");
    setStarting(true);
    recovering.current.clear();
    setMessage("");
    resetSessionState();
    sessionTitle.value = "";
    sessionStarting.value = true;
    try {
      const session = await client.createSession(engineSettingsFrom(loadAppSettings()));
      watchMeetingSummary(session.id);
      saveSessionReattach(sessionReattachStorage(), {
        sessionId: session.id
      });
      sessionStartedAt.value = { sessionId: session.id, ms: Date.now() };
      // A created meeting is active; the first poll can take seconds to say so (r4 F3).
      dispatchWsEvent({ type: "session_state", session_id: session.id, mode: "live", state: "active", status: "active" });
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
      sessionStarting.value = false;
    }
  };

  const stopCapture = async () => {
    const client = clientRef.current;
    if (!client || phase !== "active") return;
    transition("stopping");
    // The pill stops counting now; the server keeps reporting "active" while it drains (#14).
    sessionStopRequested.value = captureMeetingId.value;
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
    setMicMuted(false);
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
      // After a reload the pill counts from the meeting's real start, not from the reload.
      void openMeeting(saved.sessionId).then(meeting => {
        sessionStartedAt.value = { sessionId: meeting.id, ms: meeting.created_at_ms };
      }, () => undefined);
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
    // Device changes arrive in bursts; each follow runs after the previous one settles.
    let follows = Promise.resolve();
    const onDeviceChange = () => { follows = follows.then(() => deviceChange.current()).catch(() => undefined); };
    const devices = navigator.mediaDevices;
    void refreshMicrophones();
    devices?.addEventListener?.("devicechange", onDeviceChange);
    return () => devices?.removeEventListener?.("devicechange", onDeviceChange);
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
      turn => transcriptCardSpeakerLabel(turn, numbers),
      { sessionId: id, exportedAt: new Date() }, summary));
  }

  const configured = clientRef.current !== null;
  const reattached = phase === "viewing";
  const microphoneLevel = micMuted ? 0 : meters.microphone;
  const canStart = phase === "ready";
  const canReplace = phase === "ready" || phase === "active";

  // The dropdown names the device that is open, or the one Enable microphone will open.
  const microphoneChoices = microphoneOptions(microphones);
  const shownMicrophoneId = connected.microphone ? openMicrophoneId : chooseMicrophone(microphones, microphoneId) ?? "";

  const setupLines = [setupErrors.microphone, setupErrors.system].filter(Boolean);
  const statusLine = setupLines.length > 0 ? setupLines.join(" ")
    : message || (phase === "active" ? sessionStatusLine.value ?? "" : "");
  // #8: a keep-list line asks the operator to act, so a collapsed Controls rail opens to show it.
  // The remembered preference is unchanged; the next reload collapses the rail again.
  useEffect(() => { if (statusLine) controlPanelCollapsed.value = false; }, [statusLine]);

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
              : <button type="button" className="record-btn" data-action="start" disabled={!canStart || starting}
                  onClick={() => void startCapture()}><PlayIcon />{starting ? "Starting…" : "Start recording"}</button>}

            {statusLine ? <p className="capture-status" role="status">{statusLine}</p> : null}

            {phase === "configuring" || phase === "terminal" || phase === "error" ? <button type="button" className="btn" onClick={() => void resetCapture()}>Reset</button> : null}
            {phase === "viewing" ? <button type="button" className="btn" onClick={() => void resetCapture()}>Detach</button> : null}
            {configured && connected.microphone && (phase === "configuring" || canReplace) ? (
              <div className="btn-row">
                <button type="button" className={`btn ghost${micMuted ? " is-active" : ""}`} aria-pressed={micMuted}
                  onClick={toggleMicMute}><MicIcon muted={micMuted} />{micMuted ? "Unmute mic" : "Mute mic"}</button>
                {connected.system ? <button type="button" className="btn" onClick={() => void shareAudio()}>Share again</button> : null}
              </div>
            ) : null}
          </section>

          <section className="control-section">
            {/* Chrome names no microphone before permission, so there is nothing to pick until then. */}
            {microphoneChoices.length > 0 ? <>
              <label className="label" htmlFor="microphone-select">Microphone</label>
              <div className="field">
                <select id="microphone-select" aria-label="Microphone" value={shownMicrophoneId}
                  disabled={reattached || phase === "stopping"}
                  onFocus={() => void refreshMicrophones()}
                  onChange={event => { const id = event.currentTarget.value; setMicrophoneId(id);
                    if (clientRef.current && connected.microphone) void switchMicrophone(id, true); }}>
                  {microphoneChoices.map(device => <option key={device.deviceId} value={device.deviceId}>
                    {device.label}</option>)}
                </select>
              </div>
            </> : null}

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
              <LaneMeter label="Microphone" value={microphoneLevel} />
              <LaneMeter label="Shared audio" value={meters.system} />
            </div>
          </section>
        </> :
        <form key={mode} data-file-upload="form" className="controls-mode-form" onSubmit={event => { if (mode === "url" && !url.startsWith("https://")) event.preventDefault(); }}>
          <section className="control-section">
            <button type="submit" className="record-btn" data-action="start" disabled={!uploadReady}>
              <PlayIcon />{mode === "file" ? "Start file transcription" : "Start URL transcription"}</button>
          </section>
          <section className="control-section">
            {mode === "file" ? <><label className="label" htmlFor="meeting-files">Files</label>
              <input ref={fileInputRef} id="meeting-files" name="file" type="file" multiple
                onChange={event => setFileQueue(Array.from(event.currentTarget.files ?? []).map(file => file.name))} />
              <div className="btn-row"><button type="button" className="btn ghost" disabled={!fileQueue.length} onClick={() => { if (fileInputRef.current) fileInputRef.current.value = ""; setFileQueue([]); }}>Clear</button></div>
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
              <option value="md">Markdown (.md)</option><option value="txt">Text (.txt)</option>
              <option value="audio">Audio (.mp3)</option>
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

/** LiveTranscribe's microphone glyph; struck through while the microphone is muted. */
function MicIcon({ muted }: { muted: boolean }) {
  return (
    <svg data-icon={muted ? "mic-off" : "mic"} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" /><path d="M19 10a7 7 0 0 1-14 0" />
      <path d="M12 17v4" />{muted ? <path d="M4 4l16 16" /> : null}
    </svg>
  );
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
