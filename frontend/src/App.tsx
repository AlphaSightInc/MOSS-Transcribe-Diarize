import { SettingsDialog } from "./components/SettingsDialog";
import { ControlPanel } from "./components/ControlPanel";
import { TranscriptPane } from "./components/TranscriptPane";
import { sessionStatus, sessionStatusLine, sessionTitle, sessionMode } from "./state/session";

/** The sole Account-owned Live surface mounted inside the authenticated workspace. */
export function App() {
  const status = sessionStatus.value;
  const statusLabel = sessionStatusLine.value ?? (status === "idle" ? "Standby" : status);

  return (
    <div
      className="app"
      data-boot="ready"
      data-accent="ink"
      data-density="compact"
      data-font="serif"
      data-authority="account"
    >
      <header className="topbar">
        <span className="status top-status" data-state={status}>
          <span className="status-dot" aria-hidden="true" />
          <span>{statusLabel}</span>
        </span>

        <div className="session-meta" aria-live="polite" style={{ flexWrap: "nowrap", minWidth: 0 }}>
          <span className="session-title" title={sessionTitle.value || "MOSS"}>{sessionTitle.value || "MOSS"}</span>
          <span className="session-dot" aria-hidden="true" />
          <span className="session-chip">{sessionMode.value === "live" ? "Live" : "File / URL"}</span>
        </div>

        <div className="top-right"><SettingsDialog /></div>
      </header>

      <main className="main" id="main" data-left-collapsed="false" data-right-collapsed="true">
        <aside className="panel control-panel" id="control-panel" aria-labelledby="capture-panel-title">
          <div className="panel-head">
            <h2 className="panel-title" id="capture-panel-title">Controls</h2>
          </div>
          <div className="panel-body">
            <ControlPanel />
          </div>
        </aside>

        <section className="transcript-shell" id="transcript-panel">
          <TranscriptPane />
        </section>
      </main>
    </div>
  );
}
