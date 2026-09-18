import { describe, expect, it } from "vitest";
import type { TranscriptItem } from "../api/types";
import { groupSegmentsIntoTurns, upsertTranscriptItems } from "./mergeTranscript";
import { buildConsecutiveSpeakerMap, resolveVisibleSpeakerLabel } from "./speakerMap";
import { buildTranscriptSearchResults } from "./transcriptSearch";
import { replaceTranscript, sessionTranscriptItems } from "../state/session";

function item(overrides: Partial<TranscriptItem> = {}): TranscriptItem {
  return {
    start: 0,
    end: 1,
    text: "first recorded words",
    speaker: "SPEAKER_01",
    speaker_entity_id: "speaker-1",
    display_name: "SPEAKER_01",
    state: "confirmed",
    segment_id: "span-1:0",
    ...overrides
  };
}

describe("reference transcript model", () => {
  it("orders a committed segment before the provisional tail until the next snapshot", () => {
    const provisional = upsertTranscriptItems([], [
      item({
        state: "provisional",
        text: "provisional words",
        segment_id: "prov:7:0"
      })
    ]);

    const merged = upsertTranscriptItems(provisional, [
      item({ state: "confirmed", text: "committed words", segment_id: "span-1:0" })
    ]);

    expect(merged).toMatchObject([
      { id: "span-1:0", state: "confirmed", text: "committed words" },
      { id: "prov:7:0", state: "provisional", text: "provisional words" }
    ]);
  });

  it("replaces the transcript list when the authoritative snapshot advances", () => {
    replaceTranscript([
      item({ state: "provisional", text: "provisional words", segment_id: "prov:7:0" })
    ]);
    replaceTranscript([
      item({ state: "confirmed", text: "committed words", segment_id: "span-1:0" })
    ]);

    expect(sessionTranscriptItems.value).toMatchObject([
      { id: "span-1:0", state: "confirmed", text: "committed words" }
    ]);
  });

  it("joins an overlapping same-speaker turn without repeating its overlap", () => {
    const turns = groupSegmentsIntoTurns([
      item({ end: 2, text: "we should review the evidence today", segment_id: "span-1:0" }),
      item({
        start: 2,
        end: 4,
        text: "review the evidence today before release",
        segment_id: "span-2:0"
      })
    ]);

    expect(turns).toHaveLength(1);
    expect(turns[0]?.text).toBe("we should review the evidence today before release");
  });

  it("keeps generic speaker labels consecutive and finds matches in labels and text", () => {
    const turns = groupSegmentsIntoTurns([
      item({ display_name: "SPEAKER_03", speaker: "SPEAKER_03", text: "speaker three speaks" }),
      item({
        start: 2,
        end: 3,
        display_name: "SPEAKER_08",
        speaker: "SPEAKER_08",
        text: "the second speaker responds",
        segment_id: "span-2:0"
      })
    ]);
    const labels = buildConsecutiveSpeakerMap(turns);
    const results = buildTranscriptSearchResults(
      turns,
      "speaker",
      (turn) => resolveVisibleSpeakerLabel(turn.display_name, labels)
    );

    expect([...labels.values()]).toEqual(["SPEAKER_01", "SPEAKER_02"]);
    expect(results.matchCount).toBe(4);
    expect(results.turns).toHaveLength(2);
  });
});
