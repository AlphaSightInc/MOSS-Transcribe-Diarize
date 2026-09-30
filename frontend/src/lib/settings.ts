import defaultPrompt from "./final-summary-prompt.txt?raw";

export type Vendor = "gemini" | "openai_compatible";
export interface AppSettings {
  transcription: { vendor: Vendor; url: string; model: string; apiKey: string;
                   refreshSeconds: number; contextSeconds: number };
  summary: { vendor: Vendor | "off"; url: string; model: string; apiKey: string;
             rolling: boolean; waitSeconds: number; language: string;
             timeoutSeconds: number; prompt: string };
  general: { cleanupAfterStop: boolean };
}

/** I-2 transcription settings object, identical for live, File and URL. */
export interface TranscriptionWire { vendor: Vendor; url: string | null; model: string; api_key: string | null }
export interface EngineSettingsWire {
  transcription: TranscriptionWire; refresh_seconds: number; context_seconds: number; cleanup_after_stop: boolean;
}
export interface SummaryProviderWire { vendor: "gemini"; model: string; api_key: string | null }
export interface SecondsBounds { min: number; max: number; default: number }

const KEY = "moss.settings.v2";
const V1_KEY = "moss.settings.v1";
const OLD_KEY = "moss.browser-final-summary.v1";
export const SETTINGS_CHANGED = "moss:settings-changed";
export const DEFAULT_TRANSCRIPTION_MODEL = "gemini-3.5-transcribe";
export const DEFAULT_SUMMARY_MODEL = "gemini-3.8-flash";
export const DEFAULT_SUMMARY_PROMPT = defaultPrompt;
/** Fallback bounds when the descriptor carries no `engine_options` (I-3). */
export const REFRESH_SECONDS: SecondsBounds = { min: 5, max: 60, default: 15 };
export const CONTEXT_SECONDS: SecondsBounds = { min: 90, max: 300, default: 90 };
// The round-2 default prompt opened with this sentence; an untouched copy saved by v1 is replaced by the new default.
const V1_DEFAULT_PROMPT_OPENING = "Create the sole final briefing for a thoughtful reader who will not read the transcript.";

export function defaultAppSettings(): AppSettings {
  return {
    transcription: { vendor: "gemini", url: "", model: DEFAULT_TRANSCRIPTION_MODEL, apiKey: "",
      refreshSeconds: REFRESH_SECONDS.default, contextSeconds: CONTEXT_SECONDS.default },
    summary: { vendor: "gemini", url: "", model: DEFAULT_SUMMARY_MODEL, apiKey: "", rolling: true,
      waitSeconds: 60, language: "", timeoutSeconds: 120, prompt: DEFAULT_SUMMARY_PROMPT },
    general: { cleanupAfterStop: true }
  };
}

export function loadAppSettings(): AppSettings {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (saved) return normalize(saved);
    const v1 = JSON.parse(localStorage.getItem(V1_KEY) ?? "null");
    const old = v1 ? null : JSON.parse(localStorage.getItem(OLD_KEY) ?? "null");
    if (v1 || old) {
      const migrated = v1 ? migrateV1(v1) : migrateBrowserSummary(old);
      saveAppSettings(migrated);
      localStorage.removeItem(V1_KEY);
      localStorage.removeItem(OLD_KEY);
      return migrated;
    }
  } catch { /* A malformed browser value falls back to defaults. */ }
  return defaultAppSettings();
}

export function saveAppSettings(settings: AppSettings): void {
  const normalized = normalize(settings);
  // An unedited prompt is stored empty so a later default reaches this browser too.
  const stored = { ...normalized, summary: { ...normalized.summary,
    prompt: normalized.summary.prompt === DEFAULT_SUMMARY_PROMPT ? "" : normalized.summary.prompt } };
  localStorage.setItem(KEY, JSON.stringify(stored));
  document.dispatchEvent(new Event(SETTINGS_CHANGED));
}

export function transcriptionWire(settings: AppSettings): TranscriptionWire {
  const { vendor, url, model, apiKey } = settings.transcription;
  return { vendor, url: vendor === "openai_compatible" && url.trim() ? url.trim() : null,
    model: model.trim() || DEFAULT_TRANSCRIPTION_MODEL, api_key: apiKey.trim() || null };
}

