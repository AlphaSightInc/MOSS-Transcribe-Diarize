import defaultPrompt from "./final-summary-prompt.txt?raw";

export type SummaryProvider = "built-in" | "external" | "off";
export type SpeakerWindow = "balanced" | "economy" | "max";
export interface AppSettings {
  speakerWindow: SpeakerWindow;
  cleanupAfterStop: boolean;
  summary: {
    provider: SummaryProvider;
    model: string;
    externalUrl: string;
    externalModel: string;
    externalApiKey: string;
    language: string;
    intervalSeconds: number;
    timeoutSeconds: number;
    prompt: string;
  };
}

const KEY = "moss.settings.v1";
const OLD_KEY = "moss.browser-final-summary.v1";
export const SETTINGS_CHANGED = "moss:settings-changed";
export const BUILT_IN_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"] as const;

export function defaultAppSettings(): AppSettings {
  return { speakerWindow: "balanced", cleanupAfterStop: false, summary: {
    provider: "built-in", model: BUILT_IN_MODELS[0], externalUrl: "", externalModel: "",
    externalApiKey: "", language: "", intervalSeconds: 60, timeoutSeconds: 120, prompt: defaultPrompt
  } };
}

export function loadAppSettings(): AppSettings {
  const defaults = defaultAppSettings();
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (saved) return normalize(saved, defaults);
    const old = JSON.parse(localStorage.getItem(OLD_KEY) ?? "null");
    if (old) {
      const migrated = normalize({ summary: {
        provider: old.endpoint && old.model ? "external" : "off", model: defaults.summary.model, intervalSeconds: defaults.summary.intervalSeconds, externalUrl: old.endpoint,
        externalModel: old.model, externalApiKey: old.apiKey, prompt: old.prompt,
        language: old.language, timeoutSeconds: old.timeoutSeconds
      } }, defaults);
      saveAppSettings(migrated);
      localStorage.removeItem(OLD_KEY);
      return migrated;
    }
  } catch { /* A malformed browser value falls back to defaults. */ }
  return defaults;
}

export function saveAppSettings(settings: AppSettings): void {
  const normalized = normalize(settings, defaultAppSettings());
  localStorage.setItem(KEY, JSON.stringify(normalized));
  document.dispatchEvent(new Event(SETTINGS_CHANGED));
}

function normalize(value: Partial<AppSettings>, defaults: AppSettings): AppSettings {
  const summary = value.summary ?? defaults.summary;
  const provider = ["built-in", "external", "off"].includes(summary.provider) ? summary.provider : defaults.summary.provider;
  const model = BUILT_IN_MODELS.find(candidate => candidate === summary.model) ?? defaults.summary.model;
  const number = (field: number | undefined, fallback: number) => Number.isFinite(field) && field! > 0 ? field! : fallback;
  return {
    speakerWindow: ["balanced", "economy", "max"].includes(value.speakerWindow ?? "") ? value.speakerWindow! : defaults.speakerWindow,
    cleanupAfterStop: typeof value.cleanupAfterStop === "boolean" ? value.cleanupAfterStop : defaults.cleanupAfterStop,
    summary: { provider, model,
      externalUrl: typeof summary.externalUrl === "string" ? summary.externalUrl : "",
      externalModel: typeof summary.externalModel === "string" ? summary.externalModel : "",
      externalApiKey: typeof summary.externalApiKey === "string" ? summary.externalApiKey : "",
      language: typeof summary.language === "string" ? summary.language : "",
      intervalSeconds: summary.intervalSeconds === 0 ? 0 : number(summary.intervalSeconds, defaults.summary.intervalSeconds),
      timeoutSeconds: number(summary.timeoutSeconds, defaults.summary.timeoutSeconds),
      prompt: typeof summary.prompt === "string" ? summary.prompt : defaults.summary.prompt
    }
  };
}
