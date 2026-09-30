import { useEffect, useRef, useState } from "preact/hooks";
import { summaryUrl, validateSettings, RELAY_ENDPOINT } from "../lib/finalSummary";
import { externalSettings } from "../lib/summaryRequests";
import {
  CONTEXT_SECONDS, DEFAULT_SUMMARY_MODEL, DEFAULT_SUMMARY_PROMPT, DEFAULT_TRANSCRIPTION_MODEL, loadAppSettings,
  REFRESH_SECONDS, saveAppSettings, type AppSettings, type SecondsBounds, type Vendor
} from "../lib/settings";
import "../styles/settings.css";

type Tab = "transcription" | "summary" | "general";
type ModelTab = "transcription" | "summary";
interface Status { message: string; tone: "neutral" | "success" | "error" }
interface EngineOptions { vendors: Vendor[]; refresh: SecondsBounds; context: SecondsBounds; cleanupAvailable: boolean }
interface Numbers { refresh: string; context: string; wait: string }

const TABS: { id: Tab; label: string }[] = [
  { id: "transcription", label: "Transcription" }, { id: "summary", label: "Summary" }, { id: "general", label: "General" }];
const VENDOR_LABELS: Record<Vendor | "off", string> = {
  gemini: "Gemini (AI Studio)", openai_compatible: "OpenAI-compatible", off: "Off" };
const MODEL_DEFAULTS: Record<ModelTab, string> = { transcription: DEFAULT_TRANSCRIPTION_MODEL, summary: DEFAULT_SUMMARY_MODEL };
const FALLBACK_OPTIONS: EngineOptions = { vendors: ["gemini", "openai_compatible"], refresh: REFRESH_SECONDS,
  context: CONTEXT_SECONDS, cleanupAvailable: true };
const KEY_NEEDED = "Enter your Gemini API key.";

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function bounds(value: unknown, fallback: SecondsBounds): SecondsBounds {
  const range = record(value);
  return range && Number.isInteger(range.min) && Number.isInteger(range.max)
    ? { min: range.min as number, max: range.max as number, default: Number.isInteger(range.default) ? range.default as number : fallback.default }
    : fallback;
}
/** I-3 descriptor `engine_options`; older descriptors keep the documented fallback bounds. */
export function readEngineOptions(payload: unknown): EngineOptions {
  const options = record(record(record(payload)?.descriptor)?.engine_options);
  if (!options) return FALLBACK_OPTIONS;
  const vendors = Array.isArray(options.transcription_vendors)
    ? options.transcription_vendors.filter((v): v is Vendor => v === "gemini" || v === "openai_compatible") : [];
  return { vendors: vendors.length ? vendors : FALLBACK_OPTIONS.vendors,
    refresh: bounds(options.refresh_seconds, REFRESH_SECONDS), context: bounds(options.context_seconds, CONTEXT_SECONDS),
    cleanupAvailable: record(options.cleanup_after_stop)?.available !== false };
}

function isHttpUrl(value: string): boolean {
  try { return ["http:", "https:"].includes(new URL(value).protocol); } catch { return false; }
}
function integer(value: string): number | null {
  return /^\d+$/.test(value.trim()) ? Number(value.trim()) : null;
}

/** Parse and check the draft; the first problem names its tab. */
function validate(draft: AppSettings, numbers: Numbers, options: EngineOptions): { settings: AppSettings } | { error: string; tab: Tab } {
  const refresh = integer(numbers.refresh), context = integer(numbers.context), wait = integer(numbers.wait);
  const t = draft.transcription, s = draft.summary;
  const fail = (tab: Tab, error: string) => ({ tab, error });
  if (refresh === null || refresh < options.refresh.min || refresh > options.refresh.max)
    return fail("transcription", `Refresh every must be ${options.refresh.min}–${options.refresh.max} seconds.`);
  if (context === null || context < options.context.min || context > options.context.max)
    return fail("transcription", `Context must be ${options.context.min}–${options.context.max} seconds.`);
  if (refresh > context) return fail("transcription", "Refresh every cannot exceed Context.");
  if (t.vendor === "openai_compatible" && !isHttpUrl(t.url.trim())) return fail("transcription", "Enter the transcription URL (http or https).");
  if (!t.model.trim()) return fail("transcription", "Enter a model name.");
  if (s.vendor !== "off") {
    if (wait === null) return fail("summary", "Wait after each summary must be 0 seconds or more.");
    if (!s.model.trim()) return fail("summary", "Enter a model name.");
    if (s.vendor === "openai_compatible") {
      if (!s.url.trim()) return fail("summary", "Enter the summary URL.");
      try { validateSettings(externalSettings(draft)); } catch (cause) {
        return fail("summary", cause instanceof Error ? cause.message : "Check the summary URL.");
      }
    }
  }
  return { settings: { ...draft,
    transcription: { ...t, url: t.url.trim(), model: t.model.trim(), refreshSeconds: refresh, contextSeconds: context },
    summary: { ...s, url: s.url.trim(), model: s.model.trim(), waitSeconds: wait ?? s.waitSeconds } } };
}

