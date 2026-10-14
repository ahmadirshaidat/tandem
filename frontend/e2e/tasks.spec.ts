import {
  test,
  expect,
  type BrowserContext,
  type Browser,
} from "@playwright/test";
async function write(
  context: BrowserContext,
  path: string,
  data: unknown,
  method = "POST",
) {
  const csrf = await context.request.get("/api/auth/csrf");
  const token = (await csrf.json()).csrf_token;
  const result = await context.request.fetch(`/api${path}`, {
    method,
    data,
    headers: { "X-CSRF-Token": token },
  });
  expect(
    result.ok(),
    `${method} ${path}: ${result.status()} ${await result.text()}`,
  ).toBeTruthy();
  return result.status() === 204 ? null : result.json();
}
async function setup(browser: Browser, role = "editor") {
  const a = await browser.newContext({
      viewport: { width: 1440, height: 900 },
    }),
    b = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const stamp = `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  await write(a, "/auth/register", {
    name: "Layla",
    email: `tasks-a-${stamp}@example.com`,
    password: "tasks-test-password-123",
  });
  const bob = await write(b, "/auth/register", {
    name: "Omar",
    email: `tasks-b-${stamp}@example.com`,
    password: "tasks-test-password-123",
  });
  const workspace = await write(a, "/workspaces", { name: "Acme Studio" });
  const base = `/workspaces/${workspace.id}`;
  const invite = await write(a, base + "/invitations", {
    email: bob.email,
    role,
  });
  await write(
    b,
    `/invitations/${new URL(invite.invite_url).searchParams.get("token")}/accept`,
    {},
  );
  const project = await write(a, base + "/projects", {
    name: "Web app",
    key: "WEB",
    description: "Ship the next version together.",
  });
  return { a, b, workspace, project, base };
}
test("two-session tasks, conflict choices, table bulk, message link, reconnect and mobile offline", async ({
  browser,
}, testInfo) => {
  test.setTimeout(60000);
  const { a, b, project, base } = await setup(browser);
  const page = await a.newPage(),
    editor = await b.newPage();
  await Promise.all([
    page.goto(`/tasks?project=${project.id}`),
    editor.goto(`/tasks?project=${project.id}`),
  ]);
  await expect(page.locator(".task-connection")).toHaveText("Live");
  await expect(editor.locator(".task-connection")).toHaveText("Live");
  await page.getByRole("button", { name: "New task", exact: true }).click();
  const create = page.getByRole("dialog", { name: "New task", exact: true });
  await create
    .getByLabel("Title", { exact: true })
    .fill("Login returns 500 for SSO accounts");
  await create.getByLabel("Type", { exact: true }).selectOption("bug");
  await create.getByLabel("Priority", { exact: true }).selectOption("P1");
  await create
    .getByLabel("Description", { exact: true })
    .fill("Investigate **session middleware**.");
  await create
    .getByRole("button", { name: "Create task", exact: true })
    .click();
  const detail = page.getByRole("dialog", { name: "BUG-1", exact: true });
  await expect(detail.getByLabel("Task title")).toHaveValue(
    "Login returns 500 for SSO accounts",
  );
  await expect(
    editor.locator('.task-card[data-task-key="BUG-1"]'),
  ).toContainText("Login returns 500");
  const first = (await (await a.request.get(`/api${base}/tasks`)).json())
    .tasks[0];
  await detail
    .getByLabel("Task comment")
    .fill("I can reproduce this on staging.");
  await detail
    .getByRole("button", { name: "Post comment", exact: true })
    .click();
  await expect(
    editor.locator('.task-card[data-task-key="BUG-1"] .task-card-footer'),
  ).toContainText("1");
  await editor
    .locator('.task-card[data-task-key="BUG-1"] .task-card-title')
    .click();
  const other = editor.getByRole("dialog", { name: "BUG-1", exact: true });
  await expect(
    other.getByText("I can reproduce this on staging.", { exact: true }),
  ).toBeVisible();
  await detail.getByLabel("Task title").fill("Layla's title");
  await other.getByLabel("Task title").fill("Omar's title");
  await detail
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    detail.getByRole("button", { name: "Save changes", exact: true }),
  ).toBeDisabled();
  await other
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    other.getByRole("heading", { name: "This task changed" }),
  ).toBeVisible();
  await other.getByRole("button", { name: "Keep mine", exact: true }).click();
  await expect(
    other.getByRole("button", { name: "Save changes", exact: true }),
  ).toBeDisabled();
  await expect(detail.getByLabel("Task title")).toHaveValue("Omar's title");
  await detail.getByLabel("Task title").fill("Discard this draft");
  await other.getByLabel("Task title").fill("Server wins");
  await other
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    other.getByRole("button", { name: "Save changes", exact: true }),
  ).toBeDisabled();
  await detail
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    detail.getByRole("heading", { name: "This task changed" }),
  ).toBeVisible();
  await detail
    .getByRole("button", { name: "Take server's", exact: true })
    .click();
  await expect(detail.getByLabel("Task title")).toHaveValue("Server wins");
  await detail.getByRole("button", { name: "Close task detail" }).click();
  await other.getByRole("button", { name: "Close task detail" }).click();
  await page
    .locator('.task-card[data-task-key="BUG-1"]')
    .dragTo(page.getByRole("region", { name: "Done", exact: true }));
  await expect(
    editor
      .getByRole("region", { name: "Done", exact: true })
      .locator('.task-card[data-task-key="BUG-1"]'),
  ).toBeVisible();
  await page.getByRole("button", { name: "Actions for BUG-1" }).click();
  await page
    .getByRole("dialog", { name: "BUG-1" })
    .getByRole("button", { name: "In progress", exact: true })
    .click();
  await expect(
    editor
      .getByRole("region", { name: "In progress", exact: true })
      .locator('.task-card[data-task-key="BUG-1"]'),
  ).toBeVisible();
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await page.getByLabel("Select BUG-1", { exact: true }).check();
  await page.getByLabel("Bulk assignee").selectOption({ label: "Omar" });
  await expect(
    editor
      .locator('.task-card[data-task-key="BUG-1"]')
      .getByLabel("Assigned to Omar"),
  ).toBeVisible();
  await page.getByLabel("Select BUG-1", { exact: true }).check();
  await page.getByLabel("Bulk status").selectOption("done");
  await expect(
    editor
      .getByRole("region", { name: "Done", exact: true })
      .locator('.task-card[data-task-key="BUG-1"]'),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("task-table.png") });
  await b.setOffline(true);
  const second = await write(a, base + "/tasks", {
    project_id: project.id,
    title: "Write the onboarding empty states",
  });
  await write(
    a,
    base + `/tasks/${first.id}`,
    {
      version: (
        await (await a.request.get(`/api${base}/tasks/${first.id}`)).json()
      ).version,
      priority: "P3",
    },
    "PATCH",
  );
  await b.setOffline(false);
  await expect(
    editor.locator(`.task-card[data-task-key="${second.key}"]`),
  ).toHaveCount(1);
  await expect(
    editor.locator('.task-card[data-task-key="BUG-1"]'),
  ).toContainText("P3 Low");
  const general = (
    await (await a.request.get(`/api${base}/channels`)).json()
  )[0];
  await page.goto(`/channels?channel=${general.id}`);
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill("Review the release checklist");
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .press("Enter");
  const message = page
    .locator(".channel-main .chat-message")
    .filter({ hasText: "Review the release checklist" });
  await message.locator("summary").click();
  await message
    .getByRole("button", { name: "Create task from message" })
    .click();
  const fromMessage = page.getByRole("dialog", {
    name: "Create task from message",
  });
  await expect(fromMessage.getByLabel("Title", { exact: true })).toHaveValue(
    "Review the release checklist",
  );
  await fromMessage
    .getByRole("button", { name: "Create task", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "TASK-3", exact: true }),
  ).toBeVisible();
  // The linked source is older than the initial 50-message history page.
  for (let index = 0; index < 51; index++) await write(a, base + `/channels/${general.id}/messages`, { body: `Later message ${index}`, client_message_id: crypto.randomUUID() });
  await page
    .getByRole("link", { name: "Conversation in #general", exact: true })
    .click();
  await expect(
    page
      .locator(".channel-main .chat-message")
      .filter({ hasText: "Review the release checklist" }),
  ).toBeFocused();
  await page.goto(`/tasks?project=${project.id}`);
  await expect(page.locator(".task-card")).toHaveCount(3);
  await expect(page.locator(".task-connection")).toHaveText("Live");
  await page.screenshot({ path: testInfo.outputPath("task-board.png") });
  await page
    .locator('.task-card[data-task-key="BUG-1"] .task-card-title')
    .click();
  await expect(page.getByLabel("Task title")).toHaveValue("Server wins");
  await expect(
    page.getByText("I can reproduce this on staging.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("task-detail.png") });
  await page.getByRole("button", { name: "Close task detail" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("group", { name: "Board status" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("task-mobile.png") });
  await page
    .getByRole("group", { name: "Board status" })
    .getByRole("button", { name: "Done" })
    .click();
  await page
    .locator('.task-card[data-task-key="BUG-1"] .task-card-title')
    .click();
  await expect(page.getByRole("dialog", { name: "BUG-1" })).toBeVisible();
  await page.getByRole("button", { name: "Close task detail" }).click();
  await page
    .locator(".mobile-app-header")
    .getByRole("switch", { name: "Dark mode" })
    .click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.setViewportSize({ width: 844, height: 390 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(
    async () =>
      !!navigator.serviceWorker.controller &&
      !!(await (await caches.open("tandem-chat-shell-v1")).match("/tasks")),
  );
  await a.setOffline(true);
  await page.reload();
  await expect(
    page.getByText(/You are offline. Tasks are read only/),
  ).toBeVisible();
  await page
    .getByRole("group", { name: "Board status" })
    .getByRole("button", { name: "Done" })
    .click();
  await page
    .locator('.task-card[data-task-key="BUG-1"] .task-card-title')
    .click();
  await expect(page.getByLabel("Task title")).toHaveValue("Server wins");
  await expect(page.getByLabel("Task title")).toBeDisabled();
  await expect(page.getByLabel("Task comment")).toBeDisabled();
  await page.getByRole("button", { name: "Close task detail" }).click();
  await page.getByRole("button", { name: "Table", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "Tasks", exact: true }),
  ).toContainText("Server wins");
  await expect(page.getByLabel("Select BUG-1", { exact: true })).toBeDisabled();
  await Promise.all([a.close(), b.close()]);
});
test("viewer reads tasks without mutation controls or private message links", async ({
  browser,
}) => {
  const { a, b, project, base } = await setup(browser, "viewer");
  const channel = await write(a, base + "/channels", {
    name: "private-leads",
    is_private: true,
  });
  const message = await write(a, base + `/channels/${channel.id}/messages`, {
    body: "Private source",
    client_message_id: crypto.randomUUID(),
  });
  const task = await write(a, base + "/tasks/from-message", {
    project_id: project.id,
    title: "Workspace-visible title",
    message_id: message.id,
  });
  const viewer = await b.newPage();
  await viewer.goto(`/tasks?project=${project.id}&task=${task.id}`);
  await expect(viewer.getByLabel("Task title")).toHaveValue(
    "Workspace-visible title",
  );
  await expect(viewer.getByLabel("Task title")).toBeDisabled();
  await expect(viewer.getByLabel("Task comment")).toBeDisabled();
  await expect(
    viewer.getByRole("button", { name: "Save changes", exact: true }),
  ).toHaveCount(0);
  await expect(
    viewer.getByRole("link", { name: /Conversation in/ }),
  ).toHaveCount(0);
  await expect(viewer.getByText("private-leads", { exact: false })).toHaveCount(
    0,
  );
  await viewer.getByRole("button", { name: "Close task detail" }).click();
  await expect(
    viewer.getByRole("button", { name: "New task", exact: true }),
  ).toBeDisabled();
  await expect(
    viewer.getByRole("button", { name: "Create project", exact: true }),
  ).toHaveCount(0);
  await Promise.all([a.close(), b.close()]);
});
