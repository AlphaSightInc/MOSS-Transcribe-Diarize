// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applySessionStateEvent, captureMeetingId, replaceTranscript, resetSessionState, sessionId, sessionMode, sessionNeedsReview, sessionStatus } from "../state/session";
import { autoscroll, resetUiState, selectedSummaryMeeting } from "../state/ui";
import { TranscriptPane } from "./TranscriptPane";
import { dispatchWsEvent } from "../api/ws";
import { createMemoryStorage } from "../lib/persistence";

describe("TranscriptPane", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    resetSessionState();
    autoscroll.value = true;
    selectedSummaryMeeting.value = null;
    root = document.createElement("div");
    document.body.appendChild(root);
    // Node's own non-functional localStorage shadows jsdom's here; use a working one.
    vi.stubGlobal("localStorage", createMemoryStorage());
  });

  afterEach(() => {
    act(() => {
      render(null, root);
    });
    root.remove();
    resetSessionState();
    autoscroll.value = true;
    selectedSummaryMeeting.value = null;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("uses the product name for an untitled transcript", () => {
    act(() => render(<TranscriptPane />, root));
    expect(root.querySelector(".tr-title")?.textContent).toContain("aiSight - LiveTranscribe");
    expect(root.querySelector(".tr-title")?.textContent).not.toContain("MOSS");
  });

  it("disables passage correction while clean-up runs with a tooltip and no status text", () => {
    const meeting = { id: "refining", mode: "live" as const, title: "Meeting", title_source: "automatic" as const,
      status: "completed" as const, created_at_ms: Date.now(), transcript_version: 1,
      refinement_state: "running" as const, transcript: { segments: [] }, audio: null };
    act(() => {
      sessionId.value = meeting.id;
      sessionStatus.value = "closed";
      selectedSummaryMeeting.value = meeting;
      replaceTranscript([{ start: 0, end: 1, text: "Live words", speaker: "speaker-0001",
        speaker_entity_id: "speaker-0001", display_name: "Alex", state: "final", segment_id: "seg-1" }]);
      render(<TranscriptPane />, root);
    });
    const removed = ["Improving transcript", "Passage corrections wait", "Transcript improved", "Improvement unavailable"];
    const reassign = () => root.querySelector<HTMLButtonElement>("[data-reassign-passage]");
    expect(reassign()?.disabled).toBe(true);
    expect(reassign()?.title).toBe("Wait until the transcript finishes improving");
    expect(root.querySelector<HTMLButtonElement>("button.utt-speaker")?.disabled).toBe(false);
    act(() => { selectedSummaryMeeting.value = { ...meeting, refinement_state: "done", transcript_version: 2 }; });
    expect(reassign()?.disabled).toBe(false);
    act(() => { selectedSummaryMeeting.value = { ...meeting, refinement_state: "failed",
      notice: "Improvement unavailable — the live transcript was kept" }; });
    for (const text of removed) expect(root.textContent).not.toContain(text);
    expect(root.querySelector(".tr-notice")).toBeNull();
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
    await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
    // An enrolled voiceprint is a success: no message.
    expect(root.querySelector(".tr-notice")).toBeNull();
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

  it("explains why a row cannot be named only on the disabled control", () => {
    showSpeakers(false);
    act(() => { sessionId.value = null; });
    const speaker = () => root.querySelector<HTMLButtonElement>(".utt-speaker")!;
    expect(speaker().disabled).toBe(true);
    expect(speaker().title).toBe("Open a meeting to name speakers");
    act(() => speaker().click());
    expect(root.querySelector("dialog")).toBeNull();
    act(() => {
      sessionId.value = "meeting/one";
      replaceTranscript([{ start: 0, end: 1, text: "Preview", speaker: "S01", speaker_entity_id: "canonical/a", display_name: "Alex", state: "provisional" }]);
    });
    expect(speaker().disabled).toBe(true);
    expect(speaker().title).toBe("Wait for confirmed speech");
    expect(root.querySelector(".tr-notice")).toBeNull();
    act(() => replaceTranscript([{ start: 0, end: 1, text: "Unattributed", speaker: "S00", speaker_entity_id: "S00", display_name: "S00", state: "confirmed" }]));
    expect(speaker().title).toBe("No identified speaker");
    expect(speaker().classList.contains("is-unidentified")).toBe(true);
  });

  it("merges committed prose and marks only canonical speaker changes as new blocks", () => {
    showSpeakers();
    act(() => replaceTranscript([
      { start: 0, end: 1, text: "First sentence.", speaker: "S01", speaker_entity_id: "a", display_name: "Alex", state: "confirmed" },
      { start: 1, end: 2, text: "Second sentence.", speaker: "S01", speaker_entity_id: "a", display_name: "Alex", state: "confirmed" },
      { start: 2, end: 3, text: "Preview", speaker: "S01", speaker_entity_id: "b", display_name: "Alex", state: "provisional" },
      { start: 3, end: 4, text: "Other speaker", speaker: "S01", speaker_entity_id: "b", display_name: "Alex", state: "confirmed" }
    ]));
    expect(root.querySelectorAll(".utt")).toHaveLength(2);
    expect(root.querySelector(".utt-text")?.textContent).toBe("First sentence. Second sentence.");
    expect([...root.querySelectorAll(".utt")].map(row => row.getAttribute("data-new-speaker"))).toEqual(["true", "true"]);
    expect([...root.querySelectorAll(".utt")[1].querySelectorAll(".utt-text")].map(row => row.textContent))
      .toEqual(["Other speaker", "Preview"]);
  });

  it.each([
    ["browser", "Browser"], ["window", "Window"], ["monitor", "Screen"], [null, "Shared"]
  ] as const)("labels live rows by I-4 and the %s share as %s (J5), never with raw tags", (surface, shared) => {
    if (surface) localStorage.setItem("moss.captureSurface.q5-live", surface);
    act(() => {
      render(<TranscriptPane />, root);
      applySessionStateEvent({ type: "session_state", session_id: "q5-live", mode: "live",
        state: "active", status: "active" });
      replaceTranscript([
        { source_lane: "system", start: 0, end: 1, text: "Theirs first", speaker: "S02",
          speaker_entity_id: "speaker-0003", display_name: "S02", state: "confirmed", segment_id: "a" },
        { source_lane: "microphone", start: 1, end: 2, text: "Me", speaker: "S01",
          speaker_entity_id: "local-0001", display_name: "S01", state: "confirmed", segment_id: "b" },
        { source_lane: "microphone", start: 2, end: 3, text: "Guest", speaker: "S04",
          speaker_entity_id: "local-0002", display_name: "S04", state: "confirmed", segment_id: "c" },
        { source_lane: "system", start: 3, end: 4, text: "Theirs second", speaker: "S03",
          speaker_entity_id: "speaker-0001", display_name: "S03", state: "confirmed", segment_id: "d" }
      ]);
    });
    expect([...root.querySelectorAll(".utt-speaker-label")].map(node => node.textContent))
      .toEqual(["Speaker 1", "You", "User 1", "Speaker 2"]);
    expect([...root.querySelectorAll(".legend-chip-name")].map(node => node.textContent))
      .toEqual(["Speaker 1", "You", "User 1", "Speaker 2"]);
    expect([...root.querySelectorAll(".utt-source")].map(node => node.textContent))
      .toEqual([shared, "Mic", "Mic", shared]);
    expect([...root.querySelectorAll(".utt-time")].map(node => node.textContent))
      .toEqual(["00:00:00", "00:00:01", "00:00:02", "00:00:03"]);
    const visible = `${root.querySelector(".tr-legend")?.textContent} ${root.querySelector("#tr-body")?.textContent}`;
    expect(visible).not.toMatch(/\bS0\d|Local \d|Remote\b|System|Shared audio|Microphone/);
    expect(root.querySelector("[data-settling-hint]")).toBeNull();
    expect(root.textContent).not.toContain("Identity settling");
  });

  it("shows no source label for File/URL meetings", () => {
    localStorage.setItem("moss.captureSurface.file-1", "browser");
    act(() => {
      render(<TranscriptPane />, root);
      applySessionStateEvent({ type: "session_state", session_id: "file-1", mode: "file", state: "completed", status: "closed" });
      replaceTranscript([{ start: 0, end: 1, text: "From a file", speaker: "S01", speaker_entity_id: "speaker-0001",
        display_name: "S01", state: "final" }]);
    });
    expect(sessionMode.value).toBe("file");
    expect(root.querySelector(".utt-source")).toBeNull();
    expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("Speaker 1");
  });

  it("uses the reference row structure: meta column, colour, separators and the live caret", () => {
    act(() => {
      render(<TranscriptPane />, root);
      applySessionStateEvent({ type: "session_state", session_id: "rows", mode: "live", state: "active", status: "active" });
      replaceTranscript([
        { source_lane: "system", start: 0, end: 1, text: "One", speaker: "S01", speaker_entity_id: "speaker-0001", display_name: "S01", state: "confirmed" },
        { source_lane: "system", start: 1, end: 2, text: "two", speaker: "S01", speaker_entity_id: "speaker-0001", display_name: "S01", state: "confirmed" },
        { source_lane: "microphone", start: 5, end: 6, text: "Mine", speaker: "S02", speaker_entity_id: "local-0001", display_name: "S02", state: "confirmed" },
        { source_lane: "microphone", start: 6, end: 7, text: "still talking", speaker: "S02", speaker_entity_id: "local-0001", display_name: "S02", state: "provisional" }
      ]);
    });
    const rows = [...root.querySelectorAll<HTMLElement>("article.utt")];
    expect(rows).toHaveLength(2);
    expect(rows.map(row => row.style.getPropertyValue("--sp"))).toEqual(["var(--sp-1)", "var(--sp-2)"]);
    expect(rows.map(row => row.dataset.newSpeaker)).toEqual(["true", "true"]);
    expect(rows[0]?.querySelector(".utt-meta .utt-speaker + .utt-source + .utt-time")).not.toBeNull();
    expect(rows[0]?.querySelector(".utt-text")?.textContent).toBe("One two");
    expect(rows[1]?.dataset.activeTail).toBe("true");
    expect(rows[1]?.querySelector(".utt-text .prov")?.textContent).toBe("still talking");
    expect(root.querySelectorAll(".live-caret")).toHaveLength(1);
    expect(rows[1]?.querySelector(".live-caret")).not.toBeNull();
    expect(root.querySelector("[title^='Text ']")).toBeNull();
  });

  it("keeps one confirmed speaker card across a long gap but splits S00", () => {
    act(() => {
      render(<TranscriptPane />, root);
      applySessionStateEvent({ type: "session_state", session_id: "q5-split", mode: "live",
        state: "active", status: "active", live_label_policy: "La" });
      replaceTranscript([
        { source_lane: "system", start: 0, end: 1, text: "Settled first", speaker: "S01",
          speaker_entity_id: "same", display_name: "S01", state: "confirmed", settled: true },
        { source_lane: "system", start: 5, end: 6, text: "Unsettled later", speaker: "S01",
          speaker_entity_id: "same", display_name: "S01", state: "confirmed", settled: false },
        { source_lane: "system", start: 10, end: 11, text: "Unknown first", speaker: "S00",
          speaker_entity_id: "S00", display_name: "S00", state: "confirmed" },
        { source_lane: "system", start: 15, end: 16, text: "Unknown later", speaker: "S00",
          speaker_entity_id: "S00", display_name: "S00", state: "confirmed" }
      ]);
    });
    const cards = [...root.querySelectorAll<HTMLElement>(".transcript-card")];
    expect(cards).toHaveLength(3);
    expect(cards.map(card => card.dataset.continuation)).toEqual(["false", "false", "false"]);
    expect(cards.map(card => card.querySelector(".utt-meta .utt-speaker-label")?.textContent))
      .toEqual(["Speaker 1", "Speaker TBD", "Speaker TBD"]);
    expect(cards[0]?.querySelectorAll(".utt-text")).toHaveLength(2);
  });

  it("follows new text only while Auto-scroll is on and Find is closed", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => { callback(0); return 1; });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    act(() => render(<TranscriptPane />, root));
    act(() => { autoscroll.value = false; });
    const body = root.querySelector<HTMLDivElement>("#tr-body")!;
    Object.defineProperty(body, "scrollHeight", { configurable: true, value: 500 });
    const control = [...root.querySelectorAll<HTMLButtonElement>("button")]
      .find(button => button.textContent === "Auto-scroll")!;
    act(() => control.click());
    expect(body.scrollTop).toBe(500);
    act(() => control.click());
    body.scrollTop = 120;
    act(() => replaceTranscript([{ start: 0, end: 1, text: "New text", speaker: "S01",
      speaker_entity_id: "person", display_name: "S01", state: "confirmed" }]));
    expect(body.scrollTop).toBe(120);
    act(() => control.click());
    const find = [...root.querySelectorAll<HTMLButtonElement>("button")]
      .find(button => button.textContent === "Find")!;
    act(() => find.click());
    body.scrollTop = 80;
    act(() => replaceTranscript([{ start: 0, end: 1, text: "Revised text", speaker: "S01",
      speaker_entity_id: "person", display_name: "S01", state: "confirmed" }]));
    expect(body.scrollTop).toBe(80);
  });

  it("renders committed S00 as uncertain and never offers to name it", () => {
    showSpeakers();
    act(() => replaceTranscript([{ start: 0, end: 1, text: "Unattributed speech", speaker: "S00", speaker_entity_id: "S00", display_name: "S00", state: "confirmed" }]));
    expect(root.querySelector<HTMLButtonElement>(".legend-chip")?.disabled).toBe(true);
    expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("Speaker TBD");
    expect(root.querySelector(".utt-text")?.textContent).toBe("Unattributed speech");
  });

  it.each(["pending", "error"])("shows nothing for %s success and keeps the input on failure", async (outcome) => {
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
      await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
      expect(root.querySelector(".tr-notice")).toBeNull();
      expect(root.textContent).not.toContain("after recording finishes");
    }
  });

  it.each(["refused", "unavailable"] as const)("keeps one voiceprint line when enrollment is %s", async (outcome) => {
    const fetcher = vi.fn(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(String(init.body));
      return outcome === "refused" && body.save_voiceprint !== false
        ? Response.json({ detail: { code: "voiceprint_evidence_not_admitted", message: "server copy" } }, { status: 400 })
        : Response.json({ meeting_id: "meeting/one", speaker_id: "canonical/a", label: "Alex",
            enrollment: outcome === "refused" ? "not_requested" : "unavailable" });
    });
    vi.stubGlobal("fetch", fetcher);
    showSpeakers();
    act(() => root.querySelector<HTMLButtonElement>(".legend-chip")!.click());
    await act(async () => {
      root.querySelector("dialog form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
    expect([...root.querySelectorAll(".tr-notice")].map(node => [node.getAttribute("role"), node.textContent]))
      .toEqual([["status", "Voiceprint not saved — not enough clear speech"]]);
    expect(root.textContent).not.toContain("server copy");
    expect(root.textContent).not.toContain("Saved Alex");
  });

  it("drops review, settling and dialog hint text from the pane", () => {
    showSpeakers();
    act(() => { sessionNeedsReview.value = true; });
    expect(root.textContent).not.toContain("Needs review");
    expect(root.textContent).not.toContain("Identity settling");
    act(() => root.querySelector<HTMLButtonElement>(".legend-chip")!.click());
    const dialog = root.querySelector("dialog")!;
    expect(dialog.querySelector(".hint")).toBeNull();
    expect(dialog.textContent).not.toContain("Applies to this speaker");
    expect(dialog.querySelector("input[type='checkbox']")).not.toBeNull();
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

    act(() => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })); });
    expect(root.querySelector(".tr-find-meta")?.textContent).toBe("1 of 2 matches");
    act(() => { input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true })); });
    expect(root.querySelector(".tr-find-meta")?.textContent).toBe("2 of 2 matches");
    act(() => root.querySelector<HTMLButtonElement>("[aria-label='Clear search']")!.click());
    expect(root.querySelector(".tr-find-meta")).toBeNull();
    expect(root.querySelector("mark")).toBeNull();
  });

  it("opens the glass find bar with Cmd/Ctrl+F, closes it with Esc, and scrolls matches to the centre", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => { callback(0); return 1; });
    vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    act(() => {
      render(<TranscriptPane />, root);
      replaceTranscript([{ start: 0, end: 1, text: "alpha beta alpha", speaker: "S01",
        speaker_entity_id: "speaker-0001", display_name: "S01", state: "final" }]);
    });
    const tools = root.querySelector(".tr-body-wrap > .tr-floating-tools")!;
    expect([...tools.children].map(node => node.className)).toEqual(["mini-btn", "divider", "mini-btn", "divider", "mini-btn is-on"]);
    expect(root.querySelector(".tr-find")).toBeNull();
    act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "f", metaKey: true })); });
    expect(root.querySelector(".tr-body-wrap > .tr-find")).not.toBeNull();
    const input = root.querySelector<HTMLInputElement>("#transcript-find-input")!;
    act(() => { input.value = "alpha"; input.dispatchEvent(new InputEvent("input", { bubbles: true })); });
    expect(root.querySelector(".tr-find-meta")?.textContent).toBe("1 of 2 matches");
    expect(root.querySelectorAll("mark.tr-search-match")).toHaveLength(2);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: "center", inline: "nearest", behavior: "smooth" });
    act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); });
    expect(root.querySelector(".tr-find")).toBeNull();
    act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "f", ctrlKey: true })); });
    expect(root.querySelector<HTMLInputElement>("#transcript-find-input")?.value).toBe("");
  });

  describe("Auto-scroll hand-off", () => {
    const segment = (text: string) => ({ start: 0, end: 1, text, speaker: "S01",
      speaker_entity_id: "speaker-0001", display_name: "S01", state: "final" as const });
    let height: number;
    function mount() {
      vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => { callback(0); return 1; });
      vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
      height = 1000;
      act(() => render(<TranscriptPane />, root));
      const body = root.querySelector<HTMLDivElement>("#tr-body")!;
      Object.defineProperty(body, "scrollHeight", { configurable: true, get: () => height });
      Object.defineProperty(body, "clientHeight", { configurable: true, value: 400 });
      return body;
    }
    /** A scroll event at `top`; the browser clamps scrollTop to the scrollable range. */
    const scroll = (body: HTMLDivElement, top: number) => act(() => {
      body.scrollTop = Math.max(0, Math.min(top, height - 400));
      body.dispatchEvent(new Event("scroll"));
    });
    const button = () => [...root.querySelectorAll<HTMLButtonElement>(".mini-btn")].find(b => b.textContent === "Auto-scroll")!;

    it("starts on, including after a UI reset and a meeting switch", async () => {
      vi.resetModules();
      expect((await import("../state/ui")).autoscroll.value).toBe(true);
      const body = mount();
      expect(button().getAttribute("aria-pressed")).toBe("true");
      expect(button().classList.contains("is-on")).toBe(true);
      scroll(body, 600); scroll(body, 200);
      expect(autoscroll.value).toBe(false);
      act(() => { sessionId.value = "another-meeting"; });
      expect(autoscroll.value).toBe(true);
      autoscroll.value = false;
      act(() => resetUiState());
      expect(autoscroll.value).toBe(true);
    });

    it("turns off when the reader scrolls up and back on at the very bottom", () => {
      const body = mount();
      scroll(body, 600);
      expect(autoscroll.value).toBe(true);
      scroll(body, 500);
      expect(autoscroll.value).toBe(false);
      expect(button().getAttribute("aria-pressed")).toBe("false");
      // Words arrive while the reader is up: the view stays where they left it.
      height = 1400;
      act(() => replaceTranscript([segment("new words")]));
      expect(body.scrollTop).toBe(500);
      scroll(body, 900);
      expect(autoscroll.value).toBe(false);
      scroll(body, 993); // within 8 px of the bottom
      expect(autoscroll.value).toBe(true);
    });

    it("stays on while content grows, shrinks or is anchored, and follows it to the bottom", () => {
      const body = mount();
      scroll(body, 600);
      // Growth: a scroll event fired before the next pin reads a larger distance from the bottom.
      height = 1200;
      act(() => { body.dispatchEvent(new Event("scroll")); });
      expect(autoscroll.value).toBe(true);
      // Chrome's scroll anchoring moves scrollTop up when preview rows above the view settle shorter
      // while new words land below it: the size changed, so it is not the reader.
      height = 1350;
      scroll(body, 550);
      expect(autoscroll.value).toBe(true);
      // Shrink: the browser clamps scrollTop down to the new bottom.
      height = 800;
      scroll(body, 550);
      expect(body.scrollTop).toBe(400);
      expect(autoscroll.value).toBe(true);
      // New content while on pins the view to the bottom.
      height = 1500;
      act(() => replaceTranscript([segment("latest words")]));
      expect(body.scrollTop).toBe(1500);
      expect(autoscroll.value).toBe(true);
    });

    it("toggles by hand; turning it on jumps to the bottom", () => {
      const body = mount();
      scroll(body, 600);
      act(() => button().click());
      expect(autoscroll.value).toBe(false);
      scroll(body, 300);
      height = 1300;
      act(() => replaceTranscript([segment("more words")]));
      expect(body.scrollTop).toBe(300);
      act(() => button().click());
      expect(autoscroll.value).toBe(true);
      expect(body.scrollTop).toBe(1300);
    });

    it("hands control to Find: a match scrolled into view turns Auto-scroll off", () => {
      const body = mount();
      scroll(body, 600);
      Element.prototype.scrollIntoView = vi.fn(function scrollMatch() { scroll(body, 120); });
      act(() => replaceTranscript([{ ...segment("alpha beta alpha") }]));
      act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "f", metaKey: true })); });
      const input = root.querySelector<HTMLInputElement>("#transcript-find-input")!;
      act(() => { input.value = "alpha"; input.dispatchEvent(new InputEvent("input", { bubbles: true })); });
      expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
      expect(autoscroll.value).toBe(false);
      // New words while Find is open do not pull the view away from the match.
      height = 1400;
      act(() => replaceTranscript([{ ...segment("alpha beta alpha gamma") }]));
      expect(body.scrollTop).toBe(120);
    });
  });

  it("shows lane-bound preview guesses as grey tentative blocks without duplicate preview rows", () => {
    act(() => {
      sessionId.value = "m"; sessionStatus.value = "active";
      render(<TranscriptPane />, root);
      dispatchWsEvent({ type: "transcript_update", session_id: "m", seq: 1,
        timestamp: new Date().toISOString(), items: [{ start: 0, end: 1, text: "hello", speaker: "UNKNOWN",
          speaker_entity_id: "UNKNOWN", display_name: "Speaker TBD", state: "provisional" }],
        provisional_segments: [{ start_sample: 0, end_sample: 8000, text: "hello", source_lane: "microphone", tentative_speaker: "local-0001" },
          { start_sample: 8000, end_sample: 16000, text: "again", source_lane: "microphone", tentative_speaker: "local-0001" },
          { start_sample: 16000, end_sample: 24000, text: "wait", source_lane: "microphone", tentative_speaker: null }] });
    });
    expect(root.querySelectorAll("[data-tentative-block]")).toHaveLength(2);
    expect(root.querySelector("[data-tentative-block]")?.textContent).toContain("hello again");
    expect(root.querySelector("[data-tentative-block] .utt-speaker.is-guess")).not.toBeNull();
    expect(root.querySelector("[data-tentative-block] .utt-text .prov")?.textContent).toBe("hello again");
    // Issue #7: a guessed name shows as the plain name; the dotted colour rule marks it instead of "?".
    expect([...root.querySelectorAll("[data-tentative-block] .utt-speaker-label")].map(node => node.textContent))
      .toEqual(["You", "Speaker TBD"]);
    expect(root.querySelector("#tr-body")?.textContent).not.toContain("?");
    const rows = [...root.querySelectorAll<HTMLElement>("article.utt")];
    expect(rows.map(row => row.dataset.speakerGuess ?? "")).toEqual(["true", ""]);
    // Screen readers still hear that the name is a guess; unattributed text needs no such note.
    expect(rows.map(row => row.querySelector(".utt-speaker .sr-only")?.textContent ?? null))
      .toEqual([" (guess)", null]);
    expect(root.querySelectorAll(".transcript-card:not([data-tentative-block])")).toHaveLength(0);
  });

  it("finds a guessed name by its plain label", () => {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => { callback(0); return 1; });
    Element.prototype.scrollIntoView = vi.fn();
    act(() => {
      sessionId.value = "m"; sessionStatus.value = "active";
      render(<TranscriptPane />, root);
      dispatchWsEvent({ type: "transcript_update", session_id: "m", seq: 1,
        timestamp: new Date().toISOString(), items: [],
        provisional_segments: [{ start_sample: 0, end_sample: 8000, text: "hello", source_lane: "microphone",
          tentative_speaker: "local-0001" }] });
    });
    act(() => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "f", metaKey: true })); });
    const input = root.querySelector<HTMLInputElement>("#transcript-find-input")!;
    act(() => { input.value = "you"; input.dispatchEvent(new InputEvent("input", { bubbles: true })); });
    expect(root.querySelector(".tr-find-meta")?.textContent).toBe("1 of 1 matches");
    expect(root.querySelector("[data-tentative-block] .utt-speaker-label mark.tr-search-match")?.textContent)
      .toBe("You");
  });

  it("continues the confirmed block when the guess is the same speaker (G9)", () => {
    act(() => {
      sessionId.value = "m"; sessionStatus.value = "active";
      render(<TranscriptPane />, root);
      dispatchWsEvent({ type: "transcript_update", session_id: "m", seq: 1,
        timestamp: new Date().toISOString(), items: [{ source_lane: "system", start: 0, end: 1, text: "Confirmed words",
          speaker: "S01", speaker_entity_id: "speaker-0001", display_name: "S01", state: "confirmed" }],
        provisional_segments: [
          { start_sample: 16000, end_sample: 24000, text: "and more", source_lane: "system", tentative_speaker: "speaker-0001" },
          { start_sample: 24000, end_sample: 32000, text: "new voice", source_lane: "system", tentative_speaker: "speaker-0004" }
        ] });
    });
    const rows = [...root.querySelectorAll<HTMLElement>("article.utt")];
    expect(rows.map(row => [row.dataset.tentativeBlock ?? "", row.dataset.continuation])).toEqual([
      ["", "false"], ["true", "true"], ["true", "false"]
    ]);
    expect(rows.map(row => row.querySelector(".utt-speaker-label")?.textContent))
      .toEqual(["Speaker 1", "Speaker 1", "Speaker 2"]);
    // The confirmed row keeps its solid rule; both guesses, including the continuation, are dotted.
    expect(rows.map(row => row.dataset.speakerGuess ?? "")).toEqual(["", "true", "true"]);
    expect(rows[1]?.style.getPropertyValue("--sp")).toBe(rows[0]?.style.getPropertyValue("--sp"));
    expect(rows[2]?.dataset.activeTail).toBe("true");
  });

  it("uses display names and numbered defaults for tentative canonical speakers", () => {
    act(() => {
      sessionId.value = "m"; sessionStatus.value = "active";
      render(<TranscriptPane />, root);
      dispatchWsEvent({ type: "transcript_update", session_id: "m", seq: 1,
        timestamp: new Date().toISOString(), items: [{ start: 0, end: 1, text: "known", speaker: "S01",
          speaker_entity_id: "speaker-0001", display_name: "Alex", state: "confirmed" }],
        provisional_segments: [
          { start_sample: 0, end_sample: 8000, text: "known", source_lane: "microphone", tentative_speaker: "speaker-0001" },
          { start_sample: 8000, end_sample: 16000, text: "new", source_lane: "microphone", tentative_speaker: "speaker-0002" }
        ] });
    });
    expect([...root.querySelectorAll("[data-tentative-block] .utt-speaker-label")].map(node => node.textContent))
      .toEqual(["Alex", "Speaker 1"]);
    expect(root.textContent).not.toContain("speaker-0002");
  });

  it("keeps summary in the centre card and leaves export to Controls", () => {
    act(() => render(<TranscriptPane />, root));
    expect(root.querySelector('[aria-label="Meeting views"]')).not.toBeNull();
    expect(root.querySelector("button[title='Export transcript']")).toBeNull();
    act(() => root.querySelector<HTMLButtonElement>('[aria-label="Meeting views"] [role="tab"]:last-child')!.click());
    expect(root.querySelector('[aria-label="Summary"]')).not.toBeNull();
    expect(root.querySelector('.tr-body-wrap')?.hasAttribute('hidden')).toBe(true);
  });

});
