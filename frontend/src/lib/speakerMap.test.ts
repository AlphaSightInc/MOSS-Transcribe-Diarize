import { describe, expect, it } from "vitest";
import {
  buildConsecutiveSpeakerMap,
  buildSpeakerColorMap,
  buildSpeakerLegendKey,
  isUnidentifiedSpeakerLabel,
  resolveDisplayLabel,
  resolveSpeakerColorToken,
  resolveVisibleSpeakerLabel
} from "./speakerMap";

describe("speakerMap", () => {
  it("renumbers default speaker ids consecutively without touching named speakers", () => {
    const map = buildConsecutiveSpeakerMap([
      { display_name: "SPEAKER_02" },
      { display_name: "Alex" },
      { display_name: " SPEAKER_05 " },
      { display_name: "SPEAKER_02" }
    ]);

    expect([...map.entries()]).toEqual([
      ["SPEAKER_02", "SPEAKER_01"],
      ["SPEAKER_05", "SPEAKER_02"]
    ]);
    expect(resolveVisibleSpeakerLabel(" SPEAKER_05 ", map)).toBe("SPEAKER_02");
    expect(resolveVisibleSpeakerLabel("Alex", map)).toBe("Alex");
  });

  it("assigns stable palette colors by first speaker appearance", () => {
    const colorMap = buildSpeakerColorMap([
      { speaker: "speaker-b" },
      { speaker: "speaker-a" },
      { speaker: "speaker-b" },
      { speaker: "UNKNOWN" }
    ]);

    expect(resolveSpeakerColorToken("speaker-b", colorMap)).toBe("var(--sp-1)");
    expect(resolveSpeakerColorToken("speaker-a", colorMap)).toBe("var(--sp-2)");
    expect(resolveSpeakerColorToken("UNKNOWN", colorMap)).toBe("var(--sp-3)");
  });

  it("treats default labels as unidentified and namespaces unknown legend keys by label", () => {
    expect(isUnidentifiedSpeakerLabel("SPEAKER_04")).toBe(true);
    expect(isUnidentifiedSpeakerLabel("UNKNOWN")).toBe(true);
    expect(isUnidentifiedSpeakerLabel("S00")).toBe(true);
    expect(isUnidentifiedSpeakerLabel("Alex Rivera")).toBe(false);

    expect(buildSpeakerLegendKey("UNKNOWN", "SPEAKER_01")).toBe("unknown:SPEAKER_01");
    expect(buildSpeakerLegendKey("speaker-42", "Alex Rivera")).toBe("speaker:speaker-42");
  });

  it("displays backend UNKNOWN as Preview", () => {
    expect(resolveDisplayLabel("UNKNOWN")).toBe("Preview");
    expect(resolveVisibleSpeakerLabel("UNKNOWN", new Map())).toBe("Preview");
  });

  it("displays backend S00 as Speaker uncertain", () => {
    expect(resolveDisplayLabel("S00")).toBe("Speaker uncertain");
    expect(resolveVisibleSpeakerLabel("S00", new Map())).toBe("Speaker uncertain");
  });
});
