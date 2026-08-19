import { describe, expect, it } from "vitest";
import { laneMeterPercent } from "./ControlPanel";

// The figures below are real measurements from the operator's MacBook Pro, captured with the
// standalone diagnostic while both lanes ran together. They are the reason this scale exists: on the
// previous linear scale the microphone drew a 7% sliver next to a pegged shared lane, which read as
// "microphone dead" and sent several attended runs chasing OS permissions that were never at fault.
describe("lane meter scale", () => {
  it("renders real speech and real tab audio as clearly distinct, neither pegged", () => {
    const speech = laneMeterPercent(1.4e-2); // -37 dBFS, operator's measured voice
    const tab = laneMeterPercent(2.9e-1); // -11 dBFS, operator's measured tab audio
    expect(speech).toBeGreaterThan(25);
    expect(speech).toBeLessThan(60);
    expect(tab).toBeGreaterThan(70);
    expect(tab).toBeLessThan(100);
    expect(tab - speech).toBeGreaterThan(20);
  });

  it("would have FAILED on the old linear scale, which is the regression this guards", () => {
    const linear = (v: number) => Math.min(100, Math.max(0, Math.round(v * 500)));
    expect(linear(1.4e-2)).toBeLessThan(10); // speech: a sliver
    expect(linear(2.9e-1)).toBe(100); // tab: pegged
    expect(laneMeterPercent(1.4e-2)).toBeGreaterThan(linear(1.4e-2));
  });

  it("reads empty only for true silence and never exceeds the track", () => {
    expect(laneMeterPercent(0)).toBe(0);
    expect(laneMeterPercent(-1)).toBe(0);
    expect(laneMeterPercent(1e-4)).toBe(0); // the silence floor MOSS uses
    expect(laneMeterPercent(1)).toBe(100);
    expect(laneMeterPercent(50)).toBe(100);
  });
});
