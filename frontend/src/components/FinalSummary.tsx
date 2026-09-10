import { useEffect, useState } from "preact/hooks";
import type { Meeting } from "../api/meetings";
import {
  clearSummarySettings, defaultSettings, finalSummaryWorker, loadSummarySettings,
  saveSummarySettings, summaryApi, summaryEnabled, SUMMARY_CHANGED,
  type SummaryArtifact, type SummarySettings
} from "../lib/finalSummary";

export function FinalSummarySettings() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState(loadSummarySettings);
  const [message, setMessage] = useState("");
  const field = (key: keyof SummarySettings, value: string) => setSettings(current => ({ ...current, [key]: key === "timeoutSeconds" ? Number(value) : value }));
  return <section className="history-state-card" aria-label="Browser AI settings">
    <button type="button" className="history-action-btn" onClick={() => { setOpen(!open); setSettings(loadSummarySettings()); }}>
      Optional AI summaries · {summaryEnabled(loadSummarySettings()) ? "configured" : "off"}
    </button>
    {open && <form onSubmit={event => {
      event.preventDefault();
      try { saveSummarySettings(settings); setMessage("Saved in this browser only. Keep the creating tab open until its summary finishes."); }
      catch (error) { setMessage(error instanceof Error ? error.message : "Could not save browser settings."); }
    }}>
      <p>No setup needed for transcription. When enabled, this browser sends each new meeting's final transcript directly to your provider. MOSS stores only the finished summary. Provider CORS and trusted HTTPS are required.</p>
      <p>The API key is stored in this browser's site data, not on the MOSS server. Use a restricted key on a trusted browser profile.</p>
      {([ ["endpoint", "Provider HTTPS URL"], ["model", "Model"], ["apiKey", "API key (optional)"], ["language", "Output language (blank preserves prompt)"] ] as const).map(([key, label]) =>
        <label style={{ display: "block", marginBlock: "0.5rem" }} key={key}>{label}<input style={{ display: "block", width: "100%" }} type={key === "apiKey" ? "password" : "text"}
          autoComplete="off" value={settings[key]} onInput={event => field(key, event.currentTarget.value)} /></label>)}
      <label>Request timeout (seconds)<input type="number" step="1" min="1" value={settings.timeoutSeconds} onInput={event => field("timeoutSeconds", event.currentTarget.value)} /></label>
      <label style={{ display: "block" }}>Final-summary prompt<textarea style={{ display: "block", width: "100%" }} rows={8} value={settings.prompt} onInput={event => field("prompt", event.currentTarget.value)} /></label>
      <p>Delivery retries only: 60, 120, 240 seconds. Invalid output is not retried or repaired. Blank URL or model disables new calls.</p>
      <button type="submit" className="history-action-btn">Save on this browser</button>{" "}
      <button type="button" className="history-action-btn" onClick={() => { setSettings(current => ({ ...current, prompt: defaultSettings().prompt })); }}>Restore default prompt</button>{" "}
      <button type="button" className="history-action-btn" onClick={() => { clearSummarySettings(); setSettings(defaultSettings()); setMessage("Browser settings cleared. Cancel any running summary separately."); }}>Clear settings</button>
    </form>}
    {message && <p role="status">{message}</p>}
  </section>;
}

const active = (artifact: SummaryArtifact | null) => artifact && ["queued", "generating", "retry_wait"].includes(artifact.state);

export function FinalSummary({ meeting }: { meeting: Meeting }) {
  const [artifact, setArtifact] = useState<SummaryArtifact | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let disposed = false;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try { const result = await summaryApi(meeting.id); if (!disposed) { setArtifact(result); setError(""); } }
      catch (cause) { if (!disposed) setError(cause instanceof Error ? cause.message : "Summary unavailable."); }
      finally { pending = false; if (!disposed) setLoading(false); }
    };
    setArtifact(null); setLoading(true); setError("");
    void refresh();
    const changed = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.meeting_id !== meeting.id) return;
      if (detail.artifact) { setArtifact(detail.artifact); setLoading(false); }
      if (detail.error) setError(detail.error);
    };
    document.addEventListener(SUMMARY_CHANGED, changed);
    const timer = setInterval(() => void refresh(), 2000);
    return () => { disposed = true; clearInterval(timer); document.removeEventListener(SUMMARY_CHANGED, changed); };
  }, [meeting.id]);

  const retry = async () => {
    if (!summaryEnabled()) { setError("Configure Optional AI summaries above, then Retry."); return; }
    setBusy(true); setError("");
    try { await finalSummaryWorker.enqueue(meeting); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Summary failed. Refresh, then Cancel/Retry if needed."); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!artifact) return;
    try { await finalSummaryWorker.cancel(meeting.id, artifact); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Cancel failed."); }
  };
  const result = artifact?.state === "current" ? artifact.document : null;
  return <section className="history-state-card" aria-label="Final summary" data-summary-state={artifact?.state ?? "off"}>
    <h3>Final summary</h3>
    <p role="status">{loading ? "Loading saved summary…" : artifact ? `${artifact.state.replace("_", " ")} · transcript v${artifact.source_version}` : "No saved summary. Opening history does not call AI."}</p>
    {active(artifact) && <p>Keep the worker tab open. If it was closed, Cancel this attempt, then Retry here.</p>}
    {artifact?.error_code && <p>Summary failed: {artifact.error_code.replaceAll("_", " ")}. Transcription and audio are unaffected.</p>}
    {error && <p role="alert">{error}</p>}
    {active(artifact) ? <button type="button" className="history-action-btn" onClick={() => void cancel()}>Cancel summary</button>
      : <button type="button" className="history-action-btn" disabled={loading || busy || meeting.status !== "completed"} onClick={() => void retry()}>{result ? "Regenerate summary" : "Retry summary"}</button>}
    {result && <div data-final-summary>
      <p>{result.summary}</p>
      {result.topics.map((topic, index) => <section key={index}><h4>{topic.title}</h4><p>{topic.description}</p></section>)}
      {result.details.length > 0 && <><h4>Supporting details</h4><ul>{result.details.map((detail, index) => <li key={index}><strong>{detail.timestamp} · {detail.title}</strong> — {detail.description}</li>)}</ul></>}
      {result.speaker_background.length > 0 && <><h4>Speaker background</h4><ul>{result.speaker_background.map((line, index) => <li key={index}>{line}</li>)}</ul></>}
      {result.data_references.length > 0 && <><h4>Data references</h4><ul>{result.data_references.map((item, index) => <li key={index}><strong>{item.item}: {item.value}</strong> — {item.context}</li>)}</ul></>}
    </div>}
  </section>;
}
