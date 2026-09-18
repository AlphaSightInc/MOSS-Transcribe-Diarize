import { compareTranscriptOrder } from "./transcriptOrder";
import type { SourceLane } from "./transcriptOrder";
import type { TranscriptItem, TranscriptUpdateMetadata } from "../api/types";
import { buildTranscriptTargetKey } from "./transcriptKeys";
import { normalizeInlineWhitespace, trimString } from "./text";

const MIN_TURN_TEXT_OVERLAP_TOKENS = 4;
const MAX_TURN_TEXT_OVERLAP_TOKENS = 32;
const LIVE_PROVISIONAL_SEGMENT_ID = "live-provisional";

export type TranscriptState = TranscriptItem["state"];

export interface MergedTranscriptItem extends TranscriptItem {
  id: string;
  isNewSpeaker: boolean;
  isContinuation: boolean;
}

export interface TranscriptTurn {
  source_lane?: SourceLane;
  start: number;
  end: number;
  speaker: string;
  speaker_entity_id: string;
  display_name: string;
  state: TranscriptState;
  text: string;
  segment_ids: string[];
  target_segment_keys: string[];
  provisional_stale: boolean;
}

type TranscriptLike = TranscriptItem | MergedTranscriptItem;

const COMMITTED_STATES = new Set(["final", "confirmed"] as const);

export function isCommittedState(
  utterance: Pick<TranscriptItem, "state"> | { state: string }
): utterance is Pick<TranscriptItem, "state"> & { state: "final" | "confirmed" } {
  return COMMITTED_STATES.has(utterance.state as "final" | "confirmed");
}

export function buildTranscriptIdentity(
  item: Pick<TranscriptItem, "segment_id" | "start" | "end" | "text"> & Partial<Pick<TranscriptItem, "source_lane" | "speaker" | "speaker_entity_id">>
): string {
  const segmentId = trimString(item.segment_id);
  if (segmentId) {
    return segmentId;
  }

  return `${item.start}:${item.end}:${item.text}:${item.source_lane ?? ""}:${item.speaker_entity_id ?? item.speaker ?? ""}`;
}

export function compareSegments(left: TranscriptLike, right: TranscriptLike): number {
  return compareTranscriptOrder(left, right);
}

export function upsertTranscriptItems(
  existingItems: readonly TranscriptLike[],
  incomingItems: readonly TranscriptItem[],
  metadata?: TranscriptUpdateMetadata
): MergedTranscriptItem[] {
  let nextItems = existingItems.map(stripDecorations);

  if (isClearDirective(metadata)) {
    const replacementKey = trimString(metadata.replacement_key);
    if (replacementKey.length > 0) {
      nextItems = nextItems.filter(
        (candidate) => trimString(candidate.segment_id) !== replacementKey
      );
    }
  }

  const normalizedIncomingItems = incomingItems
    .map(normalizeTranscriptItem)
    .map((item) => applyProvisionalMetadata(item, metadata))
    .filter((item): item is TranscriptItem => item !== null);

  if (normalizedIncomingItems.length === 0) {
    return decorateTranscript(nextItems);
  }

  const incomingIdentities = new Set(
    normalizedIncomingItems.map((item) => buildTranscriptIdentity(item))
  );
  const incomingProvisionalItems = normalizedIncomingItems.filter(
    (item) => item.state === "provisional"
  );

  nextItems = nextItems.filter((candidate) => {
    if (incomingIdentities.has(buildTranscriptIdentity(candidate))) {
      return false;
    }

    if (
      candidate.state === "provisional" &&
      incomingProvisionalItems.some((item) => provisionalRowsConflict(candidate, item))
    ) {
      return false;
    }

    if (
      normalizedIncomingItems.some(item => item.state !== "provisional" && item.source_lane === candidate.source_lane) &&
      candidate.state === "provisional" &&
      trimString(candidate.segment_id) === LIVE_PROVISIONAL_SEGMENT_ID
    ) {
      return false;
    }

    return true;
  });

  nextItems.push(...normalizedIncomingItems);

  return decorateTranscript(nextItems);
}

function isClearDirective(
  metadata?: TranscriptUpdateMetadata
): metadata is TranscriptUpdateMetadata & { operation: "clear"; replacement_key: string } {
  return metadata?.operation === "clear" && typeof metadata.replacement_key === "string";
}

