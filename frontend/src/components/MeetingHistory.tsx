import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { FinalSummary, FinalSummarySettings } from "./FinalSummary";
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
  OPEN_MEETING_EVENT,
  MEETING_HISTORY_REFRESH_EVENT
} from "../lib/meetingEvents";
import {
  resetSessionState,
  sessionId,
  sessionMode,
  sessionNeedsReview,
  sessionStatus,
  sessionTitle
} from "../state/session";
import { historyView } from "../state/ui";

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
  const renameDialogRef = useRef<HTMLDialogElement | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  const groups = useMemo(
    () => groupMeetings(filterMeetings(meetings, query)),
    [meetings, query]
  );

  const replaceSelection = (meeting: Meeting | null) => {
    selectedRef.current = meeting;
    setSelected(meeting);
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
        // Stop completes through the Live poller, not a manual History selection. Hydrate
        // its durable notice/review projection as soon as the terminal row is visible.
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
    return () => document.removeEventListener(MEETING_HISTORY_REFRESH_EVENT, handleRefresh);
  }, []);

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
      setError("Stop the current capture before opening another Meeting.");
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

  return (
    <section className="panel history-panel account-history-panel" aria-label="Meeting history">
      <div className="panel-body">
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

        {historyView.value === "sessions" ? <>
        <FinalSummarySettings />
        {error ? <p className="history-state-card is-error" role="alert">{error}</p> : null}
        {selected ? <p className="hint" role="status">Selected: {meetingTitle(selected)}. <a href="#transcript-panel">View selected transcript and export</a></p> : null}
        {selected && (selected.failure_reason || selected.notice) && <p role="status">{selected.failure_reason || selected.notice}</p>}
        {selected?.status === "completed" && <FinalSummary key={selected.id} meeting={selected} />}
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
                      onClick={() => void selectMeeting(meeting.id)}
                    >
                      <span className="history-card-headline">
                        <span className="history-card-copy">
                          <span className="history-card-title">{meetingTitle(meeting)}</span>
                          <span className="history-card-meta">
                            {formatMeetingTimestamp(meeting.created_at_ms)} · {modeLabel(meeting.mode)} · {statusLabel(meeting.status)}
                          </span>
                          <span className="history-card-subtitle">
                            {meeting.failure_reason || meeting.notice || meetingPreview(meeting)}
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
      ? meeting.failure_reason || statusLabel(meeting.status)
      : null,
    status_line: meeting.failure_reason || meeting.notice || (meeting.status === "active" ? "Meeting active" : statusLabel(meeting.status)),
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
