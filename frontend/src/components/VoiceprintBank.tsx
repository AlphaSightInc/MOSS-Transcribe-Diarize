import { useRef, useState } from "preact/hooks";
import { changeVoiceprint, listVoiceprints, type Voiceprint } from "../api/speakers";

export function VoiceprintBank() {
  const [open, setOpen] = useState(false);
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

  return <section className="control-section" aria-label="Private voiceprints">
    <button type="button" className="history-toolbar-btn" aria-expanded={open} onClick={() => {
      setOpen(!open);
      if (!open) void refresh();
    }}>Voiceprints</button>
    {open ? <div>
      <p className="hint">Private to this browser workspace. Name a speaker during capture to save their voiceprint; no separate recording needed.</p>
      <button type="button" className="history-toolbar-btn" disabled={busy} onClick={() => void refresh()}>Refresh</button>
      {error ? <p role="alert">{error}</p> : null}
      {busy ? <p role="status">Working…</p> : null}
      {!busy && !rows.length && !error ? <p className="hint">No voiceprints yet.</p> : null}
      <ul className="voiceprint-list">{rows.map(row => <li key={row.id} data-voiceprint-id={row.id}>
        <strong>{row.label}</strong> <span className="hint">{row.sample_count} saved sample{row.sample_count === 1 ? "" : "s"}</span>
        {row.compatibility === "re_enrollment_required" ? <p className="hint">Re-enrollment required: this voiceprint uses a different encoder.</p> : null}
        <div className="history-dialog-actions">
          <button type="button" className="history-toolbar-btn" disabled={busy} onClick={() => { setTarget({ row, deleting: false }); setLabel(row.label); setError(null); }}>Rename</button>
          <button type="button" className="history-toolbar-btn" disabled={busy} onClick={() => { setTarget({ row, deleting: true }); setError(null); }}>Delete</button>
        </div>
      </li>)}</ul>
      {target ? <form onSubmit={event => void save(event)} aria-label={target.deleting ? "Delete voiceprint" : "Rename voiceprint"}>
        {target.deleting ? <p>Delete “{target.row.label}” and its saved samples? Recorded names stay; future recognition cannot use this voiceprint.</p>
          : <label>Voiceprint name<input value={label} required disabled={busy} onInput={event => setLabel(event.currentTarget.value)} /></label>}
        <div className="history-dialog-actions">
          <button type="button" className="history-toolbar-btn" disabled={busy} onClick={() => setTarget(null)}>Cancel</button>
          <button type="submit" className="history-toolbar-btn" disabled={busy || (!target.deleting && !label.trim())}>{target.deleting ? "Confirm delete" : "Save name"}</button>
        </div>
      </form> : null}
    </div> : null}
  </section>;
}
