// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { captureMeetingId, replaceTranscript, resetSessionState, sessionId, sessionStatus } from "../state/session";
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

  it("uses the product name for an untitled transcript", () => {
    act(() => render(<TranscriptPane />, root));
    expect(root.querySelector(".tr-title")?.textContent).toContain("MOSS");
    expect(root.querySelector(".tr-title")?.textContent).not.toContain("LiveTranscribe");
  });

  it("renders display names and a provisional row without exposing canonical IDs", () => {
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
      "Named person",
      "Another name"
    ]);
    expect([...root.querySelectorAll(".utt-speaker-label")].map((node) => node.textContent)).toEqual([
      "Named person",
      "Another name"
    ]);
    expect(root.querySelector(".utt[data-state='provisional'] .prov")).not.toBeNull();
    expect(root.querySelector(".utt[data-state='provisional'] .live-caret")).not.toBeNull();
    expect(root.querySelectorAll("button.utt-speaker")).toHaveLength(2);
  });

  it("publishes each rendered turn's model-state custody", () => {
    act(() => {
      render(<TranscriptPane />, root);
      replaceTranscript([
        {
          start: 3.25,
          end: 4,
          text: "First part.",
          speaker: "SPEAKER_07",
          speaker_entity_id: "speaker-7",
          display_name: "Named person",
          state: "final",
          segment_id: "segment-a"
        },
        {
          start: 4,
          end: 6.5,
          text: "Second part.",
          speaker: "SPEAKER_07",
          speaker_entity_id: "speaker-7",
          display_name: "Named person",
          state: "final",
          segment_id: "segment-b"
        }
      ]);
    });

    const row = root.querySelector(".utt");
    expect(root.querySelectorAll(".utt")).toHaveLength(1);
    expect(row?.getAttribute("data-turn-start")).toBe("3.25");
    expect(row?.getAttribute("data-turn-end")).toBe("6.5");
    expect(row?.getAttribute("data-target-keys")).toBe("segment:segment-a|segment:segment-b");
    expect(JSON.parse(row?.getAttribute("data-segments") ?? "null")).toEqual([
      { start: 3.25, end: 4, text: "First part." },
      { start: 4, end: 6.5, text: "Second part." }
    ]);
  });

  function showSpeakers(originating = true): void {
    act(() => {
      sessionId.value = "meeting/one";
      captureMeetingId.value = originating ? "meeting/one" : null;
      sessionStatus.value = "active";
      render(<TranscriptPane />, root);
      replaceTranscript(["a", "b"].map((id, index) => ({
        start: index, end: index + 1, text: `Words from ${id}`,
        speaker: `S0${index + 1}`, speaker_entity_id: `canonical/${id}`,
        display_name: "Alex", state: "confirmed" as const
      })));
    });
  }

  it("keeps an explicitly chosen generic-looking name literal in view and copy", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    showSpeakers();
    act(() => replaceTranscript([{ start: 0, end: 1, text: "Hello", speaker: "S01", speaker_entity_id: "canonical/a", display_name: "SPEAKER_07", state: "confirmed" }]));
    expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("SPEAKER_07");
    await act(async () => root.querySelector<HTMLButtonElement>("button[title='Copy']")!.click());
    expect(writeText).toHaveBeenCalledWith("[00:00:00] SPEAKER_07:\nHello");
  });

  it("keeps duplicate names separate and saves the chosen canonical speaker only", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      meeting_id: "meeting/one", speaker_id: "canonical/b", label: "Sam", enrollment: "enrolled"
    })));
    vi.stubGlobal("fetch", fetcher);
    showSpeakers();
    expect(root.querySelectorAll(".utt")).toHaveLength(2);
    expect(root.querySelectorAll(".legend-chip")).toHaveLength(2);
    act(() => root.querySelectorAll<HTMLButtonElement>(".utt-speaker")[1].click());
    const input = root.querySelector<HTMLInputElement>("#speaker-name-input")!;
    act(() => {
      input.value = "  Sam  ";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      root.querySelector("dialog form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(fetcher).toHaveBeenCalledWith("/api/meetings/meeting%2Fone/speakers/canonical%2Fb/name", expect.objectContaining({
      method: "PUT", credentials: "same-origin", body: JSON.stringify({ label: "Sam" })
    }));
    await vi.waitFor(() => expect(root.textContent).toContain("Voiceprint saved privately"));
    expect(root.querySelector("dialog")).toBeNull();
    // Apply the acknowledged name immediately while preserving the other identity.
    expect([...root.querySelectorAll(".utt-speaker-label")].map(node => node.textContent)).toEqual(["Alex", "Sam"]);
    expect([...root.querySelectorAll(".legend-chip-name")].map(node => node.textContent)).toEqual(["Alex", "Sam"]);
  });

  it("allows owned observers and terminal meetings but keeps provisional-only speakers read-only", () => {
    showSpeakers(false);
    expect([...root.querySelectorAll<HTMLButtonElement>(".legend-chip")].every(button => !button.disabled)).toBe(true);
    act(() => {
      captureMeetingId.value = "meeting/one";
      sessionStatus.value = "closed";
    });
    expect(root.querySelector<HTMLButtonElement>(".legend-chip")?.disabled).toBe(false);
    act(() => {
      sessionStatus.value = "active";
      replaceTranscript([{ start: 0, end: 1, text: "preview", speaker: "S01", speaker_entity_id: "canonical/a", display_name: "S01", state: "provisional" }]);
    });
    expect(root.querySelector<HTMLButtonElement>(".legend-chip")?.disabled).toBe(true);
  });

  it("explains why a row cannot be named", () => {
    showSpeakers(false);
    act(() => { sessionId.value = null; });
    act(() => root.querySelector<HTMLButtonElement>(".utt-speaker")!.click());
    expect(root.querySelector('[role="status"]')?.textContent).toContain("Open a meeting");
    expect(root.querySelector("dialog")).toBeNull();
    act(() => {
      sessionId.value = "meeting/one";
      replaceTranscript([{ start: 0, end: 1, text: "Preview", speaker: "S01", speaker_entity_id: "canonical/a", display_name: "Alex", state: "provisional" }]);
    });
    act(() => root.querySelector<HTMLButtonElement>(".utt-speaker")!.click());
    expect(root.querySelector('[role="status"]')?.textContent).toContain("committed");
    expect(root.querySelector("dialog")).toBeNull();
  });

  it("merges committed prose and marks only canonical speaker changes as new blocks", () => {
    showSpeakers();
    act(() => replaceTranscript([
      { start: 0, end: 1, text: "First sentence.", speaker: "S01", speaker_entity_id: "a", display_name: "Alex", state: "confirmed" },
      { start: 1, end: 2, text: "Second sentence.", speaker: "S01", speaker_entity_id: "a", display_name: "Alex", state: "confirmed" },
      { start: 2, end: 3, text: "Preview", speaker: "S01", speaker_entity_id: "b", display_name: "Alex", state: "provisional" },
      { start: 3, end: 4, text: "Other speaker", speaker: "S01", speaker_entity_id: "b", display_name: "Alex", state: "confirmed" }
    ]));
    expect(root.querySelectorAll(".utt")).toHaveLength(3);
    expect(root.querySelector(".utt-text")?.textContent).toBe("First sentence. Second sentence.");
    expect([...root.querySelectorAll(".utt")].map(row => row.getAttribute("data-new-speaker"))).toEqual(["true", "true", "false"]);
  });

  it("renders committed S00 as uncertain and never offers to name it", () => {
    showSpeakers();
    act(() => replaceTranscript([{ start: 0, end: 1, text: "Unattributed speech", speaker: "S00", speaker_entity_id: "S00", display_name: "S00", state: "confirmed" }]));
    expect(root.querySelector<HTMLButtonElement>(".legend-chip")?.disabled).toBe(true);
    expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("Speaker uncertain");
    expect(root.querySelector(".utt-text")?.textContent).toBe("Unattributed speech");
  });

  it.each(["pending", "error"])("explains %s naming without losing the input", async (outcome) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(outcome === "error"
      ? { detail: "Meeting Speaker not found." }
      : { meeting_id: "meeting/one", speaker_id: "canonical/a", label: "Alex", enrollment: "pending" }),
    { status: outcome === "error" ? 404 : 200 })));
    showSpeakers();
    act(() => root.querySelector<HTMLButtonElement>(".legend-chip")!.click());
    await act(async () => {
      root.querySelector("dialog form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    if (outcome === "error") {
      await vi.waitFor(() => expect(root.querySelector("[role='alert']")?.textContent).toBe("Meeting Speaker not found."));
      expect(root.querySelector<HTMLInputElement>("#speaker-name-input")?.value).toBe("Alex");
    } else {
      await vi.waitFor(() => expect(root.textContent).toContain("before Stop"));
    }
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
    act(() => {
      sessionId.value = "empty-meeting";
      replaceTranscript([]);
    });
    expect(root.querySelector<HTMLButtonElement>("button[title='Export transcript']")?.disabled).toBe(true);
  });

  it.each([
    ["Markdown (.md)", "md"], ["Plain text (.txt)", "txt"], ["JSON (.json)", "json"],
    ["SubRip (.srt)", "srt"], ["WebVTT (.vtt)", "vtt"]
  ])("downloads %s with the active session id and ISO timestamp", (label, format) => {
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
    const markdownItem = [...root.querySelectorAll<HTMLButtonElement>("[role='menuitem']")].find(item => item.textContent === label);
    if (!markdownItem) {
      throw new Error(`Missing ${label} export item`);
    }
    act(() => {
      markdownItem.click();
      vi.runAllTimers();
    });

    expect(downloadedNames).toEqual([`transcript-session-42-2026-08-18T20:00:16.182Z.${format}`]);
    expect(createObjectUrl).toHaveBeenCalledOnce();
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:transcript-export");
  });
});
