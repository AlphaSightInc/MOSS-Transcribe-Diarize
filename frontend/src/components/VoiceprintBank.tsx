import { useEffect, useRef, useState } from "preact/hooks";
import { SPEAKER_NAMED_EVENT } from "../lib/meetingEvents";
import { changeVoiceprint, listVoiceprints, type Voiceprint } from "../api/speakers";
import { historyView } from "../state/ui";

export function VoiceprintBank() {
  const [rows, setRows] = useState<Voiceprint[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<{ row: Voiceprint; deleting: boolean } | null>(null);
  const [label, setLabel] = useState("");
  const generation = useRef(0);

  async function refresh() {
    const current = ++generation.current;
    setBusy(true);
    setError(null);
    try {
      const next = await listVoiceprints();
      if (current === generation.current) setRows(next);
    } catch (cause) {
      if (current === generation.current) setError(cause instanceof Error ? cause.message : "Could not load voiceprints.");
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }

  useEffect(() => {
    if (historyView.value !== "voiceprints") return;
    void refresh();
    const changed = () => void refresh();
    document.addEventListener(SPEAKER_NAMED_EVENT, changed);
    return () => document.removeEventListener(SPEAKER_NAMED_EVENT, changed);
  }, [historyView.value]);

  async function save(event: Event) {
    event.preventDefault();
    if (!target || busy) return;
    setBusy(true);
    setError(null);
    try {
      await changeVoiceprint(target.row.id, target.deleting ? null : label.trim());
      setTarget(null);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Voiceprint change failed.");
    } finally {
      setBusy(false);
    }
  }

  if (historyView.value !== "voiceprints") return null;

  return <section className="control-section" aria-label="Voiceprints"><div>
      <button type="button" className="history-toolbar-btn" disabled={busy} onClick={() => void refresh()}>Refresh</button>
      {error ? <p role="alert">{error}</p> : null}
      {!busy && !rows.length && !error ? <p className="hint">No voiceprints yet.</p> : null}
      {/* Reference history-card rows (LiveTranscribe VoiceprintSurface). */}
      <ul className="voiceprint-list history-group-list">{rows.map(row => <li key={row.id} data-voiceprint-id={row.id}
        className="history-card history-card-voiceprint">
        <div className="history-card-headline">
          <div className="history-card-copy">
            <p className="history-card-title">{row.label}</p>
            {row.compatibility === "re_enrollment_required" ? <p className="history-card-meta">Re-enroll needed</p> : null}
          </div>
          <span className="history-duration-chip">{row.sample_count} sample{row.sample_count === 1 ? "" : "s"}</span>
        </div>
        <div className="history-card-actions">
          <button type="button" className="history-action-btn" disabled={busy} onClick={() => { setTarget({ row, deleting: false }); setLabel(row.label); setError(null); }}>Rename</button>
          <button type="button" className="history-action-btn is-danger" disabled={busy} onClick={() => { setTarget({ row, deleting: true }); setError(null); }}>Delete</button>
        </div>
      </li>)}</ul>
      {target ? <form onSubmit={event => void save(event)} aria-label={target.deleting ? "Delete voiceprint" : "Rename voiceprint"}>
        {target.deleting ? <p>Delete “{target.row.label}”?</p>
          : <label>Name<input value={label} required disabled={busy} onInput={event => setLabel(event.currentTarget.value)} /></label>}
        <div className="history-dialog-actions">
          <button type="button" className="history-toolbar-btn" disabled={busy} onClick={() => setTarget(null)}>Cancel</button>
          <button type="submit" className="history-toolbar-btn" disabled={busy || (!target.deleting && !label.trim())}>{target.deleting ? "Delete" : "Save"}</button>
        </div>
      </form> : null}
    </div>
  </section>;
}