function provisionalRowsConflict(left: TranscriptLike, right: TranscriptItem): boolean {
  if (left.source_lane !== right.source_lane || left.speaker_entity_id !== right.speaker_entity_id ||
      left.state !== "provisional" || right.state !== "provisional") {
    return false;
  }

  const leftSegmentId = trimString(left.segment_id);
  const rightSegmentId = trimString(right.segment_id);
  if (leftSegmentId.length > 0 && leftSegmentId === rightSegmentId) {
    return true;
  }

  return timeRangesOverlap(left, right);
}

function timeRangesOverlap(
  left: Pick<TranscriptLike, "start" | "end">,
  right: Pick<TranscriptItem, "start" | "end">
): boolean {
  const latestStart = Math.max(left.start, right.start);
  const earliestEnd = Math.min(left.end, right.end);
  return latestStart < earliestEnd || (left.start === right.start && left.end === right.end);
}

export function groupSegmentsIntoTurns<T extends TranscriptLike>(
  segments: readonly T[],
  options: {
    preserveResolvedWhitespace?: boolean;
    skipOverlapTrimming?: boolean;
    resolveText?: (segment: T) => string;
  } = {}
): TranscriptTurn[] {
  const preserveResolvedWhitespace = options.preserveResolvedWhitespace === true;
  const skipOverlapTrimming = options.skipOverlapTrimming === true;
  const resolveText = options.resolveText ?? ((segment: T) => segment.text);
  const turns: TranscriptTurn[] = [];

  for (const segment of [...segments].sort(compareTranscriptOrder)) {
    const last = turns.at(-1) ?? null;
    const sameTranscriptLane =
      last !== null && last.source_lane === segment.source_lane &&
      ((last.state === "provisional" && segment.state === "provisional") ||
        (isCommittedState(last) && isCommittedState(segment)));
    const sameEntity =
      last !== null &&
      trimString(last.speaker_entity_id) &&
      trimString(segment.speaker_entity_id)
        ? last.speaker_entity_id === segment.speaker_entity_id
        : last !== null && last.speaker === segment.speaker;
    const sameDisplayName =
      last !== null &&
      normalizeTurnDisplayName(last.display_name) === normalizeTurnDisplayName(segment.display_name);

    if (last !== null && sameEntity && sameTranscriptLane && sameDisplayName) {
      last.end = Math.max(last.end, segment.end);
      last.state = segment.state;
      if (preserveResolvedWhitespace) {
        last.text = joinPreservedTurnText(last.text, resolveText(segment));
      } else {
        last.text = skipOverlapTrimming
          ? joinTurnText(last.text, resolveText(segment))
          : mergeTurnText(last.text, resolveText(segment));
      }
      last.provisional_stale ||= segment.provisional_stale === true;
      const segmentId = trimString(segment.segment_id);
      if (segmentId) {
        last.segment_ids.push(segmentId);
      }
      last.target_segment_keys.push(buildTranscriptTargetKey(segment));
      continue;
    }

    const segmentIds: string[] = [];
    const segmentId = trimString(segment.segment_id);
    if (segmentId) {
      segmentIds.push(segmentId);
    }

    turns.push({
      ...(segment.source_lane ? { source_lane: segment.source_lane } : {}),
      start: segment.start,
      end: segment.end,
      speaker: segment.speaker,
      speaker_entity_id: segment.speaker_entity_id,
      display_name: segment.display_name,
      state: segment.state,
      text: resolveText(segment),
      segment_ids: segmentIds,
      target_segment_keys: [buildTranscriptTargetKey(segment)],
      provisional_stale: segment.state === "provisional" && segment.provisional_stale === true
    });
  }

  return turns;
}

function normalizeTurnDisplayName(value: string): string {
  return normalizeInlineWhitespace(value);
}

function stripDecorations(item: TranscriptLike): TranscriptItem {
  return {
    ...(item.source_lane ? { source_lane: item.source_lane } : {}),
    start: item.start,
    end: item.end,
    text: item.text,
    speaker: item.speaker,
    speaker_entity_id: item.speaker_entity_id,
    display_name: item.display_name,
    confidence: item.confidence ?? null,
    state: normalizeSegmentState(item.state),
    segment_id: trimString(item.segment_id) || null,
    provisional_stale: item.provisional_stale === true,
    refinement_status: item.refinement_status ?? null,
    preview_speaker: trimString(item.preview_speaker) || null,
    deep_refinement_speaker: trimString(item.deep_refinement_speaker) || null,
    deep_refinement_changed: item.deep_refinement_changed === true
  };
}

