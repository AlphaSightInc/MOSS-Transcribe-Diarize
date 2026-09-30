import { useEffect, useRef, useState } from "preact/hooks";
import { SettingsDialog } from "./components/SettingsDialog";
import { ControlPanel } from "./components/ControlPanel";
import { TranscriptPane } from "./components/TranscriptPane";
import { PanelCollapseButton, PanelRailTitle } from "./components/PanelCollapse";
import { controlPanelCollapsed, setControlPanelCollapsed } from "./state/ui";
import { sessionId, sessionMode, sessionStartedAt, sessionStatus, sessionTitle } from "./state/session";

export const PRODUCT_NAME = "aiSight - LiveTranscribe";

/** The sole Account-owned Live surface mounted inside the authenticated workspace. */
export function App() {
  const pill = useStatusPill();
  const controlsCollapsed = controlPanelCollapsed.value;

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
        {/* Over a collapsed Controls rail the pill is its dot alone (styles/index.css); hover shows the label. */}
        <span className="status top-status" data-state={pill.state} title={controlsCollapsed ? pill.label : undefined}>
          <span className="status-dot" aria-hidden="true" />
          <span>{pill.label}</span>
        </span>

        <div className="session-meta" aria-live="polite" style={{ flexWrap: "nowrap", minWidth: 0 }}>
          <span className="session-title" title={sessionTitle.value || PRODUCT_NAME}>{sessionTitle.value || PRODUCT_NAME}</span>
          <span className="session-dot" aria-hidden="true" />
          <span className="session-chip">{sessionMode.value === "live" ? "Live" : "File / URL"}</span>
        </div>

        <div className="top-right"><SettingsDialog /></div>
      </header>

      <main className="main" id="main" data-left-collapsed={String(controlsCollapsed)} data-right-collapsed="true">
        <aside className={`panel control-panel${controlsCollapsed ? " collapsed" : ""}`} id="control-panel"
          aria-labelledby="capture-panel-title">
          <div className="panel-head">
            <h2 className="panel-title" id="capture-panel-title">
              <span className="panel-title-text">Controls</span>
              <PanelRailTitle name="Controls" onExpand={() => setControlPanelCollapsed(false)} />
            </h2>
            <PanelCollapseButton name="Controls" side="left" collapsed={controlsCollapsed}
              onChange={setControlPanelCollapsed} />
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

/** The pill carries lifecycle only: Standby, Recording mm:ss, Stopping, Processing (File/URL). */
function useStatusPill(): { label: string; state: "idle" | "recording" | "processing" } {
  const status = sessionStatus.value;
  const id = sessionId.value;
  const recording = status === "active" && sessionMode.value === "live" && id !== null;
  const firstSeen = useRef<{ sessionId: string; ms: number } | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!recording) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [recording]);

  if (status === "closing") return { label: "Stopping", state: "processing" };
  if (status === "active" && !recording) return { label: "Processing", state: "processing" };
  if (!recording) return { label: "Standby", state: "idle" };
  const known = sessionStartedAt.value?.sessionId === id ? sessionStartedAt.value : null;
  if (!known && firstSeen.current?.sessionId !== id) firstSeen.current = { sessionId: id, ms: Date.now() };
  const startedMs = known?.ms ?? firstSeen.current!.ms;
  return { label: `Recording ${formatElapsed(now - startedMs)}`, state: "recording" };
}

export function formatElapsed(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(hours ? 2 : 1, "0");
  const rest = String(seconds % 60).padStart(2, "0");
  return hours ? `${hours}:${minutes}:${rest}` : `${minutes}:${rest}`;
}
