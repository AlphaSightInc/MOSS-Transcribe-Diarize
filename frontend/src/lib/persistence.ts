// Browser preferences and the Account Meeting ID used for read-only reload reattachment.
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
  sessionId: "lt:session:id",
  sessionReattach: "lt:session:reattach",
  llmSettings: "lt:llm:settings"
} as const;

export interface SessionReattachRecord {
  sessionId: string;
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

export function loadSessionId(storage: StorageLike): string | null {
  const value = storage.getItem(storageKeys.sessionId)?.trim();
  return value ? value : null;
}

export function saveSessionId(storage: StorageLike, sessionId: string): void {
  storage.setItem(storageKeys.sessionId, sessionId);
}

export function clearSessionId(storage: StorageLike): void {
  storage.removeItem(storageKeys.sessionId);
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
  return record;
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
