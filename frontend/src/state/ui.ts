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

export function hydrateUiState(storage: StorageLike = browserStorage()): void {
  controlPanelCollapsed.value =
    loadBoolean(storage, storageKeys.controlPanelCollapsed) ?? false;
  historyPanelCollapsed.value =
    loadBoolean(storage, storageKeys.historyPanelCollapsed) ?? false;
}

export function setControlPanelCollapsed(
  nextValue: boolean,
  storage: StorageLike = browserStorage()
): void {
  controlPanelCollapsed.value = nextValue;
  saveBoolean(storage, storageKeys.controlPanelCollapsed, nextValue);
}

export function setHistoryPanelCollapsed(
  nextValue: boolean,
  storage: StorageLike = browserStorage()
): void {
  historyPanelCollapsed.value = nextValue;
  saveBoolean(storage, storageKeys.historyPanelCollapsed, nextValue);
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
