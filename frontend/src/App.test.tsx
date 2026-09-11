// @vitest-environment jsdom

import { render } from "preact";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";

describe("Account application shell", () => {
  afterEach(() => document.body.replaceChildren());

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
