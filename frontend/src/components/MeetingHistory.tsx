import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import {
  listMeetings,
  openMeeting,
  renameMeeting,
  type Meeting,
  type MeetingStatus
} from "../api/meetings";
import type { SessionLifecycle, TranscriptItem } from "../api/types";
import { dispatchWsEvent } from "../api/ws";
import {
  filterMeetings,
  formatMeetingDuration,
  formatMeetingTimestamp,
  groupMeetings,
  meetingTitle,
  reconcileSelectedMeeting
} from "../lib/meetingHistory";
import {
  LIVE_MEETING_OBSERVE_EVENT,
  OPEN_MEETING_EVENT,
  MEETING_HISTORY_REFRESH_EVENT
} from "../lib/meetingEvents";
import { summaryApi } from "../lib/finalSummary";
import { loadAppSettings } from "../lib/settings";
import { finalizeMeetingSummary, summaryPredatesRefinement } from "../lib/summaryRequests";
import {
  resetSessionState,
  sessionId,
  sessionMode,
  sessionStartedAt,
  sessionStatus,
  sessionStopRequested,
  sessionTitle
} from "../state/session";
import { historyPanelCollapsed, historyView, selectedSummaryMeeting, setHistoryPanelCollapsed } from "../state/ui";
import { PanelCollapseButton, PanelRailTitle } from "./PanelCollapse";

