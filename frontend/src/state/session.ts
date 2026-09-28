import { computed, signal } from "@preact/signals";
import type {
  SessionLifecycle,
  SessionMode,
  TranscriptItem,
  TranscriptUpdateMetadata,
  WsEvent
} from "../api/types";
import { type MergedTranscriptItem, upsertTranscriptItems } from "../lib/mergeTranscript";

export const sessionTranscriptItems = signal<MergedTranscriptItem[]>([]);
export const transcriptSearchQuery = signal("");
export const transcript = computed(() => sessionTranscriptItems.value);
export const sessionId = signal<string | null>(null);
// Page-local capture ownership, not an account credential. Reload/history observers
// stay read-only even though tabs in this browser share workspace authority.
export const captureMeetingId = signal<string | null>(null);
export const sessionMode = signal<SessionMode>("live");
export const sessionState = signal("idle");
export const sessionStatus = signal<SessionLifecycle>("idle");
export const sessionError = signal<string | null>(null);
// Titles are Phase 2, but the transcript pane renders one and falls back to "LiveTranscribe";
// the signal exists so that fallback is the only reason it is ever empty.
export const sessionTitle = signal("");
export const sessionStatusLine = signal<string | null>(null);
export const sessionNeedsReview = signal(false);
export const liveLabelPolicy = signal<"current" | "La">("current");

export function applySessionStateEvent(
  event: Extract<WsEvent, { type: "session_state" }>
): void {
  const previousSessionId = sessionId.value;
  sessionId.value = event.session_id;
  sessionMode.value = event.mode;
  sessionState.value = event.state;
  sessionStatus.value = event.status;
  sessionError.value = event.error ?? null;
  sessionStatusLine.value = event.status_line ?? null;
  if (typeof event.needs_review === "boolean") sessionNeedsReview.value = event.needs_review;
  else if (event.status === "active") sessionNeedsReview.value = false;
  if (event.live_label_policy) liveLabelPolicy.value = event.live_label_policy;
  else if (previousSessionId !== event.session_id) liveLabelPolicy.value = "current";
}

export function applyTranscriptUpdate(
  items: TranscriptItem[],
  metadata?: TranscriptUpdateMetadata
): void {
  sessionTranscriptItems.value = upsertTranscriptItems(sessionTranscriptItems.value, items, metadata);
}

export function replaceTranscript(items: TranscriptItem[]): void {
  sessionTranscriptItems.value = upsertTranscriptItems([], items);
}

export function clearSessionDisplay(): void {
  transcriptSearchQuery.value = "";
  sessionTranscriptItems.value = [];
}

export function resetSessionState(): void {
  captureMeetingId.value = null;
  sessionId.value = null;
  sessionMode.value = "live";
  sessionState.value = "idle";
  sessionStatus.value = "idle";
  sessionError.value = null;
  sessionStatusLine.value = null;
  sessionNeedsReview.value = false;
  liveLabelPolicy.value = "current";
  clearSessionDisplay();
}
