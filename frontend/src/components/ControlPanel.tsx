import { useEffect, useRef, useState } from "preact/hooks";
import { createMossSessionPoller, type MossSessionPoller } from "../api/mossPoller";
import {
  CaptureClient,
  microphoneConstraints,
  type CaptureLane
} from "../capture/captureClient";
import { chooseMicrophone, microphoneOptions } from "../capture/microphoneChoice";
import { captureMeetingId, resetSessionState, sessionError, sessionStartedAt, sessionStatusLine, sessionTitle } from "../state/session";
import { bindFileUpload } from "../lib/fileUpload";
import { groupSegmentsIntoTurns } from "../lib/mergeTranscript";
import { transcriptCardSpeakerLabel } from "../lib/transcriptCards";
import { serializeTranscriptExport, triggerTranscriptExportDownload, type TranscriptExportFormat } from "../lib/transcriptExport";
import { summaryApi } from "../lib/finalSummary";
import { openMeeting } from "../api/meetings";
import { engineSettingsFrom, loadAppSettings } from "../lib/settings";
import { sessionId, sessionStarting, sessionStatus, sessionStopRequested, transcript } from "../state/session";
import { dispatchWsEvent } from "../api/ws";
import { controlPanelCollapsed, selectedSummaryMeeting } from "../state/ui";
import { summaryPredatesRefinement, watchMeetingSummary } from "../lib/summaryRequests";
import { renameSummarySpeakers, transcriptSpeakerNames } from "../lib/summarySpeakers";
import {
  clearSessionReattach,
  loadCaptureSources,
  loadSessionReattach,
  saveCaptureSources,
  saveSessionReattach,
  sessionReattachStorage,
  type CaptureSources
} from "../lib/persistence";
import {
  LIVE_MEETING_OBSERVE_EVENT,
  requestMeetingHistoryRefresh
} from "../lib/meetingEvents";

type CapturePhase =
  | "idle"
  | "configuring"
  | "active"
  | "viewing"
  | "stopping"
  | "terminal"
  | "error";
type LaneMeters = Record<CaptureLane, number>;

/** Nothing is running in these phases, so Start is offered: no Reset between recordings. */
function startable(phase: CapturePhase): boolean {
  return phase === "idle" || phase === "terminal" || phase === "error";
}

const EMPTY_METERS: LaneMeters = { microphone: 0, system: 0 };
const HELPER_VERSION = "moss-web/1";
export { LIVE_MEETING_OBSERVE_EVENT } from "../lib/meetingEvents";

