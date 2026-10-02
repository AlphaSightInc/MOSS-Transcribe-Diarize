import { recordingInterruptionLine, type RecordingInterruption } from "./recordingInterruption.ts";
import { compareTranscriptOrder } from "./transcriptOrder.ts";
import type { SummaryDocument } from "./finalSummary";
import type { TranscriptTurn } from "./mergeTranscript";

/** Product exports are Markdown and plain text only (#11); audio downloads separately as MP3. */
export type TranscriptExportFormat = "md" | "txt";

export interface TranscriptExportFile {
  content: string;
  filename: string;
  mediaType: string;
}

export interface TranscriptExportIdentity {
  sessionId: string;
  exportedAt: Date;
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
  resolveLabel: (turn: TranscriptTurn) => string,
  interruptions: readonly RecordingInterruption[] = []
): string {
  return exportTimeline(turns, resolveLabel, interruptions, "txt");
}

/** Files carry the transcript only: no provisional, review or pending-summary notices (Q6). */
export function serializeTranscriptExport(
  format: TranscriptExportFormat,
  turns: readonly TranscriptTurn[],
  resolveLabel: (turn: TranscriptTurn) => string,
  identity: TranscriptExportIdentity,
  summary?: SummaryDocument | null,
  interruptions: readonly RecordingInterruption[] = []
): TranscriptExportFile {
  turns = [...turns].sort(compareTranscriptOrder);
  const filename = `transcript-${identity.sessionId}-${identity.exportedAt.toISOString()}.${format}`;
  if (format === "md") {
    return {
      content: `${summary ? `${formatSummaryMarkdown(summary)}\n\n# Transcript\n\n` : ""}${exportTimeline(turns, resolveLabel, interruptions, "md")}`,
      filename,
      mediaType: "text/markdown;charset=utf-8"
    };
  }
  return {
    content: buildTranscriptExportText(turns, resolveLabel, interruptions),
    filename,
    mediaType: "text/plain;charset=utf-8"
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
    start: turn.start,
    clockTime: formatTranscriptClockTime(turn.start),
    label: resolveExportLabel(turn, resolveLabel),
    text: turn.text.trim()
  })).filter((row) => row.text.length > 0);
}

function exportTimeline(turns: readonly TranscriptTurn[], resolveLabel: (turn: TranscriptTurn) => string,
  interruptions: readonly RecordingInterruption[], format: TranscriptExportFormat): string {
  const rows = buildExportRows(turns, resolveLabel).map(row => ({ start: row.start, priority: 1,
    text: format === "md" ? `## [${row.clockTime}] ${row.label}\n\n${row.text}` : `[${row.clockTime}] ${row.label}:\n${row.text}` }));
  rows.push(...interruptions.flatMap(gap => {
    const text = recordingInterruptionLine(gap);
    return text === null ? [] : [{ start: gap.start, priority: 0, text }];
  }));
  return rows.sort((a, b) => a.start - b.start || a.priority - b.priority).map(row => row.text).join("\n\n");
}

function resolveExportLabel(turn: TranscriptTurn, resolveLabel: (turn: TranscriptTurn) => string): string {
  return resolveLabel(turn).trim() || turn.display_name.trim() || turn.speaker;
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
