import { ControlPanel } from "./components/ControlPanel";
import { TranscriptPane } from "./components/TranscriptPane";
import { VoiceprintBank } from "./components/VoiceprintBank";
import { sessionStatus, sessionStatusLine } from "./state/session";

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

        <div className="session-meta" aria-live="polite">
          <span className="session-title">LiveTranscribe</span>
          <span className="session-dot" aria-hidden="true" />
          <span className="session-chip">Live</span>
        </div>

        <div className="top-right" />
      </header>

      <main className="main" id="main" data-left-collapsed="false" data-right-collapsed="true">
        <aside className="panel control-panel" id="control-panel" aria-labelledby="capture-panel-title">
          <div className="panel-head">
            <h2 className="panel-title" id="capture-panel-title">Controls</h2>
          </div>
          <div className="panel-body">
            <ControlPanel />
            <VoiceprintBank />
          </div>
        </aside>

        <section className="transcript-shell" id="transcript-panel">
          <TranscriptPane />
        </section>
      </main>
    </div>
  );
}
