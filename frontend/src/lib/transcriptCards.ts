import type { TranscriptTurn } from "./mergeTranscript";

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

function hasCustomName(turn: SpeakerRow): boolean {
  const display = turn.display_name.trim();
  return !!display && display !== turn.speaker && display !== "Remote" && display !== "You";
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
      if (!candidate || candidate.lane !== lane || candidate.speakerId !== id ||
          turn.start - candidate.end > SHORT_GAP_SECONDS) continue;
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

export function isSettledTurn(turn: SpeakerRow, finalized: boolean): boolean {
  return turn.settled === true || (finalized && turn.state === "final");
}

/** Recompute from current settled identities, so reconciliation cannot leave number gaps. */
export function settledSpeakerNumbers(turns: readonly TranscriptTurn[], finalized: boolean): Map<string, number> {
  const numbers = new Map<string, number>();
  for (const turn of turns) {
    const id = speakerId(turn);
    if (!isSettledTurn(turn, finalized) || id === "S00" || id === "UNKNOWN" ||
        hasCustomName(turn) || numbers.has(id)) continue;
    numbers.set(id, numbers.size + 1);
  }
  return numbers;
}

export function transcriptCardSpeakerLabel(
  turn: SpeakerRow, numbers: ReadonlyMap<string, number>,
  policy: "current" | "La", finalized: boolean
): string {
  const id = speakerId(turn);
  if (id === "S00" || id === "UNKNOWN") return "Speaker uncertain";
  const display = turn.display_name.trim();
  // A name chosen by the operator is literal, including a generic-looking name.
  if (hasCustomName(turn)) return display;
  if (!isSettledTurn(turn, finalized) && policy === "La") {
    if (turn.source_lane === "system") return "Remote";
    if (turn.source_lane === "microphone") return "You";
  }
  const number = numbers.get(id);
  return number === undefined ? display || turn.speaker : `Speaker ${number}`;
}
