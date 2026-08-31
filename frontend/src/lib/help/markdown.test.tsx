// Markdown renderer locks (HELP CENTER ARC): the block parser understands the
// constructs the guides and notes use; inline links route help:/cmd: targets
// to the handler and open http links in a new tab; nothing is injected as
// HTML (React escapes everything).
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Markdown, headingSlug, parseBlocks } from "./markdown";

const SRC = [
  "# Title",
  "",
  "Intro with **bold**, *em*, `code`, $w(k,T)$ and a [guide](help:guides:graph).",
  "",
  "## Section",
  "- one",
  "- two",
  "  - nested",
  "1. first",
  "2. second",
  "",
  "> a quote",
  "",
  "| a | b |",
  "|---|---|",
  "| 1 | 2 |",
  "",
  "```py",
  "x = 1",
  "```",
  "---",
  "Run [Calibrate](cmd:calibrate.both) or read <https://example.com>.",
].join("\n");

describe("parseBlocks", () => {
  it("splits headings, paragraphs, lists, quotes, tables, code and rules", () => {
    const types = parseBlocks(SRC).map((b) => b.t);
    expect(types).toEqual(["h", "p", "h", "ul", "ol", "quote", "table", "code", "hr", "p"]);
    const ul = parseBlocks(SRC).find((b) => b.t === "ul") as { items: string[][] };
    expect(ul.items).toEqual([["one"], ["two", "  nested"]]);
    const table = parseBlocks(SRC).find((b) => b.t === "table") as { header: string[]; rows: string[][] };
    expect(table.header).toEqual(["a", "b"]);
    expect(table.rows).toEqual([["1", "2"]]);
  });

  it("joins wrapped paragraph lines and tolerates CRLF", () => {
    const [p] = parseBlocks("line one\r\nline two\r\n\r\nnext");
    expect(p).toEqual({ t: "p", text: "line one line two" });
  });

  it("slugs headings", () => {
    expect(headingSlug("What it is")).toBe("what-it-is");
    expect(headingSlug("Related `settings` & links")).toBe("related-settings-links");
  });
});

describe("<Markdown>", () => {
  it("renders inline marks and routes internal links through the handler", () => {
    const onLink = vi.fn(() => true);
    render(<Markdown source={SRC} handlers={{ onLink }} />);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("code").tagName).toBe("CODE");
    screen.getByRole("button", { name: "guide" }).click();
    expect(onLink).toHaveBeenCalledWith("help:guides:graph");
    screen.getByRole("button", { name: "▶ Calibrate" }).click();
    expect(onLink).toHaveBeenCalledWith("cmd:calibrate.both");
    expect(screen.getByRole("heading", { level: 2, name: "Section" }).id).toBe("section");
    expect(screen.getByText("x = 1").closest("pre")).not.toBeNull();
  });

  it("opens ordinary links in a new tab and never injects HTML", () => {
    render(<Markdown source={"See [docs](https://example.com/x) and <b>raw</b>."} />);
    const a = screen.getByRole("link", { name: "docs" });
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("rel")).toContain("noopener");
    expect(screen.getByText(/<b>raw<\/b>/)).not.toBeNull();
  });
});
