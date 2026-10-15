import { test, expect, type BrowserContext, type Page } from "@playwright/test";

async function write(
  context: BrowserContext,
  path: string,
  data: unknown,
  method = "POST",
) {
  const csrf = await context.request.get("/api/auth/csrf");
  expect(csrf.ok()).toBeTruthy();
  const response = await context.request.fetch(`/api${path}`, {
    method,
    data,
    headers: { "X-CSRF-Token": (await csrf.json()).csrf_token },
  });
  expect(response.ok(), `${method} ${path}: ${response.status()}`).toBeTruthy();
  return response.status() === 204 ? null : response.json();
}
async function mention(page: Page, text: string) {
  await page
    .getByRole("textbox", { name: "Message general", exact: true })
    .fill(text);
  await page
    .getByRole("button", { name: "Send Message general", exact: true })
    .click();
}

test("two-session proposals, review, risk rules, replay, offline and Arabic mobile", async ({
  browser,
}, testInfo) => {
  test.setTimeout(180000);
  const owner = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    }),
    editor = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    });
  const stamp = Date.now();
  await write(owner, "/auth/register", {
    name: "Layla",
    email: `approver-${stamp}@example.com`,
    password: "approval-test-password-123",
  });
  const user = await write(editor, "/auth/register", {
    name: "Omar",
    email: `requester-${stamp}@example.com`,
    password: "approval-test-password-123",
  });
  const workspace = await write(owner, "/workspaces", {
    name: "Tandem Planning",
  });
  const wid = workspace.id;
  const project = await write(owner, `/workspaces/${wid}/projects`, {
    name: "Platform",
    key: "PLAT",
  });
  const invitation = await write(owner, `/workspaces/${wid}/invitations`, {
    email: user.email,
    role: "editor",
  });
  await write(
    editor,
    `/invitations/${new URL(invitation.invite_url).searchParams.get("token")}/accept`,
    {},
  );
  await write(
    owner,
    `/workspaces/${wid}/agent/settings`,
    {
      enabled: true,
      provider_chain: ["groq", "gemini"],
      monthly_run_limit: 1000,
      pause_at_limit: true,
    },
    "PUT",
  );
  const admin = await owner.newPage(),
    requester = await editor.newPage(),
    board = await editor.newPage();
  const events: {
    type: string;
    at: number;
    data: { task?: { id: string; title: string } };
  }[] = [];
  board.on("websocket", (ws) =>
    ws.on("framereceived", (f) => {
      try {
        const event = JSON.parse(String(f.payload));
        events.push({ ...event, at: Date.now() });
      } catch {}
    }),
  );
  await Promise.all([
    admin.goto("/channels"),
    requester.goto("/channels"),
    board.goto(`/tasks?project=${project.id}`),
  ]);
  await expect(admin.locator(".connection-status")).toContainText("Live");
  await expect(requester.locator(".connection-status")).toContainText("Live");
  const started = Date.now();
  await mention(requester, "@Agent plan JWT authentication");
  const card = admin.locator(".proposal-card").first();
  await expect(card).toContainText("JWT backend authentication");
  const creationMs = Date.now() - started;
  await expect(card.locator(".proposal-item")).toHaveCount(3);
  await expect(card.getByText("Low risk", { exact: true })).toBeVisible();
  await expect(board.locator(".task-card")).toHaveCount(0);
  await admin.setViewportSize({ width: 1440, height: 1500 });
  await admin.locator(".message-list").evaluate((el) => {
    el.scrollTop = 0;
  });
  await admin.screenshot({
    path: testInfo.outputPath("proposal-multi.png"),
    fullPage: true,
  });
  await admin.setViewportSize({ width: 1440, height: 1000 });
  // Inbox reflects real actionable data, and the channel's card remains the decision source.
  const inbox = await owner.newPage();
  await inbox.goto("/inbox");
  await expect(
    inbox.getByRole("tab", { name: "Approvals", exact: true }),
  ).toBeVisible();
  await expect(inbox.locator(".pending-proposal")).toContainText(
    "JWT backend authentication",
  );
  await expect(inbox.getByRole("tab", { name: /Mentions/ })).toBeDisabled();
  await inbox.screenshot({
    path: testInfo.outputPath("approvals-inbox.png"),
    fullPage: true,
  });
  await card.getByRole("button", { name: "Edit", exact: true }).click();
  const review = admin.getByRole("dialog", { name: "Review proposal" });
  await review
    .getByLabel("Title", { exact: true })
    .first()
    .fill("Reviewed JWT backend");
  await review
    .getByRole("button", { name: "Remove task 3", exact: true })
    .click();
  await expect(review.getByLabel("Title", { exact: true })).toHaveCount(2);
  await review
    .getByRole("button", { name: "Approve reviewed changes" })
    .click();
  await expect(card.getByText("Completed", { exact: true })).toBeVisible();
  await expect(
    board.getByText("Reviewed JWT backend", { exact: true }),
  ).toBeVisible();
  await expect(
    board.getByText("JWT frontend session flow", { exact: true }),
  ).toBeVisible();
  await expect(
    board.getByText("JWT integration tests", { exact: true }),
  ).toHaveCount(0);
  await expect(
    requester
      .locator(".proposal-card")
      .first()
      .getByText("Completed", { exact: true }),
  ).toBeVisible();
  await admin.screenshot({
    path: testInfo.outputPath("proposal-completed.png"),
    fullPage: true,
  });
  await expect(inbox.locator(".pending-proposal")).toHaveCount(0);
  // Fast unedited approval measurement observed through a second user's real task subscription.
  await mention(requester, "@Agent create a task for review");
  const simple = admin
    .locator(".proposal-card")
    .filter({ hasText: "Proposed task for review" })
    .last();
  await expect(
    simple.getByRole("button", { name: "Approve and create" }),
  ).toBeVisible();
  const approvalStart = Date.now();
  await simple.getByRole("button", { name: "Approve and create" }).click();
  await expect(
    board.getByText("Proposed task for review", { exact: true }),
  ).toBeVisible();
  const taskVisibleMs = Date.now() - approvalStart;
  await expect
    .poll(() =>
      events.some(
        (e) =>
          e.type === "task.created" &&
          e.data.task?.title === "Proposed task for review",
      ),
    )
    .toBeTruthy();
  const delivered = events.find(
    (e) =>
      e.type === "task.created" &&
      e.data.task?.title === "Proposed task for review",
  )!;
  const approvalMs = delivered.at - approvalStart;
  // High-risk proposal is read-only to Editor and executable only by Admin.
  await mention(requester, "@Agent propose a priority change");
  const high = requester
    .locator(".proposal-card")
    .filter({ hasText: "High risk" })
    .last();
  await expect(high).toContainText("Only an Admin can approve this");
  await expect(
    high.getByRole("button", { name: "Approve change" }),
  ).toHaveCount(0);
  await requester.screenshot({
    path: testInfo.outputPath("proposal-admin-only.png"),
    fullPage: true,
  });
  const adminHigh = admin
    .locator(".proposal-card")
    .filter({ hasText: "High risk" })
    .last();
  await adminHigh.getByRole("button", { name: "Reject", exact: true }).click();
  await admin
    .getByRole("dialog")
    .getByRole("button", { name: "Reject proposal", exact: true })
    .click();
  await expect(high.getByText("Rejected", { exact: true })).toBeVisible();
  await admin.screenshot({
    path: testInfo.outputPath("proposal-rejected.png"),
    fullPage: true,
  });
  // Tightened create-task rule affects already visible eligibility; high-risk stays locked.
  const settings = await owner.newPage();
  await settings.goto("/settings/agent");
  await settings
    .getByRole("combobox", { name: "Create tasks approver" })
    .selectOption("admin");
  await expect
    .poll(async () => {
      const r = await owner.request.get(
        `/api/workspaces/${wid}/agent/approval-rules`,
      );
      return (await r.json()).create_tasks_approver;
    })
    .toBe("admin");
  await settings
    .getByRole("heading", { name: "Approval rules", exact: true })
    .scrollIntoViewIfNeeded();
  await settings.screenshot({
    path: testInfo.outputPath("approval-rules.png"),
    fullPage: true,
  });
  await mention(requester, "@Agent خطط للمصادقة باستخدام JWT");
  const arabic = admin
    .locator(".proposal-card")
    .filter({ hasText: "تنفيذ المصادقة في الخادم" })
    .last();
  await expect(arabic).toBeVisible();
  await expect(arabic.locator("h3").first()).toHaveAttribute("dir", "auto");
  await expect(arabic.locator(".message-body").first()).toHaveAttribute(
    "dir",
    "auto",
  );
  await expect
    .poll(() =>
      arabic
        .locator("h3")
        .first()
        .evaluate((el) => getComputedStyle(el).direction),
    )
    .toBe("rtl");
  await admin.screenshot({
    path: testInfo.outputPath("proposal-arabic.png"),
    fullPage: true,
  });
  await admin.setViewportSize({ width: 390, height: 844 });
  await arabic.getByRole("button", { name: "Edit", exact: true }).click();
  const mobileSheet = admin.getByRole("dialog", { name: "Review proposal" });
  await expect(mobileSheet).toBeVisible();
  await expect(
    mobileSheet.getByLabel("Title", { exact: true }).first(),
  ).toHaveAttribute("dir", "auto");
  await admin.screenshot({
    path: testInfo.outputPath("proposal-mobile-sheet.png"),
    fullPage: true,
  });
  await owner.setOffline(true);
  await expect(
    mobileSheet.getByRole("button", { name: "Approve reviewed changes" }),
  ).toBeDisabled();
  await expect(mobileSheet).toContainText(
    "Approvals require an internet connection",
  );
  await owner.setOffline(false);
  await mobileSheet.getByRole("button", { name: "Back", exact: true }).click();
  await arabic.scrollIntoViewIfNeeded();
  await admin.screenshot({
    path: testInfo.outputPath("proposal-mobile.png"),
    fullPage: true,
  });
  await admin.emulateMedia({ colorScheme: "dark" });
  await admin.screenshot({
    path: testInfo.outputPath("proposal-mobile-dark.png"),
    fullPage: true,
  });
  // Reconnect reloads authoritative state once and never duplicates a proposal.
  await requester.reload();
  await expect(requester.locator(".proposal-card")).toHaveCount(4);
  await expect(
    requester
      .locator(".proposal-card")
      .first()
      .getByText("Completed", { exact: true }),
  ).toBeVisible();
  // Inbox deep links must open thread proposals, including triggers outside the main timeline.
  const channels = await owner.request.get(`/api/workspaces/${wid}/channels`);
  const cid = (await channels.json())[0].id;
  const root = await write(
    editor,
    `/workspaces/${wid}/channels/${cid}/messages`,
    { body: "Thread planning", client_message_id: crypto.randomUUID() },
  );
  const reply = await write(
    editor,
    `/workspaces/${wid}/channels/${cid}/messages`,
    {
      body: "@Agent خطط للمصادقة داخل الرد",
      client_message_id: crypto.randomUUID(),
      thread_root_id: root.id,
    },
  );
  let threadProposalId = "";
  await expect
    .poll(async () => {
      const result = await owner.request.get(
        `/api/workspaces/${wid}/proposals?channel_id=${cid}`,
      );
      const p = (await result.json()).proposals.find(
        (p: { trigger_message_id: string }) =>
          p.trigger_message_id === reply.id,
      );
      threadProposalId = p?.id ?? "";
      return !!p;
    })
    .toBeTruthy();
  await admin.setViewportSize({ width: 1440, height: 1000 });
  await admin.goto(`/channels?channel=${cid}&proposal=${threadProposalId}`);
  await expect(
    admin.locator(`.thread-panel [data-proposal-id="${threadProposalId}"]`),
  ).toBeVisible();
  await testInfo.attach("fake-proposal-performance", {
    body: JSON.stringify({
      mode: "fake_provider",
      proposal_creation_ms: creationMs,
      approval_to_second_session_task_event_ms: approvalMs,
      approval_to_second_user_task_visible_ms: taskVisibleMs,
    }),
    contentType: "application/json",
  });
  console.log(
    JSON.stringify({
      mode: "fake_provider",
      proposal_creation_ms: creationMs,
      approval_to_second_session_task_event_ms: approvalMs,
      approval_to_second_user_task_visible_ms: taskVisibleMs,
    }),
  );
  await owner.close();
  await editor.close();
});
