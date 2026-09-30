import { describe, expect, it } from "vitest";
import type { TranscriptTurn } from "./mergeTranscript";
import { buildTranscriptExportText, serializeTranscriptExport } from "./transcriptExport";

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

  it("serializes Markdown and text with resolved labels", () => {
    const turns = [makeTurn(36, "SPEAKER_02", "Second turn")];
    const resolveLabel = () => "Jamie";
    const identity = {
      sessionId: "session-42",
      exportedAt: new Date("2026-08-18T20:00:16.182Z")
    };

    expect(serializeTranscriptExport("md", turns, resolveLabel, identity)).toEqual({
      content: "## [00:00:36] Jamie\n\nSecond turn",
      filename: "transcript-session-42-2026-08-18T20:00:16.182Z.md",
      mediaType: "text/markdown;charset=utf-8"
    });
    expect(serializeTranscriptExport("txt", turns, resolveLabel, identity)).toEqual({
      content: "[00:00:36] Jamie:\nSecond turn",
      filename: "transcript-session-42-2026-08-18T20:00:16.182Z.txt",
      mediaType: "text/plain;charset=utf-8"
    });
  });

  it("includes a saved summary in Markdown export", () => {
    const file = serializeTranscriptExport("md", [makeTurn(0, "Jamie", "Hello")], () => "Jamie",
      { sessionId: "m", exportedAt: new Date(0) },
      { summary: "Decision made.", topics: [{ title: "Schedule", description: "Next week." }],
        details: [], speaker_background: [], data_references: [] });
    expect(file.content).toContain("# Summary\n\nDecision made.");
    expect(file.content).toContain("## Schedule\n\nNext week.");
    expect(file.content).toContain("# Transcript\n\n## [00:00:00] Jamie");
  });

  it.each(["confirmed", "provisional"] as const)(
    "exports %s turns as plain transcript without an attribution notice (Q6)",
    (state) => {
      const turns = [makeTurn(36, "SPEAKER_02", "Second turn", { state })];
      const resolveLabel = () => "Jamie";
      const identity = {
        sessionId: "session-42",
        exportedAt: new Date("2026-08-18T20:00:16.182Z")
      };

      expect(serializeTranscriptExport("md", turns, resolveLabel, identity).content).toBe("## [00:00:36] Jamie\n\nSecond turn");
      expect(serializeTranscriptExport("txt", turns, resolveLabel, identity).content).toBe("[00:00:36] Jamie:\nSecond turn");
    }
  );
});

function makeTurn(
  start: number,
  displayName: string,
  text: string,
  overrides: Partial<TranscriptTurn> = {}
): TranscriptTurn {
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
    segments: [{ start, end: start + 1, text }],
    provisional_stale: false,
    ...overrides
  };
}


it("serializes labelled overlapping md/txt turns exactly in lane order", () => {
  const system: TranscriptTurn = {...makeTurn(0, "Alex", "System"), end:3, source_lane:"system", state:"final"};
  const microphone: TranscriptTurn = {...makeTurn(0, "Alex", "Mic"), end:1, source_lane:"microphone", state:"final"};
  const turns = [microphone,system];
  const identity = {sessionId:"lanes",exportedAt:new Date(0)};
  expect(serializeTranscriptExport("md", turns, t=>t.display_name,identity).content).toBe("## [00:00:00] Alex\n\nSystem\n\n## [00:00:00] Alex\n\nMic");
  expect(serializeTranscriptExport("txt", turns, t=>t.display_name,identity).content).toBe("[00:00:00] Alex:\nSystem\n\n[00:00:00] Alex:\nMic");
});


it.each(["md", "txt"] as const)(
  "never writes a needs-review notice into %s output",
  format => {
    const file = serializeTranscriptExport(
      format,
      [makeTurn(0, "Speaker 1", "Uncertain words", {
        speaker: "S00", speaker_entity_id: "S00"
      })],
      item => item.display_name,
      { sessionId: "review", exportedAt: new Date(0) }
    );
    expect(file.content).not.toContain("Needs review");
    expect(file.content).toContain("Uncertain words");
    expect(file.content).not.toContain("S00");
  }
);
