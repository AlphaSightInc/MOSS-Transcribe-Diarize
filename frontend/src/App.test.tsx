// @vitest-environment jsdom

import { render } from "preact";
import { act } from "preact/test-utils";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";

describe("App shell", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders the phase-one shell with an inert collapsed rail", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    expect(root.querySelector("#transcript-panel")).not.toBeNull();
    expect(root.querySelector(".main")?.getAttribute("data-right-collapsed")).toBe("true");
    expect(root.querySelector(".history-panel .panel-body")).toBeNull();
    expect(root.querySelectorAll("[data-transcript-segment]")).toHaveLength(0);
    expect(root.querySelector('a[href="/live"]')).toBeNull();
  });

  it("keeps only Live and File modes, and the File tab exposes browser file selection", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    const modeTabs = root.querySelectorAll('[role="tab"]');
    expect([...modeTabs].map((tab) => tab.textContent)).toEqual(["Live", "File"]);
    expect(root.textContent).not.toContain("URL");
    expect(root.textContent).not.toContain("Batch");

    const fileTab = [...modeTabs].find((tab) => tab.textContent === "File");
    if (!fileTab) {
      throw new Error("Missing File mode tab");
    }
    act(() => {
      (fileTab as HTMLButtonElement).click();
    });

    expect(root.querySelector('[data-mode="file"]')).not.toBeNull();
    expect(root.querySelector('input[type="file"]')).not.toBeNull();
  });
});
