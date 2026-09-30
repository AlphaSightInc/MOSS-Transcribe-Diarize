import type { TranscriptTurn } from "./mergeTranscript";
import { UNATTRIBUTED_SPEAKER_LABEL, UNRESOLVED_SPEAKER_ID } from "./speakerMap";
import type { SourceLane } from "./transcriptOrder";

/** Display-only projection of canonical voice guesses over provisional words. */
export interface TentativeSpan {
  start_sample: number;
  end_sample: number;
  source_lane: string;
  speaker: string;
}

export interface TentativeWord {
  start: number;
  end: number;
  text: string;
  source_lane?: string;
}

export interface TentativeBlock {
  speakerId: string | null;
  label: string;
  tentative: boolean;
  lane: string;
  start: number;
  end: number;
  text: string;
}

const SAMPLE_RATE = 16_000;

/** A guess reads as the speaker's label plus "?"; no guess, or no label, is simply unattributed. */
function guessLabel(speakerId: string | null, speakerLabels: Readonly<Record<string, string>>): string {
  const label = speakerId ? speakerLabels[speakerId] : undefined;
  return label && label !== UNATTRIBUTED_SPEAKER_LABEL ? `${label}?` : UNATTRIBUTED_SPEAKER_LABEL;
}

export function projectTentativeBlocks(
  words: readonly TentativeWord[], spans: readonly TentativeSpan[],
  speakerLabels: Readonly<Record<string, string>>
): TentativeBlock[] {
  const blocks: TentativeBlock[] = [];
  for (const word of words) {
    const lane = word.source_lane || "mixed";
    const startSample = Math.round(word.start * SAMPLE_RATE);
    const endSample = Math.round(word.end * SAMPLE_RATE);
    const best = spans.filter(span => span.source_lane === lane)
      .map(span => ({ span, overlap: Math.max(0, Math.min(endSample, span.end_sample) -
        Math.max(startSample, span.start_sample)) }))
      .sort((left, right) => right.overlap - left.overlap)[0];
    const speakerId = best && best.overlap > 0 ? best.span.speaker : null;
    const label = guessLabel(speakerId, speakerLabels);
    const prior = blocks.at(-1);
    if (prior && prior.lane === lane && prior.speakerId === speakerId) {
      prior.end = Math.max(prior.end, word.end);
      prior.text = `${prior.text} ${word.text.trim()}`.trim();
    } else {
      blocks.push({ speakerId, label, tentative: speakerId !== null, lane,
        start: word.start, end: word.end, text: word.text.trim() });
    }
  }
  return blocks;
}

export interface ProvisionalDisplaySegment {
  start_sample: number;
  end_sample: number;
  text: string;
  source_lane: string;
  tentative_speaker: string | null;
}

/** Use the lane-bearing Gemini preview surface when two voices speak at once. */
export function projectTentativeSegments(
  segments: readonly ProvisionalDisplaySegment[],
  speakerLabels: Readonly<Record<string, string>>
): TentativeBlock[] {
  const blocks: TentativeBlock[] = [];
  for (const segment of segments) {
    const speakerId = segment.tentative_speaker;
    const lane = segment.source_lane;
    const prior = blocks.at(-1);
    const text = segment.text.trim();
    if (prior && prior.lane === lane && prior.speakerId === speakerId) {
      prior.end = Math.max(prior.end, segment.end_sample / SAMPLE_RATE);
      prior.text = `${prior.text} ${text}`.trim();
    } else {
      blocks.push({ speakerId, label: guessLabel(speakerId, speakerLabels),
        tentative: speakerId !== null, lane,
        start: segment.start_sample / SAMPLE_RATE, end: segment.end_sample / SAMPLE_RATE, text });
    }
  }
  return blocks;
}

/** Guess blocks in the transcript's row shape, so they render and search like any other row. */
export function tentativeTurns(blocks: readonly TentativeBlock[]): TranscriptTurn[] {
  return blocks.map(block => {
    const id = block.speakerId ?? UNRESOLVED_SPEAKER_ID;
    const segment = { start: block.start, end: block.end, text: block.text };
    return { source_lane: block.lane as SourceLane, start: block.start, end: block.end, speaker: id,
      speaker_entity_id: id, display_name: block.label, state: "provisional", text: block.text,
      segment_ids: [], target_segment_keys: [`tentative:${block.lane}:${block.start}`],
      segments: [segment], provisional_stale: false };
  });
}
