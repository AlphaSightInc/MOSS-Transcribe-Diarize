import { compareTranscriptOrder } from "./transcriptOrder";
import type { TranscriptTurn } from "./mergeTranscript";

export interface TranscriptSearchPart {
  matchId: number | null;
  text: string;
}

export interface TranscriptSearchTurn {
  speakerLabel: string;
  speakerParts: TranscriptSearchPart[];
  textParts: TranscriptSearchPart[];
  turn: TranscriptTurn;
}

export interface TranscriptSearchResults {
  matchCount: number;
  turns: TranscriptSearchTurn[];
}

export function buildTranscriptSearchResults(
  turns: readonly TranscriptTurn[],
  query: string,
  resolveSpeakerLabel: (turn: TranscriptTurn) => string
): TranscriptSearchResults {
  turns = [...turns].sort(compareTranscriptOrder);
  const normalizedQuery = query.trim();
  if (normalizedQuery.length === 0) {
    return {
      matchCount: 0,
      turns: turns.map((turn) => {
        const speakerLabel = resolveSpeakerLabel(turn);
        return {
          speakerLabel,
          speakerParts: [{ matchId: null, text: speakerLabel }],
          textParts: [{ matchId: null, text: turn.text }],
          turn
        };
      })
    };
  }

  let nextMatchId = 0;

  return {
    matchCount: countTranscriptMatches(turns, normalizedQuery, resolveSpeakerLabel),
    turns: turns.map((turn) => {
      const speakerLabel = resolveSpeakerLabel(turn);
      const speakerMatches = splitTranscriptMatches(speakerLabel, normalizedQuery, nextMatchId);
      nextMatchId = speakerMatches.nextMatchId;
      const textMatches = splitTranscriptMatches(turn.text, normalizedQuery, nextMatchId);
      nextMatchId = textMatches.nextMatchId;
      return {
        speakerLabel,
        speakerParts: speakerMatches.parts,
        textParts: textMatches.parts,
        turn
      };
    })
  };
}

export function countTranscriptMatches(
  turns: readonly TranscriptTurn[],
  query: string,
  resolveSpeakerLabel: (turn: TranscriptTurn) => string
): number {
  const normalizedQuery = query.trim();
  if (normalizedQuery.length === 0) {
    return 0;
  }

  return turns.reduce(
    (total, turn) =>
      total +
      countQueryOccurrences(resolveSpeakerLabel(turn), normalizedQuery) +
      countQueryOccurrences(turn.text, normalizedQuery),
    0
  );
}

export function countQueryOccurrences(text: string, query: string): number {
  const normalizedQuery = query.trim();
  if (normalizedQuery.length === 0) {
    return 0;
  }

  const pattern = new RegExp(escapeRegExp(normalizedQuery), "gi");
  let count = 0;

  while (pattern.exec(text) !== null) {
    count += 1;
  }

  return count;
}

function splitTranscriptMatches(
  text: string,
  query: string,
  nextMatchId: number
): {
  nextMatchId: number;
  parts: TranscriptSearchPart[];
} {
  const pattern = new RegExp(escapeRegExp(query), "gi");
  const parts: TranscriptSearchPart[] = [];
  let currentIndex = 0;
  let currentMatchId = nextMatchId;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    const matchStart = match.index;
    const matchEnd = match.index + match[0].length;

    if (matchStart > currentIndex) {
      parts.push({
        matchId: null,
        text: text.slice(currentIndex, matchStart)
      });
    }

    parts.push({
      matchId: currentMatchId,
      text: text.slice(matchStart, matchEnd)
    });

    currentIndex = matchEnd;
    currentMatchId += 1;
  }

  if (currentIndex < text.length) {
    parts.push({
      matchId: null,
      text: text.slice(currentIndex)
    });
  }

  if (parts.length === 0) {
    parts.push({
      matchId: null,
      text
    });
  }

  return {
    nextMatchId: currentMatchId,
    parts
  };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