/** Keep-list copy (plan-r3-ui §1 Q6). Nothing else is shown as status text. */
export const RECONNECTING_LINE = "Reconnecting — keep this tab open."; // K4
export const CONNECTION_LOST_LINE = "Recording stopped: connection lost."; // K5
// Round 5 (Q16): what one Start click could not record.
export const MICROPHONE_UNAVAILABLE_LINE = "Microphone unavailable";
export const SYSTEM_NOT_SHARED_LINE = "System sound output not shared";
export const NO_AUDIO_SHARED_LINE = "No audio was shared — turn on “Also share audio” in Chrome’s picker";
export const NO_SOURCE_TOOLTIP = "Tick System Sound Output or Microphone."; // K6

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
  // The sources the next Start takes: ticked by the person, remembered per browser.
  const [sources, setSources] = useState<CaptureSources>(() => loadCaptureSources());
  const [microphones, setMicrophones] = useState<MediaDeviceInfo[]>([]);
  // The person's dropdown pick ("" = none yet) and the device the running lane opened.
  const [microphoneId, setMicrophoneId] = useState("");
  const [openMicrophoneId, setOpenMicrophoneId] = useState("");
  const [micMuted, setMicMuted] = useState(false);
  const [phase, setPhase] = useState<CapturePhase>("idle");
  // The sources this recording really takes; the other lane, if any, is silent.
  const [connected, setConnected] = useState({ microphone: false, system: false });
  const [meters, setMeters] = useState<LaneMeters>(EMPTY_METERS);
  // Empty unless a keep-list line applies; buttons and the top pill carry every other state.
  const [message, setMessage] = useState("");
  // A source this recording does not take: what Start could not record (Q16), or the source that
  // stopped since (K3). It yields to any line that asks for action.
  const [sourceNote, setSourceNote] = useState("");
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

  const chooseSources = (next: CaptureSources) => {
    setSources(next);
    saveCaptureSources(next);
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

  // A Start that records nothing, or that Reset cancelled: close what it opened and return to idle
  // with at most one line. The meeting on screen is untouched. A client already retired changes
  // nothing here.
  const abandonStart = async (client: CaptureClient | null, line: string) => {
    if (!client || clientRef.current !== client) return;
    clientRef.current = null;
    metersRef.current = EMPTY_METERS;
    setMeters(EMPTY_METERS);
    setConnected({ microphone: false, system: false });
    setStarting(false);
    sessionStarting.value = false;
    preflightLine.current = null;
    transition("idle");
    setMessage(line);
    setSourceNote("");
    // A meeting this Start had already created is ended at the server too, not left to its lease.
    await client.stop(0).catch(() => client.close()).catch(() => undefined);
  };

  // A recorded source stopped mid-recording (Chrome's "Stop sharing", an unplugged microphone).
  // Its lane now sends silence, so the recording goes on and Stop completes normally (K3).
  const sourceStopped = (lane: CaptureLane) => {
    metersRef.current = { ...metersRef.current, [lane]: 0 };
    setMeters(metersRef.current);
    setConnected(current => ({ ...current, [lane]: false }));
    if (lane === "microphone") setMicMuted(false);
    setSourceNote(sourceStoppedLine(lane));
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
    setSourceNote("");
    requestMeetingHistoryRefresh();
  };

  // "Share again" swaps a recorded system lane for another share (same lane, next device epoch).
  const shareAgain = async () => {
    const client = clientRef.current;
    if (!client || phaseRef.current !== "active" || !connected.system) return;
    try {
      const stream = await client.requestDisplayMedia();
      if (clientRef.current !== client) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      metersRef.current = { ...metersRef.current, system: 0 };
      setMeters(metersRef.current);
      await client.replaceLane("system", stream, stream.getTracks());
      if (clientRef.current === client) setMessage("");
    } catch (error) {
      // The recorded share is untouched when its replacement cannot be attached.
      if (clientRef.current === client && !chooserDismissed(error)) {
        setMessage("Could not share again — stop and start a new recording.");
      }
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

  // A dropdown pick during a recording replaces the recorded microphone in place (same lane,
  // next device epoch). Before Start the pick only names the device Start will open.
  const switchMicrophone = async (deviceId: string) => {
    const client = clientRef.current;
    if (!client || phaseRef.current !== "active") return;
    const previousId = microphoneId;
    try {
      const stream = await navigator.mediaDevices.getUserMedia(microphoneConstraints(deviceId));
      metersRef.current = { ...metersRef.current, microphone: 0 };
      setMeters(metersRef.current);
      await client.replaceLane("microphone", stream, stream.getTracks());
      setOpenMicrophoneId(deviceId);
      void refreshMicrophones();
      if (clientRef.current === client) setMessage("");
    } catch (error) {
      // The running microphone is untouched, so the dropdown goes back to it.
      setMicrophoneId(previousId);
      if (clientRef.current === client && !chooserDismissed(error)) {
        setMessage("Could not switch the microphone — stop and start a new recording.");
      }
    }
  };

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

  /**
   * One click (round 5): the share picker if System Sound Output is ticked, then the microphone if it is
   * ticked, then the meeting. A source that is not recorded gets a silent lane, because the server
   * needs both lanes. Q16: (a) no microphone or permission denied -> system sound only; (b) picker
   * closed -> nothing starts, nothing said; (c) a surface without audio -> microphone only, or
   * nothing when there is no microphone either.
   */
  const startCapture = async () => {
    const want = sources;
    if (!startable(phaseRef.current) || (!want.system && !want.microphone)) return;
    // A Stop that failed leaves its closed client and its poller behind; Start replaces them.
    void clientRef.current?.close().catch(() => undefined);
    pollerRef.current?.stop();
    pollerRef.current = null;
    const client = new CaptureClient({
      helperVersion: HELPER_VERSION,
      workletUrl: workletUrl(),
      onMeter: (lane, rms) => {
        if (clientRef.current === client) updateMeter(lane, rms);
      },
      onPreflightStatus: line => {
        if (clientRef.current !== client) return;
        preflightLine.current = line;
        setMessage(line);
      },
      // A source that stops between its attachment and the meeting (K3): nothing starts.
      onPreSessionFailure: failure => void abandonStart(client, sourceStoppedLine(failure.lane)),
      onSourceStopped: lane => {
        if (clientRef.current === client) sourceStopped(lane);
      },
      onTransportError: () => {
        if (clientRef.current === client) transportFailed("capture");
      },
      onTransportRecovered: () => {
        if (clientRef.current === client) transportRecovered("capture");
      }
    });
    clientRef.current = client;
    transition("configuring");
    setStarting(true);
    recovering.current.clear();
    setMessage("");
    setSourceNote("");
    setMicMuted(false);
    sessionStarting.value = true;
    let display: MediaStream | null = null;
    // Reset, or a source that stopped, retired this Start: release whatever it still holds.
    const retired = async () => {
      if (clientRef.current === client) return false;
      display?.getTracks().forEach(track => track.stop());
      await client.close().catch(() => undefined);
      return true;
    };
    const laneStep = async <T,>(lane: CaptureLane, step: Promise<T>): Promise<T> => {
      try { return await step; } catch (error) { throw new Error(laneFailedLine(lane, error)); }
    };
    try {
      if (want.system) {
        try {
          // First, with nothing awaited before it: Chrome's picker needs this click's activation.
          display = await client.requestDisplayMedia();
        } catch (error) {
          // (b) Closing the picker is a choice: nothing starts and nothing is said.
          await abandonStart(client, chooserDismissed(error) ? "" : laneFailedLine("system", error));
          return;
        }
        if (await retired()) return;
      }
      await client.prepare();
      if (await retired()) return;
      const system = display !== null && await laneStep("system", client.attachDisplayMedia(display));
      if (await retired()) return;
      let microphone: string | null = null;
      if (want.microphone) {
        // Unnamed only while Chrome hides the devices; the client then names the device itself.
        const devices = await refreshMicrophones();
        microphone = await laneStep("microphone",
          client.startMicrophone(chooseMicrophone(devices, microphoneId) ?? undefined));
        void refreshMicrophones();
        if (await retired()) return;
      }
      const microphoneFailed = want.microphone && microphone === null;
      // A microphone found unavailable unticks itself, so the next Start does not ask for it again.
      if (microphoneFailed && (system || !display)) chooseSources({ ...want, microphone: false });
      if (!system && microphone === null) {
        await abandonStart(client, display ? NO_AUDIO_SHARED_LINE : MICROPHONE_UNAVAILABLE_LINE);
        return;
      }
      if (!system) await client.attachSilentLane("system");
      if (microphone === null) await client.attachSilentLane("microphone");
      if (await retired()) return;
      setConnected({ microphone: microphone !== null, system });
      if (microphone !== null) setOpenMicrophoneId(microphone);
      setSourceNote(microphoneFailed ? MICROPHONE_UNAVAILABLE_LINE : want.system && !system ? SYSTEM_NOT_SHARED_LINE : "");

      const session = await client.createSession(engineSettingsFrom(loadAppSettings()));
      if (clientRef.current !== client) {
        // Reset while the meeting was being created: end it at the server too.
        await client.stop(0).catch(() => undefined);
        return;
      }
      // Only now does the page leave the meeting it was showing: a Start that records nothing
      // (a closed picker, a refused meeting) changes nothing.
      resetSessionState();
      sessionTitle.value = "";
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
      setStarting(false);
      sessionStarting.value = false;
      transition("active");
      poller.start();
      requestMeetingHistoryRefresh();
    } catch (error) {
      display?.getTracks().forEach(track => track.stop());
      // Create refusals are human copy (K7, validation detail); a dropped request is not.
      await abandonStart(client,
        error instanceof TypeError ? "Start failed: no connection to the server." : errorMessage(error));
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
    setSourceNote("");
    try {
      // Five seconds bounds local frame delivery and this request's wait only.
      // A 202 leaves the existing poller running while the server finishes draining.
      await client.stop(5);
    } catch (error) {
      // A Stop that fails after its meeting ended (and perhaps the next began) changes nothing.
      if (clientRef.current !== client) return;
      transition("error");
      setMessage(`Stop failed: ${errorMessage(error)}`);
    }
  };

  // Leave a meeting this page was only watching.
  const detach = () => {
    clearSessionReattach(sessionReattachStorage());
    pollerRef.current?.stop();
    pollerRef.current = null;
    resetSessionState();
    sessionTitle.value = "";
    transition("idle");
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
    // Plugging headphones in or out moves the system default: before Start the dropdown follows
    // it; a recording keeps its microphone until the person picks another.
    const onDeviceChange = () => void refreshMicrophones();
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
    const snapshot = transcript.value;
    const turns = groupSegmentsIntoTurns(snapshot);
    const names = transcriptSpeakerNames(snapshot);
    const finalized = sessionStatus.value !== "active" && sessionStatus.value !== "closing";
    let summary = null;
    if (exportFormat === "md" && finalized) {
      try {
        const meeting = selectedSummaryMeeting.value?.id === id ? selectedSummaryMeeting.value : await openMeeting(id);
        const artifact = await summaryApi(id);
        // Only the clean-up outdates a summary; a rename raises the version too and keeps it (D1, #15),
        // read under the names captured with the exported transcript.
        summary = artifact?.state === "current" && artifact.document && !summaryPredatesRefinement(meeting, artifact)
          ? renameSummarySpeakers(artifact.document, artifact.speaker_names, names)
          : null;
      }
      catch { /* A transcript remains exportable when its optional summary cannot be fetched. */ }
    }
    if (selectedSummaryMeeting.value?.id === id && selectedSummaryMeeting.value.refinement_state === "running") return;
    triggerTranscriptExportDownload(serializeTranscriptExport(exportFormat, turns,
      transcriptCardSpeakerLabel,
      { sessionId: id, exportedAt: new Date() }, summary));
  }

  const recording = phase === "active" || phase === "stopping";
  const ready = startable(phase);
  // The boxes choose the sources of the next Start; a recording shows the ones it really takes.
  const ticked = recording ? connected : sources;
  const noSource = !sources.system && !sources.microphone;
  const microphoneLevel = micMuted ? 0 : meters.microphone;

  // The dropdown names the device that is open, or the one Start will open.
  const microphoneChoices = microphoneOptions(microphones);
  const shownMicrophoneId = recording ? openMicrophoneId : chooseMicrophone(microphones, microphoneId) ?? "";

  const statusLine = message || (phase === "active" ? sessionStatusLine.value || sourceNote : "");
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
            data-observer-mode={phase === "viewing" ? "read-only" : "none"}
          >
            {phase === "active" ? <button type="button" className="record-btn" data-action="stop" onClick={() => void stopCapture()}><StopIcon />Stop recording</button>
              : phase === "stopping" ? <button type="button" className="record-btn" data-action="stop" disabled><StopIcon />Stopping…</button>
              : phase === "viewing" ? null
              : <button type="button" className="record-btn" data-action="start" disabled={starting || noSource}
                  title={noSource ? NO_SOURCE_TOOLTIP : undefined}
                  onClick={() => void startCapture()}><PlayIcon />{starting ? "Starting…" : "Start recording"}</button>}

            {statusLine ? <p className="capture-status" role="status">{statusLine}</p> : null}

            {/* Reset exists only while a Start is pending (an open picker, an unanswered prompt): it cancels it. */}
            {phase === "configuring" ? <button type="button" className="btn" onClick={() => void abandonStart(clientRef.current, "")}>Reset</button> : null}
            {phase === "viewing" ? <button type="button" className="btn" onClick={detach}>Detach</button> : null}
            {phase === "active" && (connected.microphone || connected.system) ? (
              <div className="btn-row">
                {connected.microphone ? <button type="button" className={`btn ghost${micMuted ? " is-active" : ""}`} aria-pressed={micMuted}
                  onClick={toggleMicMute}><MicIcon muted={micMuted} />{micMuted ? "Unmute mic" : "Mute mic"}</button> : null}
                {connected.system ? <button type="button" className="btn" onClick={() => void shareAgain()}>Share again</button> : null}
              </div>
            ) : null}
          </section>

          <section className="control-section capture-sources">
            <div className="label">Sources</div>
            {(["system", "microphone"] as const).map(lane => {
              const label = lane === "system" ? "System Sound Output" : "Microphone";
              return <div key={lane} className="source-row">
                <label className="check-row">
                  <input type="checkbox" checked={ticked[lane]} disabled={!ready}
                    onChange={event => { chooseSources({ ...sources, [lane]: event.currentTarget.checked }); setMessage(""); }} />
                  <span>{label}</span>
                </label>
                {recording && connected[lane]
                  ? <LaneMeter label={label} value={lane === "microphone" ? microphoneLevel : meters.system} /> : null}
              </div>;
            })}
            {/* Chrome names no microphone before permission, so there is nothing to pick until then. */}
            {ticked.microphone && microphoneChoices.length > 0 ? (
              <div className="field">
                <select id="microphone-select" aria-label="Microphone device" value={shownMicrophoneId}
                  disabled={!ready && phase !== "active"}
                  onFocus={() => void refreshMicrophones()}
                  onChange={event => { const id = event.currentTarget.value; setMicrophoneId(id);
                    if (phase === "active") void switchMicrophone(id); }}>
                  {microphoneChoices.map(device => <option key={device.deviceId} value={device.deviceId}>
                    {device.label}</option>)}
                </select>
              </div>
            ) : null}
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

/** A recorded source that stopped, before the meeting existed or during it, as its keep-list line (K3). */
function sourceStoppedLine(lane: CaptureLane): string {
  return lane === "microphone" ? "Microphone stopped." : "System sound output stopped.";
}

function laneFailedLine(lane: CaptureLane, error: unknown): string {
  return `${lane === "microphone" ? "Microphone" : "System sound output"} failed: ${errorMessage(error)}`;
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

/** The level of a recorded source, beside its checkbox. */
function LaneMeter({ label, value }: { label: string; value: number }) {
  const level = laneMeterPercent(value);
  return (
    <span className="capture-meter-track" aria-label={`${label} level ${level}%`}>
      <span style={{ width: `${level}%` }} />
    </span>
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