async function detailOf(response: Response): Promise<string> {
  const payload = await response.json().catch(() => null);
  return typeof payload?.detail === "string" ? payload.detail : "";
}

/**
 * Test one tab's provider. Server path: `POST /api/providers/test` (I-2). An OpenAI-compatible
 * summary is called from this browser in use, so it is tested from here too (reachability, CORS, key).
 */
export async function testProvider(purpose: ModelTab, settings: AppSettings, fetcher: typeof fetch = fetch): Promise<Status> {
  const tab = settings[purpose];
  if (tab.vendor === "gemini" && !tab.apiKey.trim()) return { message: KEY_NEEDED, tone: "error" };
  try {
    if (purpose === "summary" && tab.vendor === "openai_compatible") return await testBrowserProvider(settings, fetcher);
    const response = await fetcher("/api/providers/test", { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ purpose, vendor: tab.vendor,
        url: tab.vendor === "openai_compatible" ? tab.url.trim() || null : null, model: tab.model.trim(),
        api_key: tab.apiKey.trim() || null }) });
    const payload = await response.json().catch(() => null);
    if (response.ok && payload?.ok === true) return { message: "Connection OK", tone: "success" };
    const detail = typeof payload?.detail === "string" ? payload.detail : "";
    return { message: detail || "Test failed.", tone: "error" };
  } catch { return { message: "Test failed — the server could not be reached.", tone: "error" }; }
}

async function testBrowserProvider(settings: AppSettings, fetcher: typeof fetch): Promise<Status> {
  let external;
  try { external = validateSettings(externalSettings(settings)); } catch (cause) {
    return { message: cause instanceof Error ? cause.message : "Check the summary URL.", tone: "error" };
  }
  const relay = external.endpoint === RELAY_ENDPOINT;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), external.timeoutSeconds * 1000);
  try {
    const response = await fetcher(summaryUrl(external.endpoint).replace(/\/chat\/completions$/, "/models"), {
      credentials: relay ? "same-origin" : "omit", redirect: "error", referrerPolicy: "no-referrer", signal: controller.signal,
      headers: !relay && external.apiKey ? { Authorization: `Bearer ${external.apiKey}` } : {} });
    if (response.status === 401 || response.status === 403) return { message: "The provider rejected the API key.", tone: "error" };
    if (!response.ok) return { message: (await detailOf(response)) || `The provider answered ${response.status}.`, tone: "error" };
    const models = (await response.json().catch(() => null))?.data;
    if (Array.isArray(models) && !models.some(model => model?.id === external.model))
      return { message: "The provider does not list this model.", tone: "error" };
    return { message: "Connection OK", tone: "success" };
  } catch { return { message: "Could not reach the provider from this browser.", tone: "error" }; }
  finally { clearTimeout(timer); }
}

const numbersOf = (settings: AppSettings): Numbers => ({ refresh: String(settings.transcription.refreshSeconds),
  context: String(settings.transcription.contextSeconds), wait: String(settings.summary.waitSeconds) });

