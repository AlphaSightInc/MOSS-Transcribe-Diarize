import { useEffect, useRef, useState } from "preact/hooks";
import { BUILT_IN_MODELS, defaultAppSettings, loadAppSettings, saveAppSettings } from "../lib/settings";
import type { AppSettings, SpeakerWindow } from "../lib/settings";

const WINDOW_CHOICES: { value: SpeakerWindow; label: string; tradeoff: string }[] = [
  { value: "balanced", label: "Balanced", tradeoff: "15-second updates with 90 seconds of context." },
  { value: "economy", label: "Economy", tradeoff: "30-second updates with fewer calls." },
  { value: "max", label: "Max context", tradeoff: "15-second updates with up to 3 minutes of context." }
];

export function SettingsDialog() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState(loadAppSettings);
  const [engineOptions, setEngineOptions] = useState(false);
  const [message, setMessage] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetch("/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2", { credentials: "same-origin" })
      .then(response => response.ok ? response.json() : null)
      .then(payload => { if (!cancelled) setEngineOptions(Boolean(payload?.engine_options)); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const dialog = dialogRef.current;
    if (dialog && typeof dialog.showModal === "function") dialog.showModal();
    else dialog?.setAttribute("open", "");
    return () => { if (dialog?.open && typeof dialog.close === "function") dialog.close(); else dialog?.removeAttribute("open"); };
  }, [open]);
  const update = (patch: Partial<AppSettings>) => setSettings(current => ({ ...current, ...patch }));
  const summary = (patch: Partial<AppSettings["summary"]>) => setSettings(current => ({ ...current,
    summary: { ...current.summary, ...patch } }));
  const close = () => { setOpen(false); setMessage(""); };
  return <>
    <button type="button" className="settings-trigger" aria-label="Settings" title="Settings"
      onClick={() => { setSettings(loadAppSettings()); setOpen(true); }}>⚙</button>
    {open && <dialog ref={dialogRef} className="settings-dialog" aria-label="Settings" onCancel={close}>
      <form onSubmit={event => { event.preventDefault(); saveAppSettings(settings); setMessage("Settings saved in this browser."); close(); }}>
        <header className="settings-head"><div><span className="eyebrow">Meeting preferences</span><h2>Settings</h2></div>
          <button type="button" aria-label="Close settings" onClick={close}>×</button></header>
        <div className="settings-body">
          {engineOptions && <section aria-label="Transcription settings"><h3>Transcription</h3>
            <label>Speaker window<select aria-label="Speaker window" value={settings.speakerWindow}
              onChange={event => update({ speakerWindow: event.currentTarget.value as SpeakerWindow })}>
              {WINDOW_CHOICES.map(choice => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></label>
            <p className="hint">{WINDOW_CHOICES.find(choice => choice.value === settings.speakerWindow)?.tradeoff}</p>
            <label className="settings-checkbox"><input type="checkbox" checked={settings.cleanupAfterStop}
              onChange={event => update({ cleanupAfterStop: event.currentTarget.checked })} /> Improve transcript after Stop (runs in the background; export waits for it)</label>
          </section>}
          <section aria-label="Summary settings"><h3>Summary</h3>
            <label>Provider<select aria-label="Summary provider" value={settings.summary.provider}
              onChange={event => summary({ provider: event.currentTarget.value as AppSettings["summary"]["provider"] })}>
              <option value="built-in">Built-in Gemini</option><option value="external">External (OpenAI-compatible)</option><option value="off">Off</option>
            </select></label>
            {settings.summary.provider === "built-in" && <label>Model<select aria-label="Summary model" value={settings.summary.model}
              onChange={event => summary({ model: event.currentTarget.value })}>
              {BUILT_IN_MODELS.map(model => <option key={model} value={model}>{model}</option>)}</select></label>}
            {settings.summary.provider === "external" && <>
              <label>Provider HTTPS URL<input aria-label="Provider HTTPS URL" value={settings.summary.externalUrl}
                onInput={event => summary({ externalUrl: event.currentTarget.value })} placeholder="https://example.com/v1" /></label>
              <label>External model<input aria-label="External model" value={settings.summary.externalModel}
                onInput={event => summary({ externalModel: event.currentTarget.value })} /></label>
              <label>API key (optional)<input aria-label="API key" type="password" autoComplete="off"
                value={settings.summary.externalApiKey} onInput={event => summary({ externalApiKey: event.currentTarget.value })} /></label>
            </>}
            {settings.summary.provider !== "off" && <>
              <label>Output language<input aria-label="Output language" value={settings.summary.language}
                onInput={event => summary({ language: event.currentTarget.value })} placeholder="Use prompt language" /></label>
              <label>Rolling interval<select aria-label="Rolling summary interval" value={settings.summary.intervalSeconds}
                onChange={event => summary({ intervalSeconds: Number(event.currentTarget.value) })}>
                <option value="0">Off</option><option value="60">60 seconds</option><option value="120">120 seconds</option><option value="300">5 minutes</option>
              </select></label>
              <label>Request timeout (seconds)<input aria-label="Request timeout" type="number" min="1" value={settings.summary.timeoutSeconds}
                onInput={event => summary({ timeoutSeconds: Number(event.currentTarget.value) })} /></label>
              <label>Summary prompt<textarea aria-label="Summary prompt" rows={7} value={settings.summary.prompt}
                onInput={event => summary({ prompt: event.currentTarget.value })} /></label>
              <button type="button" className="btn" onClick={() => summary({ prompt: defaultAppSettings().summary.prompt })}>Restore default prompt</button>
            </>}
          </section>
        </div>
        <footer className="settings-actions"><button type="button" className="btn" onClick={close}>Cancel</button>
          <button type="submit" className="btn btn-primary">Save</button></footer>
      </form>
    </dialog>}
    {message && <span role="status" className="sr-only">{message}</span>}
  </>;
}
