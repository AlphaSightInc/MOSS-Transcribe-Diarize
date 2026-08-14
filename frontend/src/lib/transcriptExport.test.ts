import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { buildTranscriptExportText } from "./transcriptExport";

describe("transcriptExport", () => {
  it("places speaker labels on their own line with blank lines between turns", () => {
    const turns: TranscriptTurn[] = [
      makeTurn(0, "SPEAKER_01", "First turn"),
      makeTurn(36, "SPEAKER_02", "Second turn")
    ];

    expect(buildTranscriptExportText(turns, (turn) => turn.display_name)).toBe(
      [
        "[00:00:00] SPEAKER_01:",
        "First turn",
        "",
        "[00:00:36] SPEAKER_02:",
        "Second turn"
      ].join("\n")
    );
  });
});

function makeTurn(start: number, displayName: string, text: string): TranscriptTurn {
  return {
    start,
    end: start + 1,
    speaker: displayName,
    speaker_entity_id: displayName,
    display_name: displayName,
    state: "final",
    text,
    segment_ids: [],
    target_segment_keys: [],
    provisional_stale: false
  };
}