export function SettingsDialog() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("transcription");
  const [draft, setDraft] = useState(loadAppSettings);
  const [numbers, setNumbers] = useState(() => numbersOf(draft));
  const [options, setOptions] = useState(FALLBACK_OPTIONS);
  const [status, setStatus] = useState<Status>({ message: "", tone: "neutral" });
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const stash = useRef(new Map<string, Pick<AppSettings["summary"], "url" | "model" | "apiKey">>());
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetch("/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2", { credentials: "same-origin" })
      .then(response => response.ok ? response.json() : null)
      .then(payload => { if (!cancelled) setOptions(readEngineOptions(payload)); })
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

  const show = () => {
    const saved = loadAppSettings();
    setDraft(saved); setNumbers(numbersOf(saved)); setTab("transcription");
    setStatus({ message: "", tone: "neutral" }); setShowKey(false); stash.current.clear(); setOpen(true);
  };
  const close = () => setOpen(false);
  const edit = <K extends keyof AppSettings>(section: K, patch: Partial<AppSettings[K]>) =>
    setDraft(current => ({ ...current, [section]: { ...current[section], ...patch } }));
  const selectTab = (next: Tab) => { setTab(next); setStatus({ message: "", tone: "neutral" }); };
  // Each vendor keeps its own URL, model and key while the dialog is open, so a key never follows a vendor switch.
  const switchVendor = (section: ModelTab, vendor: Vendor | "off") => {
    const current = draft[section];
    stash.current.set(`${section}:${current.vendor}`, { url: current.url, model: current.model, apiKey: current.apiKey });
    const restored = stash.current.get(`${section}:${vendor}`)
      ?? { url: "", model: vendor === "gemini" ? MODEL_DEFAULTS[section]
        // OpenAI's speaker-labelling model; text-only models give one speaker per request (WP-F F2).
        : section === "transcription" && vendor === "openai_compatible" ? "gpt-4o-transcribe-diarize" : "", apiKey: "" };
    edit(section, { vendor, ...(vendor === "off" ? {} : restored) } as Partial<AppSettings[typeof section]>);
  };
  const save = (event: Event) => {
    event.preventDefault();
    const result = validate(draft, numbers, options);
    if ("error" in result) { setTab(result.tab); setStatus({ message: result.error, tone: "error" }); return; }
    saveAppSettings(result.settings);
    close();
  };
  const test = async () => {
    if (tab === "general") return;
    setTesting(true); setStatus({ message: "", tone: "neutral" }); // The button reads "Testing…".
    try { setStatus(await testProvider(tab, draft)); } finally { setTesting(false); }
  };

  const t = draft.transcription, s = draft.summary;
  const cleanupBlocked = t.vendor === "openai_compatible" ? "Not available for OpenAI-compatible transcription"
    : !options.cleanupAvailable ? "Not available on this server" : "";
  const keyField = (section: ModelTab) => {
    const value = draft[section];
    return <label className="llm-modal-field llm-modal-field--full">
      <span className="field-label">API key</span>
      <span className="llm-modal-inline-field">
        <input type={showKey ? "text" : "password"} autoComplete="off" spellcheck={false} aria-label={`${TABS.find(x => x.id === section)!.label} API key`}
          placeholder={value.vendor === "gemini" ? "Required" : "Optional"} value={value.apiKey}
          onInput={event => edit(section, { apiKey: event.currentTarget.value })} />
        <button type="button" className="icon-btn" aria-label={showKey ? "Hide API key" : "Show API key"}
          aria-pressed={showKey} onClick={() => setShowKey(current => !current)}>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12Z" fill="none" stroke="currentColor"
              strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
            <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.7" />
          </svg>
        </button>
      </span>
    </label>;
  };
  const endpointFields = (section: ModelTab, vendors: (Vendor | "off")[]) => {
    const value = draft[section];
    const label = TABS.find(x => x.id === section)!.label;
    return <>
      <label className="llm-modal-field">
        <span className="field-label">Vendor</span>
        <select aria-label={`${label} vendor`} value={value.vendor}
          onChange={event => switchVendor(section, event.currentTarget.value as Vendor | "off")}>
          {vendors.map(vendor => <option key={vendor} value={vendor}>{VENDOR_LABELS[vendor]}</option>)}
        </select>
      </label>
      {value.vendor !== "off" && <>
        <label className="llm-modal-field">
          <span className="field-label">Model name</span>
          <input type="text" autoComplete="off" spellcheck={false} aria-label={`${label} model`} value={value.model}
            onInput={event => edit(section, { model: event.currentTarget.value })} />
        </label>
        {value.vendor === "openai_compatible" && <label className="llm-modal-field llm-modal-field--full">
          <span className="field-label">URL</span>
          <input type="url" autoComplete="off" spellcheck={false} aria-label={`${label} URL`} value={value.url}
            placeholder="https://…/v1" onInput={event => edit(section, { url: event.currentTarget.value })} />
        </label>}
        {keyField(section)}
      </>}
    </>;
  };

  return <>
    <button type="button" className="settings-trigger" aria-label="Settings" title="Settings" onClick={show}>⚙</button>
    {open && <dialog ref={dialogRef} className="llm-modal settings-modal" aria-labelledby="settings-title" onCancel={close}>
      <form className="llm-modal-shell" onSubmit={save} noValidate>
        <header className="llm-modal-head">
          <div><p className="eyebrow">Preferences</p><h2 id="settings-title">Settings</h2></div>
          <button type="button" className="icon-btn" aria-label="Close settings" onClick={close}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6 18 18M18 6 6 18" fill="none" stroke="currentColor"
              strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" /></svg>
          </button>
        </header>
        <div className="llm-modal-body">
          <div className="seg settings-tabs" role="tablist" aria-label="Settings sections">
            {TABS.map(item => <button key={item.id} type="button" role="tab" id={`settings-tab-${item.id}`}
              className="seg-btn" aria-selected={tab === item.id} aria-controls="settings-panel"
              onClick={() => selectTab(item.id)}>{item.label}</button>)}
          </div>
          <div className="llm-modal-grid" role="tabpanel" id="settings-panel" aria-labelledby={`settings-tab-${tab}`}>
            {tab === "transcription" && <>
              {endpointFields("transcription", options.vendors)}
              <label className="llm-modal-field">
                <span className="field-label">Refresh every (s)</span>
                <input type="number" inputMode="numeric" min={options.refresh.min} max={options.refresh.max} step={1}
                  aria-label="Refresh every (s)" value={numbers.refresh}
                  onInput={event => setNumbers(current => ({ ...current, refresh: event.currentTarget.value }))} />
              </label>
              <label className="llm-modal-field">
                <span className="field-label">Context (s)</span>
                <input type="number" inputMode="numeric" min={options.context.min} max={options.context.max} step={1}
                  aria-label="Context (s)" value={numbers.context}
                  onInput={event => setNumbers(current => ({ ...current, context: event.currentTarget.value }))} />
              </label>
            </>}
            {tab === "summary" && <>
              {endpointFields("summary", ["gemini", "openai_compatible", "off"])}
              {s.vendor !== "off" && <>
                <label className="llm-modal-toggle llm-modal-field" title={s.vendor === "gemini" ? undefined : "Rolling summary needs Gemini"}>
                  <input type="checkbox" aria-label="Rolling summary" checked={s.rolling && s.vendor === "gemini"}
                    disabled={s.vendor !== "gemini"} onChange={event => edit("summary", { rolling: event.currentTarget.checked })} />
                  <span>Rolling summary</span>
                </label>
                <label className="llm-modal-field">
                  <span className="field-label">Wait after each summary (s)</span>
                  <input type="number" inputMode="numeric" min={0} step={1} aria-label="Wait after each summary (s)"
                    value={numbers.wait} disabled={!s.rolling || s.vendor !== "gemini"}
                    onInput={event => setNumbers(current => ({ ...current, wait: event.currentTarget.value }))} />
                </label>
                <label className="llm-modal-field">
                  <span className="field-label">Language</span>
                  <input type="text" autoComplete="off" aria-label="Summary language" placeholder="Auto" value={s.language}
                    onInput={event => edit("summary", { language: event.currentTarget.value })} />
                </label>
                <label className="llm-modal-field llm-modal-field--full">
                  <span className="settings-label-row"><span className="field-label">Prompt</span>
                    <button type="button" className="btn ghost settings-inline-btn" disabled={s.prompt === DEFAULT_SUMMARY_PROMPT}
                      onClick={() => edit("summary", { prompt: DEFAULT_SUMMARY_PROMPT })}>Restore default</button></span>
                  <textarea className="settings-prompt" rows={4} aria-label="Summary prompt" value={s.prompt}
                    onInput={event => edit("summary", { prompt: event.currentTarget.value })} />
                </label>
              </>}
            </>}
            {tab === "general" && <label className="llm-modal-toggle llm-modal-field llm-modal-field--full" title={cleanupBlocked || undefined}>
              <input type="checkbox" aria-label="Improve transcript after Stop" disabled={Boolean(cleanupBlocked)}
                checked={draft.general.cleanupAfterStop && !cleanupBlocked}
                onChange={event => edit("general", { cleanupAfterStop: event.currentTarget.checked })} />
              <span>Improve transcript after Stop</span>
            </label>}
          </div>
        </div>
        <footer className="llm-modal-actions">
          <span className="llm-modal-status" data-tone={status.tone} role="status">{status.message}</span>
          <div className="llm-modal-action-row">
            <button type="button" className="btn ghost" onClick={close}>Cancel</button>
            {(tab === "transcription" || (tab === "summary" && s.vendor !== "off")) &&
              <button type="button" className="btn" data-settings-test disabled={testing} onClick={() => void test()}>
                {testing ? "Testing…" : "Test"}</button>}
            <button type="submit" className="btn btn-primary" disabled={testing}>Save</button>
          </div>
        </footer>
      </form>
    </dialog>}
  </>;
}
