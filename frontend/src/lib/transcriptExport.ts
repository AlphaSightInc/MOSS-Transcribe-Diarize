import { compareTranscriptOrder } from "./transcriptOrder.ts";
import type { SourceLane } from "./transcriptOrder.ts";
import type { TranscriptTurn } from "./mergeTranscript";
import { isBackendUnknownSpeakerId, UNRESOLVED_SPEAKER_ID } from "./speakerMap.ts";

export const TRANSCRIPT_EXPORT_FORMATS = ["md", "txt", "json", "srt", "vtt"] as const;
export type TranscriptExportFormat = (typeof TRANSCRIPT_EXPORT_FORMATS)[number];

const PROVISIONAL_ATTRIBUTION_CAVEAT =
  "Speaker attribution is provisional and may be revised by the retrospective sweep after the session ends.";
const TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT =
  `Provisional attribution: ${PROVISIONAL_ATTRIBUTION_CAVEAT}`;
const MARKDOWN_PROVISIONAL_ATTRIBUTION_CAVEAT =
  `> **Provisional attribution:** ${PROVISIONAL_ATTRIBUTION_CAVEAT}`;
const NEEDS_REVIEW_NOTICE = "Needs review: one or more speaker assignments remain uncertain or processing ended partially.";
const MARKDOWN_NEEDS_REVIEW_NOTICE =
  "> **Needs review:** One or more speaker assignments remain uncertain or processing ended partially.";

export interface TranscriptExportFile {
  content: string;
  filename: string;
  mediaType: string;
}

export interface TranscriptExportIdentity {
  sessionId: string;
  exportedAt: Date;
}

export interface TranscriptExportJsonTurn {
  source_lane?: SourceLane;
  start: number;
  end: number;
  speaker: string;
  speaker_entity_id: string;
  display_name: string;
  speaker_label: string;
  state: TranscriptTurn["state"];
  text: string;
  segment_ids: string[];
  target_segment_keys: string[];
  provisional_stale: boolean;
}

export interface TranscriptExportJsonDocument {
  version: 1;
  provisional_attribution_notice?: string;
  review_status?: "Needs review";
  turns: TranscriptExportJsonTurn[];
}

export interface TranscriptExportReview {
  needsReview: boolean;
}

export function formatTranscriptClockTime(seconds: number): string {
  const clampedSeconds = Math.max(0, Math.floor(seconds));
  const hours = String(Math.floor(clampedSeconds / 3600)).padStart(2, "0");
  const minutes = String(Math.floor((clampedSeconds % 3600) / 60)).padStart(2, "0");
  const remainingSeconds = String(clampedSeconds % 60).padStart(2, "0");
  return `${hours}:${minutes}:${remainingSeconds}`;
}

export function buildTranscriptExportText(
  turns: readonly TranscriptTurn[],
  resolveLabel: (turn: TranscriptTurn) => string
): string {
  return buildExportRows(turns, resolveLabel)
    .map((row) => `[${row.clockTime}] ${row.label}:\n${row.text}`)
    .join("\n\n");
}

export function serializeTranscriptExport(
  format: TranscriptExportFormat,
  turns: readonly TranscriptTurn[],
  resolveLabel: (turn: TranscriptTurn) => string,
  identity: TranscriptExportIdentity,
  review: TranscriptExportReview = { needsReview: false }
): TranscriptExportFile {
  turns = [...turns].sort(compareTranscriptOrder);
  const rows = buildExportRows(turns, resolveLabel);
  const provisionalAttribution = hasProvisionalAttribution(turns);
  const filename = `transcript-${identity.sessionId}-${identity.exportedAt.toISOString()}.${format}`;
  if (format === "srt" || format === "vtt") {
    const cues = turns.filter(turn => turn.text.trim()).map((turn, index) => {
      const start = Math.max(0, Math.round(turn.start * 1000));
      const end = Math.max(start + 1, Math.round(turn.end * 1000));
      const text = subtitleText(turn.text.trim());
      const label = subtitleText(resolveExportLabel(turn, resolveLabel)).replace(/\n/g, " ");
      const provisional = format === "srt" && turn.state !== "final" ? "[Provisional attribution] " : "";
      const needsReview = format === "srt" && review.needsReview && index === 0 ? "[Needs review] " : "";
      return `${index + 1}\n${subtitleTime(start, format)} --> ${subtitleTime(end, format)}\n${needsReview}${provisional}${label}: ${text}`;
    }).join("\n\n");
    const header = format === "vtt"
      ? `WEBVTT\n\n${review.needsReview ? `NOTE ${NEEDS_REVIEW_NOTICE}\n\n` : ""}${provisionalAttribution ? `NOTE ${TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT}\n\n` : ""}` : "";
    return { content: `${header}${cues}${cues ? "\n" : ""}`, filename,
      mediaType: format === "vtt" ? "text/vtt;charset=utf-8" : "application/x-subrip;charset=utf-8" };
  }
  if (format === "md") {
    return {
      content: prependNotice(prependProvisionalAttributionCaveat(
        rows.map((row) => `## [${row.clockTime}] ${row.label}\n\n${row.text}`).join("\n\n"),
        MARKDOWN_PROVISIONAL_ATTRIBUTION_CAVEAT,
        provisionalAttribution
      ), MARKDOWN_NEEDS_REVIEW_NOTICE, review.needsReview),
      filename,
      mediaType: "text/markdown;charset=utf-8"
    };
  }
  if (format === "txt") {
    return {
      content: prependNotice(prependProvisionalAttributionCaveat(
        buildTranscriptExportText(turns, resolveLabel),
        TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT,
        provisionalAttribution
      ), NEEDS_REVIEW_NOTICE, review.needsReview),
      filename,
      mediaType: "text/plain;charset=utf-8"
    };
  }
  return {
    content: `${JSON.stringify(buildTranscriptExportJsonDocument(turns, resolveLabel, review), null, 2)}\n`,
    filename,
    mediaType: "application/json;charset=utf-8"
  };
}

