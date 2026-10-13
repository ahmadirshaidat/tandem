import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthPage } from "@/components/auth-page";
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(),
}));
function open(mode: "login" | "signup" | "forgot-password") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AuthPage mode={mode} />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  replace.mockClear();
  document.cookie = "tandem_csrf=test";
});
describe("connected authentication screens", () => {
  it("submits a registration to the real API contract and enters the workspace", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ id: "1", name: "Alex", email: "alex@example.com" }),
          { status: 201 },
        ),
      );
    vi.stubGlobal("fetch", fetcher);
    open("signup");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Your name"), "Alex");
    await user.type(screen.getByLabelText("Email address"), "alex@example.com");
    await user.type(screen.getByLabelText("Password"), "a-long-password");
    await user.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      email: "alex@example.com",
      name: "Alex",
      password: "a-long-password",
    });
  });
  it("shows login failures and keeps the user on the login page", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              error: { message: "Email or password is incorrect" },
            }),
            { status: 401 },
          ),
        ),
    );
    open("login");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email address"), "alex@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email or password is incorrect",
    );
    expect(replace).not.toHaveBeenCalled();
  });
  it("shows the non-disclosing password-reset acknowledgement", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({
              message:
                "If an account exists, a password reset link has been sent.",
            }),
          ),
        ),
    );
    open("forgot-password");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email address"), "alex@example.com");
    await user.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "If an account exists",
    );
    expect(
      screen.getByRole("link", { name: /Back to log in/ }),
    ).toHaveAttribute("href", "/login");
  });
});