export function MeetingHistory() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<Meeting | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [renaming, setRenaming] = useState(false);
  const selectedRef = useRef<Meeting | null>(null);
  const refreshGenerationRef = useRef(0);
  const summaryRegenerated = useRef(new Set<string>());
  const renameDialogRef = useRef<HTMLDialogElement | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  const groups = useMemo(
    () => groupMeetings(filterMeetings(meetings, query)),
    [meetings, query]
  );

  const replaceSelection = (meeting: Meeting | null) => {
    selectedRef.current = meeting;
    setSelected(meeting);
    selectedSummaryMeeting.value = meeting?.status === "completed" ? meeting : null;
  };

  const refresh = async () => {
    const generation = ++refreshGenerationRef.current;
    setLoading(true);
    setError(null);
    try {
      const next = await listMeetings();
      if (generation !== refreshGenerationRef.current) return;
      setMeetings(next);
      const previous = selectedRef.current;
      const repaired = reconcileSelectedMeeting(next, selectedRef.current);
      replaceSelection(repaired);
      const currentSession = next.find(meeting => meeting.id === sessionId.value);
      if (repaired && sessionId.value === repaired.id) {
        publishMeeting(repaired, false);
      } else if (currentSession && currentSession.status !== "active") {
        // Stop completes through the Live poller; select its durable Meeting automatically.
        replaceSelection(currentSession);
        publishMeeting(currentSession, false);
      } else if (!repaired && previous && sessionId.value === previous.id) {
        resetSessionState();
        sessionTitle.value = "";
      }
    } catch (cause) {
      if (generation === refreshGenerationRef.current) {
        setError(errorMessage(cause));
      }
    } finally {
      if (generation === refreshGenerationRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void refresh();
    const handleRefresh = () => void refresh();
    document.addEventListener(MEETING_HISTORY_REFRESH_EVENT, handleRefresh);
    return () => {
      document.removeEventListener(MEETING_HISTORY_REFRESH_EVENT, handleRefresh);
      selectedSummaryMeeting.value = null;
    };
  }, []);

  const refiningIds = meetings.filter(meeting => meeting.refinement_state === "running")
    .map(meeting => meeting.id).join("\n");
  useEffect(() => {
    if (!refiningIds) return;
    const ids = refiningIds.split("\n");
    let disposed = false;
    let reading = false;
    const timer = setInterval(async () => {
      if (reading) return;
      reading = true;
      try {
        await Promise.all(ids.map(async id => {
          try {
            const next = await openMeeting(id);
            if (disposed) return;
            const previous = selectedRef.current?.id === id
              ? selectedRef.current : meetings.find(meeting => meeting.id === id);
            if (previous && previous.refinement_state === next.refinement_state &&
                previous.transcript_version === next.transcript_version) return;
            setMeetings(current => current.map(meeting => meeting.id === id ? next : meeting));
            if (selectedRef.current?.id === id) {
              replaceSelection(next);
              if (sessionId.value === id) publishMeeting(next, false);
            } else if (next.refinement_state === "done") {
              const key = `${id}:${next.transcript_version}`;
              if (summaryRegenerated.current.has(key)) return;
              summaryRegenerated.current.add(key);
              const artifact = await summaryApi(id);
              if (summaryPredatesRefinement(next, artifact) && loadAppSettings().summary.vendor === "gemini") {
                await finalizeMeetingSummary(next);
              }
            }
          } catch { /* Keep the last durable version and try again at the next interval. */ }
        }));
      }
      finally { reading = false; }
    }, 5000);
    return () => { disposed = true; clearInterval(timer); };
  }, [refiningIds]);

  useEffect(() => {
    if (!renameTarget) return;
    const dialog = renameDialogRef.current;
    if (!dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
    renameInputRef.current?.focus();
    renameInputRef.current?.select();
    return () => {
      if (dialog.open && typeof dialog.close === "function") {
        dialog.close();
      } else {
        dialog.removeAttribute("open");
      }
      previousFocus?.focus();
    };
  }, [renameTarget]);


  const selectMeeting = async (meetingId: string) => {
    if (
      sessionStatus.value === "active" &&
      sessionMode.value === "live" &&
      selectedRef.current?.id !== meetingId
    ) {
      // While Stop drains, the server still reads "active"; the recording tab keeps receiving this meeting.
      setError(sessionStopRequested.value === sessionId.value ? "Wait for Stop to finish." : "Stop recording first.");
      return;
    }
    setError(null);
    const generation = refreshGenerationRef.current;
    try {
      const opened = await openMeeting(meetingId);
      if (generation !== refreshGenerationRef.current) return;
      replaceSelection(opened);
      publishMeeting(opened, true);
      const panel = document.getElementById("transcript-panel");
      panel?.scrollIntoView?.({ block: "start" });
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  useEffect(() => {
    const open = (event: Event) => {
      const id = (event as CustomEvent).detail?.meetingId;
      if (typeof id === "string") void selectMeeting(id);
    };
    document.addEventListener(OPEN_MEETING_EVENT, open);
    return () => document.removeEventListener(OPEN_MEETING_EVENT, open);
  }, []);

  const submitRename = async (event: Event) => {
    event.preventDefault();
    if (!renameTarget || renaming) return;
    setRenaming(true);
    setError(null);
    try {
      const renamed = await renameMeeting(renameTarget.id, renameTitle);
      refreshGenerationRef.current += 1;
      setLoading(false);
      const update = (meeting: Meeting): Meeting => meeting.id === renamed.id
        ? { ...meeting, title: renamed.title, title_source: renamed.title_source }
        : meeting;
      setMeetings((current) => current.map(update));
      if (selectedRef.current?.id === renamed.id) {
        const nextSelected = update(selectedRef.current);
        replaceSelection(nextSelected);
        if (sessionId.value === renamed.id) sessionTitle.value = renamed.title;
      }
      setRenameTarget(null);
      setRenameTitle("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setRenaming(false);
    }
  };

  return (<>
    <section className={`panel history-panel account-history-panel${historyPanelCollapsed.value ? " collapsed" : ""}`}
      aria-label="Meeting history">
      <div className="panel-head">
        <div className="seg history-tabs" role="tablist" aria-label="History views">
          <button
            type="button"
            role="tab"
            className={`seg-btn${historyView.value === "sessions" ? " is-active" : ""}`}
            aria-selected={historyView.value === "sessions"}
            onClick={() => { historyView.value = "sessions"; }}
          >
            Sessions
          </button>
          <button
            type="button"
            role="tab"
            className={`seg-btn${historyView.value === "voiceprints" ? " is-active" : ""}`}
            aria-selected={historyView.value === "voiceprints"}
            onClick={() => { historyView.value = "voiceprints"; }}
          >
            Voiceprints
          </button>
        </div>
        <PanelRailTitle name="History" onExpand={() => setHistoryPanelCollapsed(false)} />
        <PanelCollapseButton name="History" side="right" collapsed={historyPanelCollapsed.value}
          onChange={setHistoryPanelCollapsed} />
      </div>
      <div className="panel-body">
        {historyView.value === "sessions" ? <div className="history-panel-actions">
          <label className="history-search">
            <span className="sr-only">Search meetings</span>
            <input
              type="search"
              aria-label="Search meetings"
              placeholder="Search meetings"
              value={query}
              onInput={(event) => setQuery(event.currentTarget.value)}
            />
          </label>
          <button
            type="button"
            className="history-toolbar-btn"
            disabled={loading}
            onClick={() => void refresh()}
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div> : null}

        {historyView.value === "sessions" ? <>
        {error ? <p className="history-state-card is-error" role="alert">{error}</p> : null}
        {!loading && meetings.length === 0 ? (
          <p className="history-state-card">No meetings yet.</p>
        ) : null}
        {!loading && meetings.length > 0 && groups.length === 0 ? (
          <p className="history-state-card">No matches.</p>
        ) : null}

        <div className="history-stack" data-history="list">
          {groups.map((group) => (
            <section className="history-group" data-history-group={group.key} key={group.key}>
              <h3 className="hist-group-label">{group.label}</h3>
              <div className="history-group-list">
                {group.meetings.map((meeting) => (
                  <article
                    className={`history-card${selected?.id === meeting.id ? " is-active" : ""}`}
                    data-meeting-card={meeting.id}
                    key={meeting.id}
                  >
                    <button
                      type="button"
                      className="history-card-hitbox"
                      data-open-meeting={meeting.id}
                      aria-pressed={selected?.id === meeting.id}
                      onClick={() => void selectMeeting(meeting.id)}
                    >
                      <span className="history-card-headline">
                        <span className="history-card-copy">
                          <span className="history-card-title">{meetingTitle(meeting)}</span>
                          <span className="history-card-meta">
                            {[formatMeetingTimestamp(meeting.created_at_ms), modeLabel(meeting.mode),
                              ...(meeting.status === "failed" || meeting.status === "interrupted" ? [statusLabel(meeting.status)] : [])].join(" · ")}
                          </span>
                          {meetingPreview(meeting) ? <span className="history-card-subtitle">{meetingPreview(meeting)}</span> : null}
                        </span>
                        {formatMeetingDuration(meeting) ? <span className="history-duration-chip">{formatMeetingDuration(meeting)}</span> : null}
                      </span>
                    </button>
                    <div className="history-card-actions">
                      <button
                        type="button"
                        className="history-action-btn"
                        onClick={() => {
                          setRenameTarget(meeting);
                          setRenameTitle(meetingTitle(meeting));
                        }}
                      >
                        Rename
                      </button>
                      {meeting.refinement_state === "running" && (meeting.audio?.state === "available" || meeting.audio?.state === "partial") ? (
                        <button type="button" className="history-action-btn" data-audio-download-pending disabled>Improving…</button>
                      ) : meeting.audio?.state === "available" || meeting.audio?.state === "partial" ? (
                        <a
                          className="history-action-btn"
                          data-audio-download
                          href={`/api/meetings/${encodeURIComponent(meeting.id)}/audio/download`}
                        >
                          {meeting.audio.state === "partial" ? "Download partial audio" : "Download audio"}
                        </a>
                      ) : meeting.audio?.state === "unavailable" ? (
                        <span className="history-audio-unavailable" data-audio-unavailable>
                          Audio unavailable
                        </span>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
        </> : null}
      </div>

      {renameTarget ? (
        <dialog
          ref={renameDialogRef}
          className="history-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rename-meeting-title"
          onCancel={(event) => {
            event.preventDefault();
            if (!renaming) setRenameTarget(null);
          }}
        >
          <form aria-label="Rename Meeting" onSubmit={submitRename}>
            <h3 id="rename-meeting-title">Rename Meeting</h3>
            <label className="history-input-stack">
              <span>Title</span>
              <input
                ref={renameInputRef}
                aria-label="Meeting title"
                value={renameTitle}
                disabled={renaming}
                onInput={(event) => setRenameTitle(event.currentTarget.value)}
              />
            </label>
            <div className="history-dialog-actions">
              <button
                type="button"
                className="history-action-btn"
                disabled={renaming}
                onClick={() => setRenameTarget(null)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="history-action-btn is-primary"
                disabled={renaming || !renameTitle.trim()}
              >
                {renaming ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </dialog>
      ) : null}
    </section>
  </>);
}

function publishMeeting(meeting: Meeting, observeActive: boolean): void {
  sessionTitle.value = meetingTitle(meeting);
  sessionStartedAt.value = { sessionId: meeting.id, ms: meeting.created_at_ms };
  dispatchWsEvent({
    type: "session_state",
    session_id: meeting.id,
    mode: meeting.mode,
    state: meeting.status,
    status: sessionLifecycle(meeting.status),
    error: meeting.status === "failed" || meeting.status === "interrupted"
      ? meeting.failure_reason || statusLabel(meeting.status)
      : null,
    // Saved outcome notices and raw failure reasons are not shown (Q6); the pill reads lifecycle only.
    status_line: null,
    needs_review: meeting.needs_review
  });
  dispatchWsEvent({
    type: "transcript_update",
    session_id: meeting.id,
    seq: meeting.transcript_version,
    timestamp: new Date().toISOString(),
    items: transcriptItems(meeting),
    metadata: { operation: "snapshot" }
  });
  if (observeActive && meeting.mode === "live" && meeting.status === "active") {
    document.dispatchEvent(new CustomEvent(LIVE_MEETING_OBSERVE_EVENT, {
      detail: { meetingId: meeting.id }
    }));
  }
}

function transcriptItems(meeting: Meeting): TranscriptItem[] {
  return (meeting.transcript?.segments ?? []).map((segment) => ({
    ...(segment.source_lane ? { source_lane: segment.source_lane } : {}),
    start: segment.start,
    end: segment.end,
    text: segment.text,
    speaker: segment.speaker_entity_id ?? segment.speaker,
    speaker_entity_id: segment.speaker_entity_id ?? segment.speaker,
    display_name: segment.speaker,
    state: meeting.status === "active" ? "confirmed" : "final",
    segment_id: segment.id ?? null
  }));
}

function sessionLifecycle(status: MeetingStatus): SessionLifecycle {
  if (status === "active") return "active";
  if (status === "completed") return "closed";
  if (status === "failed") return "failed";
  return "aborted";
}

function meetingPreview(meeting: Meeting): string {
  const text = meeting.transcript?.segments.map((segment) => segment.text).join(" ").trim();
  // Q6: a meeting still recording shows its words once they exist, and nothing before.
  return text || (meeting.status === "active" ? "" : "No transcript");
}

function modeLabel(mode: Meeting["mode"]): string {
  return mode === "live" ? "Live" : "File / URL";
}

function statusLabel(status: MeetingStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Meeting history request failed.";
}
