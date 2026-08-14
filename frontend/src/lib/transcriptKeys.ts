import type { TranscriptItem } from "../api/types";
import { normalizeInlineWhitespace, trimString } from "./text";

export function serializeTranscriptSegmentKey(start: number, end: number, text: string): string {
  return `${start.toFixed(2)}|${end.toFixed(2)}|${normalizeInlineWhitespace(text).toLowerCase()}`;
}

export function buildTranscriptTargetKey(
  item: Pick<TranscriptItem, "start" | "end" | "text" | "segment_id">
): string {
  const segmentId = trimString(item.segment_id);
  if (segmentId) {
    return `segment:${segmentId}`;
  }

  return serializeTranscriptSegmentKey(item.start, item.end, item.text);
}
