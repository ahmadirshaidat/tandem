import { expect, test, type BrowserContext } from "@playwright/test";

async function write(
  context: BrowserContext,
  path: string,
  data: unknown,
  method = "POST",
) {
  const csrf = await context.request.get("/api/auth/csrf");
  const response = await context.request.fetch(`/api${path}`, {
    method,
    data,
    headers: { "X-CSRF-Token": (await csrf.json()).csrf_token },
  });
  expect(response.ok(), `${method} ${path}: ${response.status()}`).toBeTruthy();
  return response.status() === 204 ? null : response.json();
}

test("memory settings, bilingual search, private isolation, sources, forgetting and 390px offline", async ({
  browser,
}, testInfo) => {
  test.setTimeout(180000);
  const owner = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const viewer = await browser.newContext();
  const stamp = Date.now();
  await write(owner, "/auth/register", {
    name: "Memory owner",
    email: `memory-owner-${stamp}@example.com`,
    password: "synthetic-memory-password-123",
  });
  const user = await write(viewer, "/auth/register", {
    name: "Memory viewer",
    email: `memory-viewer-${stamp}@example.com`,
    password: "synthetic-memory-password-123",
  });
  const workspace = await write(owner, "/workspaces", {
    name: "Memory Laboratory",
  });
  const wid = workspace.id;
  const invitation = await write(owner, `/workspaces/${wid}/invitations`, {
    email: user.email,
    role: "viewer",
  });
  await write(
    viewer,
    `/invitations/${new URL(invitation.invite_url).searchParams.get("token")}/accept`,
    {},
  );
  const project = await write(owner, `/workspaces/${wid}/projects`, {
    name: "Platform",
    key: "MEM",
  });
  const bug = await write(owner, `/workspaces/${wid}/tasks`, {
    project_id: project.id,
    title: "Refresh token retry loop",
    type: "bug",
    description:
      "Resolved authentication failure by stopping retries of revoked tokens.",
    status: "done",
  });
  await write(owner, `/workspaces/${wid}/tasks`, {
    project_id: project.id,
    title: "إصلاح رمز الدخول المنتهي",
    type: "bug",
    description:
      "تم إصلاح مشكلة تجديد رمز الدخول بإيقاف إعادة المحاولة بعد إلغاء الجلسة.",
    status: "done",
  });
  const channels = await (
    await owner.request.get(`/api/workspaces/${wid}/channels`)
  ).json();
  const general = channels.find((c: { name: string }) => c.name === "general");
  const secret = await write(owner, `/workspaces/${wid}/channels`, {
    name: "private-memory",
    is_private: true,
  });
  await write(owner, `/workspaces/${wid}/channels/${secret.id}/messages`, {
    body: "CLASSIFIED_PRIVATE_MEMORY secret",
    client_message_id: `memory-secret-${stamp}`,
  });
  await write(
    owner,
    `/workspaces/${wid}/memory/settings`,
    {
      include_private: true,
      retention_days: 0,
      offer_resolution_summaries: false,
    },
    "PUT",
  );
  await write(
    owner,
    `/workspaces/${wid}/agent/settings`,
    {
      enabled: true,
      provider_chain: ["groq"],
      monthly_run_limit: 1000,
      pause_at_limit: true,
    },
    "PUT",
  );
  await expect
    .poll(
      async () => {
        const response = await owner.request.get(
          `/api/workspaces/${wid}/search?query=refresh%20token`,
        );
        if (!response.ok()) return false;
        return (await response.json()).items.some(
          (i: { source_id: string }) => i.source_id === bug.id,
        );
      },
      { timeout: 40000 },
    )
    .toBeTruthy();
  const lagStarted = Date.now();
  const probe = await write(owner, `/workspaces/${wid}/tasks`, {
    project_id: project.id,
    title: "indexlagprobe",
    description: "Synthetic freshness measurement",
  });
  await expect
    .poll(
      async () => {
        const response = await owner.request.get(
          `/api/workspaces/${wid}/search?query=indexlagprobe&mode=full_text`,
        );
        return (
          response.ok() &&
          (await response.json()).items.some(
            (item: { source_id: string }) => item.source_id === probe.id,
          )
        );
      },
      { timeout: 40000, intervals: [100, 250, 500] },
    )
    .toBeTruthy();
  const indexingMs = Date.now() - lagStarted;
  expect(indexingMs).toBeLessThan(30000);
  console.log(
    JSON.stringify({
      mode: "background_worker_full_text",
      indexing_visible_ms: indexingMs,
    }),
  );
  const hidden = await (
    await viewer.request.get(
      `/api/workspaces/${wid}/search?query=CLASSIFIED_PRIVATE_MEMORY`,
    )
  ).json();
  expect(
    hidden.items.every(
      (i: { channel_id: string | null }) => i.channel_id !== secret.id,
    ),
  ).toBeTruthy();
  expect(hidden).not.toHaveProperty("total");
  expect(JSON.stringify(hidden)).not.toContain("skipped");
  const page = await owner.newPage();
  await page.goto("/search");
  await page
    .getByRole("textbox", { name: "Search query", exact: true })
    .fill("refresh token");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".memory-result")).toContainText(
    "Refresh token retry loop",
  );
  await page.screenshot({
    path: testInfo.outputPath("search-english.png"),
    fullPage: true,
  });
  await page
    .getByRole("textbox", { name: "Search query", exact: true })
    .fill("رمز الدخول");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".memory-result")).toContainText(
    "إصلاح رمز الدخول",
  );
  await expect(page.locator(".memory-snippet").first()).toHaveAttribute(
    "dir",
    "auto",
  );
  await page.screenshot({
    path: testInfo.outputPath("search-arabic.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBeLessThanOrEqual(390);
  await page.locator(".memory-results").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath("search-mobile-arabic.png"),
    fullPage: true,
  });
  await owner.setOffline(true);
  await expect(
    page.getByRole("heading", { name: "You are offline" }),
  ).toBeVisible();
  await owner.setOffline(false);
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/settings/memory");
  await expect(
    page.getByRole("heading", { name: "Workspace memory" }),
  ).toBeVisible();
  await expect(
    page.getByRole("switch", { name: /Include private channels/ }),
  ).toBeChecked();
  await page.screenshot({
    path: testInfo.outputPath("memory-settings.png"),
    fullPage: true,
  });
  await page
    .getByRole("combobox", { name: "Memory retention", exact: true })
    .selectOption("90");
  await page.getByRole("button", { name: "Save memory settings" }).click();
  await expect(
    page.getByText("Memory settings saved.", { exact: true }),
  ).toBeVisible();
  // Retention saves enqueue reindexing and immediately hide stale records.
  // Wait for the fixture to be searchable before asking the agent to cite it.
  await expect
    .poll(
      async () => {
        const response = await owner.request.get(
          `/api/workspaces/${wid}/search?query=refresh%20token&mode=full_text`,
        );
        return (
          response.ok() &&
          (await response.json()).items.some(
            (item: { source_id: string }) => item.source_id === bug.id,
          )
        );
      },
      { timeout: 40000, intervals: [100, 250, 500] },
    )
    .toBeTruthy();
  const denied = await viewer.newPage();
  await denied.goto("/settings/memory");
  await expect(
    denied.getByRole("heading", { name: "No access", exact: true }),
  ).toBeVisible();
  await page.goto(`/channels?channel=${general.id}`);
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("@Agent search memory refresh token");
  await page
    .getByRole("button", { name: "Send Message general", exact: true })
    .click();
  await expect(page.locator(".agent-message")).toContainText(
    "permitted workspace memory",
    { timeout: 30000 },
  );
  await expect(page.locator(".memory-source-chips")).toContainText(
    "Refresh token retry loop",
  );
  await page.screenshot({
    path: testInfo.outputPath("agent-memory-sources.png"),
    fullPage: true,
  });
  await page.goto("/settings/memory");
  await page
    .getByRole("textbox", { name: "Search query", exact: true })
    .fill("refresh token");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page
    .getByRole("checkbox", {
      name: "Select Refresh token retry loop",
      exact: true,
    })
    .check();
  await page.getByRole("button", { name: /Preview forgetting/ }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "memory records will be forgotten",
  );
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Forget memory", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const original = await owner.request.get(
    `/api/workspaces/${wid}/tasks/${bug.id}`,
  );
  expect(original.ok()).toBeTruthy();
  await owner.close();
  await viewer.close();
});
