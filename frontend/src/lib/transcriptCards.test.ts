import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { groupSegmentsIntoTurns } from "./mergeTranscript";
import {
  defaultSpeakerLabel,
  projectTranscriptCards,
  projectTranscriptRows,
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
  it("starts a visible speaker block after an interruption, even for the same speaker", () => {
    const rows = projectTranscriptRows([
      turn(0, 1, "system", "speaker-a", "before"),
      turn(4, 5, "system", "speaker-a", "after")
    ], [], [{ start: 1, end: 4 }]);
    expect(rows).toHaveLength(2);
    expect(rows.map(row => row.continuation)).toEqual([false, false]);
  });

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
    expect(transcriptCardSpeakerLabel(source[0]!)).toBe("Speaker TBD");
  });

  it("keeps a source key through text and label revision", () => {
    const original = turn(10, 11, "system", "speaker-a", "words");
    const revised = { ...original, display_name: "Alex", text: "revised words" };
    expect(projectTranscriptCards([original])[0]?.key).toBe(projectTranscriptCards([revised])[0]?.key);
    expect(transcriptCardSpeakerLabel(revised)).toBe("Alex");
    expect(transcriptCardSpeakerLabel({ ...revised, display_name: "SPEAKER_07" }))
      .toBe("SPEAKER_07");
  });

  it("keeps each speaker's number through clean-up: order changes, one leaves, one is new (F4)", () => {
    const row = (start: number, id: string) =>
      ({ ...turn(start, start + 1, "system", id, "words", true), speaker: "S01", display_name: "S01" });
    // r4-ui-e2e run a: live order 0001, 0002, 0003, 0004; after clean-up 0004 speaks first,
    // 0003 is gone and 0005 is new.
    const live = ["speaker-0001", "speaker-0002", "speaker-0003", "speaker-0004"].map((id, i) => row(i, id));
    const refined = ["speaker-0004", "speaker-0002", "speaker-0001", "speaker-0005"].map((id, i) => row(i, id));
    const labels = (rows: TranscriptTurn[]) =>
      Object.fromEntries(rows.map(item => [item.speaker_entity_id, transcriptCardSpeakerLabel(item)]));
    expect(labels(live)).toEqual({ "speaker-0001": "Speaker 1", "speaker-0002": "Speaker 2",
      "speaker-0003": "Speaker 3", "speaker-0004": "Speaker 4" });
    expect(labels(refined)).toEqual({ "speaker-0004": "Speaker 4", "speaker-0002": "Speaker 2",
      "speaker-0001": "Speaker 1", "speaker-0005": "Speaker 5" });
  });

  it("maps microphone voices to You / User n and shared voices to Speaker n (I-4)", () => {
    const rows = [
      { ...turn(0, 1, "system", "speaker-0003", "remote"), speaker: "S02", display_name: "S02" },
      { ...turn(1, 2, "microphone", "local-0001", "me"), speaker: "S01", display_name: "S01" },
      { ...turn(2, 3, "microphone", "local-0002", "guest"), speaker: "S03", display_name: "Local 02" },
      { ...turn(3, 4, "system", "speaker-0001", "second remote"), speaker: "S04", display_name: "S04" },
      { ...turn(4, 5, "microphone", "speaker-microphone", "hybrid"), display_name: "speaker-microphone" },
      { ...turn(5, 6, "system", "S02", "file voice"), display_name: "S02" }
    ];
    expect(rows.map(row => transcriptCardSpeakerLabel(row)))
      .toEqual(["Speaker 3", "You", "User 1", "Speaker 1", "You", "Speaker 2"]);
    for (const label of rows.map(row => transcriptCardSpeakerLabel(row))) {
      expect(label).not.toMatch(/^S\d+|^Local |\?$/);
    }
  });

  it("lets user and voiceprint names win and names a guessed-only voice by its id", () => {
    const named = { ...turn(0, 1, "microphone", "local-0001", "me"), display_name: "Yu" };
    expect(transcriptCardSpeakerLabel(named)).toBe("Yu");
    expect(defaultSpeakerLabel("speaker-0009")).toBe("Speaker 9");
    expect(defaultSpeakerLabel("local-0003")).toBe("User 2");
    expect(defaultSpeakerLabel("S00")).toBe("Speaker TBD");
    expect(defaultSpeakerLabel("never-seen")).toBe("Speaker TBD");
  });

  it("does not renumber the others when one speaker is named (F4)", () => {
    const first = { ...turn(0, 1, "system", "speaker-0001", "first", true), display_name: "S01" };
    const second = { ...turn(1, 2, "system", "speaker-0002", "second", true), display_name: "S02" };
    expect([first, second].map(row => transcriptCardSpeakerLabel(row))).toEqual(["Speaker 1", "Speaker 2"]);
    expect([{ ...first, display_name: "Alex" }, second].map(row => transcriptCardSpeakerLabel(row)))
      .toEqual(["Alex", "Speaker 2"]);
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
