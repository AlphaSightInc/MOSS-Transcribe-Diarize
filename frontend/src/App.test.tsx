// @vitest-environment jsdom

import { render } from "preact";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App";

describe("App shell", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders the reference shell without transcript data or operator routes", () => {
    const root = document.createElement("div");
    document.body.append(root);

    render(<App />, root);

    expect(root.querySelector("#transcript-panel")).not.toBeNull();
    expect(root.querySelectorAll("[data-transcript-segment]")).toHaveLength(0);
    expect(root.querySelector('a[href="/live"]')).toBeNull();
  });
});
