import type { TranscriptItem } from "../api/types";
import { normalizeInlineWhitespace } from "./text.ts";

const SPEAKER_ID_PATTERN = /^SPEAKER_(\d+)$/;
export const UNKNOWN_SPEAKER_ID = "UNKNOWN";
export const UNRESOLVED_SPEAKER_ID = "S00";
const UNKNOWN_DISPLAY_LABEL = "Preview";
const UNCERTAIN_DISPLAY_LABEL = "Speaker uncertain";
const RESERVED_UNCERTAINTY_LABELS = new Set([
  "",
  "s00",
  "unknown",
  "speaker uncertain",
  "preview"
]);

export function normalizeDisplayNameForStorage(displayName: unknown): string {
  return typeof displayName === "string" ? normalizeInlineWhitespace(displayName) : "";
}

export function normalizeDisplayName(displayName: unknown): string {
  return normalizeDisplayNameForStorage(displayName).toLowerCase();
}

export function buildConsecutiveSpeakerMap(
  segments: readonly Pick<TranscriptItem, "display_name">[]
): Map<string, string> {
  const defaultNames = new Set<string>();
  for (const segment of segments) {
    const name = normalizeDisplayNameForStorage(segment.display_name);
    if (SPEAKER_ID_PATTERN.test(name)) {
      defaultNames.add(name);
    }
  }

  const sorted = [...defaultNames].sort((left, right) => {
    const leftMatch = left.match(SPEAKER_ID_PATTERN);
    const rightMatch = right.match(SPEAKER_ID_PATTERN);
    const leftNumber = leftMatch ? Number.parseInt(leftMatch[1] ?? "0", 10) : 0;
    const rightNumber = rightMatch ? Number.parseInt(rightMatch[1] ?? "0", 10) : 0;
    return leftNumber - rightNumber;
  });

  const mapping = new Map<string, string>();
  sorted.forEach((name, index) => {
    mapping.set(name, `SPEAKER_${String(index + 1).padStart(2, "0")}`);
  });
  return mapping;
}

export function resolveVisibleSpeakerLabel(
  displayName: string,
  consecutiveMap: ReadonlyMap<string, string>
): string {
  const normalizedDisplayName = normalizeDisplayNameForStorage(displayName);
  if (normalizedDisplayName.length === 0) {
    return normalizedDisplayName;
  }

  return consecutiveMap.get(normalizedDisplayName) ?? resolveDisplayLabel(normalizedDisplayName);
}

export function resolveDisplayLabel(displayName: string): string {
  const normalizedDisplayName = normalizeDisplayNameForStorage(displayName);
  if (normalizedDisplayName === UNKNOWN_SPEAKER_ID) return UNKNOWN_DISPLAY_LABEL;
  if (normalizedDisplayName === UNRESOLVED_SPEAKER_ID) return UNCERTAIN_DISPLAY_LABEL;
  return normalizedDisplayName;
}

export function isBackendUnknownSpeakerId(speakerId: unknown): boolean {
  const normalized = normalizeDisplayNameForStorage(speakerId);
  return normalized === UNKNOWN_SPEAKER_ID || normalized === UNRESOLVED_SPEAKER_ID;
}

export function isReservedUncertaintyLabel(displayName: unknown): boolean {
  const normalized = normalizeDisplayNameForStorage(displayName).toLocaleLowerCase();
  return RESERVED_UNCERTAINTY_LABELS.has(normalized) || /^speaker_\d+$/.test(normalized);
}

export function isUnidentifiedSpeakerLabel(displayName: unknown): boolean {
  const normalizedDisplayName = normalizeDisplayNameForStorage(displayName);
  return isReservedUncertaintyLabel(normalizedDisplayName);
}

export function buildSpeakerColorMap(
  segments: readonly Pick<TranscriptItem, "speaker">[]
): Map<string, string> {
  const colorMap = new Map<string, string>();

  for (const segment of segments) {
    const normalizedSpeakerId = normalizeDisplayNameForStorage(segment.speaker) || UNKNOWN_SPEAKER_ID;
    if (colorMap.has(normalizedSpeakerId)) {
      continue;
    }

    const colorIndex = (colorMap.size % 8) + 1;
    colorMap.set(normalizedSpeakerId, `var(--sp-${colorIndex})`);
  }

  return colorMap;
}

export function resolveSpeakerColorToken(
  speakerId: string,
  colorMap: ReadonlyMap<string, string>
): string {
  const normalizedSpeakerId = normalizeDisplayNameForStorage(speakerId) || UNKNOWN_SPEAKER_ID;
  return colorMap.get(normalizedSpeakerId) ?? "var(--sp-1)";
}

export function buildSpeakerLegendKey(speakerId: string, visibleLabel: string): string {
  const normalizedSpeakerId = normalizeDisplayNameForStorage(speakerId) || UNKNOWN_SPEAKER_ID;
  const normalizedVisibleLabel = normalizeDisplayNameForStorage(visibleLabel) || UNKNOWN_SPEAKER_ID;

  if (normalizedSpeakerId === UNKNOWN_SPEAKER_ID) {
    return `unknown:${normalizedVisibleLabel}`;
  }

  return `speaker:${normalizedSpeakerId}`;
}
