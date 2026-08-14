import type { TranscriptTurn } from "./mergeTranscript";

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
  return turns
    .map((turn) => {
      const label = resolveLabel(turn).trim() || turn.display_name.trim() || turn.speaker;
      return `[${formatTranscriptClockTime(turn.start)}] ${label}:\n${turn.text.trim()}`;
    })
    .filter((block) => !block.endsWith(":\n"))
    .join("\n\n");
}
