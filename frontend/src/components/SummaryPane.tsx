import { useEffect, useRef, useState } from "preact/hooks";
import { openMeeting, type Meeting } from "../api/meetings";
import { summaryApi, SUMMARY_CHANGED, type SummaryArtifact, type SummaryDocument } from "../lib/finalSummary";
import { createRollingLoop, finalizeMeetingSummary, requestLiveSummary, SummaryRequestError,
  summaryFailureReason, summaryPredatesRefinement, type LiveSummaryResponse } from "../lib/summaryRequests";
import { loadAppSettings, SETTINGS_CHANGED, type AppSettings } from "../lib/settings";
import { renameSummarySpeakers, transcriptSpeakerNames } from "../lib/summarySpeakers";
import { sessionId, sessionStatus, sessionStopRequested, transcript } from "../state/session";
import { selectedSummaryMeeting } from "../state/ui";

type Outcome = "ok" | "not_ready" | "failed";

/** Rolling (live) summaries go through the server's Gemini path only. */
const liveSummaries = (settings: AppSettings) =>
  settings.summary.vendor === "gemini";
const reasonOf = (cause: unknown) => cause instanceof SummaryRequestError ? cause.reason
  : cause instanceof Error ? cause.message : "";

export function SummaryPane({ hidden }: { hidden: boolean }) {
  const id = sessionId.value;
  const active = sessionStatus.value === "active";
  const meeting = selectedSummaryMeeting.value?.id === id ? selectedSummaryMeeting.value : null;
  const [rolling, setRolling] = useState<LiveSummaryResponse | null>(null);
  const [artifact, setArtifact] = useState<SummaryArtifact | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [settings, setSettings] = useState(loadAppSettings);
  const improvementRequested = useRef<string | null>(null);
  const refreshLive = useRef<() => void>(() => undefined);
  useEffect(() => {
    const changed = () => setSettings(loadAppSettings());
    document.addEventListener(SETTINGS_CHANGED, changed);
    return () => document.removeEventListener(SETTINGS_CHANGED, changed);
  }, []);

  // One completion-timed loop per active meeting (J3). Settings are read at each decision.
  useEffect(() => {
    setRolling(null); setArtifact(null); setError(null); setBusy(false);
    if (!id || !active) return;
    let current = true;
    let manual = false;
    const loop = createRollingLoop<Outcome>(async () => {
      const requested = manual; manual = false;
      if (!requested && sessionStopRequested.value === id) return "failed"; // see the scheduler below
      const now = loadAppSettings();
      if (!liveSummaries(now)) return "failed";
      setBusy(true);
      try {
        const next = await requestLiveSummary(id, now);
        if (current) { setRolling(next); setError(null); }
        return "ok";
      } catch (cause) {
        const notReady = cause instanceof SummaryRequestError && cause.notReady;
        // Too little finished speech is not a failure unless the user asked for this update.
        if (current && (!notReady || requested)) setError(reasonOf(cause));
        return notReady ? "not_ready" : "failed";
      } finally {
        if (current) setBusy(false);
      }
    }, last => {
      const now = loadAppSettings();
      // After Stop the meeting reads "active" while it drains; a rolling call then would collide
      // with the final summary (429 summary_in_flight) and leave the meeting without one (r4 smoke S8).
      if (sessionStopRequested.value === id) return null;
      if (!now.summary.rolling || !liveSummaries(now)) return null;
      // The live transcript changes once per refresh window; retrying "not ready" sooner cannot succeed.
      const wait = last === "not_ready" ? Math.max(now.summary.waitSeconds, now.transcription.refreshSeconds)
        : now.summary.waitSeconds;
      return wait * 1000;
    });
    refreshLive.current = () => { manual = true; void loop.now(); };
    const changed = () => loop.reschedule();
    document.addEventListener(SETTINGS_CHANGED, changed);
    return () => {
      current = false; loop.dispose(); refreshLive.current = () => undefined;
      document.removeEventListener(SETTINGS_CHANGED, changed);
    };
  }, [id, active]);
  useEffect(() => {
    if (!active || !rolling) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active, rolling]);
  useEffect(() => {
    if (!id || active) return;
    let disposed = false;
    const read = async () => {
      try { const next = await summaryApi(id); if (!disposed) { setArtifact(next); if (next?.state === "current") setError(null); } }
      catch { /* A missed read keeps the last artifact; the next read retries. */ }
    };
    void read();
    const timer = setInterval(() => void read(), 5000);
    const changed = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.meeting_id !== id) return;
      if (detail.artifact) setArtifact(detail.artifact);
      if (typeof detail.error === "string") setError(detail.error);
    };
    document.addEventListener(SUMMARY_CHANGED, changed);
    return () => { disposed = true; clearInterval(timer); document.removeEventListener(SUMMARY_CHANGED, changed); };
  }, [id, active]);

  const summaryStale = meeting != null && summaryPredatesRefinement(meeting, artifact);
  useEffect(() => {
    if (!meeting || !summaryStale || settings.summary.vendor !== "gemini") return;
    const key = `${meeting.id}:${meeting.transcript_version}`;
    if (improvementRequested.current === key) return;
    improvementRequested.current = key;
    void finalizeMeetingSummary(meeting).catch(cause => setError(reasonOf(cause)));
  }, [meeting?.id, meeting?.transcript_version, summaryStale, settings.summary.vendor]);

  async function refreshFinal() {
    if (!id || busy) return;
    setBusy(true); setError(null);
    try {
      const current: Meeting = meeting ?? await openMeeting(id);
      await finalizeMeetingSummary(current);
      setArtifact(await summaryApi(id));
    } catch (cause) { setError(reasonOf(cause)); }
    finally { setBusy(false); }
  }

  const elapsed = rolling ? Math.max(0, Math.floor((now - rolling.generated_at_ms) / 1000)) : 0;
  const finalDocument = artifact?.state === "current" ? artifact.document : null;
  // A rename shows at once and asks the model nothing: the summary is read under today's names.
  const names = transcriptSpeakerNames(transcript.value);
  const failed = error !== null || (!active && artifact?.state === "failed");
  const reason = error ?? summaryFailureReason(artifact?.error_code);
  const unavailable = settings.summary.vendor === "off" ? "Summary is off in Settings"
    : active && settings.summary.vendor !== "gemini" ? "Rolling summary needs Gemini" : "";
  return <section className="summary-pane" aria-label="Summary" hidden={hidden}>
    {id && <>
      <div className="summary-status-row"><div><span className="eyebrow">{active ? "Rolling summary" : "Final summary"}</span>
        {active && rolling && <p role="status">Updated {elapsed}s ago</p>}</div>
        <button type="button" className="btn" data-summary-refresh disabled={busy || Boolean(unavailable)}
          title={unavailable || undefined}
          onClick={() => active ? refreshLive.current() : void refreshFinal()}>{busy ? "Refreshing…"
            : failed ? "Retry"
            : !active && summaryStale && settings.summary.vendor === "openai_compatible" ? "Update summary" : "Refresh"}</button></div>
      {failed && <p className="summary-notice" role="alert">Summary failed{reason ? ` — ${reason}` : ""}</p>}
      {/* The rolling pane shows the whole document, like the final one: its Theme line alone held about
          half of the points the document made (prototypes/gemini-live/live-summary/NOTES.md). */}
      {active ? rolling && <SummaryDocumentView document={renameSummarySpeakers(rolling.summary, rolling.speaker_names, names)} />
        : finalDocument && <SummaryDocumentView final
            document={renameSummarySpeakers(finalDocument, artifact?.speaker_names, names)} />}
    </>}
  </section>;
}

function SummaryDocumentView({ document, final = false }: { document: SummaryDocument; final?: boolean }) {
  return <div className="summary-content" data-final-summary={final || undefined}>
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
