export type User = { id: string; name: string; email: string };
export type Role = "owner" | "admin" | "editor" | "viewer";
export type Workspace = {
  id: string;
  name: string;
  role: Role;
  created_at: string;
};
export type Member = {
  id: string;
  user_id: string;
  name: string;
  email: string;
  role: Role;
};
export type Invitation = {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  status: string;
  invite_url?: string;
};
export type InvitePreview = {
  workspace_id: string;
  workspace_name: string;
  email: string;
  role: Role;
};
export const roleLabels: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  editor: "Editor / Developer",
  viewer: "Viewer",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public details?: { field: string; message: string }[],
  ) {
    super(message);
  }
}
let refreshPromise: Promise<void> | null = null;
function csrfCookie() {
  return (
    document.cookie
      .split("; ")
      .find((item) => item.startsWith("tandem_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") ?? ""
  );
}
async function csrfToken() {
  const existing = csrfCookie();
  if (existing) return existing;
  const response = await fetch("/api/auth/csrf", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok)
    throw new ApiError(response.status, "Unable to connect. Please try again.");
  return (await response.json()).csrf_token as string;
}
async function request<T>(path: string, options: RequestInit): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.method && !["GET", "HEAD"].includes(options.method))
    headers.set("X-CSRF-Token", await csrfToken());
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "Unable to connect. Check your connection and try again.",
    );
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      response.status,
      body?.error?.message ?? "Something went wrong. Please try again.",
      body?.error?.details,
    );
  return body as T;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  try {
    return await request<T>(path, options);
  } catch (error) {
    if (
      !(error instanceof ApiError) ||
      error.status !== 401 ||
      (path.startsWith("/auth/") && path !== "/auth/me")
    )
      throw error;
    if (!refreshPromise)
      refreshPromise = request<void>("/auth/refresh", {
        method: "POST",
      }).finally(() => {
        refreshPromise = null;
      });
    await refreshPromise;
    return request<T>(path, options);
  }
}
export const post = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});
