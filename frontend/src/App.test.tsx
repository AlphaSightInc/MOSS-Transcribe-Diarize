// @vitest-environment jsdom

import { render } from "preact";
import { afterEach, describe, expect, it } from "vitest";
import { resetSessionState, sessionTitle, sessionMode } from "./state/session";
import { App } from "./App";

describe("Account application shell", () => {
  afterEach(() => { document.body.replaceChildren(); resetSessionState(); sessionTitle.value = ""; });

  it("uses MOSS until a meeting is selected and shows its actual mode", () => {
    const root = document.createElement("div");
    document.body.append(root);
    render(<App />, root);
    expect(root.querySelector(".session-title")?.textContent).toBe("MOSS");
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
    expect(root.querySelector('[aria-label="Listening setup"]')).not.toBeNull();
    expect(root.textContent).toContain("Enable microphone");
    expect(root.querySelector('[role="tab"]')).toBeNull();
    expect(root.querySelector('input[type="password"]')).toBeNull();
    expect(root.querySelector('input[type="file"]')).toBeNull();
    expect(root.querySelector('.history-panel')).toBeNull();
    expect(root.querySelector('[aria-label="Private voiceprints"]')).toBeNull();
  });
});
