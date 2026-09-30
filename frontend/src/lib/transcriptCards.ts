import type { TranscriptTurn } from "./mergeTranscript";
import { isBackendUnknownSpeakerId, microphoneSpeakerLabel, UNATTRIBUTED_SPEAKER_LABEL } from "./speakerMap";

export interface TranscriptCard {
  key: string;
  speakerId: string;
  lane: string;
  start: number;
  end: number;
  rows: TranscriptTurn[];
}

type SpeakerRow = Pick<TranscriptTurn,
  "speaker" | "speaker_entity_id" | "display_name" | "source_lane" | "settled" | "state">;

const SHORT_GAP_SECONDS = 3;

function speakerId(turn: SpeakerRow): string {
  return turn.speaker_entity_id || turn.speaker || "S00";
}

/** Raw tags the poller and older saved transcripts carry before anyone is named. */
const RAW_SPEAKER_TAG = /^(?:S\d+|Local \d+|(?:speaker|local|terminal)-\d+|speaker-microphone|Remote|Preview|UNKNOWN|Speaker TBD)$/;

function hasCustomName(turn: SpeakerRow): boolean {
  const display = turn.display_name.trim();
  return !!display && display !== turn.speaker && display !== speakerId(turn) && !RAW_SPEAKER_TAG.test(display);
}

function turnKey(turn: TranscriptTurn): string {
  return `${turn.source_lane || "mixed"}:${turn.start}:${turn.target_segment_keys[0] || turn.segment_ids[0] || ""}`;
}

/** A card keeps the first source key even when later revisions change its text. */
export function projectTranscriptCards(turns: readonly TranscriptTurn[]): TranscriptCard[] {
  const cards: TranscriptCard[] = [];
  for (const turn of turns) {
    const lane = turn.source_lane || "mixed";
    const id = speakerId(turn);
    let target: TranscriptCard | undefined;
    for (let offset = 1; offset <= Math.min(2, cards.length); offset += 1) {
      const candidate = cards[cards.length - offset];
      if (!candidate || candidate.lane !== lane || candidate.speakerId !== id) continue;
      const consecutiveConfirmed = offset === 1 && id !== "S00" && id !== "UNKNOWN" &&
        turn.state !== "provisional" && candidate.rows.at(-1)?.state !== "provisional";
      if (!consecutiveConfirmed && turn.start - candidate.end > SHORT_GAP_SECONDS) continue;
      if (offset === 2) {
        const intervening = cards.at(-1);
        if (!intervening || intervening.lane === lane ||
            intervening.end - intervening.start > SHORT_GAP_SECONDS) continue;
      }
      target = candidate;
      break;
    }
    if (target) {
      target.end = Math.max(target.end, turn.end);
      target.rows.push(turn);
    } else {
      cards.push({ key: turnKey(turn), speakerId: id, lane,
        start: turn.start, end: turn.end, rows: [turn] });
    }
  }
  return cards;
}

/** One rendered row: the reference's meta column (speaker, source, time) beside the text. */
export interface TranscriptRow {
  key: string;
  speakerId: string;
  lane?: string;
  start: number;
  end: number;
  /** Preview words under a voice guess; display-only, never named or corrected. */
  guess: boolean;
  /** Same speaker and lane as the row above: no separator and no repeated name. */
  continuation: boolean;
  fragments: TranscriptTurn[];
}

/** Cards, then guess rows; a guess for the speaker already on screen continues that block (G9). */
export function projectTranscriptRows(
  turns: readonly TranscriptTurn[], guessTurns: readonly TranscriptTurn[] = []
): TranscriptRow[] {
  const rows = [
    ...projectTranscriptCards(turns).map(card => ({ ...card, lane: card.rows[0]!.source_lane,
      guess: false, fragments: card.rows })),
    ...guessTurns.map(turn => ({ key: `tentative:${turn.source_lane}:${turn.start}`, speakerId: speakerId(turn),
      lane: turn.source_lane, start: turn.start, end: turn.end, guess: true, fragments: [turn] }))
  ];
  return rows.map(({ key, speakerId: id, lane, start, end, guess, fragments }, index) => {
    const previous = rows[index - 1];
    // Unattributed speech is never "the same person" as the row above it.
    const continuation = !!previous && !isBackendUnknownSpeakerId(id) &&
      previous.speakerId === id && previous.lane === lane;
    return { key, speakerId: id, lane, start, end, guess, continuation, fragments };
  });
}

export function isSettledTurn(turn: SpeakerRow, finalized: boolean): boolean {
  return turn.settled === true || (finalized && turn.state === "final");
}

/**
 * Shared-lane "Speaker n" numbers, dense and recomputed every render so a merged identity
 * leaves no gap: settled speech first, then committed, then preview rows, then speakers that
 * so far exist only as a guess. Microphone voices, unattributed speech and named people take
 * no number.
 */
export function settledSpeakerNumbers(
  turns: readonly TranscriptTurn[], finalized: boolean, guessedSpeakerIds: readonly string[] = []
): Map<string, number> {
  const numbers = new Map<string, number>();
  const assign = (id: string) => {
    if (!numbers.has(id) && !isBackendUnknownSpeakerId(id) && microphoneSpeakerLabel(id) === null) {
      numbers.set(id, numbers.size + 1);
    }
  };
  const named = new Set(turns.filter(hasCustomName).map(speakerId));
  const passes: Array<(turn: TranscriptTurn) => boolean> = [
    turn => isSettledTurn(turn, finalized),
    turn => turn.state !== "provisional",
    () => true
  ];
  for (const pass of passes) {
    for (const turn of turns) if (pass(turn) && !named.has(speakerId(turn))) assign(speakerId(turn));
  }
  for (const id of guessedSpeakerIds) if (!named.has(id)) assign(id);
  return numbers;
}

/** The label a speaker id shows when nobody has named it (I-4); never a raw tag. */
export function defaultSpeakerLabel(id: string, numbers: ReadonlyMap<string, number>): string {
  if (isBackendUnknownSpeakerId(id)) return UNATTRIBUTED_SPEAKER_LABEL;
  const microphone = microphoneSpeakerLabel(id);
  if (microphone !== null) return microphone;
  const number = numbers.get(id);
  return number === undefined ? UNATTRIBUTED_SPEAKER_LABEL : `Speaker ${number}`;
}

/** Names chosen by a person or a voiceprint win; everything else follows the I-4 rule. */
export function transcriptCardSpeakerLabel(turn: SpeakerRow, numbers: ReadonlyMap<string, number>): string {
  const id = speakerId(turn);
  if (isBackendUnknownSpeakerId(id)) return UNATTRIBUTED_SPEAKER_LABEL;
  // A name chosen by the operator is literal, including a generic-looking name.
  return hasCustomName(turn) ? turn.display_name.trim() : defaultSpeakerLabel(id, numbers);
}
