import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { HighlightedSnippet } from "@/components/memory";

describe("safe memory snippets", () => {
  it("renders markup as text and highlights without injecting HTML", () => {
    const { container } = render(
      <HighlightedSnippet
        item={{
          snippet: "<script>alert(1)</script> timeout",
          highlights: [{ start: 26, end: 33 }],
        }}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>");
  });
  it("uses Unicode codepoint offsets for Arabic after an emoji", () => {
    const { container } = render(
      <HighlightedSnippet
        item={{ snippet: "🐛 مشكلة اتصال", highlights: [{ start: 2, end: 7 }] }}
      />,
    );
    expect(container.querySelector("mark")?.textContent).toBe("مشكلة");
    expect(container.querySelector("p")).toHaveAttribute("dir", "auto");
  });
  it("ignores overlapping or out-of-range highlight spans", () => {
    const { container } = render(
      <HighlightedSnippet
        item={{
          snippet: "safe text",
          highlights: [
            { start: 0, end: 4 },
            { start: 1, end: 8 },
            { start: 30, end: 50 },
          ],
        }}
      />,
    );
    expect(container.querySelectorAll("mark")).toHaveLength(1);
    expect(container.textContent).toBe("safe text");
  });
});
