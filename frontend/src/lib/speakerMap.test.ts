import { describe, expect, it } from "vitest";
import reservedSpeakerLabels from "../../../tests/fixtures/reserved_speaker_labels.json";
import {
  buildConsecutiveSpeakerMap,
  buildSpeakerLegendKey,
  isUnidentifiedSpeakerLabel,
  isReservedUncertaintyLabel,
  resolveDisplayLabel,
  resolveVisibleSpeakerLabel,
  speakerColorToken
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

  it("reads a speaker's colour off its id, not off the order of the transcript (F4)", () => {
    // Shared voices take slots from the front by their number, in any speaking order.
    expect(speakerColorToken("speaker-0001")).toBe("var(--sp-1)");
    expect(speakerColorToken("speaker-0004")).toBe("var(--sp-4)");
    expect(speakerColorToken("speaker-0009")).toBe("var(--sp-1)");
    expect(speakerColorToken("S02")).toBe("var(--sp-2)");
    // Microphone voices take slots from the back, so "You" keeps one colour.
    expect(speakerColorToken("local-0001")).toBe("var(--sp-8)");
    expect(speakerColorToken("local-0002")).toBe("var(--sp-7)");
    // Any other id (a person added by a correction) keeps the slot its text gives it.
    expect(speakerColorToken("manual-AbC")).toBe(speakerColorToken(" manual-AbC "));
    expect(speakerColorToken("manual-AbC")).toMatch(/^var\(--sp-[1-8]\)$/);
    // Unattributed speech is neutral and leaves the palette to real speakers.
    expect(speakerColorToken("UNKNOWN")).toBe("var(--muted-2)");
    expect(speakerColorToken("S00")).toBe("var(--muted-2)");
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
