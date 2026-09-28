import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { groupSegmentsIntoTurns } from "./mergeTranscript";
import { projectTranscriptCards, settledSpeakerNumbers, transcriptCardSpeakerLabel } from "./transcriptCards";

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

  it("keeps an S00 header and does not absorb a long interjection", () => {
    const source = [turn(0, 1, "system", "S00", "one"),
      turn(1, 6, "microphone", "speaker-b", "long"),
      turn(6, 7, "system", "S00", "two")];
    const cards = projectTranscriptCards(source);
    expect(cards).toHaveLength(3);
    expect(cards[0]?.speakerId).toBe("S00");
    expect(transcriptCardSpeakerLabel(source[0]!, new Map(), "La", false)).toBe("Speaker uncertain");
  });

  it("keeps a source key through text and label revision", () => {
    const original = turn(10, 11, "system", "speaker-a", "words");
    const revised = { ...original, display_name: "Alex", text: "revised words" };
    expect(projectTranscriptCards([original])[0]?.key).toBe(projectTranscriptCards([revised])[0]?.key);
    expect(transcriptCardSpeakerLabel(revised, new Map(), "La", false)).toBe("Alex");
    expect(transcriptCardSpeakerLabel({ ...revised, display_name: "SPEAKER_07" }, new Map(), "La", false))
      .toBe("SPEAKER_07");
  });

  it("numbers only settled identities and closes gaps after reconciliation", () => {
    const live = [turn(0, 1, "system", "birth-1", "early"),
      turn(1, 2, "microphone", "birth-2", "mic"),
      turn(2, 3, "system", "settled-a", "first", true),
      turn(3, 4, "system", "settled-b", "second", true)];
    const numbers = settledSpeakerNumbers(live, false);
    expect([...numbers]).toEqual([["settled-a", 1], ["settled-b", 2]]);
    expect(transcriptCardSpeakerLabel(live[0]!, numbers, "La", false)).toBe("Remote");
    expect(transcriptCardSpeakerLabel(live[1]!, numbers, "La", false)).toBe("You");
    expect(transcriptCardSpeakerLabel(live[2]!, numbers, "La", false)).toBe("Speaker 1");
    expect(transcriptCardSpeakerLabel(live[3]!, numbers, "La", false)).toBe("Speaker 2");
    expect([...settledSpeakerNumbers([live[0]!, live[2]!, { ...live[3]!, speaker_entity_id: "settled-a" }], false)])
      .toEqual([["settled-a", 1]]);
  });

  it("uses lane labels for unnumbered unsettled raw tags under L-a", () => {
    const remote = { ...turn(0, 1, "system", "S01", "remote"), display_name: "S04" };
    const local = { ...turn(1, 2, "microphone", "S02", "local"), display_name: "S07" };
    expect(transcriptCardSpeakerLabel(remote, new Map(), "La", false)).toBe("Remote");
    expect(transcriptCardSpeakerLabel(local, new Map(), "La", false)).toBe("You");
  });

  it("keeps displayed generic numbers dense when a settled person has a chosen name", () => {
    const named = { ...turn(0, 1, "system", "named", "first", true), display_name: "Alex" };
    const generic = turn(1, 2, "microphone", "generic", "second", true);
    const numbers = settledSpeakerNumbers([named, generic], false);
    expect([...numbers]).toEqual([["generic", 1]]);
    expect(transcriptCardSpeakerLabel(named, numbers, "La", false)).toBe("Alex");
    expect(transcriptCardSpeakerLabel(generic, numbers, "La", false)).toBe("Speaker 1");
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
});
