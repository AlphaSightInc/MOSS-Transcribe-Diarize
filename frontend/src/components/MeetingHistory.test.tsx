// @vitest-environment jsdom
import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Meeting } from "../api/meetings";
import { LIVE_MEETING_OBSERVE_EVENT } from "../lib/meetingEvents";
import { resetSessionState, sessionTitle, transcript } from "../state/session";
import { MeetingHistory } from "./MeetingHistory";

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
    vi.restoreAllMocks();
  });

  afterEach(() => {
    act(() => render(null, root));
    root.remove();
    resetSessionState();
    vi.unstubAllGlobals();
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

  it("renames durably and refresh repairs the selected record to another client's title", async () => {
    const original = meeting({ id: "shared", title: "Original" });
    const renamed = { ...original, title: "Owner title", title_source: "manual" as const };
    const otherClient = { ...renamed, title: "Other client title" };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response({ meetings: [original] }))
      .mockResolvedValueOnce(response(original))
      .mockResolvedValueOnce(response({ id: "shared", title: "Owner title", title_source: "manual" }))
      .mockResolvedValueOnce(response({ meetings: [otherClient] }))
      .mockResolvedValueOnce(response({ meetings: [] }));
    vi.stubGlobal("fetch", fetcher);

    await act(async () => {
      render(<MeetingHistory />, root);
    });
    await vi.waitFor(() => expect(root.querySelector('[data-open-meeting="shared"]')).not.toBeNull());
    await act(async () => root.querySelector<HTMLButtonElement>('[data-open-meeting="shared"]')?.click());
    act(() => root.querySelector<HTMLButtonElement>(".history-action-btn")?.click());
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
});

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as Response;
}
