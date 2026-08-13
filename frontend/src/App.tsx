export function App() {
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
          <span className="session-chip">Live</span>
        </div>

        <div className="top-right" />
      </header>

      <main
        className="main"
        id="main"
        data-left-collapsed="false"
        data-right-collapsed="false"
      >
        <section className="panel control-panel" aria-labelledby="capture-panel-title">
          <header className="panel-head">
            <h2 className="panel-title" id="capture-panel-title">
              <span className="panel-title-text">Capture</span>
            </h2>
          </header>
          <div className="panel-body">
            <p className="empty-state">Capture controls are not available yet.</p>
          </div>
        </section>

        <section className="transcript-shell" id="transcript-panel">
          <div className="transcript-pane">
            <header className="tr-head">
              <span className="tr-head-spacer" aria-hidden="true" />
              <div className="tr-title-wrap">
                <h1 className="tr-title">Live transcript</h1>
                <p className="tr-meta">Ready for a session</p>
              </div>
            </header>
            <div className="tr-body-wrap">
              <div className="tr-body">
                <p className="empty-state transcript-empty-state">
                  Start a session to see the transcript.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="panel history-panel" aria-labelledby="history-panel-title">
          <header className="panel-head">
            <h2 className="panel-title" id="history-panel-title">
              <span className="panel-title-text">History</span>
            </h2>
          </header>
          <div className="panel-body">
            <p className="empty-state">No saved sessions.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
