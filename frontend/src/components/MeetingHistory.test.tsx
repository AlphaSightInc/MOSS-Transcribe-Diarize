// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Meeting } from "../api/meetings";
import {
  LIVE_MEETING_OBSERVE_EVENT,
  OPEN_MEETING_EVENT,
  MEETING_HISTORY_REFRESH_EVENT
} from "../lib/meetingEvents";
import { replaceTranscript, resetSessionState, sessionTitle, sessionId, sessionMode, sessionNeedsReview, sessionStatus, sessionTranscriptItems, transcript } from "../state/session";
import { sessionStartedAt, sessionStopRequested } from "../state/session";
import { App } from "../App";
import { MeetingHistory } from "./MeetingHistory";
import { resetUiState, selectedSummaryMeeting } from "../state/ui";
import { defaultAppSettings, saveAppSettings } from "../lib/settings";

// These fixtures script history requests; model discovery is covered in FinalSummary.test.tsx.
vi.mock("../lib/finalSummary", async importOriginal => ({
  ...await importOriginal<typeof import("../lib/finalSummary")>(),
  initializeRelaySettings: async () => []
}));

const now = Date.now();

function meeting(overrides: Partial<Meeting> = {}): Meeting {
  return {
    id: "meeting-a",
    mode: "live",
    title: "Meeting A",
    title_source: "automatic",
    status: "completed",
    created_at_ms: now,
    transcript: {
      segments: [{ id: "seg_0001", start: 0, end: 1, speaker: "S01", text: "first words" }]
    },
    transcript_version: 1,
    audio: null,
    ...overrides
  };
}

