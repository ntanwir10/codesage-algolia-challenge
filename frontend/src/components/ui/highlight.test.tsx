import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Highlight } from "./highlight";

const marked = (text: string, query: string) => {
  const { container } = render(<Highlight text={text} query={query} />);
  return { marks: [...container.querySelectorAll("mark")].map((m) => m.textContent), html: container.innerHTML };
};

describe("Highlight", () => {
  it("marks every query word, ignoring case, longest first", () => {
    expect(marked("createStore calls create", "create createstore").marks).toEqual([
      "createStore",
      "create",
    ]);
  });

  it("renders code as text, so markup in a snippet can't run", () => {
    const { marks, html } = marked('<img src=x onerror="alert(1)"> onerror', "onerror");
    expect(marks).toEqual(["onerror", "onerror"]);
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("matches regex characters literally, and ignores a query without words", () => {
    expect(marked("price $x.y and axzy", "$x").marks).toEqual(["$x"]);
    expect(marked("a.b(c)", "% (").marks).toEqual([]);
  });
});
