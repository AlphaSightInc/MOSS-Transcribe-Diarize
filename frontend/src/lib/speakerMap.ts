import type { TranscriptItem } from "../api/types";
import { normalizeInlineWhitespace } from "./text.ts";

const SPEAKER_ID_PATTERN = /^SPEAKER_(\d+)$/;
export const UNKNOWN_SPEAKER_ID = "UNKNOWN";
export const UNRESOLVED_SPEAKER_ID = "S00";
const UNKNOWN_DISPLAY_LABEL = "Preview";
/** The one neutral label for speech nobody is attributed to; the backend saves the same. */
export const UNATTRIBUTED_SPEAKER_LABEL = "Speaker TBD";
const UNCERTAIN_DISPLAY_LABEL = UNATTRIBUTED_SPEAKER_LABEL;
const LOCAL_SPEAKER_ID = /^local-(\d+)$/;
const SHARED_SPEAKER_ID = /^(?:speaker-|S)(\d+)$/;
/** The palette is --sp-1 … --sp-8 (styles/index.css). */
const SPEAKER_COLOR_COUNT = 8;
const UNATTRIBUTED_COLOR_TOKEN = "var(--muted-2)";
const RESERVED_UNCERTAINTY_LABELS = new Set([
  "",
  "s00",
  "unknown",
  "speaker uncertain",
  "speaker tbd",
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

/**
 * Microphone-lane voices are named by their lane-local number: the first is the person at
 * this browser ("You"), later ones are "User 1", "User 2", ... (I-4). Null for other ids.
 */
export function microphoneSpeakerLabel(speakerId: string): string | null {
  if (speakerId === "speaker-microphone") return "You";
  const match = LOCAL_SPEAKER_ID.exec(speakerId);
  if (!match) return null;
  const index = Number(match[1]);
  return index <= 1 ? "You" : `User ${index - 1}`;
}

/** The number in a shared-audio voice's id ("speaker-0004", a File decoder's "S04"); null for other ids. */
export function sharedSpeakerNumber(speakerId: string): number | null {
  const number = Number(SHARED_SPEAKER_ID.exec(speakerId)?.[1] ?? 0);
  return number > 0 ? number : null;
}

/**
 * A speaker's colour is read off its id, like its default name, so it is the same during the
 * meeting, after clean-up, after a rename and when the meeting is reopened. Shared voices take
 * palette slots from the front by their number, microphone voices from the back, and any other
 * id (a person added by a correction) a slot fixed by its text.
 * Unattributed speech takes no palette slot: a colour would claim an identity it does not have.
 */
export function speakerColorToken(speakerId: string): string {
  const id = normalizeDisplayNameForStorage(speakerId) || UNKNOWN_SPEAKER_ID;
  if (isBackendUnknownSpeakerId(id)) return UNATTRIBUTED_COLOR_TOKEN;
  const shared = sharedSpeakerNumber(id);
  const local = Number(LOCAL_SPEAKER_ID.exec(id)?.[1] ?? 0);
  const slot = shared !== null ? (shared - 1) % SPEAKER_COLOR_COUNT
    : local > 0 ? SPEAKER_COLOR_COUNT - 1 - ((local - 1) % SPEAKER_COLOR_COUNT)
    : [...id].reduce((sum, char) => sum + char.charCodeAt(0), 0) % SPEAKER_COLOR_COUNT;
  return `var(--sp-${slot + 1})`;
}

export function buildSpeakerLegendKey(speakerId: string, visibleLabel: string): string {
  const normalizedSpeakerId = normalizeDisplayNameForStorage(speakerId) || UNKNOWN_SPEAKER_ID;
  const normalizedVisibleLabel = normalizeDisplayNameForStorage(visibleLabel) || UNKNOWN_SPEAKER_ID;

  if (normalizedSpeakerId === UNKNOWN_SPEAKER_ID) {
    return `unknown:${normalizedVisibleLabel}`;
  }

  return `speaker:${normalizedSpeakerId}`;
}
