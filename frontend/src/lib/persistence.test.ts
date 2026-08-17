// Ported from the reference frontend. The two LLM-settings-cache cases are omitted with the
// cache itself (Phase 2, C10); everything here covers the storage primitives Phase 1 keeps,
// including the session-id round trip the sessionStorage reattach ruling depends on.
import { describe, expect, it } from "vitest";
import {
  clearSessionReattach,
  clearSessionId,
  createMemoryStorage,
  loadBoolean,
  loadSessionReattach,
  loadSessionId,
  saveBoolean,
  saveSessionReattach,
  saveSessionId,
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

  it("reports an absent boolean key as null rather than false", () => {
    const storage = createMemoryStorage();

    expect(loadBoolean(storage, storageKeys.controlPanelCollapsed)).toBeNull();
  });

  it("round-trips and clears the session id used for mid-capture reattach", () => {
    const storage = createMemoryStorage();

    expect(loadSessionId(storage)).toBeNull();

    saveSessionId(storage, "session-42");
    expect(loadSessionId(storage)).toBe("session-42");

    clearSessionId(storage);
    expect(loadSessionId(storage)).toBeNull();
  });

  it("round-trips and clears the tab-scoped reattach record", () => {
    const storage = createMemoryStorage();

    expect(loadSessionReattach(storage)).toBeNull();
    saveSessionReattach(storage, { sessionId: "session-42", viewToken: "view-only" });
    expect(loadSessionReattach(storage)).toEqual({
      sessionId: "session-42",
      viewToken: "view-only"
    });

    clearSessionReattach(storage);
    expect(loadSessionReattach(storage)).toBeNull();
  });

  it("clears malformed reattach credentials", () => {
    const storage = createMemoryStorage({
      [storageKeys.sessionReattach]: JSON.stringify({ sessionId: "session-42" })
    });

    expect(loadSessionReattach(storage)).toBeNull();
    expect(storage.getItem(storageKeys.sessionReattach)).toBeNull();
  });
});
