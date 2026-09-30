import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { groupSegmentsIntoTurns } from "./mergeTranscript";
import {
  defaultSpeakerLabel,
  projectTranscriptCards,
  projectTranscriptRows,
  settledSpeakerNumbers,
  transcriptCardSpeakerLabel
} from "./transcriptCards";

function turn(start: number, end: number, lane: "system" | "microphone",
              id: string, text: string, settled = false): TranscriptTurn {
  return { source_lane: lane, start, end, speaker: id, speaker_entity_id: id,
    display_name: id, state: "confirmed", settled, text,
    segment_ids: [`segment-${start}`], target_segment_keys: [`target-${start}`],
    segments: [{ start, end, text }], provisional_stale: false };
}

describe("Q5 transcript cards", () => {
  it("merges one short interleaved lane row and preserves every source target", () => {
    const source = [turn(0, 1, "system", "speaker-a", "first"),
      turn(1, 2, "microphone", "speaker-b", "interjection"),
      turn(2, 3, "system", "speaker-a", "second")];
    const cards = projectTranscriptCards(source);
    expect(cards).toHaveLength(2);
    expect(cards[0]?.rows.map(row => row.text)).toEqual(["first", "second"]);
    expect(cards.flatMap(card => card.rows).map(row => row.target_segment_keys[0]).sort())
      .toEqual(source.map(row => row.target_segment_keys[0]).sort());
  });

  it("renders distant consecutive confirmed Ben rows as one card after the Ben guess settles", () => {
    const confirmed = [turn(0, 1, "system", "speaker-ben", "first", true),
      turn(12, 13, "system", "speaker-ben", "second", true)];
    expect(projectTranscriptCards(confirmed)).toHaveLength(1);
    expect(projectTranscriptCards(confirmed)[0]?.rows.map(row => row.text))
      .toEqual(["first", "second"]);
    const pending = { ...confirmed[1]!, state: "provisional" as const, speaker: "S00",
      speaker_entity_id: "S00", display_name: "Ben" };
    expect(projectTranscriptCards([confirmed[0]!, pending])).toHaveLength(2);
  });

  it("keeps an S00 header and does not absorb a long interjection", () => {
    const source = [turn(0, 1, "system", "S00", "one"),
      turn(1, 6, "microphone", "speaker-b", "long"),
      turn(6, 7, "system", "S00", "two")];
    const cards = projectTranscriptCards(source);
    expect(cards).toHaveLength(3);
    expect(cards[0]?.speakerId).toBe("S00");
    expect(transcriptCardSpeakerLabel(source[0]!, new Map())).toBe("Speaker TBD");
  });

  it("keeps a source key through text and label revision", () => {
    const original = turn(10, 11, "system", "speaker-a", "words");
    const revised = { ...original, display_name: "Alex", text: "revised words" };
    expect(projectTranscriptCards([original])[0]?.key).toBe(projectTranscriptCards([revised])[0]?.key);
    expect(transcriptCardSpeakerLabel(revised, new Map())).toBe("Alex");
    expect(transcriptCardSpeakerLabel({ ...revised, display_name: "SPEAKER_07" }, new Map()))
      .toBe("SPEAKER_07");
  });

  it("numbers settled identities first, then first committed speech, and closes gaps", () => {
    const live = [turn(0, 1, "system", "birth-1", "early"),
      turn(2, 3, "system", "settled-a", "first", true),
      turn(3, 4, "system", "settled-b", "second", true)];
    const numbers = settledSpeakerNumbers(live, false);
    expect([...numbers]).toEqual([["settled-a", 1], ["settled-b", 2], ["birth-1", 3]]);
    expect(live.map(row => transcriptCardSpeakerLabel(row, numbers)))
      .toEqual(["Speaker 3", "Speaker 1", "Speaker 2"]);
    // A reconciled identity leaves no gap.
    expect([...settledSpeakerNumbers([live[1]!, { ...live[2]!, speaker_entity_id: "settled-a" }], false)])
      .toEqual([["settled-a", 1]]);
  });

  it("maps microphone voices to You / User n and shared voices to Speaker n (I-4)", () => {
    const rows = [
      { ...turn(0, 1, "system", "speaker-0003", "remote"), speaker: "S02", display_name: "S02" },
      { ...turn(1, 2, "microphone", "local-0001", "me"), speaker: "S01", display_name: "S01" },
      { ...turn(2, 3, "microphone", "local-0002", "guest"), speaker: "S03", display_name: "Local 02" },
      { ...turn(3, 4, "system", "speaker-0001", "second remote"), speaker: "S04", display_name: "S04" },
      { ...turn(4, 5, "microphone", "speaker-microphone", "hybrid"), display_name: "speaker-microphone" }
    ];
    const numbers = settledSpeakerNumbers(rows, false);
    expect(rows.map(row => transcriptCardSpeakerLabel(row, numbers)))
      .toEqual(["Speaker 1", "You", "User 1", "Speaker 2", "You"]);
    for (const label of rows.map(row => transcriptCardSpeakerLabel(row, numbers))) {
      expect(label).not.toMatch(/^S\d+|^Local |\?$/);
    }
  });

  it("lets user and voiceprint names win and gives guessed-only voices the next number", () => {
    const named = { ...turn(0, 1, "microphone", "local-0001", "me"), display_name: "Yu" };
    const shared = { ...turn(1, 2, "system", "speaker-0002", "remote"), display_name: "S01" };
    const numbers = settledSpeakerNumbers([named, shared], false, ["speaker-0009", "local-0003"]);
    expect(transcriptCardSpeakerLabel(named, numbers)).toBe("Yu");
    expect(defaultSpeakerLabel("speaker-0009", numbers)).toBe("Speaker 2");
    expect(defaultSpeakerLabel("local-0003", numbers)).toBe("User 2");
    expect(defaultSpeakerLabel("S00", numbers)).toBe("Speaker TBD");
    expect(defaultSpeakerLabel("never-seen", numbers)).toBe("Speaker TBD");
  });

  it("keeps displayed generic numbers dense when a settled person has a chosen name", () => {
    const named = { ...turn(0, 1, "system", "named", "first", true), display_name: "Alex" };
    const generic = turn(1, 2, "microphone", "generic", "second", true);
    const numbers = settledSpeakerNumbers([named, generic], false);
    expect([...numbers]).toEqual([["generic", 1]]);
    expect(transcriptCardSpeakerLabel(named, numbers)).toBe("Alex");
    expect(transcriptCardSpeakerLabel(generic, numbers)).toBe("Speaker 1");
  });

  it("keeps a live settlement boundary visible inside one card", () => {
    const source = [
      { source_lane: "system" as const, start: 0, end: 1, speaker: "S01",
        speaker_entity_id: "speaker-a", display_name: "S01", text: "settled",
        state: "confirmed" as const, segment_id: "one", settled: true },
      { source_lane: "system" as const, start: 1, end: 2, speaker: "S01",
        speaker_entity_id: "speaker-a", display_name: "S01", text: "live",
        state: "confirmed" as const, segment_id: "two", settled: false }
    ];
    const turns = groupSegmentsIntoTurns(source);
    expect(turns.map(row => row.settled)).toEqual([true, false]);
    expect(projectTranscriptCards(turns)[0]?.rows).toHaveLength(2);
  });

  it("continues a block for the same speaker and lane, including a guess, but never for S00", () => {
    const guess = { ...turn(3, 4, "system", "speaker-a", "maybe more"), state: "provisional" as const,
      display_name: "Speaker 1", segment_ids: [] };
    const rows = projectTranscriptRows([
      turn(0, 1, "system", "speaker-a", "first"),
      turn(10, 11, "system", "S00", "unknown one"),
      turn(20, 21, "system", "S00", "unknown two"),
      { ...turn(30, 31, "system", "speaker-a", "later"), state: "provisional" as const }
    ], [guess]);
    expect(rows.map(row => [row.speakerId, row.guess, row.continuation])).toEqual([
      ["speaker-a", false, false],
      ["S00", false, false],
      ["S00", false, false],
      ["speaker-a", false, false],
      ["speaker-a", true, true]
    ]);
    expect(rows.at(-1)?.key).toBe("tentative:system:3");
  });
});
