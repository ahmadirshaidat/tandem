import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AgentSteps } from "@/components/agent";
import { stepLabel, type AgentRun } from "@/lib/agent";

describe("agent read-only trace", () => {
  it("renders actual counts and reveals safe tool statuses without raw arguments", () => {
    const run: AgentRun = {
      id: "r",
      channel_id: "c",
      trigger_message_id: "m",
      status: "completed",
      error_category: null,
      provider: "groq",
      model: "configured-model",
      latency_ms: 24,
      steps: [
        {
          name: "get_channel_context",
          count: 12,
          duration_ms: 3,
          status: "ok",
        },
        {
          name: "search_workspace",
          count: 2,
          duration_ms: 4,
          status: "denied",
        },
      ],
    };
    const { container } = render(<AgentSteps run={run} />);
    const summary = screen.getByText(
      /Read 12 messages.*Searched workspace.*Drafted an answer/,
    );
    fireEvent.click(summary);
    expect(container.querySelector("details")).toHaveAttribute("open");
    expect(screen.getByText("Unavailable")).toBeVisible();
    expect(screen.getByText("3 ms")).toBeVisible();
    expect(container.textContent).not.toMatch(/arguments|proposal/i);
    expect(stepLabel("list_tasks", 2)).toBe("list tasks");
  });
  it("has no fabricated steps when no tools ran", () => {
    const { container } = render(
      <AgentSteps
        run={{
          id: "r",
          channel_id: "c",
          trigger_message_id: "m",
          status: "blocked",
          error_category: "agent_off",
          provider: null,
          model: null,
          latency_ms: null,
          steps: [],
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
