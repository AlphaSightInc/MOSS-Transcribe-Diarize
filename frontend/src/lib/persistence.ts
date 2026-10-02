// Browser preferences and tab-scoped capture recovery.
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const noopStorage: StorageLike = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined
};

export const storageKeys = {
  controlPanelCollapsed: "lt:ui:controlPanelCollapsed",
  historyPanelCollapsed: "lt:ui:historyPanelCollapsed",
  captureSources: "lt:capture:sources",
  sessionReattach: "lt:session:reattach"
} as const;

/** Which sources a recording takes (round 5, Q15). Both by default; remembered per browser. */
export interface CaptureSources {
  system: boolean;
  microphone: boolean;
}

export interface CaptureRecord {
  instanceId: string;
  sources: CaptureSources;
  microphoneDeviceId: string | null;
  microphoneMuted: boolean;
  echoCancellation: boolean;
  shareKind: string | null;
}

export interface SessionReattachRecord {
  sessionId: string;
  capture?: CaptureRecord;
}

export function browserStorage(): StorageLike {
  if (typeof window === "undefined" || !window.localStorage) {
    return noopStorage;
  }

  return window.localStorage;
}

export function sessionReattachStorage(): StorageLike {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return noopStorage;
  }
  return window.sessionStorage;
}

export function createMemoryStorage(seed: Record<string, string> = {}): StorageLike {
  const values = new Map(Object.entries(seed));

  return {
    getItem(key) {
      return values.has(key) ? values.get(key) ?? null : null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
    removeItem(key) {
      values.delete(key);
    }
  };
}

function readJson<T>(storage: StorageLike, key: string): T | null {
  const raw = storage.getItem(key);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as T;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

function writeJson<T>(storage: StorageLike, key: string, value: T): void {
  storage.setItem(key, JSON.stringify(value));
}

export function loadBoolean(storage: StorageLike, key: string): boolean | null {
  const value = readJson<unknown>(storage, key);
  return typeof value === "boolean" ? value : null;
}

export function saveBoolean(storage: StorageLike, key: string, value: boolean): void {
  writeJson(storage, key, value);
}

/** Storage that is blocked or throws leaves both sources ticked and the boxes working for this page. */
export function loadCaptureSources(storage?: StorageLike): CaptureSources {
  try {
    const saved = readJson<Partial<CaptureSources>>(storage ?? browserStorage(), storageKeys.captureSources);
    return { system: saved?.system !== false, microphone: saved?.microphone !== false };
  } catch {
    return { system: true, microphone: true };
  }
}

export function saveCaptureSources(value: CaptureSources, storage?: StorageLike): void {
  try {
    writeJson(storage ?? browserStorage(), storageKeys.captureSources, value);
  } catch { /* not remembered across reloads */ }
}

export function loadSessionReattach(storage: StorageLike): SessionReattachRecord | null {
  const value = readJson<unknown>(storage, storageKeys.sessionReattach);
  const record = value as SessionReattachRecord;
  if (
    typeof value !== "object" ||
    value === null ||
    typeof record.sessionId !== "string" ||
    !record.sessionId.trim()
  ) {
    storage.removeItem(storageKeys.sessionReattach);
    return null;
  }
  const capture = record.capture;
  if (!capture || typeof capture.instanceId !== "string" || !capture.instanceId ||
      typeof capture.sources?.system !== "boolean" || typeof capture.sources?.microphone !== "boolean" ||
      (capture.sources.microphone ? typeof capture.microphoneDeviceId !== "string" || !capture.microphoneDeviceId : capture.microphoneDeviceId !== null && typeof capture.microphoneDeviceId !== "string") ||
      typeof capture.microphoneMuted !== "boolean" || typeof capture.echoCancellation !== "boolean" ||
      (capture.shareKind !== null && typeof capture.shareKind !== "string")) return { sessionId: record.sessionId };
  return { sessionId: record.sessionId, capture };
}

export function saveSessionReattach(
  storage: StorageLike,
  value: SessionReattachRecord
): void {
  writeJson(storage, storageKeys.sessionReattach, value);
}

export function clearSessionReattach(storage: StorageLike): void {
  storage.removeItem(storageKeys.sessionReattach);
}
