import { useEffect, useRef, useState } from "preact/hooks";
import { openMeeting, type Meeting } from "../api/meetings";
import { summaryApi, SUMMARY_CHANGED, type SummaryArtifact, type SummaryDocument } from "../lib/finalSummary";
import { finalizeMeetingSummary, requestLiveSummary, type LiveSummaryResponse } from "../lib/summaryRequests";
import { loadAppSettings, SETTINGS_CHANGED } from "../lib/settings";
import { sessionId, sessionStatus } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";

export function SummaryPane({ hidden }: { hidden: boolean }) {
  const id = sessionId.value;
  const active = sessionStatus.value === "active";
  const meeting = selectedSummaryMeeting.value?.id === id ? selectedSummaryMeeting.value : null;
  const [rolling, setRolling] = useState<LiveSummaryResponse | null>(null);
  const [artifact, setArtifact] = useState<SummaryArtifact | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [settings, setSettings] = useState(loadAppSettings);
  const improvementRequested = useRef<string | null>(null);
  useEffect(() => {
    const changed = () => setSettings(loadAppSettings());
    document.addEventListener(SETTINGS_CHANGED, changed);
    return () => document.removeEventListener(SETTINGS_CHANGED, changed);
  }, []);
  const interval = settings.summary.provider === "built-in" ? settings.summary.intervalSeconds : 0;

  async function refreshLive() {
    if (!id || !active || settings.summary.provider !== "built-in") return;
    setBusy(true); setError("");
    try { setRolling(await requestLiveSummary(id, settings)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Live summary unavailable."); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    setRolling(null); setArtifact(null); setError("");
  }, [id, active]);
  useEffect(() => {
    if (!id || !active || interval === 0) return;
    const timer = setInterval(() => void refreshLive(), interval * 1000);
    return () => clearInterval(timer);
  }, [id, active, interval]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!id || active) return;
    let disposed = false;
    const read = async () => {
      try { const next = await summaryApi(id); if (!disposed) { setArtifact(next); if (next?.state === "current") setError(""); } }
      catch (cause) { if (!disposed) setError(cause instanceof Error ? cause.message : "Summary unavailable."); }
    };
    void read();
    const timer = setInterval(() => void read(), 5000);
    const changed = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.meeting_id !== id) return;
      if (detail.artifact) setArtifact(detail.artifact);
      if (detail.error) setError(detail.error);
    };
    document.addEventListener(SUMMARY_CHANGED, changed);
    return () => { disposed = true; clearInterval(timer); document.removeEventListener(SUMMARY_CHANGED, changed); };
  }, [id, active]);

  const summaryStale = meeting?.refinement_state === "done" && artifact?.state === "current" &&
    artifact.source_version < meeting.transcript_version;
  useEffect(() => {
    if (!meeting || !summaryStale || settings.summary.provider !== "built-in") return;
    const key = `${meeting.id}:${meeting.transcript_version}`;
    if (improvementRequested.current === key) return;
    improvementRequested.current = key;
    void finalizeMeetingSummary(meeting, settings).catch(cause =>
      setError(cause instanceof Error ? cause.message : "Summary update unavailable."));
  }, [meeting?.id, meeting?.transcript_version, summaryStale, settings.summary.provider]);

  async function refreshFinal() {
    if (!id || busy) return;
    setBusy(true); setError("");
    try {
      const current: Meeting = meeting ?? await openMeeting(id);
      await finalizeMeetingSummary(current);
      setArtifact(await summaryApi(id));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Summary unavailable."); }
    finally { setBusy(false); }
  }

  const elapsed = rolling ? Math.max(0, Math.floor((now - rolling.generated_at_ms) / 1000)) : 0;
  const next = interval ? Math.max(0, interval - elapsed) : 0;
  const finalDocument = artifact?.state === "current" ? artifact.document : null;
  return <section className="summary-pane" aria-label="Summary" hidden={hidden}>
    {!id ? <p className="empty-state">Open a meeting to see its summary.</p> : <>
      <div className="summary-status-row"><div><span className="eyebrow">{active ? "Rolling summary" : "Final summary"}</span>
        <p role="status">{active ? rolling ? `Updated ${elapsed}s ago${interval && !error ? ` · next in ${next}s` : ""}` : interval ? "Waiting for first update" : "Rolling summary is off"
          : artifact?.state === "current" ? "Summary ready" : artifact ? `Summary ${artifact.state.replaceAll("_", " ")}` : "No saved summary yet"}</p></div>
        <button type="button" className="btn" data-summary-refresh disabled={busy || settings.summary.provider === "off"}
          onClick={() => void (active ? refreshLive() : refreshFinal())}>{busy ? "Refreshing…"
            : !active && (error || artifact?.state === "failed") ? "Retry"
            : !active && summaryStale && settings.summary.provider === "external" ? "Update summary" : "Refresh"}</button></div>
      {error && (active ? <p className="summary-notice" role="status">
        {rolling ? "Latest update failed; showing the last summary." : "Summary update failed."}
        {interval ? " Retrying at the next interval." : " Use Refresh to retry."}
      </p> : <p role="alert">{error}</p>)}
      {active ? rolling ? <div className="summary-content"><h3>Theme</h3><p>{rolling.summary.summary}</p></div>
        : <p className="empty-state">Summary will appear when enough finished speech is available.</p>
        : finalDocument ? <SummaryDocumentView document={finalDocument} />
        : <p className="empty-state">{artifact?.state === "failed" || error
          ? "The summary is unavailable."
          : "Finish transcription to generate a summary."}</p>}
    </>}
  </section>;
}

function SummaryDocumentView({ document }: { document: SummaryDocument }) {
  return <div className="summary-content" data-final-summary>
    <span className="eyebrow">Theme</span><h3>{document.summary}</h3>
    {document.topics.length > 0 && <section><h4>Topics discussed</h4><ol>{document.topics.map((topic, index) =>
      <li key={index}><strong>{topic.title}</strong><p>{topic.description}</p></li>)}</ol></section>}
    {document.details.length > 0 && <section><h4>Supporting details</h4><ul>{document.details.map((detail, index) =>
      <li key={index}><strong>{detail.timestamp} · {detail.title}</strong> — {detail.description}</li>)}</ul></section>}
    {document.speaker_background.length > 0 && <section><h4>Speaker background</h4><ul>{document.speaker_background.map((line, index) =>
      <li key={index}>{line}</li>)}</ul></section>}
    {document.data_references.length > 0 && <section><h4>Data references</h4><ul>{document.data_references.map((item, index) =>
      <li key={index}><strong>{item.item}: {item.value}</strong> — {item.context}</li>)}</ul></section>}
  </div>;
}
