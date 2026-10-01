// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  resetSessionState, sessionId, sessionMode, sessionStartedAt, sessionStarting, sessionStatus, sessionStatusLine,
  sessionStopRequested, sessionTitle
} from "./state/session";
import { dispatchWsEvent } from "./api/ws";
import { App, formatElapsed } from "./App";

describe("Account application shell", () => {
  afterEach(() => {
    act(() => render(null, document.body));
    document.body.replaceChildren(); resetSessionState(); sessionTitle.value = ""; sessionStartedAt.value = null;
    sessionStopRequested.value = null;
    vi.useRealTimers();
  });

  it("uses the product name until a meeting is selected and shows its actual mode", () => {
    const root = document.createElement("div");
    document.body.append(root);
    render(<App />, root);
    expect(root.querySelector(".session-title")?.textContent).toBe("aiSight - LiveTranscribe");
    expect(root.textContent).not.toContain("MOSS");
    sessionTitle.value = "Customer review";
    sessionMode.value = "file";
    render(<App />, root);
    expect(root.querySelector(".session-title")?.textContent).toBe("Customer review");
    expect(root.querySelector(".session-chip")?.textContent).toBe("File / URL");
  });

  it("renders one Account Live surface without a second authority or File job UI", () => {
    const root = document.createElement("div");
    document.body.append(root);
    render(<App />, root);

    expect(root.querySelector('[data-authority="account"]')).not.toBeNull();
    expect(root.querySelector("#transcript-panel")).not.toBeNull();
    // Live is the mode on load: the two source boxes and one Start button (round 5).
    expect(root.querySelector('.mode-tabs [aria-pressed="true"]')?.textContent).toBe("Live");
    expect([...root.querySelectorAll(".capture-sources label.check-row")].map(row =>
      [row.textContent, row.querySelector("input")?.checked])).toEqual([["System sound", true], ["Microphone", true]]);
    expect(root.querySelector<HTMLButtonElement>('.record-btn[data-action="start"]')?.textContent).toBe("Start recording");
    expect(root.querySelector('[aria-label="Listening with"]')).toBeNull();
    expect(root.querySelectorAll('[aria-label="Meeting views"] [role="tab"]')).toHaveLength(2);
    expect(root.querySelector('input[type="password"]')).toBeNull();
    expect(root.querySelector('input[type="file"]')).toBeNull();
    expect(root.querySelector('.history-panel')).toBeNull();
    expect(root.querySelector('[aria-label="Voiceprints"]')).toBeNull();
  });

  it("keeps the pill to lifecycle: Standby, Recording mm:ss, Stopping, Processing", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(100_000));
    const root = document.createElement("div");
    document.body.append(root);
    act(() => render(<App />, root));
    const pill = () => root.querySelector(".top-status");
    expect(pill()?.textContent).toBe("Standby");
    expect(pill()?.getAttribute("data-state")).toBe("idle");

    act(() => {
      sessionId.value = "live-1";
      sessionMode.value = "live";
      sessionStartedAt.value = { sessionId: "live-1", ms: 100_000 - 754_000 };
      sessionStatus.value = "active";
      // A backend capture line never lands in the pill.
      sessionStatusLine.value = "Microphone too loud — lower it.";
    });
    expect(pill()?.textContent).toBe("Recording 12:34");
    expect(pill()?.getAttribute("data-state")).toBe("recording");
    act(() => { vi.advanceTimersByTime(2000); });
    expect(pill()?.textContent).toBe("Recording 12:36");

    act(() => { sessionStatus.value = "closing"; });
    expect(pill()?.textContent).toBe("Stopping");
    act(() => { sessionStatus.value = "closed"; });
    expect(pill()?.textContent).toBe("Standby");

    act(() => { sessionId.value = "file-1"; sessionMode.value = "file"; sessionStatus.value = "active"; });
    expect(pill()?.textContent).toBe("Processing");
  });

  // r4 F3: the pill read "Standby" for 2–3 s after Start while the button already read "Stop recording".
  it("reads Starting… from the Start click until the meeting exists, then counts from its true start", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(100_000));
    const root = document.createElement("div");
    document.body.append(root);
    act(() => render(<App />, root));
    const pill = () => root.querySelector(".top-status");
    act(() => { sessionStarting.value = true; });
    expect(pill()?.textContent).toBe("Starting…");
    expect(pill()?.getAttribute("data-state")).toBe("starting");
    act(() => { vi.advanceTimersByTime(2500); });
    expect(pill()?.textContent).toBe("Starting…");

    // Create succeeded: the page publishes the active meeting and its start in the same step.
    act(() => {
      sessionStartedAt.value = { sessionId: "live-1", ms: Date.now() };
      dispatchWsEvent({ type: "session_state", session_id: "live-1", mode: "live", state: "active", status: "active" });
      sessionStarting.value = false;
    });
    expect(pill()?.textContent).toBe("Recording 0:00");
    expect(pill()?.getAttribute("data-state")).toBe("recording");
    act(() => { vi.advanceTimersByTime(3000); });
    expect(pill()?.textContent).toBe("Recording 0:03");
  });

  it("goes back to Standby when Start fails", () => {
    vi.useFakeTimers();
    const root = document.createElement("div");
    document.body.append(root);
    act(() => render(<App />, root));
    act(() => { sessionStarting.value = true; });
    expect(root.querySelector(".top-status")?.textContent).toBe("Starting…");
    act(() => { vi.advanceTimersByTime(1500); sessionStarting.value = false; });
    expect(root.querySelector(".top-status")?.textContent).toBe("Standby");
    expect(root.querySelector(".top-status")?.getAttribute("data-state")).toBe("idle");
  });

  // #14: the server keeps a draining meeting "active" after Stop, so lifecycle alone never reached "Stopping".
  it("stops the clock at Stop although the server still reports the draining meeting active", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(100_000));
    const root = document.createElement("div");
    document.body.append(root);
    act(() => render(<App />, root));
    const pill = () => root.querySelector(".top-status");
    const serverSays = (status: "active" | "closed") => dispatchWsEvent({
      type: "session_state", session_id: "live-1", mode: "live", state: status, status
    });
    act(() => {
      sessionStartedAt.value = { sessionId: "live-1", ms: 100_000 - 60_000 };
      serverSays("active");
    });
    act(() => { vi.advanceTimersByTime(5000); });
    expect(pill()?.textContent).toBe("Recording 1:05");

    act(() => { sessionStopRequested.value = "live-1"; });
    expect(pill()?.textContent).toBe("Stopping");
    expect(pill()?.getAttribute("data-state")).toBe("processing");
    // The tail drain takes seconds to minutes; polls and History refreshes keep saying "active".
    act(() => { vi.advanceTimersByTime(30_000); serverSays("active"); });
    expect(pill()?.textContent).toBe("Stopping");

    act(() => { serverSays("closed"); vi.advanceTimersByTime(5000); });
    expect(pill()?.textContent).toBe("Standby");

    // A new meeting's clock is unaffected by the previous meeting's Stop.
    act(() => {
      sessionStartedAt.value = { sessionId: "live-2", ms: Date.now() };
      dispatchWsEvent({ type: "session_state", session_id: "live-2", mode: "live", state: "active", status: "active" });
    });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(pill()?.textContent).toBe("Recording 0:03");
  });

  it("learns about a Stop from the server's stop_requested event (observers, reloads)", () => {
    const root = document.createElement("div");
    document.body.append(root);
    act(() => render(<App />, root));
    act(() => {
      sessionStartedAt.value = { sessionId: "watched", ms: Date.now() - 90_000 };
      dispatchWsEvent({ type: "session_state", session_id: "watched", mode: "live", state: "active", status: "active" });
    });
    expect(root.querySelector(".top-status")?.textContent).toMatch(/^Recording 1:3\d$/);
    act(() => dispatchWsEvent({ type: "stop_progress", session_id: "watched", stop_phase: "stop_requested", llm_state: null }));
    expect(root.querySelector(".top-status")?.textContent).toBe("Stopping");
  });

  it("shows no time rather than a wrong one until a reattached meeting's start is known", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(5_000_000));
    const root = document.createElement("div");
    document.body.append(root);
    act(() => render(<App />, root));
    act(() => { sessionId.value = "reloaded"; sessionMode.value = "live"; sessionStatus.value = "active"; });
    act(() => { vi.advanceTimersByTime(3000); });
    expect(root.querySelector(".top-status")?.textContent).toBe("Recording");
    act(() => { sessionStartedAt.value = { sessionId: "reloaded", ms: Date.now() - 1_800_000 }; });
    expect(root.querySelector(".top-status")?.textContent).toBe("Recording 30:00");
  });

  it("formats elapsed time as m:ss, then h:mm:ss", () => {
    expect(formatElapsed(5_000)).toBe("0:05");
    expect(formatElapsed(754_000)).toBe("12:34");
    expect(formatElapsed(3_723_000)).toBe("1:02:03");
    expect(formatElapsed(-1)).toBe("0:00");
  });
});
