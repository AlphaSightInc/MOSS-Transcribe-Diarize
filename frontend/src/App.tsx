import { useRef, useState } from "preact/hooks";
import { SegmentedControl } from "./components/SegmentedControl";
import { TranscriptPane } from "./components/TranscriptPane";

type PhaseOneMode = "live" | "file";

export function App() {
  const [mode, setMode] = useState<PhaseOneMode>("live");
  const [selectedFileName, setSelectedFileName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const modeLabel = mode === "live" ? "Live" : "File";

  return (
    <div
      className="app"
      data-boot="ready"
      data-accent="ink"
      data-density="compact"
      data-font="serif"
    >
      <header className="topbar">
        <span className="status top-status" data-state="idle">
          <span className="status-dot" aria-hidden="true" />
          <span>Standby</span>
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
                options={[
                  { value: "live", label: "Live" },
                  { value: "file", label: "File" }
                ]}
                value={mode}
                onChange={setMode}
              />
            </section>

            {mode === "live" ? (
              <section className="control-section" data-mode="live">
                <div className="label">Capture</div>
                <p className="hint">Choose Start capture when browser capture is connected.</p>
                <button type="button" className="record-btn" disabled>
                  <span>Start capture</span>
                </button>
              </section>
            ) : (
              <section className="control-section" data-mode="file">
                <div className="label">File</div>
                <div className="field field--input-prompt">
                  <input
                    aria-label="Selected file"
                    readOnly
                    type="text"
                    value={selectedFileName}
                    placeholder="No file selected."
                  />
                  <button
                    type="button"
                    className="field-btn"
                    aria-label="Choose file"
                    title="Choose file"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <span aria-hidden="true">↑</span>
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*"
                    hidden
                    onChange={(event) => setSelectedFileName(event.currentTarget.files?.[0]?.name ?? "")}
                  />
                </div>
                <p className="hint">Select an audio file to prepare it for transcription.</p>
              </section>
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
