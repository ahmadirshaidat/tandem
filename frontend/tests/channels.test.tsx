import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { SafeMarkdown } from "@/components/safe-markdown";
import { mergeMessages, type Message } from "@/lib/channels";
import { cached, saveCache, clearChatCache } from "@/lib/offline";

const message = (overrides: Partial<Message> = {}): Message => ({
  id: "a",
  channel_id: "c",
  workspace_id: "w",
  author: { id: "u", name: "User" },
  body: "Hello",
  seq: 1,
  client_message_id: "retry",
  thread_root_id: null,
  attachments: [],
  mentions: [],
  mentions_agent: false,
  created_at: "2026-10-14T00:00:00Z",
  edited_at: null,
  deleted_at: null,
  reply_count: 0,
  ...overrides,
});
describe("safe message rendering", () => {
  it("renders script and HTML as text, preserves safe formatting and rejects unsafe links", () => {
    const { container } = render(
      <SafeMarkdown
        body={
          "<script>alert(1)</script> <img src=x onerror=alert(1)> **bold** *italic* `code` [unsafe](javascript:alert) [safe](https://example.com)\n```js\n<script>code only</script>\n```"
        }
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelectorAll("a")).toHaveLength(1);
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("em")).toHaveTextContent("italic");
    expect(screen.getByRole("link", { name: "safe" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(container).toHaveTextContent("<script>alert(1)</script>");
    expect(container.querySelector("pre")).toHaveTextContent(
      "<script>code only</script>",
    );
  });
});
describe("live acknowledgement and retry", () => {
  it("replaces an optimistic message with one server acknowledgement and applies edits without duplicates", () => {
    const pending = message({ id: "temp", pending: "sending", seq: 10000 });
    const actual = message({ id: "saved", seq: 4 });
    const ack = mergeMessages([pending], [actual, actual]);
    expect(ack).toHaveLength(1);
    expect(ack[0].pending).toBeUndefined();
    const updated = mergeMessages(ack, [
      message({ id: "saved", seq: 4, body: "edited", edited_at: "later" }),
    ]);
    expect(updated).toHaveLength(1);
    expect(updated[0].body).toBe("edited");
  });
  it("preserves a newer edit against a delayed create acknowledgement", () => {
    const newer = message({
      body: "edited",
      edited_at: "2026-10-14T01:00:00Z",
    });
    expect(mergeMessages([newer], [message()])[0].body).toBe("edited");
  });
  it("does not collapse another author's client ID and sorts by creation sequence", () => {
    const rows = mergeMessages(
      [message({ seq: 3 })],
      [
        message({
          id: "other",
          author: { id: "another", name: "Another" },
          seq: 2,
        }),
      ],
    );
    expect(rows.map((m) => m.id)).toEqual(["other", "a"]);
  });
});
describe("offline cache boundaries", () => {
  beforeEach(() => localStorage.clear());
  it("retains drafts and recent data with last-sync time, and clears only this application's cache", () => {
    localStorage.setItem("unrelated-app", "keep");
    saveCache("draft:u:c", "unsent");
    saveCache("history:u:c", [message()], "2026-10-14");
    expect(cached<string>("draft:u:c")?.value).toBe("unsent");
    expect(cached<Message[]>("history:u:c")?.syncedAt).toBe("2026-10-14");
    clearChatCache();
    expect(cached("draft:u:c")).toBeUndefined();
    expect(localStorage.getItem("unrelated-app")).toBe("keep");
  });
  it("tolerates corrupted local data", () => {
    localStorage.setItem("tandem-chat:bad", "invalid JSON");
    expect(cached("bad")).toBeUndefined();
  });
});

it("preserves a newer edit against a delayed create acknowledgement", () => {
  const newer = message({ body: "edited", edited_at: "2026-10-14T01:00:00Z" });
  expect(mergeMessages([newer], [message()])[0].body).toBe("edited");
});
