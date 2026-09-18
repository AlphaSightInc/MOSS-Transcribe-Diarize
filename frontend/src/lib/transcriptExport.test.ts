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

  it("serializes Markdown, text, and versioned JSON with resolved labels", () => {
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

    const json = serializeTranscriptExport("json", turns, resolveLabel, identity);
    expect(json.filename).toBe("transcript-session-42-2026-08-18T20:00:16.182Z.json");
    expect(json.mediaType).toBe("application/json;charset=utf-8");
    expect(JSON.parse(json.content)).toEqual({
      version: 1,
      turns: [expect.objectContaining({
        start: 36,
        end: 37,
        speaker: "SPEAKER_02",
        speaker_label: "Jamie",
        state: "final",
        text: "Second turn"
      })]
    });
  });

  it.each(["confirmed", "provisional"] as const)(
    "marks %s exports in every format until finalization",
    (state) => {
      const turns = [makeTurn(36, "SPEAKER_02", "Second turn", { state })];
      const caveat = "Speaker attribution is provisional and may be revised by the retrospective sweep after the session ends.";
      const resolveLabel = () => "Jamie";
      const identity = {
        sessionId: "session-42",
        exportedAt: new Date("2026-08-18T20:00:16.182Z")
      };

      expect(serializeTranscriptExport("md", turns, resolveLabel, identity).content).toContain(
        `> **Provisional attribution:** ${caveat}`
      );
      expect(serializeTranscriptExport("txt", turns, resolveLabel, identity).content).toContain(
        `Provisional attribution: ${caveat}`
      );
      expect(JSON.parse(serializeTranscriptExport("json", turns, resolveLabel, identity).content)).toMatchObject({
        provisional_attribution_notice: `Provisional attribution: ${caveat}`
      });
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
    provisional_stale: false,
    ...overrides
  };
}


it.each(["srt", "vtt"] as const)("exports valid %s cues with millisecond rollover and literal speaker/text", format => {
  const turns = [makeTurn(59.9996, "Old", " <b>Hello</b> & yes\r\n\r\nNext line ", { end: 3600.0124 }),
    makeTurn(4000, "Old", "  "), makeTurn(4001.1234, "Old", "Second", { end: 4001.1234 })];
  const file = serializeTranscriptExport(format, turns, () => "Alex & Sam", { sessionId: "m", exportedAt: new Date(0) });
  const separator = format === "srt" ? "," : ".";
  expect(file.filename.endsWith(`.${format}`)).toBe(true);
  expect(file.mediaType).toBe(format === "vtt" ? "text/vtt;charset=utf-8" : "application/x-subrip;charset=utf-8");
  expect(file.content).toBe((format === "vtt" ? "WEBVTT\n\n" : "") +
    `1\n00:01:00${separator}000 --> 01:00:00${separator}012\nAlex &amp; Sam: &lt;b&gt;Hello&lt;/b&gt; &amp; yes\nNext line\n\n` +
    `2\n01:06:41${separator}123 --> 01:06:41${separator}124\nAlex &amp; Sam: Second\n`);
});

it.each(["srt", "vtt"] as const)("keeps %s empty and provisional exports syntactically valid", format => {
  const identity = { sessionId: "m", exportedAt: new Date(0) };
  expect(serializeTranscriptExport(format, [], () => "Alex", identity).content).toBe(format === "vtt" ? "WEBVTT\n\n" : "");
  const content = serializeTranscriptExport(format, [makeTurn(0, "Alex", "Words", { state: "provisional" })], t => t.display_name, identity).content;
  expect(content).toContain("Provisional attribution");
  expect(content).toContain("Alex: Words");
  expect(content).toMatch(format === "vtt" ? /^WEBVTT\n\nNOTE / : /^1\n00:00:00,000 --> 00:00:01,000\n/);
});


it("serializes labelled overlapping md/txt/json turns exactly in lane order", () => {
  const system: TranscriptTurn = {...makeTurn(0, "Alex", "System"), end:3, source_lane:"system", state:"final"};
  const microphone: TranscriptTurn = {...makeTurn(0, "Alex", "Mic"), end:1, source_lane:"microphone", state:"final"};
  const turns = [microphone,system];
  const identity = {sessionId:"lanes",exportedAt:new Date(0)};
  expect(serializeTranscriptExport("md", turns, t=>t.display_name,identity).content).toBe("## [00:00:00] Alex [System]\n\nSystem\n\n## [00:00:00] Alex [Microphone]\n\nMic");
  expect(serializeTranscriptExport("txt", turns, t=>t.display_name,identity).content).toBe("[00:00:00] Alex [System]:\nSystem\n\n[00:00:00] Alex [Microphone]:\nMic");
  expect(serializeTranscriptExport("json", turns, t=>t.display_name,identity).content).toBe(JSON.stringify({version:1,turns:[
    {source_lane:"system",start:0,end:3,speaker:system.speaker,speaker_entity_id:system.speaker_entity_id,display_name:"Alex",speaker_label:"Alex [System]",state:"final",text:"System",segment_ids:system.segment_ids,target_segment_keys:system.target_segment_keys,provisional_stale:false},
    {source_lane:"microphone",start:0,end:1,speaker:microphone.speaker,speaker_entity_id:microphone.speaker_entity_id,display_name:"Alex",speaker_label:"Alex [Microphone]",state:"final",text:"Mic",segment_ids:microphone.segment_ids,target_segment_keys:microphone.target_segment_keys,provisional_stale:false}
  ]},null,2)+"\n");
});
