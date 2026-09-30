import { describe, expect, it } from "vitest";
import { createMemoryStorage, type StorageLike } from "./persistence";
import { displaySurfaceOf, recallCaptureSurface, rememberCaptureSurface, transcriptSourceLabel } from "./captureSurface";

function displayStream(displaySurface: unknown): MediaStream {
  return { getVideoTracks: () => [{ getSettings: () => ({ displaySurface }) }] } as unknown as MediaStream;
}

describe("J5 capture source labels", () => {
  it("reads Chrome's share choice from the display video track", () => {
    expect(displaySurfaceOf(displayStream("browser"))).toBe("browser");
    expect(displaySurfaceOf(displayStream("window"))).toBe("window");
    expect(displaySurfaceOf(displayStream("monitor"))).toBe("monitor");
    expect(displaySurfaceOf(displayStream("application"))).toBeNull();
    expect(displaySurfaceOf({ getVideoTracks: () => [] } as unknown as MediaStream)).toBeNull();
  });

  it("labels shared rows by surface, microphone rows Mic, and File/URL rows not at all", () => {
    expect(transcriptSourceLabel("system", "browser", "live")).toBe("Browser");
    expect(transcriptSourceLabel("system", "window", "live")).toBe("Window");
    expect(transcriptSourceLabel("system", "monitor", "live")).toBe("Screen");
    expect(transcriptSourceLabel("system", null, "live")).toBe("Shared");
    expect(transcriptSourceLabel("microphone", "browser", "live")).toBe("Mic");
    expect(transcriptSourceLabel(undefined, "browser", "live")).toBeNull();
    expect(transcriptSourceLabel("system", "browser", "file")).toBeNull();
  });

  it("keeps the choice per meeting and survives refused storage", () => {
    const storage = createMemoryStorage();
    rememberCaptureSurface("m1", "window", storage);
    rememberCaptureSurface("m2", null, storage);
    expect(storage.getItem("moss.captureSurface.m1")).toBe("window");
    expect(recallCaptureSurface("m1", storage)).toBe("window");
    expect(recallCaptureSurface("m2", storage)).toBeNull();
    storage.setItem("moss.captureSurface.m3", "tab");
    expect(recallCaptureSurface("m3", storage)).toBeNull();
    const refusing: StorageLike = {
      getItem: () => { throw new DOMException("denied", "SecurityError"); },
      setItem: () => { throw new DOMException("full", "QuotaExceededError"); },
      removeItem: () => undefined
    };
    expect(() => rememberCaptureSurface("m1", "browser", refusing)).not.toThrow();
    expect(recallCaptureSurface("m1", refusing)).toBeNull();
  });
});