describe("MeetingHistory", () => {
  let root: HTMLDivElement;

  beforeEach(() => {
    root = document.createElement("div");
    document.body.append(root);
    resetSessionState();
    resetUiState();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    act(() => render(null, root));
    root.remove();
    resetSessionState();
    sessionStartedAt.value = null;
    sessionStopRequested.value = null;
    resetUiState();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it.each([
    { status: "failed" as const, failure_code: "decode_failed", failure_reason: "Decoder unavailable." },
    { status: "completed" as const, notice: "No speech detected." }
  ])("keeps saved outcome notices and raw reasons off the history row and selection (Q6)", async outcome => {
    const selected = meeting({ mode: "file", transcript: { segments: [] }, ...outcome });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url === "/api/meetings" ? { meetings: [selected] } : selected)));
    await act(async () => render(<MeetingHistory />, root));
    const reason = selected.failure_reason || selected.notice!;
    await vi.waitFor(() => expect(root.querySelector(".history-card-subtitle")?.textContent).toBe("No transcript"));
    expect(root.querySelector(".history-card-meta")?.textContent?.endsWith(selected.status === "failed" ? "Failed" : "File / URL")).toBe(true);
    await act(async () => { document.dispatchEvent(new CustomEvent(OPEN_MEETING_EVENT, { detail: { meetingId: selected.id } })); });
    await vi.waitFor(() => expect(sessionId.value).toBe(selected.id));
    expect(root.textContent).not.toContain(reason);
  });

  it("shows partial audio after tape exhaustion without the retained-words notice", async () => {
    const notice = "Final transcript refinement was unavailable for some audio. Previously committed words were kept.";
    const selected = meeting({ notice, audio: {
      state: "partial", relative_path: "audio.partial.mp3", byte_count: 360693,
      duration_ms: 60000, format: "mp3", sample_rate_hz: 16000, channels: 1, bit_rate_bps: 48000
    } });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url === "/api/meetings" ? { meetings: [selected] } : selected)));
    await act(async () => render(<MeetingHistory />, root));
    await vi.waitFor(() => expect(root.querySelector(".history-card-subtitle")?.textContent).toBe("first words"));
    expect(root.querySelector("[data-audio-download]")?.textContent).toBe("Download partial audio");
    await act(async () => { document.dispatchEvent(new CustomEvent(OPEN_MEETING_EVENT, { detail: { meetingId: selected.id } })); });
    await vi.waitFor(() => expect(transcript.value.map(segment => segment.text)).toEqual(["first words"]));
    expect(root.textContent).not.toContain(notice);
  });

  // #14: the top pill never runs a clock for a finished meeting, and an observed one counts from its real start.
  it.each([
    { name: "a finished meeting", status: "completed" as const, liveEvents: [], pill: /^Standby$/ },
    { name: "an active meeting", status: "active" as const, liveEvents: [], pill: /^Recording 5:0\d$/ },
    { name: "a meeting draining after Stop", status: "active" as const,
      liveEvents: [{ seq: 7, session_id: "observed", kind: "stop_requested", payload: {} }], pill: /^Stopping$/ }
  ])("opening $name from History shows the true pill state", async ({ status, liveEvents, pill }) => {
    const opened = meeting({ id: "observed", status, created_at_ms: Date.now() - 300_000 });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/meetings") return response({ meetings: [opened] });
      if (url.includes("/events")) return response({ events: liveEvents });
      if (url.includes("/snapshot")) return response({ unchanged: false, snapshot: {
        session_id: "observed", descriptor: { sample_rate: 16_000 },
        session: { committed_samples: 0, status: "active", version: 1, failure_reason: null, label_revision_version: 0,
          identity_snapshot: { canonical_speakers: [] }, committed: [], provisional: null } } });
      if (url.endsWith("/summary")) return response({ summary: null });
      return response(opened);
    }));
    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="observed"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="observed"]')!.click());
    await vi.waitFor(() => expect(root.querySelector(".top-status")?.textContent).toMatch(pill));
  });

  it("opens the selected meeting summary in the centre card", async () => {
    const first = meeting({ id: "first", title: "First meeting" });
    const second = meeting({ id: "second", title: "Second meeting" });
    const meetings = [first, second];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/meetings") return response({ meetings });
      if (url.endsWith("/summary")) return response({ summary: null });
      return response(meetings.find(item => url.endsWith(`/${item.id}`)));
    }));
    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="first"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="first"]')!.click());
    await vi.waitFor(() => expect(sessionId.value).toBe("first"));
    act(() => root.querySelector<HTMLButtonElement>('[aria-label="Meeting views"] [role="tab"]:last-child')!.click());
    expect(root.querySelector('[aria-label="Summary"]')).not.toBeNull();
    expect(sessionId.value).toBe("first");
    expect(document.body.querySelector('[aria-label="Summary view"]')).toBeNull();
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="second"]')!.click());
    await vi.waitFor(() => expect(sessionId.value).toBe("second"));
  });

  it("hydrates saved review truth after Stop settles without a manual reopen", async () => {
    const active = meeting({ id: "just-stopped", status: "active", needs_review: false });
    const completed = meeting({
      id: "just-stopped",
      status: "completed",
      needs_review: true,
      notice: "Final transcript refinement was unavailable for some audio. Previously committed words were kept.",
      transcript_version: 2,
      transcript: { segments: [
        { id: "uncertain", start: 0, end: 1, speaker: "Speaker TBD", speaker_entity_id: "S00", text: "kept words" }
      ] }
    });
    let lists = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url !== "/api/meetings") return response(completed);
      lists += 1;
      return response({ meetings: [lists === 1 ? active : completed] });
    }));
    sessionId.value = "just-stopped";
    sessionStatus.value = "closed";

    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="just-stopped"]')).not.toBeNull());
    expect(sessionNeedsReview.value).toBe(false);

    act(() => {
      document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT));
    });
    await vi.waitFor(() => expect(sessionNeedsReview.value).toBe(true));
    expect(transcript.value.map(row => row.text)).toEqual(["kept words"]);
    // Q6: review state is kept, but the transcript pane no longer prints it.
    expect(root.querySelector(".transcript-pane")?.textContent).not.toContain("Needs review");
    expect(lists).toBe(2);
  });

  it("polls a refining meeting and replaces the selected transcript when improvement completes", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const running = meeting({ id: "refining", refinement_state: "running",
      transcript: { segments: [{ id: "first", start: 0, end: 1, speaker: "Alex", text: "Live words" }] } });
    const done = meeting({ ...running, refinement_state: "done", transcript_version: 2, refined_version: 2,
      transcript: { segments: [{ id: "second", start: 0, end: 1, speaker: "Named Alex", text: "Improved words" }] } });
    let detailReads = 0;
    const fetcher = vi.fn(async (url: string) => url === "/api/meetings"
      ? response({ meetings: [running] })
      : response(detailReads++ < 2 ? running : done));
    vi.stubGlobal("fetch", fetcher);
    await act(async () => render(<MeetingHistory />, root));
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="refining"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="refining"]')!.click());
    await vi.waitFor(() => expect(selectedSummaryMeeting.value?.id).toBe("refining"));
    expect(selectedSummaryMeeting.value?.refinement_state).toBe("running");
    expect(transcript.value.map(row => row.text)).toEqual(["Live words"]);
    act(() => { sessionTranscriptItems.value = sessionTranscriptItems.value.map(row => ({ ...row, display_name: "Named Alex" })); });
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(transcript.value[0].display_name).toBe("Named Alex");
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(fetcher.mock.calls.filter(([url]) => url === "/api/meetings/refining")).toHaveLength(3);
    expect(selectedSummaryMeeting.value?.refinement_state).toBe("done");
    expect(transcript.value.map(row => row.text)).toEqual(["Improved words"]);
  });

  it("polls an unselected refining meeting and updates its saved Gemini summary", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const values = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
    const settings = defaultAppSettings();
    settings.summary.apiKey = "key";
    saveAppSettings(settings);
    const running = meeting({ id: "refining", refinement_state: "running" });
    const done = meeting({ ...running, refinement_state: "done", transcript_version: 2, refined_version: 2,
      transcript: { segments: [{ id: "improved", start: 0, end: 1, speaker: "Alex", text: "Improved words" }] } });
    const other = meeting({ id: "other", title: "Other meeting" });
    const oldSummary = { state: "current", attempt_id: "old", source_version: 1,
      artifact_version: 1, error_code: null, document: { summary: "Old summary", topics: [],
        details: [], speaker_background: [], data_references: [] } };
    let refined = false;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/meetings") return response({ meetings: [refined ? done : running, other] });
      if (url === "/api/meetings/refining") { refined = true; return response(done); }
      if (url === "/api/meetings/other") return response(other);
      if (url === "/api/meetings/refining/summary") return response({ summary: oldSummary });
      if (url === "/api/meetings/refining/summary/server" && init?.method === "POST")
        return response({ ...oldSummary, source_version: 2, attempt_id: "new" });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetcher);
    await act(async () => render(<MeetingHistory />, root));
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="other"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="other"]')!.click());
    await vi.waitFor(() => expect(selectedSummaryMeeting.value?.id).toBe("other"));
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(root.querySelector('[data-meeting-card="refining"]')?.textContent).toContain("Improved words");
    expect(selectedSummaryMeeting.value?.id).toBe("other");
    const posts = fetcher.mock.calls.filter(([url, init]) => url.endsWith("/summary/server") && init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0][1]!.body as string).source_version).toBe(2);
  });

  it("keeps rename available but holds History audio download during improvement", async () => {
    const running = meeting({ refinement_state: "running", audio: {
      state: "available", relative_path: "meeting.mp3", byte_count: 100, duration_ms: 1000,
      format: "mp3", sample_rate_hz: 16000, channels: 1, bit_rate_bps: 48000
    } });
    vi.stubGlobal("fetch", vi.fn(async () => response({ meetings: [running] })));
    await act(async () => render(<MeetingHistory />, root));
    await vi.waitFor(() => expect(root.querySelector('[data-meeting-card="meeting-a"]')).not.toBeNull());
    expect(root.querySelector("[data-audio-download]")).toBeNull();
    expect(root.textContent).not.toContain("Audio export waits");
    // The state lives on the control, as with Export Save.
    expect(root.querySelector<HTMLButtonElement>("[data-audio-download-pending]")?.textContent).toBe("Improving…");
    expect(root.querySelector<HTMLButtonElement>("[data-audio-download-pending]")?.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".history-action-btn")?.disabled).toBe(false);
  });

  it("brings an explicitly opened import into view but leaves background refresh in place", async () => {
    const selected = meeting({ id: "imported", title: "Imported review" });
    vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url === "/api/meetings" ? { meetings: [selected] } : selected)));
    const panel = document.createElement("section");
    panel.id = "transcript-panel";
    const scroll = vi.fn();
    panel.scrollIntoView = scroll;
    document.body.append(panel);
    const history = root;
    await act(async () => render(<MeetingHistory />, history));
    await act(async () => { document.dispatchEvent(new CustomEvent(OPEN_MEETING_EVENT, { detail: { meetingId: "imported" } })); });
    await vi.waitFor(() => expect(scroll).toHaveBeenCalledOnce());
    expect(history.querySelector('[data-open-meeting="imported"]')?.getAttribute("aria-pressed")).toBe("true");
    await act(async () => { document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT)); });
    expect(scroll).toHaveBeenCalledOnce();
    sessionId.value = "new-live";
    sessionMode.value = "live";
    sessionTitle.value = "Current live meeting";
    await act(async () => { document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT)); });
    expect(sessionTitle.value).toBe("Current live meeting");
    expect(sessionMode.value).toBe("live");
    expect(scroll).toHaveBeenCalledOnce();
    panel.remove();
  });

  it("renders one Active group before terminal dates and filters locally", async () => {
    const rows = [
      meeting({ id: "terminal", title: "Customer review" }),
      meeting({ id: "active-old", title: "Live now", status: "active", created_at_ms: now - 3 * 86_400_000 })
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ meetings: rows })));

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.querySelectorAll("[data-meeting-card]")).toHaveLength(2));
    expect([...root.querySelectorAll(".hist-group-label")].map((node) => node.textContent)).toEqual([
      "Active",
      "Today"
    ]);

    const input = root.querySelector<HTMLInputElement>('[aria-label="Search meetings"]');
    if (!input) throw new Error("missing search input");
    input.value = "customer";
    act(() => {
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect([...root.querySelectorAll(".history-card-title")].map((node) => node.textContent)).toEqual([
      "Customer review"
    ]);
  });

  it("renders explicit unavailable audio truth without a download link", async () => {
    const unavailable = meeting({
      audio: {
        state: "unavailable",
        relative_path: null,
        byte_count: null,
        duration_ms: null,
        format: null,
        sample_rate_hz: null,
        channels: null,
        bit_rate_bps: null
      }
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ meetings: [unavailable] })));

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.querySelector("[data-audio-unavailable]")).not.toBeNull());
    expect(root.querySelector("[data-audio-unavailable]")?.textContent).toBe("Audio unavailable");
    expect(root.querySelector("[data-audio-download]")).toBeNull();
  });

  it("opens an active Live Meeting read-only and renders its transcript", async () => {
    const active = meeting({ id: "live-active", status: "active", title: "Standup" });
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ meetings: [active] }))
      .mockResolvedValueOnce(response(active));
    vi.stubGlobal("fetch", fetcher);
    const observed: string[] = [];
    document.addEventListener(LIVE_MEETING_OBSERVE_EVENT, ((event: CustomEvent) => {
      observed.push(event.detail.meetingId);
    }) as EventListener, { once: true });

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="live-active"]')).not.toBeNull());
    await act(async () => {
      root.querySelector<HTMLButtonElement>('[data-open-meeting="live-active"]')?.click();
    });
    await vi.waitFor(() => expect(observed).toEqual(["live-active"]));
    expect(sessionTitle.value).toBe("Standup");
    expect(transcript.value[0].text).toBe("first words");
    expect(window.sessionStorage.length).toBe(0);
  });

  it("keeps two saved speakers with the same name separate in history", async () => {
    const completed = meeting({ transcript: { segments: [
      { id: "one", start: 0, end: 1, speaker: "Alex", speaker_entity_id: "canonical-a", text: "First" },
      { id: "two", start: 1, end: 2, speaker: "Alex", speaker_entity_id: "canonical-b", text: "Second" }
    ] } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ meetings: [completed] })).mockResolvedValueOnce(response(completed)));
    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="meeting-a"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="meeting-a"]')!.click());
    await vi.waitFor(() => expect(root.querySelectorAll(".utt")).toHaveLength(2));
    expect([...root.querySelectorAll(".utt-speaker-label")].map(node => node.textContent)).toEqual(["Alex", "Alex"]);
    expect(transcript.value.map(item => item.speaker_entity_id)).toEqual(["canonical-a", "canonical-b"]);
    expect(root.textContent).not.toContain("canonical-a");
  });

  it("opens Account history into the transcript pane and exports both transcript formats", async () => {
    const completed = meeting({ id: "export-meeting", title: "Export source" });
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(response({ meetings: [completed] }))
        .mockResolvedValueOnce(response(completed))
    );
    const downloads: string[] = [];
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:account-export"),
      revokeObjectURL: vi.fn()
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      downloads.push(this.download);
    });
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-28T12:00:00.000Z"));

    await act(async () => {
      render(
        <div>
          <App />
          <MeetingHistory />
        </div>,
        root
      );
    });
    await vi.waitFor(() =>
      expect(root.querySelector('[data-open-meeting="export-meeting"]')).not.toBeNull()
    );
    await act(async () => {
      root.querySelector<HTMLButtonElement>('[data-open-meeting="export-meeting"]')?.click();
    });
    await vi.waitFor(() =>
      expect(root.querySelector("#tr-body")?.textContent).toContain("first words")
    );

    expect(root.querySelector('[data-open-meeting="export-meeting"]')?.getAttribute("aria-pressed")).toBe("true");
    expect(root.querySelector("#transcript-panel")).not.toBeNull();
    for (const format of ["md", "txt"]) {
      act(() => { root.querySelector<HTMLSelectElement>('[aria-label="Export format"]')!.value = format;
        root.querySelector<HTMLSelectElement>('[aria-label="Export format"]')!.dispatchEvent(new Event("change", { bubbles: true })); });
      await act(async () => root.querySelector<HTMLButtonElement>(".controls-export button")!.click());
    }

    expect(downloads).toHaveLength(2);
    expect(downloads.map((name) => name.split(".").at(-1))).toEqual(["md", "txt"]);
    expect(downloads.every((name) => name.startsWith("transcript-export-meeting-"))).toBe(true);
  });

  it("keeps reopened review truth through failed History and real transcript downloads", async () => {
    const savedReview = meeting({
      id: "review-meeting",
      needs_review: true,
      transcript: {
        segments: [{
          id: "seg_0001",
          start: 0,
          end: 1,
          speaker: "S00",
          speaker_entity_id: "S00",
          text: "words kept after partial processing"
        }]
      }
    });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/meetings") throw new Error("controlled History failure");
      if (path.endsWith("/summary")) return response({ summary: null });
      if (path === "/api/meetings/review-meeting") return response(savedReview);
      throw new Error(`unexpected request: ${path}`);
    }));
    const blobs: Blob[] = [];
    const downloads: string[] = [];
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn((blob: Blob) => {
        blobs.push(blob);
        return `blob:review-${blobs.length}`;
      }),
      revokeObjectURL: vi.fn()
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      downloads.push(this.download);
    });

    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await act(async () => {
      document.dispatchEvent(new CustomEvent(OPEN_MEETING_EVENT, {
        detail: { meetingId: "review-meeting" }
      }));
    });
    await vi.waitFor(() =>
      expect(root.querySelector("#tr-body")?.textContent).toContain(
        "words kept after partial processing"
      )
    );

    expect(root.querySelector(".transcript-pane")?.textContent).not.toContain("Needs review");
    expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("Speaker TBD");
    for (const [index, format] of ["md", "txt"].entries()) {
      act(() => { const select = root.querySelector<HTMLSelectElement>('[aria-label="Export format"]')!;
        select.value = format; select.dispatchEvent(new Event("change", { bubbles: true })); });
      await act(async () => root.querySelector<HTMLButtonElement>(".controls-export button")!.click());
      await vi.waitFor(() => expect(downloads).toHaveLength(index + 1));
    }

    expect(downloads.map(name => name.split(".").at(-1))).toEqual(["md", "txt"]);
    const downloadedText = await Promise.all(blobs.map(blob => blob.text()));
    expect(downloadedText).toHaveLength(2);
    for (const content of downloadedText) {
      // Export files carry the transcript only (Q6): no review notice.
      expect(content).not.toContain("Needs review");
      expect(content).toContain("Speaker TBD");
      expect(content).not.toContain("S00");
    }
  });

  it.each([
    ["absent", undefined, true],
    ["explicit healthy", false, false]
  ] as const)("treats reopened %s review truth without inventing false", async (
    _case,
    needsReview,
    expected
  ) => {
    const saved = meeting({ id: "review-source", needs_review: needsReview });
    sessionNeedsReview.value = true;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/meetings") throw new Error("controlled History failure");
      if (path.endsWith("/summary")) return response({ summary: null });
      if (path === "/api/meetings/review-source") return response(saved);
      throw new Error(`unexpected request: ${path}`);
    }));

    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await act(async () => {
      document.dispatchEvent(new CustomEvent(OPEN_MEETING_EVENT, {
        detail: { meetingId: "review-source" }
      }));
    });
    await vi.waitFor(() => expect(sessionId.value).toBe("review-source"));

    expect(sessionNeedsReview.value).toBe(expected);
  });

  it("renames durably and refresh repairs the selected record to another client's title", async () => {
    const original = meeting({ id: "shared", title: "Original" });
    const renamed = { ...original, title: "Owner title", title_source: "manual" as const };
    const otherClient = { ...renamed, title: "Other client title" };
    const lists = [[original], [otherClient], []];
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/summary")) return response({ summary: null });
      if (url.endsWith("/title") && init?.method === "PUT") return response({ id: "shared", title: "Owner title", title_source: "manual" });
      if (url === "/api/meetings") return response({ meetings: lists.shift() ?? [] });
      return response(original);
    });
    vi.stubGlobal("fetch", fetcher);

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="shared"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="shared"]')?.click());
    act(() => root.querySelector<HTMLButtonElement>('[data-meeting-card="shared"] .history-action-btn')?.click());
    const title = root.querySelector<HTMLInputElement>('[aria-label="Meeting title"]');
    if (!title) throw new Error("missing title field");
    title.value = "  Owner title  ";
    act(() => {
      title.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => root.querySelector<HTMLButtonElement>('button[type="submit"]')?.click());
    await vi.waitFor(() => expect(root.textContent).toContain("Owner title"));
    expect(sessionTitle.value).toBe("Owner title");

    await act(async () => {
      [...root.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent === "Refresh")?.click();
    });
    await vi.waitFor(() => expect(root.textContent).toContain("Other client title"));
    expect(sessionTitle.value).toBe("Other client title");

    await act(async () => {
      [...root.querySelectorAll<HTMLButtonElement>("button")]
        .find((button) => button.textContent === "Refresh")?.click();
    });
    await vi.waitFor(() => expect(root.textContent).toContain("No meetings yet."));
    expect(root.querySelector('[aria-pressed="true"]')).toBeNull();
    expect(sessionTitle.value).toBe("");
  });

  it("keeps the newest overlapping refresh response", async () => {
    const older = deferred<Response>();
    const newest = deferred<Response>();
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ meetings: [meeting({ title: "Initial" })] }))
      .mockReturnValueOnce(older.promise)
      .mockReturnValueOnce(newest.promise);
    vi.stubGlobal("fetch", fetcher);

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.textContent).toContain("Initial"));

    act(() => {
      document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT));
      document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT));
    });
    await act(async () => {
      newest.resolve(response({ meetings: [meeting({ title: "Newest response" })] }));
    });
    await vi.waitFor(() => expect(root.textContent).toContain("Newest response"));
    await act(async () => {
      older.resolve(response({ meetings: [meeting({ title: "Older response" })] }));
    });
    expect(root.textContent).toContain("Newest response");
    expect(root.textContent).not.toContain("Older response");
  });

  it("does not let an Open in flight across correction acknowledgement revert view or export", async () => {
    const staleOpen = deferred<Response>();
    const original = meeting({
      id: "corrected",
      transcript: { segments: [{ id: "seg_0001", start: 0, end: 1,
        speaker: "Alex", speaker_entity_id: "person-a", text: "kept words" }] }
    });
    const corrected = meeting({
      id: "corrected",
      transcript_version: 2,
      transcript: { segments: [{ id: "seg_0001", start: 0, end: 1,
        speaker: "Casey", speaker_entity_id: "person-c", text: "kept words" }] }
    });
    let listCount = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/meetings") {
        listCount += 1;
        return response({ meetings: [listCount === 1 ? original : corrected] });
      }
      if (path === "/api/meetings/corrected") return staleOpen.promise;
      if (path.endsWith("/summary")) return response({ summary: null });
      throw new Error(`unexpected request: ${path}`);
    }));
    const blobs: Blob[] = [];
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn((blob: Blob) => {
        blobs.push(blob);
        return "blob:corrected";
      }),
      revokeObjectURL: vi.fn()
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await act(async () => render(<div><App /><MeetingHistory /></div>, root));
    await vi.waitFor(() =>
      expect(root.querySelector('[data-open-meeting="corrected"]')).not.toBeNull()
    );
    act(() => root.querySelector<HTMLButtonElement>('[data-open-meeting="corrected"]')!.click());
    act(() => {
      sessionId.value = "corrected";
      sessionStatus.value = "closed";
      replaceTranscript([{ segment_id: "seg_0001", start: 0, end: 1, text: "kept words",
        speaker: "person-c", speaker_entity_id: "person-c", display_name: "Casey", state: "final" }]);
      document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT));
    });
    await vi.waitFor(() => expect(listCount).toBe(2));
    await vi.waitFor(() =>
      expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("Casey")
    );

    await act(async () => {
      staleOpen.resolve(response(original));
      await Promise.resolve();
      await Promise.resolve();
      await new Promise(resolve => setTimeout(resolve, 0));
    });
    expect(root.querySelector(".utt-speaker-label")?.textContent).toBe("Casey");
    expect(transcript.value.map(item => item.display_name)).toEqual(["Casey"]);
    act(() => { const select = root.querySelector<HTMLSelectElement>('[aria-label="Export format"]')!;
      select.value = "txt"; select.dispatchEvent(new Event("change", { bubbles: true })); });
    await act(async () => root.querySelector<HTMLButtonElement>(".controls-export button")!.click());
    expect(await blobs[0].text()).toContain("Casey");
    expect(await blobs[0].text()).not.toContain("Alex");
  });

  it("does not let an older in-flight refresh overwrite a successful rename", async () => {
    const stale = deferred<Response>();
    const original = meeting({ id: "shared", title: "Original" });
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ meetings: [original] }))
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(response({ id: "shared", title: "Owner title", title_source: "manual" }));
    vi.stubGlobal("fetch", fetcher);

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.textContent).toContain("Original"));
    act(() => {
      document.dispatchEvent(new Event(MEETING_HISTORY_REFRESH_EVENT));
    });

    const rename = [...root.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "Rename");
    if (!rename) throw new Error("missing Rename button");
    rename.focus();
    act(() => rename.click());
    const title = root.querySelector<HTMLInputElement>('[aria-label="Meeting title"]');
    if (!title) throw new Error("missing title field");
    title.value = "Owner title";
    act(() => {
      title.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => root.querySelector<HTMLButtonElement>('button[type="submit"]')?.click());
    await vi.waitFor(() => expect(root.textContent).toContain("Owner title"));

    await act(async () => {
      stale.resolve(response({ meetings: [original] }));
    });
    expect(root.textContent).toContain("Owner title");
    expect(root.textContent).not.toContain("Original");
    expect(root.textContent).toContain("Refresh");
    expect(root.textContent).not.toContain("Refreshing…");
  });

  it("opens rename as a modal dialog and restores focus after Escape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ meetings: [meeting()] })));

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.textContent).toContain("Meeting A"));
    const rename = [...root.querySelectorAll<HTMLButtonElement>("button")]
      .find((button) => button.textContent === "Rename");
    if (!rename) throw new Error("missing Rename button");
    rename.focus();
    act(() => rename.click());

    const dialog = root.querySelector<HTMLDialogElement>('dialog[role="dialog"]');
    const title = root.querySelector<HTMLInputElement>('[aria-label="Meeting title"]');
    if (!dialog || !title) throw new Error("missing rename dialog");
    expect(dialog.hasAttribute("open")).toBe(true);
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-labelledby")).toBe("rename-meeting-title");
    expect(document.activeElement).toBe(title);

    act(() => {
      dialog.dispatchEvent(new Event("cancel", { cancelable: true }));
    });
    await vi.waitFor(() => expect(root.querySelector("dialog")).toBeNull());
    expect(document.activeElement).toBe(rename);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept) => {
    resolve = accept;
  });
  return { promise, resolve };
}

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as Response;
}