export function buildTranscriptExportJsonDocument(
  turns: readonly TranscriptTurn[],
  resolveLabel: (turn: TranscriptTurn) => string,
  review: TranscriptExportReview = { needsReview: false }
): TranscriptExportJsonDocument {
  return {
    version: 1,
    ...(review.needsReview ? { review_status: "Needs review" as const } : {}),
    ...(hasProvisionalAttribution(turns)
      ? { provisional_attribution_notice: TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT }
      : {}),
    turns: [...turns].sort(compareTranscriptOrder).map((turn) => {
      const speakerLabel = resolveExportLabel(turn, resolveLabel);
      const unidentified = isBackendUnknownSpeakerId(turn.speaker_entity_id);
      return {
        ...(turn.source_lane ? { source_lane: turn.source_lane } : {}),
        start: turn.start,
        end: turn.end,
        speaker: unidentified ? UNRESOLVED_SPEAKER_ID : turn.speaker,
        speaker_entity_id: unidentified ? UNRESOLVED_SPEAKER_ID : turn.speaker_entity_id,
        display_name: unidentified ? speakerLabel : turn.display_name,
        speaker_label: speakerLabel,
        state: turn.state,
        text: turn.text,
        segment_ids: [...turn.segment_ids],
        target_segment_keys: [...turn.target_segment_keys],
        provisional_stale: turn.provisional_stale
      };
    })
  };
}

function prependNotice(content: string, notice: string, present: boolean): string {
  if (!present) return content;
  return content ? `${notice}\n\n${content}` : notice;
}

export function triggerTranscriptExportDownload(file: TranscriptExportFile): void {
  if (typeof document === "undefined" || typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
    throw new Error("Downloads are unavailable in this environment.");
  }
  const href = URL.createObjectURL(new Blob([file.content], { type: file.mediaType }));
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = file.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  globalThis.setTimeout(() => URL.revokeObjectURL(href), 0);
}

function buildExportRows(
  turns: readonly TranscriptTurn[],
  resolveLabel: (turn: TranscriptTurn) => string
) {
  return [...turns].sort(compareTranscriptOrder).map((turn) => ({
    clockTime: formatTranscriptClockTime(turn.start),
    label: resolveExportLabel(turn, resolveLabel),
    text: turn.text.trim()
  })).filter((row) => row.text.length > 0);
}

function resolveExportLabel(turn: TranscriptTurn, resolveLabel: (turn: TranscriptTurn) => string): string {
  return resolveLabel(turn).trim() || turn.display_name.trim() || turn.speaker;
}

function hasProvisionalAttribution(turns: readonly TranscriptTurn[]): boolean {
  return turns.some((turn) => turn.state !== "final");
}

function prependProvisionalAttributionCaveat(
  content: string,
  caveat: string,
  provisionalAttribution: boolean
): string {
  if (!provisionalAttribution) {
    return content;
  }
  return content ? `${caveat}\n\n${content}` : caveat;
}


function subtitleTime(milliseconds: number, format: "srt" | "vtt"): string {
  const seconds = Math.floor(milliseconds / 1000);
  return `${formatTranscriptClockTime(seconds)}${format === "srt" ? "," : "."}${String(milliseconds % 1000).padStart(3, "0")}`;
}

function subtitleText(text: string): string {
  // Blank lines delimit cues; escape markup so transcript words remain literal.
  return text.replace(/\r\n?/g, "\n").replace(/\n[ \t]*\n+/g, "\n")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
