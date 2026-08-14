import { describe, expect, it } from "vitest";
import { isApplePlatform, matchesPrimaryShortcut } from "./keyboardShortcuts";

describe("keyboardShortcuts", () => {
  it("detects Apple platforms from navigator-style strings", () => {
    expect(isApplePlatform("MacIntel")).toBe(true);
    expect(isApplePlatform("iPhone")).toBe(true);
    expect(isApplePlatform("Win32")).toBe(false);
  });

  it("normalizes the primary shortcut modifier by platform", () => {
    expect(
      matchesPrimaryShortcut(
        { altKey: false, ctrlKey: false, key: "f", metaKey: true, shiftKey: false },
        "f",
        "MacIntel"
      )
    ).toBe(true);
    expect(
      matchesPrimaryShortcut(
        { altKey: false, ctrlKey: true, key: "f", metaKey: false, shiftKey: false },
        "f",
        "Win32"
      )
    ).toBe(true);
  });

  it("rejects the wrong modifier or extra modifier keys", () => {
    expect(
      matchesPrimaryShortcut(
        { altKey: false, ctrlKey: true, key: "f", metaKey: false, shiftKey: false },
        "f",
        "MacIntel"
      )
    ).toBe(false);
    expect(
      matchesPrimaryShortcut(
        { altKey: true, ctrlKey: false, key: "[", metaKey: true, shiftKey: false },
        "[",
        "MacIntel"
      )
    ).toBe(false);
  });
});
