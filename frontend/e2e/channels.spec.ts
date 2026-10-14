import { test, expect, type BrowserContext } from "@playwright/test";

async function write(
  context: BrowserContext,
  path: string,
  body: unknown,
  method = "POST",
) {
  const csrf = await context.request.get("/api/auth/csrf");
  const token = (await csrf.json()).csrf_token;
  const result = await context.request.fetch(`/api${path}`, {
    method,
    data: body,
    headers: { "X-CSRF-Token": token },
  });
  expect(result.ok(), `${method} ${path}: ${result.status()}`).toBeTruthy();
  return result.status() === 204 ? null : result.json();
}
async function account(context: BrowserContext, name: string, email: string) {
  return write(context, "/auth/register", {
    name,
    email,
    password: "channels-test-password-123",
  });
}

test("two-session live channels, thread, attachments, reconnect, offline drafts and mobile", async ({
  browser,
}, testInfo) => {
  test.setTimeout(120000);
  const a = await browser.newContext({
      viewport: { width: 1440, height: 900 },
    }),
    b = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const stamp = Date.now();
  const alice = await account(a, "Layla", `channels-a-${stamp}@example.com`);
  const bob = await account(b, "Omar", `channels-b-${stamp}@example.com`);
  const workspace = await write(a, "/workspaces", {
    name: `Acme Studio ${stamp}`,
  });
  const invite = await write(a, `/workspaces/${workspace.id}/invitations`, {
    email: bob.email,
    role: "viewer",
  });
  const token = new URL(invite.invite_url).searchParams.get("token");
  await write(b, `/invitations/${token}/accept`, {});
  const channels = await a.request.get(
    `/api/workspaces/${workspace.id}/channels`,
  );
  const general = (await channels.json())[0];
  const base = `/workspaces/${workspace.id}/channels/${general.id}`;
  const page = await a.newPage(),
    viewer = await b.newPage();
  await page.addInitScript(() => {
    const events: unknown[] = [];
    (window as unknown as { channelEvents: unknown[] }).channelEvents = events;
    const Original = window.WebSocket;
    window.WebSocket = class extends Original {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        if (String(url).endsWith("/api/ws"))
          this.addEventListener("message", (event) =>
            events.push(JSON.parse(event.data)),
          );
      }
    };
  });
  await Promise.all([page.goto("/channels"), viewer.goto("/channels")]);
  await expect(
    page.getByRole("heading", { name: "general", exact: true }),
  ).toBeVisible();
  await expect(
    viewer.getByRole("heading", { name: "general", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".connection-status")).toContainText("Live");
  await expect(page.locator(".presence-pill")).toHaveText("2 online");
  await expect(
    viewer.getByRole("button", { name: "Create channel" }),
  ).toHaveCount(0);
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("Login returns a 500 after yesterday's deploy.");
  await expect(page.locator(".typing-indicator")).toContainText(
    "Omar is typing",
  );
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .press("Enter");
  const root = page
    .locator(".channel-main .chat-message")
    .filter({ hasText: "Login returns a 500" });
  await expect(root).toHaveCount(1);
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("@Agent **analyze this** — mention only.");
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .press("Enter");
  await expect(
    viewer.getByText("Agent mentioned", { exact: true }),
  ).toBeVisible();
  const history = await a.request.get(`/api${base}/messages`);
  const rows = (await history.json()).messages;
  expect(
    rows.find((m: { body: string }) => m.body.startsWith("@Agent"))
      .mentions_agent,
  ).toBe(true);
  const trials = await a.request.get(
    `/api/workspaces/${workspace.id}/ai/trials`,
  );
  expect(await trials.json()).toHaveLength(0);
  await root.getByRole("button", { name: "Reply in thread" }).click();
  const viewerRoot = viewer
    .locator(".channel-main .chat-message")
    .filter({ hasText: "Login returns a 500" });
  await viewerRoot.getByRole("button", { name: "Reply in thread" }).click();
  await viewer
    .getByRole("textbox", { name: "Reply", exact: true })
    .fill("Same on staging. I think the session middleware changed.");
  await viewer
    .getByRole("textbox", { name: "Reply", exact: true })
    .press("Enter");
  await expect(page.locator(".thread-messages")).toContainText(
    "Same on staging",
  );
  await page.screenshot({
    path: "test-results/channel-thread-desktop-light.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Close thread" }).click();
  await viewer.getByRole("button", { name: "Close thread" }).click();
  const xss =
    "<script>window.hacked=true</script> <img src=x onerror=alert(1)>";
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill(xss);
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .press("Enter");
  await expect(
    page.locator(".message-body").filter({ hasText: xss }),
  ).toHaveCount(1);
  expect(
    await page.evaluate(() =>
      Boolean((window as unknown as { hacked?: boolean }).hacked),
    ),
  ).toBe(false);
  await expect(
    page.locator(".message-body script,.message-body img"),
  ).toHaveCount(0);
  // A small valid PNG, served only through the authenticated channel endpoint.
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAGCAIAAABxZ0isAAAAFElEQVR4nGNkYPjPgA0wYRWlkwQAlocBCyQOisYAAAAASUVORK5CYII=",
    "base64",
  );
  await viewer.locator('input[type="file"]').setInputFiles({
    name: "login-500.png",
    mimeType: "image/png",
    buffer: png,
  });
  await expect(viewer.locator(".composer-attachments img")).toHaveCount(1);
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("Screenshot attached");
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .press("Enter");
  await expect(page.locator(".message-images img")).toHaveCount(1);
  await page.getByRole("button", { name: "Open attached image" }).click();
  await expect(
    page.getByRole("dialog", { name: "Shared image" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  const before = await page.evaluate(
    () =>
      (
        window as unknown as { channelEvents: { seq: number | null }[] }
      ).channelEvents.filter((e) => e.seq !== null).length,
  );
  await a.setOffline(true);
  await expect(page.locator(".connection-status")).toContainText(
    "You are offline",
  );
  await expect(root).toBeVisible();
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("Unsent offline draft");
  await expect(
    page.getByRole("button", { name: "Send Message general" }),
  ).toBeDisabled();
  const missed = [];
  for (let n = 0; n < 3; n++)
    missed.push(
      await write(b, base + "/messages", {
        body: `Reconnect message ${n}`,
        client_message_id: `catchup-${stamp}-${n}`,
      }),
    );
  await write(
    b,
    base + `/messages/${missed[0].id}`,
    { body: "Reconnect message 0 — edited" },
    "PATCH",
  );
  await a.setOffline(false);
  await expect(page.locator(".connection-status")).toContainText("Live");
  await expect(
    page
      .locator(".message-body")
      .filter({ hasText: "Reconnect message 0 — edited" }),
  ).toHaveCount(1);
  for (let n = 1; n < 3; n++)
    await expect(
      page
        .locator(".message-body")
        .filter({ hasText: `Reconnect message ${n}` }),
    ).toHaveCount(1);
  await expect(
    page.getByRole("textbox", { name: "Message general", exact: true }),
  ).toHaveValue("Unsent offline draft");
  await expect(
    viewer.locator(".message-body").filter({ hasText: "Unsent offline draft" }),
  ).toHaveCount(0);
  const replay = await page.evaluate(
    (before) =>
      (
        window as unknown as {
          channelEvents: {
            type: string;
            seq: number | null;
            data: { message?: { body: string } };
          }[];
        }
      ).channelEvents
        .filter((e) => e.seq !== null)
        .slice(before)
        .filter((e) => ["message.created", "message.updated"].includes(e.type)),
    before,
  );
  expect(replay.map((e) => e.type)).toEqual([
    "message.created",
    "message.created",
    "message.created",
    "message.updated",
  ]);
  expect(new Set(replay.map((e) => e.seq)).size).toBe(4);
  expect(replay.map((e) => e.seq)).toEqual(
    [...replay.map((e) => e.seq)].sort((a, b) => a! - b!),
  );
  let failOnce = true;
  await b.route("**/api/workspaces/*/channels/*/messages", async (route) => {
    if (route.request().method() === "POST" && failOnce) {
      failOnce = false;
      await route.abort("failed");
    } else await route.continue();
  });
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("Explicit retry sends one message");
  await viewer
    .getByRole("textbox", { name: "Message general", exact: true })
    .press("Enter");
  await expect(viewer.locator(".failed-send")).toContainText(
    "Message wasn’t sent",
  );
  await viewer.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(
    page
      .locator(".message-body")
      .filter({ hasText: "Explicit retry sends one message" }),
  ).toHaveCount(1);
  await expect(viewer.locator(".failed-send")).toHaveCount(0);
  await b.unroute("**/api/workspaces/*/channels/*/messages");
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(
    await page
      .getByRole("textbox", { name: "Message general", exact: true })
      .evaluate((el) => getComputedStyle(el).fontSize),
  ).toBe("16px");
  await expect(page.locator(".mobile-tabs")).toBeVisible();
  expect((await page.locator(".mobile-tabs").boundingBox())!.y).toBeLessThan(
    844,
  );
  await page.screenshot({
    path: "test-results/channel-mobile-light.png",
    fullPage: true,
  });
  await root.getByRole("button", { name: /reply/ }).click();
  await expect(
    page.getByRole("textbox", { name: "Reply", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/thread-mobile-light.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Back to channel" }).click();
  await page.evaluate(() => {
    document.documentElement.classList.add("dark");
    localStorage.setItem("tandem-theme", "dark");
  });
  await page.screenshot({
    path: "test-results/channel-mobile-dark.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 844, height: 390 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.locator(".connection-status")).toContainText("Live");
  await page.waitForFunction(async () =>
    (await caches.open("tandem-chat-shell-v1"))
      .match("/channels")
      .then(Boolean),
  );
  await a.setOffline(true);
  await page.reload();
  await expect(page.locator(".connection-status")).toContainText(
    "You are offline",
  );
  await expect(
    page
      .locator(".message-body")
      .filter({ hasText: "Reconnect message 0 — edited" }),
  ).toHaveCount(1);
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("Offline reload draft");
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "Message general", exact: true }),
  ).toHaveValue("Offline reload draft");
  await a.setOffline(false);
  await expect(page.locator(".connection-status")).toContainText("Live");
  await expect(
    viewer.locator(".message-body").filter({ hasText: "Offline reload draft" }),
  ).toHaveCount(0);
  // Keep the new project namespace and typed event stream observable for failures.
  await testInfo.attach("live-event-count", {
    body: String(replay.length),
    contentType: "text/plain",
  });
  expect(alice.id).not.toBe(bob.id);
  await a.close();
  await b.close();
});
