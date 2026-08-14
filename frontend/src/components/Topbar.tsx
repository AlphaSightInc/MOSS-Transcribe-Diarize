import llmIconUrl from "../../../data/llm.png";

interface TopbarProps {
  onOpenSettings: () => void;
  sessionModeLabel: string;
  sessionTitle: string | null;
  sessionTimerLabel: string | null;
  statusLabel: string;
  statusState:
    | "idle"
    | "starting"
    | "processing"
    | "recording"
    | "success"
    | "completed"
    | "warning"
    | "error";
}

export function Topbar({
  onOpenSettings,
  sessionModeLabel,
  sessionTitle,
  sessionTimerLabel,
  statusLabel,
  statusState
}: TopbarProps) {
  return (
    <header className="topbar">
      <span className="status top-status" data-state={statusState}>
        <span className="status-dot" aria-hidden="true" />
        <span>{statusLabel}</span>
      </span>

      <div className="session-meta" aria-live="polite">
        <span className="session-title">{sessionTitle ?? "LiveTranscribe"}</span>
        <span className="session-dot" aria-hidden="true" />
        <span className="session-chip">{sessionModeLabel}</span>
        {sessionTimerLabel ? (
          <>
            <span className="session-dot" aria-hidden="true" />
            <span className="session-timer">{sessionTimerLabel}</span>
          </>
        ) : null}
      </div>

      <div className="top-right">
        <button
          type="button"
          className="icon-btn"
          aria-label="LLM settings"
          title="LLM settings"
          onClick={onOpenSettings}
        >
          <img className="icon-btn-image" src={llmIconUrl} alt="" />
        </button>
      </div>
    </header>
  );
}