export function engineSettingsFrom(settings: AppSettings): EngineSettingsWire {
  return { transcription: transcriptionWire(settings), refresh_seconds: settings.transcription.refreshSeconds,
    context_seconds: settings.transcription.contextSeconds,
    // J1: clean-up after Stop is offered only for Gemini transcription.
    cleanup_after_stop: settings.general.cleanupAfterStop && settings.transcription.vendor === "gemini" };
}

/** The server-side summary provider; null when summaries do not go through the server. */
export function summaryProviderWire(settings: AppSettings): SummaryProviderWire | null {
  if (settings.summary.vendor !== "gemini") return null;
  return { vendor: "gemini", model: settings.summary.model.trim() || DEFAULT_SUMMARY_MODEL,
    api_key: settings.summary.apiKey.trim() || null };
}

const text = (value: unknown, fallback = "") => typeof value === "string" ? value : fallback;
const flag = (value: unknown, fallback: boolean) => typeof value === "boolean" ? value : fallback;
const seconds = (value: unknown, fallback: number, min: number) =>
  typeof value === "number" && Number.isInteger(value) && value >= min ? value : fallback;
const vendor = (value: unknown): Vendor | null => value === "gemini" || value === "openai_compatible" ? value : null;
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};

function normalize(value: unknown): AppSettings {
  const defaults = defaultAppSettings();
  const root = record(value), t = record(root.transcription), s = record(root.summary), g = record(root.general);
  const summaryVendor = s.vendor === "off" ? "off" : vendor(s.vendor) ?? defaults.summary.vendor;
  return {
    transcription: { vendor: vendor(t.vendor) ?? defaults.transcription.vendor, url: text(t.url),
      model: text(t.model, defaults.transcription.model), apiKey: text(t.apiKey),
      refreshSeconds: seconds(t.refreshSeconds, defaults.transcription.refreshSeconds, 1),
      contextSeconds: seconds(t.contextSeconds, defaults.transcription.contextSeconds, 1) },
    summary: { vendor: summaryVendor, url: text(s.url), model: text(s.model, defaults.summary.model),
      apiKey: text(s.apiKey), rolling: flag(s.rolling, defaults.summary.rolling),
      waitSeconds: seconds(s.waitSeconds, defaults.summary.waitSeconds, 0), language: text(s.language),
      timeoutSeconds: seconds(s.timeoutSeconds, defaults.summary.timeoutSeconds, 1),
      prompt: text(s.prompt) || defaults.summary.prompt },
    general: { cleanupAfterStop: flag(g.cleanupAfterStop, defaults.general.cleanupAfterStop) }
  };
}

function migratedPrompt(value: unknown): string {
  const prompt = text(value);
  return prompt.startsWith(V1_DEFAULT_PROMPT_OPENING) ? "" : prompt;
}

/** v1 → v2: presets become explicit seconds; built-in/external become vendors. */
function migrateV1(value: unknown): AppSettings {
  const v1 = record(value), s = record(v1.summary);
  const [refreshSeconds, contextSeconds] = v1.speakerWindow === "economy" ? [30, 90]
    : v1.speakerWindow === "max" ? [15, 180] : [15, 90];
  const external = s.provider === "external";
  const interval = typeof s.intervalSeconds === "number" ? s.intervalSeconds : 60;
  return normalize({
    transcription: { refreshSeconds, contextSeconds },
    summary: { vendor: s.provider === "off" ? "off" : external ? "openai_compatible" : "gemini",
      url: external ? s.externalUrl : "", model: external ? s.externalModel : s.model,
      apiKey: external ? s.externalApiKey : "", rolling: interval !== 0,
      waitSeconds: interval === 0 ? 60 : interval, language: s.language, timeoutSeconds: s.timeoutSeconds,
      prompt: migratedPrompt(s.prompt) },
    general: { cleanupAfterStop: v1.cleanupAfterStop }
  });
}

/** The older browser-only summary settings: a configured endpoint means OpenAI-compatible. */
function migrateBrowserSummary(value: unknown): AppSettings {
  const old = record(value);
  const configured = Boolean(text(old.endpoint) && text(old.model));
  return normalize({ summary: { vendor: configured ? "openai_compatible" : "off", url: old.endpoint,
    model: configured ? old.model : DEFAULT_SUMMARY_MODEL, apiKey: old.apiKey, language: old.language,
    timeoutSeconds: old.timeoutSeconds, prompt: migratedPrompt(old.prompt) } });
}
