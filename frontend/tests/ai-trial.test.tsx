import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { AITrialPage } from "@/components/ai-trial";
import type { Workspace } from "@/lib/api";

const workspace: Workspace = {
  id: "workspace",
  name: "North",
  role: "owner",
  created_at: "2026-10-13",
};
const providers = {
  primary: "groq",
  providers: [{ id: "groq", configured: true, model: "trial-model" }],
  requests_per_minute: 5,
  max_output_tokens: 512,
};
function open(value = workspace) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AITrialPage workspace={value} />
    </QueryClientProvider>,
  );
}
describe("AI trial screen", () => {
  it("protects the trial page for viewers without requesting provider settings", () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    open({ ...workspace, role: "viewer" });
    expect(
      screen.getByRole("heading", {
        name: "An Admin or Owner can run trials.",
      }),
    ).toBeVisible();
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("sends a question to the scoped API and renders AI content as plain text", async () => {
    document.cookie = "tandem_csrf=test";
    const fetcher = vi
      .fn()
      .mockImplementation((path: string, options?: RequestInit) => {
        if (path.endsWith("providers"))
          return Promise.resolve(new Response(JSON.stringify(providers)));
        if (options?.method === "POST")
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "trial",
                provider: "groq",
                model: "trial-model",
                answer: "<script>unsafe()</script>",
                attempts: [{ provider: "groq", status: "completed" }],
              }),
            ),
          );
        return Promise.resolve(new Response("[]"));
      });
    vi.stubGlobal("fetch", fetcher);
    open();
    const user = userEvent.setup();
    await screen.findByText("Key configured");
    await user.type(
      screen.getByLabelText("Your test question"),
      "Test question",
    );
    await user.click(
      screen.getByRole("button", { name: "Send test question" }),
    );
    expect(await screen.findByText("<script>unsafe()</script>")).toBeVisible();
    expect(document.querySelector(".ai-answer script")).toBeNull();
    const request = fetcher.mock.calls.find(
      ([, options]) => options?.method === "POST",
    );
    expect(request?.[0]).toBe("/api/workspaces/workspace/ai/trials");
    expect(JSON.parse(request?.[1].body)).toEqual({
      provider: "auto",
      prompt: "Test question",
    });
  });
  it("shows server failure and does not invent an AI answer", async () => {
    document.cookie = "tandem_csrf=test";
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((path: string, options?: RequestInit) =>
          Promise.resolve(
            options?.method === "POST"
              ? new Response(
                  JSON.stringify({
                    error: { message: "No configured provider answered." },
                  }),
                  { status: 503 },
                )
              : new Response(
                  path.endsWith("providers") ? JSON.stringify(providers) : "[]",
                ),
          ),
        ),
    );
    open();
    const user = userEvent.setup();
    await screen.findByText("Key configured");
    await user.type(screen.getByLabelText("Your test question"), "Question");
    await user.click(
      screen.getByRole("button", { name: "Send test question" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "No configured provider answered.",
      ),
    );
    expect(screen.queryByText("Your teammate’s reply")).not.toBeInTheDocument();
  });
  it("disables sending when no provider key is configured", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation((path: string) =>
          Promise.resolve(
            new Response(
              path.endsWith("providers")
                ? JSON.stringify({
                    ...providers,
                    providers: [
                      { id: "groq", configured: false, model: "trial-model" },
                    ],
                  })
                : "[]",
            ),
          ),
        ),
    );
    open();
    await screen.findByText("Not configured");
    await userEvent
      .setup()
      .type(screen.getByLabelText("Your test question"), "Question");
    expect(
      screen.getByRole("button", { name: "Send test question" }),
    ).toBeDisabled();
  });
});
