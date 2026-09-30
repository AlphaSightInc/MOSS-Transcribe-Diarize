import { describe, expect, it } from "vitest";
import reservedSpeakerLabels from "../../../tests/fixtures/reserved_speaker_labels.json";
import {
  buildConsecutiveSpeakerMap,
  buildSpeakerColorMap,
  buildSpeakerLegendKey,
  isUnidentifiedSpeakerLabel,
  isReservedUncertaintyLabel,
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
    // Unattributed speech is neutral and leaves the palette to real speakers.
    expect(resolveSpeakerColorToken("UNKNOWN", colorMap)).toBe("var(--muted-2)");
    expect(resolveSpeakerColorToken("S00", colorMap)).toBe("var(--muted-2)");
    expect(resolveSpeakerColorToken("speaker-c", buildSpeakerColorMap([
      { speaker: "S00" }, { speaker: "x", speaker_entity_id: "speaker-c" }
    ]))).toBe("var(--sp-1)");
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

  it("displays backend S00 as Speaker TBD", () => {
    expect(resolveDisplayLabel("S00")).toBe("Speaker TBD");
    expect(resolveVisibleSpeakerLabel("S00", new Map())).toBe("Speaker TBD");
  });

  it.each(reservedSpeakerLabels.reserved_labels)(
    "keeps backend and frontend reserved-label contract for %s",
    label => {
      expect(isReservedUncertaintyLabel(label)).toBe(true);
      expect(isUnidentifiedSpeakerLabel(label)).toBe(true);
    }
  );

  it.each(reservedSpeakerLabels.allowed_labels)(
    "does not reserve real person label %s",
    label => {
      expect(isReservedUncertaintyLabel(label)).toBe(false);
    }
  );
});
