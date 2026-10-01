// Account workspace browser preferences and read-only Meeting reattachment.
import { describe, expect, it } from "vitest";
import {
  clearSessionReattach,
  createMemoryStorage,
  loadBoolean,
  loadCaptureSources,
  loadSessionReattach,
  saveBoolean,
  saveCaptureSources,
  saveSessionReattach,
  storageKeys
} from "./persistence";

describe("persistence helpers", () => {
  it("round-trips the first-ship lt: boolean keys", () => {
    const storage = createMemoryStorage();

    saveBoolean(storage, storageKeys.controlPanelCollapsed, true);
    saveBoolean(storage, storageKeys.historyPanelCollapsed, false);

    expect(loadBoolean(storage, storageKeys.controlPanelCollapsed)).toBe(true);
    expect(loadBoolean(storage, storageKeys.historyPanelCollapsed)).toBe(false);
  });

  it("ticks both capture sources until the person chooses, then remembers the choice", () => {
    const storage = createMemoryStorage();
    expect(loadCaptureSources(storage)).toEqual({ system: true, microphone: true });
    saveCaptureSources({ system: false, microphone: true }, storage);
    expect(storage.getItem(storageKeys.captureSources)).toBe('{"system":false,"microphone":true}');
    expect(loadCaptureSources(storage)).toEqual({ system: false, microphone: true });
    // A damaged record falls back to both.
    storage.setItem(storageKeys.captureSources, "not json");
    expect(loadCaptureSources(storage)).toEqual({ system: true, microphone: true });
  });

  it("keeps both capture sources ticked and the boxes usable when storage throws", () => {
    const blocked = () => { throw new DOMException("blocked", "SecurityError"); };
    const storage = { getItem: blocked, setItem: blocked, removeItem: blocked };
    expect(loadCaptureSources(storage)).toEqual({ system: true, microphone: true });
    expect(() => saveCaptureSources({ system: true, microphone: false }, storage)).not.toThrow();
  });

  it("reports an absent boolean key as null rather than false", () => {
    const storage = createMemoryStorage();

    expect(loadBoolean(storage, storageKeys.controlPanelCollapsed)).toBeNull();
  });

  it("round-trips and clears the Account Meeting reattach record", () => {
    const storage = createMemoryStorage();

    expect(loadSessionReattach(storage)).toBeNull();
    saveSessionReattach(storage, { sessionId: "session-42" });
    expect(loadSessionReattach(storage)).toEqual({ sessionId: "session-42" });

    clearSessionReattach(storage);
    expect(loadSessionReattach(storage)).toBeNull();
  });

  it("clears malformed reattach records", () => {
    const storage = createMemoryStorage({
      [storageKeys.sessionReattach]: JSON.stringify({ sessionId: "" })
    });

    expect(loadSessionReattach(storage)).toBeNull();
    expect(storage.getItem(storageKeys.sessionReattach)).toBeNull();
  });
});
