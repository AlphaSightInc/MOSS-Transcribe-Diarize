import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { buildTranscriptSearchResults, countQueryOccurrences } from "./transcriptSearch";

function makeTurn(overrides: Partial<TranscriptTurn> = {}): TranscriptTurn {
  return {
    start: 0,
    end: 1,
    speaker: "SPEAKER_01",
    speaker_entity_id: "speaker-1",
    display_name: "Speaker A",
    state: "final",
    text: "alpha beta alpha",
    segment_ids: ["seg-1"],
    target_segment_keys: ["seg-1"],
    provisional_stale: false,
    ...overrides
  };
}

describe("transcriptSearch", () => {
  it("counts repeated query occurrences in a single text block", () => {
    expect(countQueryOccurrences("alpha beta alpha ALPHA", "alpha")).toBe(3);
  });

  it("keeps all turns visible and counts total occurrences across speaker labels and turn text", () => {
    const turns = [
      makeTurn({
        display_name: "Jamie Dimon",
        text: "Jamie opened the session and Jamie closed it."
      }),
      makeTurn({
        display_name: "Lex Fridman",
        text: "This turn does not include the keyword.",
        segment_ids: ["seg-2"],
        target_segment_keys: ["seg-2"]
      })
    ];

    const result = buildTranscriptSearchResults(turns, "jamie", (turn) => turn.display_name);

    expect(result.matchCount).toBe(3);
    expect(result.turns).toHaveLength(2);
    expect(result.turns[0]?.turn.display_name).toBe("Jamie Dimon");
    expect(result.turns[1]?.turn.display_name).toBe("Lex Fridman");
    expect(result.turns[0]?.speakerParts.filter((part) => part.matchId !== null)).toHaveLength(1);
    expect(result.turns[0]?.textParts.filter((part) => part.matchId !== null)).toHaveLength(2);
  });

  it("returns unhighlighted parts when the query is empty", () => {
    const turns = [makeTurn()];

    const result = buildTranscriptSearchResults(turns, "", (turn) => turn.display_name);

    expect(result.matchCount).toBe(0);
    expect(result.turns).toHaveLength(1);
    expect(result.turns[0]?.speakerParts).toEqual([{ matchId: null, text: "Speaker A" }]);
    expect(result.turns[0]?.textParts).toEqual([{ matchId: null, text: "alpha beta alpha" }]);
  });
});
