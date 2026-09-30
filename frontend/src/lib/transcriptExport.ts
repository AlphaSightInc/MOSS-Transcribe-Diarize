import { compareTranscriptOrder } from "./transcriptOrder.ts";
import type { SourceLane } from "./transcriptOrder.ts";
import type { SummaryDocument } from "./finalSummary";
import type { TranscriptTurn } from "./mergeTranscript";
import { isBackendUnknownSpeakerId, UNRESOLVED_SPEAKER_ID } from "./speakerMap.ts";

export const TRANSCRIPT_EXPORT_FORMATS = ["md", "txt", "json", "srt", "vtt"] as const;
export type TranscriptExportFormat = (typeof TRANSCRIPT_EXPORT_FORMATS)[number];

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

/** Files carry the transcript only: no provisional, review or pending-summary notices (Q6). */
export interface TranscriptExportJsonDocument {
  version: 1;
  turns: TranscriptExportJsonTurn[];
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
  summary?: SummaryDocument | null
): TranscriptExportFile {
  turns = [...turns].sort(compareTranscriptOrder);
  const rows = buildExportRows(turns, resolveLabel);
  const filename = `transcript-${identity.sessionId}-${identity.exportedAt.toISOString()}.${format}`;
  if (format === "srt" || format === "vtt") {
    const cues = turns.filter(turn => turn.text.trim()).map((turn, index) => {
      const start = Math.max(0, Math.round(turn.start * 1000));
      const end = Math.max(start + 1, Math.round(turn.end * 1000));
      const text = subtitleText(turn.text.trim());
      const label = subtitleText(resolveExportLabel(turn, resolveLabel)).replace(/\n/g, " ");
      return `${index + 1}\n${subtitleTime(start, format)} --> ${subtitleTime(end, format)}\n${label}: ${text}`;
    }).join("\n\n");
    const header = format === "vtt" ? "WEBVTT\n\n" : "";
    return { content: `${header}${cues}${cues ? "\n" : ""}`, filename,
      mediaType: format === "vtt" ? "text/vtt;charset=utf-8" : "application/x-subrip;charset=utf-8" };
  }
  if (format === "md") {
    return {
      content: `${summary ? `${formatSummaryMarkdown(summary)}\n\n# Transcript\n\n` : ""}${rows.map((row) => `## [${row.clockTime}] ${row.label}\n\n${row.text}`).join("\n\n")}`,
      filename,
      mediaType: "text/markdown;charset=utf-8"
    };
  }
  if (format === "txt") {
    return {
      content: buildTranscriptExportText(turns, resolveLabel),
      filename,
      mediaType: "text/plain;charset=utf-8"
    };
  }
  return {
    content: `${JSON.stringify(buildTranscriptExportJsonDocument(turns, resolveLabel), null, 2)}\n`,
    filename,
    mediaType: "application/json;charset=utf-8"
  };
}

export function buildTranscriptExportJsonDocument(
  turns: readonly TranscriptTurn[],
  resolveLabel: (turn: TranscriptTurn) => string
): TranscriptExportJsonDocument {
  return {
    version: 1,
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


function subtitleTime(milliseconds: number, format: "srt" | "vtt"): string {
  const seconds = Math.floor(milliseconds / 1000);
  return `${formatTranscriptClockTime(seconds)}${format === "srt" ? "," : "."}${String(milliseconds % 1000).padStart(3, "0")}`;
}

function subtitleText(text: string): string {
  // Blank lines delimit cues; escape markup so transcript words remain literal.
  return text.replace(/\r\n?/g, "\n").replace(/\n[ \t]*\n+/g, "\n")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatSummaryMarkdown(document: SummaryDocument): string {
  const sections = [`# Summary\n\n${document.summary}`];
  for (const topic of document.topics) sections.push(`## ${topic.title}\n\n${topic.description}`);
  if (document.details.length) sections.push(`## Supporting details\n\n${document.details.map(detail =>
    `- ${detail.timestamp} · **${detail.title}** — ${detail.description}`).join("\n")}`);
  if (document.speaker_background.length) sections.push(`## Speaker background\n\n${document.speaker_background.map(line => `- ${line}`).join("\n")}`);
  if (document.data_references.length) sections.push(`## Data references\n\n${document.data_references.map(item =>
    `- **${item.item}: ${item.value}** — ${item.context}`).join("\n")}`);
  return sections.join("\n\n");
}
