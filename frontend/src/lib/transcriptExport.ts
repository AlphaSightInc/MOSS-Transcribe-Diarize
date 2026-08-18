import type { TranscriptTurn } from "./mergeTranscript";

export const TRANSCRIPT_EXPORT_FORMATS = ["md", "txt", "json"] as const;
export type TranscriptExportFormat = (typeof TRANSCRIPT_EXPORT_FORMATS)[number];

const PROVISIONAL_ATTRIBUTION_CAVEAT =
  "Speaker attribution is provisional and may be revised by the retrospective sweep after the session ends.";
const TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT =
  `Provisional attribution: ${PROVISIONAL_ATTRIBUTION_CAVEAT}`;
const MARKDOWN_PROVISIONAL_ATTRIBUTION_CAVEAT =
  `> **Provisional attribution:** ${PROVISIONAL_ATTRIBUTION_CAVEAT}`;

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
  identity: TranscriptExportIdentity
): TranscriptExportFile {
  const rows = buildExportRows(turns, resolveLabel);
  const provisionalAttribution = hasProvisionalAttribution(turns);
  const filename = `transcript-${identity.sessionId}-${identity.exportedAt.toISOString()}.${format}`;
  if (format === "md") {
    return {
      content: prependProvisionalAttributionCaveat(
        rows.map((row) => `## [${row.clockTime}] ${row.label}\n\n${row.text}`).join("\n\n"),
        MARKDOWN_PROVISIONAL_ATTRIBUTION_CAVEAT,
        provisionalAttribution
      ),
      filename,
      mediaType: "text/markdown;charset=utf-8"
    };
  }
  if (format === "txt") {
    return {
      content: prependProvisionalAttributionCaveat(
        buildTranscriptExportText(turns, resolveLabel),
        TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT,
        provisionalAttribution
      ),
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
    ...(hasProvisionalAttribution(turns)
      ? { provisional_attribution_notice: TEXT_PROVISIONAL_ATTRIBUTION_CAVEAT }
      : {}),
    turns: turns.map((turn) => ({
      start: turn.start,
      end: turn.end,
      speaker: turn.speaker,
      speaker_entity_id: turn.speaker_entity_id,
      display_name: turn.display_name,
      speaker_label: resolveExportLabel(turn, resolveLabel),
      state: turn.state,
      text: turn.text,
      segment_ids: [...turn.segment_ids],
      target_segment_keys: [...turn.target_segment_keys],
      provisional_stale: turn.provisional_stale
    }))
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
  return turns.map((turn) => ({
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
