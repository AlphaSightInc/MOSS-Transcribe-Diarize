import { formatTranscriptClockTime } from "./transcriptExport.ts";

/** Separate timeline metadata: never inserted into speech, speaker maps or summary input. */
export interface RecordingInterruption { start: number; end: number | null }

export function recordingInterruptionLine(gap: RecordingInterruption): string | null {
  if (gap.end === null) return null;
  return `([${formatTranscriptClockTime(gap.start)}-${formatTranscriptClockTime(gap.end)}] Recording Interrupted)`;
}

export function parseRecordingInterruptions(value: unknown, sampleRate = 16000): RecordingInterruption[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error("Recording interruptions are invalid.");
  return value.map(gap => {
    if (!Number.isInteger(gap?.start_sample) || gap.start_sample < 0 ||
        (gap.end_sample !== null && (!Number.isInteger(gap.end_sample) || gap.end_sample < gap.start_sample)))
      throw new Error("Recording interruption is invalid.");
    return { start: gap.start_sample / sampleRate, end: gap.end_sample === null ? null : gap.end_sample / sampleRate };
  });
}
