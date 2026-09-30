// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { MeetingHistory } from "./MeetingHistory";
import { createMemoryStorage, storageKeys, type StorageLike } from "../lib/persistence";
import { resetSessionState } from "../state/session";
import {
  controlPanelCollapsed,
  historyPanelCollapsed,
  hydrateUiState,
  resetUiState,
  setControlPanelCollapsed
} from "../state/ui";

vi.mock("../lib/finalSummary", async importOriginal => ({
  ...await importOriginal<typeof import("../lib/finalSummary")>(),
  initializeRelaySettings: async () => []
}));

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
const button = (root: Element, label: string) => root.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);

describe("collapsible side panels (#8)", () => {
  let root: HTMLDivElement;
  let storage: StorageLike;

  beforeEach(() => {
    resetSessionState();
    resetUiState();
    storage = createMemoryStorage();
    // Node's own non-functional localStorage shadows jsdom's here; use a working one.
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal("fetch", vi.fn(async () => json({ meetings: [], voiceprints: [] })));
    root = document.createElement("div");
    document.body.append(root);
  });

  afterEach(() => {
    act(() => render(null, root));
    root.remove();
    resetSessionState();
    resetUiState();
    vi.unstubAllGlobals();
  });

  it("folds Controls into a rail, remembers it, and opens again from the rail", async () => {
    await act(async () => render(<App />, root));
    const panel = root.querySelector("#control-panel")!;
    expect(panel.classList.contains("collapsed")).toBe(false);
    expect(root.querySelector("#main")?.getAttribute("data-left-collapsed")).toBe("false");
    expect(root.querySelector(".top-status")?.getAttribute("title")).toBeNull();

    act(() => button(root, "Collapse controls")!.click());
    expect(panel.classList.contains("collapsed")).toBe(true);
    expect(root.querySelector("#main")?.getAttribute("data-left-collapsed")).toBe("true");
    expect(storage.getItem(storageKeys.controlPanelCollapsed)).toBe("true");
    // The pill shrinks to its dot over the rail; its label moves to the hover title.
    expect(root.querySelector(".top-status")?.getAttribute("title")).toBe("Standby");
    // The panel stays mounted: capture state lives in it and must survive a collapse.
    expect(panel.querySelector('[aria-label="Listening with"]')).not.toBeNull();

    act(() => root.querySelector<HTMLButtonElement>("#control-panel .panel-title-rail")!.click());
    expect(panel.classList.contains("collapsed")).toBe(false);
    expect(button(root, "Collapse controls")).not.toBeNull();
    expect(storage.getItem(storageKeys.controlPanelCollapsed)).toBe("false");
  });

  it("folds History into a rail and remembers it", async () => {
    await act(async () => render(<MeetingHistory />, root));
    const panel = root.querySelector(".history-panel")!;
    act(() => button(root, "Collapse history")!.click());
    expect(panel.classList.contains("collapsed")).toBe(true);
    expect(storage.getItem(storageKeys.historyPanelCollapsed)).toBe("true");
    act(() => button(root, "Expand history")!.click());
    expect(panel.classList.contains("collapsed")).toBe(false);
    expect(storage.getItem(storageKeys.historyPanelCollapsed)).toBe("false");
  });

  it("restores both panels from this browser's storage", async () => {
    storage.setItem(storageKeys.controlPanelCollapsed, "true");
    storage.setItem(storageKeys.historyPanelCollapsed, "true");
    hydrateUiState();
    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    expect(root.querySelector("#control-panel")?.classList.contains("collapsed")).toBe(true);
    expect(root.querySelector(".history-panel")?.classList.contains("collapsed")).toBe(true);
    expect(button(root, "Expand controls")).not.toBeNull();
    expect(button(root, "Expand history")).not.toBeNull();
  });

  it("keeps working when browser storage is blocked", () => {
    const blocked: StorageLike = {
      getItem: () => { throw new DOMException("blocked", "SecurityError"); },
      setItem: () => { throw new DOMException("blocked", "SecurityError"); },
      removeItem: () => { throw new DOMException("blocked", "SecurityError"); }
    };
    expect(() => hydrateUiState(blocked)).not.toThrow();
    expect(controlPanelCollapsed.value).toBe(false);
    expect(historyPanelCollapsed.value).toBe(false);
    expect(() => setControlPanelCollapsed(true, blocked)).not.toThrow();
    expect(controlPanelCollapsed.value).toBe(true);
  });
});
