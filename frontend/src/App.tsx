import { useState } from "preact/hooks";
import { ControlPanel } from "./components/ControlPanel";
import { FilePanel } from "./components/FilePanel";
import { SegmentedControl } from "./components/SegmentedControl";
import { TranscriptPane } from "./components/TranscriptPane";
import { resetSessionState, sessionStatus, sessionStatusLine } from "./state/session";

type PhaseOneMode = "live" | "file";

export function App() {
  const [mode, setMode] = useState<PhaseOneMode>("live");
  const [captureBearer, setCaptureBearer] = useState("");

  const modeLabel = mode === "live" ? "Live" : "File";
  const status = sessionStatus.value;
  const modeLocked = status === "active" || status === "closing";
  const statusLabel = sessionStatusLine.value ?? (status === "idle" ? "Standby" : status);

  return (
    <div
      className="app"
      data-boot="ready"
      data-accent="ink"
      data-density="compact"
      data-font="serif"
    >
      <header className="topbar">
        <span className="status top-status" data-state={status}>
          <span className="status-dot" aria-hidden="true" />
          <span>{statusLabel}</span>
        </span>

        <div className="session-meta" aria-live="polite">
          <span className="session-title">LiveTranscribe</span>
          <span className="session-dot" aria-hidden="true" />
          <span className="session-chip">{modeLabel}</span>
        </div>

        <div className="top-right" />
      </header>

      <main
        className="main"
        id="main"
        data-left-collapsed="false"
        data-right-collapsed="true"
      >
        <aside className="panel control-panel" id="control-panel" aria-labelledby="capture-panel-title">
          <div className="panel-head">
            <h2 className="panel-title" id="capture-panel-title">Controls</h2>
          </div>
          <div className="panel-body">
            <section className="control-section">
              <div className="label">Mode</div>
              <SegmentedControl
                ariaLabel="Session mode"
                disabled={modeLocked}
                options={[
                  { value: "live", label: "Live" },
                  { value: "file", label: "File" }
                ]}
                value={mode}
                onChange={(nextMode) => {
                  if (nextMode === mode || modeLocked) return;
                  resetSessionState();
                  setMode(nextMode);
                }}
              />
            </section>

            {mode === "live" ? (
              <ControlPanel
                captureBearer={captureBearer}
                onCaptureBearerChange={setCaptureBearer}
              />
            ) : (
              <FilePanel captureBearer={captureBearer} />
            )}
          </div>
        </aside>

        <section className="transcript-shell" id="transcript-panel">
          <TranscriptPane />
        </section>

        <aside
          className="panel history-panel collapsed"
          aria-hidden="true"
          aria-labelledby="history-panel-title"
        >
          <div className="panel-head">
            <h2 className="panel-title" id="history-panel-title">
              <span className="panel-title-rail">History</span>
            </h2>
          </div>
        </aside>
      </main>
    </div>
  );
}
