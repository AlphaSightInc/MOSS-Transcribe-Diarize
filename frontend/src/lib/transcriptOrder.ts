/** Stable publication order; time never establishes speaker identity. */
export type SourceLane = "system" | "microphone";
export interface TimedTranscriptSegment { start: number; end: number; source_lane?: SourceLane; }
export function compareTranscriptOrder(a: TimedTranscriptSegment, b: TimedTranscriptSegment): number {
  return a.start - b.start || laneOrder(a.source_lane) - laneOrder(b.source_lane) || a.end - b.end;
}
function laneOrder(lane?: SourceLane): number { return lane === "system" ? 0 : lane === "microphone" ? 1 : 2; }
export function transcriptLaneLabel(lane: SourceLane): string { return lane === "system" ? "System" : "Microphone"; }
