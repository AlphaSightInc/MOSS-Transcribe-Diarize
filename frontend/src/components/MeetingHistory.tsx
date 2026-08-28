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
  formatMeetingTimestamp,
  groupMeetings,
  meetingTitle,
  reconcileSelectedMeeting
} from "../lib/meetingHistory";
import {
  LIVE_MEETING_OBSERVE_EVENT,
  MEETING_HISTORY_REFRESH_EVENT
} from "../lib/meetingEvents";
import {
  resetSessionState,
  sessionMode,
  sessionStatus,
  sessionTitle
} from "../state/session";

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

  const groups = useMemo(
    () => groupMeetings(filterMeetings(meetings, query)),
    [meetings, query]
  );

  const replaceSelection = (meeting: Meeting | null) => {
    selectedRef.current = meeting;
    setSelected(meeting);
  };

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await listMeetings();
      setMeetings(next);
      const previous = selectedRef.current;
      const repaired = reconcileSelectedMeeting(next, selectedRef.current);
      replaceSelection(repaired);
      if (repaired) {
        publishMeeting(repaired, false);
      } else if (previous) {
        resetSessionState();
        sessionTitle.value = "";
      }
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    const handleRefresh = () => void refresh();
    document.addEventListener(MEETING_HISTORY_REFRESH_EVENT, handleRefresh);
    return () => document.removeEventListener(MEETING_HISTORY_REFRESH_EVENT, handleRefresh);
  }, []);

  const selectMeeting = async (meeting: Meeting) => {
    if (
      sessionStatus.value === "active" &&
      sessionMode.value === "live" &&
      selectedRef.current?.id !== meeting.id
    ) {
      setError("Stop the current capture before opening another Meeting.");
      return;
    }
    setError(null);
    try {
      const opened = await openMeeting(meeting.id);
      replaceSelection(opened);
      publishMeeting(opened, true);
    } catch (cause) {
      setError(errorMessage(cause));
    }
  };

  const submitRename = async (event: Event) => {
    event.preventDefault();
    if (!renameTarget || renaming) return;
    setRenaming(true);
    setError(null);
    try {
      const renamed = await renameMeeting(renameTarget.id, renameTitle);
      const update = (meeting: Meeting): Meeting => meeting.id === renamed.id
        ? { ...meeting, title: renamed.title, title_source: renamed.title_source }
        : meeting;
      setMeetings((current) => current.map(update));
      if (selectedRef.current?.id === renamed.id) {
        const nextSelected = update(selectedRef.current);
        replaceSelection(nextSelected);
        sessionTitle.value = renamed.title;
      }
      setRenameTarget(null);
      setRenameTitle("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setRenaming(false);
    }
  };

  return (
    <section className="panel history-panel account-history-panel" aria-label="Meeting history">
      <div className="panel-body">
        <div className="history-panel-actions">
          <label className="history-search">
            <span className="sr-only">Search meetings</span>
            <input
              type="search"
              aria-label="Search meetings"
              placeholder="Search title, transcript, mode, status"
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
        </div>

        {error ? <p className="history-state-card is-error" role="alert">{error}</p> : null}
        {loading && meetings.length === 0 ? (
          <p className="history-state-card" role="status">Loading meetings…</p>
        ) : null}
        {!loading && meetings.length === 0 ? (
          <p className="history-state-card">No meetings yet.</p>
        ) : null}
        {!loading && meetings.length > 0 && groups.length === 0 ? (
          <p className="history-state-card">No meetings match this search.</p>
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
                      onClick={() => void selectMeeting(meeting)}
                    >
                      <span className="history-card-headline">
                        <span className="history-card-copy">
                          <span className="history-card-title">{meetingTitle(meeting)}</span>
                          <span className="history-card-meta">
                            {formatMeetingTimestamp(meeting.created_at_ms)} · {modeLabel(meeting.mode)} · {statusLabel(meeting.status)}
                          </span>
                          <span className="history-card-subtitle">
                            {meetingPreview(meeting)}
                          </span>
                        </span>
                        <span className="history-count-chip">v{meeting.transcript_version}</span>
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
                      {meeting.audio?.state === "available" || meeting.audio?.state === "partial" ? (
                        <a
                          className="history-action-btn"
                          data-audio-download
                          href={`/api/meetings/${encodeURIComponent(meeting.id)}/audio/download`}
                        >
                          {meeting.audio.state === "partial" ? "Download partial audio" : "Download audio"}
                        </a>
                      ) : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>

      {renameTarget ? (
        <div className="history-dialog-wrap">
          <button
            type="button"
            className="history-dialog-backdrop"
            aria-label="Cancel rename"
            disabled={renaming}
            onClick={() => setRenameTarget(null)}
          />
          <form className="history-dialog" aria-label="Rename Meeting" onSubmit={submitRename}>
            <h3>Rename Meeting</h3>
            <label className="history-input-stack">
              <span>Title</span>
              <input
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
        </div>
      ) : null}
    </section>
  );
}

function publishMeeting(meeting: Meeting, observeActive: boolean): void {
  sessionTitle.value = meetingTitle(meeting);
  dispatchWsEvent({
    type: "session_state",
    session_id: meeting.id,
    mode: meeting.mode,
    state: meeting.status,
    status: sessionLifecycle(meeting.status),
    error: meeting.status === "failed" || meeting.status === "interrupted"
      ? statusLabel(meeting.status)
      : null,
    status_line: meeting.status === "active" ? "Meeting active" : statusLabel(meeting.status)
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
    start: segment.start,
    end: segment.end,
    text: segment.text,
    speaker: segment.speaker,
    speaker_entity_id: segment.speaker,
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
  return text || (meeting.status === "active" ? "Waiting for transcript…" : "No transcript");
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
