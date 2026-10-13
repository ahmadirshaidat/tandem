import { describe, expect, it, vi } from "vitest";
import { api, ApiError, post } from "@/lib/api";
import { safeNext } from "@/lib/utils";
describe("API client", () => {
  it("uses cookie credentials and a CSRF header for mutations", async () => {
    document.cookie = "tandem_csrf=csrf-test";
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: "workspace" }), { status: 201 }),
      );
    vi.stubGlobal("fetch", fetcher);
    await expect(api("/workspaces", post({ name: "North" }))).resolves.toEqual({
      id: "workspace",
    });
    const [path, options] = fetcher.mock.calls[0];
    expect(path).toBe("/api/workspaces");
    expect(options.credentials).toBe("same-origin");
    expect(options.headers.get("X-CSRF-Token")).toBe("csrf-test");
  });
  it("refreshes an expired session once before retrying the request", async () => {
    document.cookie = "tandem_csrf=csrf-test";
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ error: { message: "Expired" } }), {
          status: 401,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ message: "Refreshed" })),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify([{ id: "workspace" }])),
      );
    vi.stubGlobal("fetch", fetcher);
    await expect(api("/workspaces")).resolves.toEqual([{ id: "workspace" }]);
    expect(fetcher.mock.calls.map(([path]) => path)).toEqual([
      "/api/workspaces",
      "/api/auth/refresh",
      "/api/workspaces",
    ]);
  });
  it("returns useful server errors without retrying a failed login", async () => {
    document.cookie = "tandem_csrf=csrf-test";
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { message: "Email or password is incorrect" },
          }),
          { status: 401 },
        ),
      );
    vi.stubGlobal("fetch", fetcher);
    await expect(
      api("/auth/login", post({ email: "a@example.com", password: "wrong" })),
    ).rejects.toThrow("Email or password is incorrect");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("handles network errors and empty successful responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await expect(api("/workspaces")).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    await expect(api("/workspaces/a/members/b")).resolves.toBeUndefined();
  });
});
describe("post-login redirects", () => {
  it.each([
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "javascript:alert(1)",
    null,
  ])("rejects external redirects: %s", (value) => {
    expect(safeNext(value)).toBe("/");
  });
  it("preserves invitation tokens on safe internal paths", () => {
    expect(safeNext("/accept-invitation?token=abc")).toBe(
      "/accept-invitation?token=abc",
    );
  });
});
