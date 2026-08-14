import { computed, signal } from "@preact/signals";
import type { TranscriptItem, TranscriptUpdateMetadata } from "../api/types";
import { type MergedTranscriptItem, upsertTranscriptItems } from "../lib/mergeTranscript";

export const sessionTranscriptItems = signal<MergedTranscriptItem[]>([]);
export const transcriptSearchQuery = signal("");
export const transcript = computed(() => sessionTranscriptItems.value);

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
