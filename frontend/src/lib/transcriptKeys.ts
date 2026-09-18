import type { TranscriptItem } from "../api/types";
import { normalizeInlineWhitespace, trimString } from "./text";

export function serializeTranscriptSegmentKey(start: number, end: number, text: string): string {
  return `${start.toFixed(2)}|${end.toFixed(2)}|${normalizeInlineWhitespace(text).toLowerCase()}`;
}

export function buildTranscriptTargetKey(
  item: Pick<TranscriptItem, "start" | "end" | "text" | "segment_id"> & Partial<Pick<TranscriptItem, "source_lane" | "speaker" | "speaker_entity_id">>
): string {
  const segmentId = trimString(item.segment_id);
  if (segmentId) {
    return `segment:${segmentId}`;
  }

  const key = serializeTranscriptSegmentKey(item.start, item.end, item.text);
  const speaker = item.speaker_entity_id ?? item.speaker;
  return `${key}${item.source_lane ? `|${item.source_lane}` : ""}${speaker ? `|${speaker}` : ""}`;
}
