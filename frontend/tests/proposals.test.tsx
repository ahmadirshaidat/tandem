import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { canApprove, mergeProposals, type Proposal } from "@/lib/proposals";
import { SafeMarkdown } from "@/components/safe-markdown";

const proposal = (version: number, status: string): Proposal => ({
  id: "p",
  workspace_id: "w",
  run_id: "r",
  channel_id: "c",
  trigger_message_id: "m",
  kind: "create_tasks",
  risk: "low",
  status,
  payload: { items: [] },
  payload_hash: "a".repeat(64),
  sources: [],
  requested_by: { id: "u", name: "مستخدم" },
  decided_by: null,
  decided_at: null,
  decision_reason: null,
  execution_result: null,
  expires_at: "2026-10-22",
  created_at: "2026-10-15",
  version,
  required_role: "editor",
});
describe("human approval boundaries", () => {
  it("keeps Viewers read-only and high risk restricted to Admin/Owner", () => {
    expect(canApprove("viewer", "editor")).toBe(false);
    expect(canApprove("editor", "editor")).toBe(true);
    expect(canApprove("editor", "admin")).toBe(false);
    expect(canApprove("admin", "admin")).toBe(true);
    expect(canApprove("owner", "admin")).toBe(true);
  });
  it("deduplicates replay and never regresses completed cards to an older proposed snapshot", () => {
    const result = mergeProposals(
      [proposal(3, "completed")],
      [
        proposal(1, "proposed"),
        proposal(2, "approved"),
        proposal(3, "completed"),
      ],
    );
    expect(result).toHaveLength(1);
    expect(result[0].status).toBe("completed");
  });
  it("isolates Arabic and mixed user text with automatic direction and safe markup", () => {
    const { container } = render(
      <SafeMarkdown body="خطة JWT جديدة **للمصادقة** <script>delete()</script>" />,
    );
    expect(container.querySelector(".message-body")).toHaveAttribute(
      "dir",
      "auto",
    );
    expect(screen.getByText("للمصادقة")).toBeVisible();
    expect(container.querySelector("script")).toBeNull();
  });
});
