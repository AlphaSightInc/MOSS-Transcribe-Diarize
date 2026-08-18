// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { replaceTranscript, resetSessionState, sessionId } from "../state/session";
import { TranscriptPane } from "./TranscriptPane";

describe("TranscriptPane", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    resetSessionState();
    root = document.createElement("div");
    document.body.appendChild(root);
  });

  afterEach(() => {
    act(() => {
      render(null, root);
    });
    root.remove();
    resetSessionState();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("renders generic speaker labels and a provisional row from transcript state", () => {
    act(() => {
      render(<TranscriptPane />, root);
      replaceTranscript([
        {
          start: 3,
          end: 4,
          text: "A completed sentence.",
          speaker: "SPEAKER_07",
          speaker_entity_id: "speaker-7",
          display_name: "Named person",
          state: "final"
        },
        {
          start: 5,
          end: 6,
          text: "A live preview.",
          speaker: "SPEAKER_13",
          speaker_entity_id: "speaker-13",
          display_name: "Another name",
          state: "provisional"
        }
      ]);
    });

    expect([...root.querySelectorAll(".legend-chip-name")].map((node) => node.textContent)).toEqual([
      "SPEAKER_01",
      "SPEAKER_02"
    ]);
    expect([...root.querySelectorAll(".utt-speaker-label")].map((node) => node.textContent)).toEqual([
      "SPEAKER_01",
      "SPEAKER_02"
    ]);
    expect(root.querySelector(".utt[data-state='provisional'] .prov")).not.toBeNull();
    expect(root.querySelector(".utt[data-state='provisional'] .live-caret")).not.toBeNull();
    expect(root.querySelector("button.utt-speaker")).toBeNull();
  });

  it("searches rendered transcript rows and cycles actual matches", () => {
    act(() => {
      render(<TranscriptPane />, root);
      replaceTranscript([
        {
          start: 0,
          end: 1,
          text: "Ready for the next item.",
          speaker: "SPEAKER_01",
          speaker_entity_id: "speaker-1",
          display_name: "SPEAKER_01",
          state: "final"
        },
        {
          start: 1,
          end: 2,
          text: "The ready preview is still updating.",
          speaker: "SPEAKER_02",
          speaker_entity_id: "speaker-2",
          display_name: "SPEAKER_02",
          state: "provisional"
        }
      ]);
    });

    const findButton = [...root.querySelectorAll<HTMLButtonElement>("button")].find(
      (button) => button.textContent === "Find"
    );
    if (!findButton) {
      throw new Error("Missing transcript search control");
    }

    act(() => {
      findButton.click();
    });

    const input = root.querySelector<HTMLInputElement>("#transcript-find-input");
    if (!input) {
      throw new Error("Missing transcript search input");
    }

    act(() => {
      input.value = "ready";
      input.dispatchEvent(new InputEvent("input", { bubbles: true, data: "ready" }));
    });

    expect(root.querySelector(".tr-find-meta")?.textContent).toBe("1 of 2 matches");
    expect(root.querySelectorAll("[data-search-match-id]")).toHaveLength(2);

    const nextButton = root.querySelector<HTMLButtonElement>("[aria-label='Next match']");
    if (!nextButton) {
      throw new Error("Missing next-match control");
    }

    act(() => {
      nextButton.click();
    });

    expect(root.querySelector(".tr-find-meta")?.textContent).toBe("2 of 2 matches");
    expect(root.querySelector(".tr-search-match.is-active")?.getAttribute("data-search-match-id")).toBe("1");
  });

  it("keeps export disabled until transcript state has a session id", () => {
    act(() => {
      render(<TranscriptPane />, root);
      replaceTranscript([
        {
          start: 0,
          end: 1,
          text: "Transcript without session identity.",
          speaker: "SPEAKER_01",
          speaker_entity_id: "speaker-1",
          display_name: "SPEAKER_01",
          state: "final"
        }
      ]);
    });

    expect(root.querySelector<HTMLButtonElement>("button[title='Export transcript']")?.disabled).toBe(true);
  });

  it("downloads an export named with the active session id and ISO timestamp", () => {
    const downloadedNames: string[] = [];
    const createObjectUrl = vi.fn(() => "blob:transcript-export");
    const revokeObjectUrl = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: createObjectUrl, revokeObjectURL: revokeObjectUrl });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloadedNames.push(this.download);
    });
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-18T20:00:16.182Z"));

    act(() => {
      sessionId.value = "session-42";
      render(<TranscriptPane />, root);
      replaceTranscript([
        {
          start: 0,
          end: 1,
          text: "Ready to export.",
          speaker: "SPEAKER_01",
          speaker_entity_id: "speaker-1",
          display_name: "SPEAKER_01",
          state: "final"
        }
      ]);
    });

    const exportButton = root.querySelector<HTMLButtonElement>("button[title='Export transcript']");
    if (!exportButton) {
      throw new Error("Missing transcript export control");
    }
    act(() => {
      exportButton.click();
    });
    const markdownItem = root.querySelector<HTMLButtonElement>("[role='menuitem']");
    if (!markdownItem) {
      throw new Error("Missing Markdown export item");
    }
    act(() => {
      markdownItem.click();
      vi.runAllTimers();
    });

    expect(downloadedNames).toEqual(["transcript-session-42-2026-08-18T20:00:16.182Z.md"]);
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:transcript-export");
  });
});
