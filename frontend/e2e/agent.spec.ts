import { test, expect, type BrowserContext } from "@playwright/test";

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
  return response.json();
}

test("shared agent two-session answer, live steps, settings, audit, offline draft and 390px panel", async ({
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  const a = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    }),
    b = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const stamp = Date.now();
  await write(a, "/auth/register", {
    name: "Layla",
    email: `agent-owner-${stamp}@example.com`,
    password: "test-agent-password-123",
  });
  const viewer = await write(b, "/auth/register", {
    name: "Omar",
    email: `agent-viewer-${stamp}@example.com`,
    password: "test-agent-password-123",
  });
  const workspace = await write(a, "/workspaces", { name: "Tandem Studio" });
  const wid = workspace.id;
  const invite = await write(a, `/workspaces/${wid}/invitations`, {
    email: viewer.email,
    role: "viewer",
  });
  await write(
    b,
    `/invitations/${new URL(invite.invite_url).searchParams.get("token")}/accept`,
    {},
  );
  await write(
    a,
    `/workspaces/${wid}/agent/settings`,
    {
      enabled: true,
      provider_chain: ["groq", "gemini"],
      monthly_run_limit: 1000,
      pause_at_limit: true,
    },
    "PUT",
  );
  const page = await a.newPage(),
    other = await b.newPage();
  const events: string[] = [];
  other.on("websocket", (ws) =>
    ws.on("framereceived", (frame) => {
      try {
        events.push(JSON.parse(String(frame.payload)).type);
      } catch {}
    }),
  );
  await Promise.all([page.goto("/channels"), other.goto("/channels")]);
  await expect(other.locator(".connection-status")).toContainText("Live");
  await expect(page.locator(".connection-status")).toContainText("Live");
  await other
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("@Agent summarize this channel");
  await other
    .getByRole("button", { name: "Send Message general", exact: true })
    .click();
  await expect(page.locator(".agent-message")).toContainText(
    "read the accessible channel context",
  );
  await expect(other.locator(".agent-message")).toContainText("human approval");
  await expect.poll(() => events).toContain("agent.step");
  await expect.poll(() => events).toContain("agent.message_created");
  await page.locator(".agent-message .agent-steps summary").click();
  await expect(page.locator(".agent-message .agent-steps li")).toHaveCount(1);
  await expect(
    page.getByRole("heading", { name: "What the agent can see" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("agent-channel.png"),
    fullPage: true,
  });
  await page.goto("/settings/agent");
  await expect(
    page.getByRole("heading", { name: "Models and data sharing" }),
  ).toBeVisible();
  await expect(page.getByText(/Owner opt-in:/)).toBeVisible();
  await page.getByLabel("Monthly run limit").fill("500");
  await page.getByRole("button", { name: "Save agent settings" }).click();
  await expect(page.getByRole("status")).toContainText("Agent settings saved.");
  await page.locator(".main-panel").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.screenshot({
    path: testInfo.outputPath("agent-settings.png"),
    fullPage: true,
  });
  await page.goto("/settings/audit");
  await expect(page.locator(".audit-table")).toContainText("agent.tool_call");
  await page.getByLabel("Action", { exact: true }).fill("agent.tool_call");
  await expect(page.locator(".audit-table tbody tr")).toHaveCount(1);
  await page
    .getByRole("button", { name: "View agent.tool_call details" })
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "redacted_arguments".replaceAll("_", " "),
  );
  await page.getByRole("button", { name: "Close dialog" }).click();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await downloading).suggestedFilename()).toBe("tandem-audit.csv");
  await page.screenshot({
    path: testInfo.outputPath("agent-audit.png"),
    fullPage: true,
  });
  await other.goto("/settings/audit");
  await expect(other.getByRole("heading", { name: "No access" })).toBeVisible();
  await other.goto("/channels");
  await other.setViewportSize({ width: 390, height: 844 });
  await expect(other.locator(".agent-message")).toBeVisible();
  await other.getByRole("tab", { name: "Agent", exact: true }).click();
  await expect(
    other.getByRole("heading", { name: "What the agent can see" }),
  ).toBeVisible();
  await other.screenshot({
    path: testInfo.outputPath("agent-mobile-panel.png"),
    fullPage: true,
  });
  await other.getByRole("button", { name: "Close Agent panel" }).click();
  await other.screenshot({
    path: testInfo.outputPath("agent-mobile.png"),
    fullPage: true,
  });
  await other.emulateMedia({ colorScheme: "dark" });
  await other.screenshot({
    path: testInfo.outputPath("agent-mobile-dark.png"),
    fullPage: true,
  });
  await expect(other.locator(".mobile-tabs")).toBeVisible();
  await expect(other.locator(".mobile-tabs .nav-item")).toHaveCount(4);
  expect(
    await other.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await b.setOffline(true);
  await other
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("@Agent keep this unsent draft");
  await expect(
    other.getByRole("button", {
      name: "Agent needs an internet connection",
      exact: true,
    }),
  ).toBeDisabled();
  await expect(
    other.getByRole("button", { name: "Send Message general", exact: true }),
  ).toBeDisabled();
  await b.setOffline(false);
  await expect(
    other.getByRole("textbox", { name: "Message general", exact: true }),
  ).toHaveValue("@Agent keep this unsent draft");
  await expect(other.locator(".agent-message")).toHaveCount(1);
  await a.close();
  await b.close();
});