function normalizeTranscriptItem(rawItem: TranscriptItem): TranscriptItem | null {
  const start = Number(rawItem.start);
  const end = Number(rawItem.end);
  const text = trimString(rawItem.text);
  if (!Number.isFinite(start) || !Number.isFinite(end) || text.length === 0) {
    return null;
  }

  const speaker = trimString(rawItem.speaker) || "UNKNOWN";
  const displayName = trimString(rawItem.display_name) || speaker;
  const speakerEntityId = trimString(rawItem.speaker_entity_id) || speaker;

  return {
    ...(rawItem.source_lane ? { source_lane: rawItem.source_lane } : {}),
    start,
    end,
    text,
    speaker,
    speaker_entity_id: speakerEntityId,
    display_name: displayName,
    confidence: rawItem.confidence ?? null,
    state: normalizeSegmentState(rawItem.state),
    segment_id: trimString(rawItem.segment_id) || null,
    provisional_stale: rawItem.provisional_stale === true,
    refinement_status: rawItem.refinement_status ?? null,
    preview_speaker: trimString(rawItem.preview_speaker) || null,
    deep_refinement_speaker: trimString(rawItem.deep_refinement_speaker) || null,
    deep_refinement_changed: rawItem.deep_refinement_changed === true
  };
}

function applyProvisionalMetadata(
  item: TranscriptItem | null,
  metadata?: TranscriptUpdateMetadata
): TranscriptItem | null {
  if (!item || item.state !== "provisional") {
    return item;
  }
  if (metadata?.operation !== "stale" || metadata.lane !== "provisional") {
    return item;
  }
  return {
    ...item,
    provisional_stale: true
  };
}

function normalizeSegmentState(state: string): TranscriptState {
  if (state === "provisional" || state === "confirmed" || state === "final") {
    return state;
  }
  return "confirmed";
}

function decorateTranscript(items: readonly TranscriptItem[]): MergedTranscriptItem[] {
  const sorted = [...items].sort(compareSegments);

  return sorted.map((item, index) => {
    const previous = index > 0 ? sorted[index - 1] : null;
    const isNewSpeaker = previous ? previous.speaker_entity_id !== item.speaker_entity_id || previous.source_lane !== item.source_lane : true;

    return {
      ...item,
      id: buildTranscriptIdentity(item),
      isNewSpeaker,
      isContinuation: !isNewSpeaker
    };
  });
}

function joinTurnText(previousText: string, currentText: string): string {
  const previous = normalizeInlineWhitespace(previousText);
  const current = normalizeInlineWhitespace(currentText);
  if (current.length === 0) {
    return previous;
  }
  if (previous.length === 0) {
    return current;
  }
  return `${previous} ${current}`;
}

function joinPreservedTurnText(previousText: string, currentText: string): string {
  const previous = previousText.trim();
  const current = currentText.trim();
  if (current.length === 0) {
    return previous;
  }
  if (previous.length === 0) {
    return current;
  }
  return `${previous}\n\n${current}`;
}

function mergeTurnText(previousText: string, currentText: string): string {
  const previous = normalizeInlineWhitespace(previousText);
  const current = normalizeInlineWhitespace(currentText);
  if (current.length === 0) {
    return previous;
  }
  if (previous.length === 0) {
    return current;
  }

  const previousTokens = previous.split(" ");
  const currentTokens = current.split(" ");
  const maxOverlap = Math.min(
    MAX_TURN_TEXT_OVERLAP_TOKENS,
    previousTokens.length,
    currentTokens.length
  );

  for (let overlap = maxOverlap; overlap >= MIN_TURN_TEXT_OVERLAP_TOKENS; overlap -= 1) {
    const previousWindow = previousTokens
      .slice(previousTokens.length - overlap)
      .map(tokenMatchKey);
    const currentWindow = currentTokens.slice(0, overlap).map(tokenMatchKey);
    if (previousWindow.join(" ") !== currentWindow.join(" ")) {
      continue;
    }

    const suffixTokens = currentTokens.slice(overlap);
    if (suffixTokens.length === 0) {
      return previous;
    }
    return `${previous} ${suffixTokens.join(" ")}`;
  }

  return `${previous} ${current}`;
}

function tokenMatchKey(token: string): string {
  const normalized = String(token).toLocaleLowerCase().replace(/^\W+|\W+$/g, "");
  return normalized.length > 0 ? normalized : String(token).toLocaleLowerCase();
}
