import { computed, signal } from "@preact/signals";
import type { Meeting } from "../api/meetings";
import { browserStorage, loadBoolean, saveBoolean, storageKeys, type StorageLike } from "../lib/persistence";

export type AppView = "transcript" | "summary";
export type DisplayMode = "formatted" | "raw";
export type ToastTone = "info" | "success" | "warning" | "error";

export interface ToastItem {
  id: string;
  message: string;
  tone: ToastTone;
  createdAt: number;
}

export const view = signal<AppView>("transcript");
export const selectedSummaryMeeting = signal<Meeting | null>(null);
export const summaryPageOpen = signal(false);
export const displayMode = signal<DisplayMode>("formatted");
export const controlPanelCollapsed = signal(false);
export const historyPanelCollapsed = signal(false);
export const historyView = signal<"sessions" | "voiceprints">("sessions");
// On by default: the transcript follows the newest words until the reader scrolls up.
export const autoscroll = signal(true);
export const llmModalOpen = signal(false);
export const toastQueue = signal<ToastItem[]>([]);
export const activeToast = computed(() => toastQueue.value[0] ?? null);

/**
 * Side-panel collapse is a per-browser convenience (#8). Storage that is blocked or throws leaves the
 * panels expanded and the toggles working for this page.
 */
export function hydrateUiState(storage?: StorageLike): void {
  try {
    const store = storage ?? browserStorage();
    controlPanelCollapsed.value = loadBoolean(store, storageKeys.controlPanelCollapsed) ?? false;
    historyPanelCollapsed.value = loadBoolean(store, storageKeys.historyPanelCollapsed) ?? false;
  } catch { /* expanded defaults */ }
}

export function setControlPanelCollapsed(nextValue: boolean, storage?: StorageLike): void {
  controlPanelCollapsed.value = nextValue;
  persistCollapse(storageKeys.controlPanelCollapsed, nextValue, storage);
}

export function setHistoryPanelCollapsed(nextValue: boolean, storage?: StorageLike): void {
  historyPanelCollapsed.value = nextValue;
  persistCollapse(storageKeys.historyPanelCollapsed, nextValue, storage);
}

function persistCollapse(key: string, value: boolean, storage?: StorageLike): void {
  try {
    saveBoolean(storage ?? browserStorage(), key, value);
  } catch { /* not remembered across reloads */ }
}

export function setLlmModalOpen(nextValue: boolean): void {
  llmModalOpen.value = nextValue;
}

export function enqueueToast(message: string, tone: ToastTone = "info"): string {
  const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  toastQueue.value = [
    ...toastQueue.value,
    {
      id,
      message,
      tone,
      createdAt: Date.now()
    }
  ];
  return id;
}

export function dismissToast(id: string): void {
  toastQueue.value = toastQueue.value.filter((toast) => toast.id !== id);
}

export function clearToasts(): void {
  toastQueue.value = [];
}

export function resetUiState(): void {
  view.value = "transcript";
  selectedSummaryMeeting.value = null;
  summaryPageOpen.value = false;
  displayMode.value = "formatted";
  controlPanelCollapsed.value = false;
  historyPanelCollapsed.value = false;
  historyView.value = "sessions";
  autoscroll.value = true;
  llmModalOpen.value = false;
  clearToasts();
}
