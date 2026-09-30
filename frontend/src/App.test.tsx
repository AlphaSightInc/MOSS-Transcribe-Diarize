// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  resetSessionState, sessionId, sessionMode, sessionStartedAt, sessionStatus, sessionStatusLine, sessionTitle
} from "./state/session";
import { App, formatElapsed } from "./App";

describe("Account application shell", () => {
  afterEach(() => {
    act(() => render(null, document.body));
    document.body.replaceChildren(); resetSessionState(); sessionTitle.value = ""; sessionStartedAt.value = null;
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
    expect(root.querySelector('[aria-label="Listening with"]')).not.toBeNull();
    expect(root.textContent).toContain("Enable microphone");
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

  it("formats elapsed time as m:ss, then h:mm:ss", () => {
    expect(formatElapsed(5_000)).toBe("0:05");
    expect(formatElapsed(754_000)).toBe("12:34");
    expect(formatElapsed(3_723_000)).toBe("1:02:03");
    expect(formatElapsed(-1)).toBe("0:00");
  });
});
