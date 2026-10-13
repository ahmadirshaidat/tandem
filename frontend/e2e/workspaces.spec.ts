import { test, expect, type Page } from "@playwright/test";

async function register(page: Page, email: string, name: string) {
  await page.getByLabel("Your name").fill(name);
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("e2e-long-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
}

test("two users register, create a workspace, accept an invite, and enforce roles", async ({
  page,
  browser,
}) => {
  const suffix = `${Date.now()}`;
  const ownerEmail = `owner-${suffix}@example.com`;
  const viewerEmail = `viewer-${suffix}@example.com`;
  await page.goto("/signup");
  await register(page, ownerEmail, "Team Owner");
  await expect(
    page.getByRole("heading", { name: "Your team starts here." }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Create workspace", exact: true })
    .click();
  await page.getByLabel("Workspace name").fill(`North ${suffix}`);
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "A good place to begin." }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Invite your team", exact: true })
    .click();
  await page.getByLabel("Their email address").fill(viewerEmail);
  await page.getByLabel("Role", { exact: true }).selectOption("viewer");
  await page.getByRole("button", { name: "Create invitation" }).click();
  const link = page.getByLabel("Invitation link", { exact: true });
  await expect(link).toBeVisible();
  const url = await link.inputValue();
  const context = await browser.newContext();
  const viewer = await context.newPage();
  await viewer.goto(url);
  await viewer
    .getByRole("link", { name: /Create an account and join/ })
    .click();
  await register(viewer, viewerEmail, "Team Viewer");
  await expect(
    viewer.getByRole("button", { name: "Accept invitation", exact: true }),
  ).toBeVisible();
  await viewer
    .getByRole("button", { name: "Accept invitation", exact: true })
    .click();
  await expect(
    viewer.getByRole("heading", { name: "A good place to begin." }),
  ).toBeVisible();
  await viewer.getByRole("link", { name: "Meet your team" }).click();
  await expect(viewer.getByText("Team Viewer (you)")).toBeVisible();
  await expect(
    viewer.getByRole("button", { name: "Create invitation" }),
  ).toHaveCount(0);
  await viewer.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    viewer.getByRole("button", { name: "Save changes" }),
  ).toBeDisabled();
  await page.reload();
  const viewerRow = page.getByRole("row").filter({ hasText: viewerEmail });
  await expect(viewerRow).toBeVisible();
  await viewerRow.getByRole("combobox").selectOption("admin");
  await expect(viewerRow.getByRole("combobox")).toHaveValue("admin");
  await viewer.reload();
  await expect(
    viewer.getByRole("button", { name: "Save changes" }),
  ).toBeEnabled();
  await page.screenshot({
    path: "test-results/members-desktop-light.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "New workspace", exact: true }).click();
  await page.getByLabel("Workspace name").fill(`South ${suffix}`);
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "A good place to begin." }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Switch workspace" })
    .selectOption({ label: `North ${suffix}` });
  await expect(page.locator(".page-heading .eyebrow")).toHaveText(
    `North ${suffix}`,
  );
  await page.getByRole("switch", { name: "Dark mode" }).first().click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/members");
  await expect(page.getByText("Team Owner (you)")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/members-mobile-dark.png",
    fullPage: true,
  });
  await context.close();
});

test("mobile login is usable at 390px and respects dark mode", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "Good to see you again." }),
  ).toBeVisible();
  await expect(page.getByLabel("Email address")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(
    await page
      .getByLabel("Email address")
      .evaluate((element) => parseFloat(getComputedStyle(element).fontSize)),
  ).toBeGreaterThanOrEqual(16);
  await page.getByRole("switch", { name: "Dark mode" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.screenshot({
    path: "test-results/mobile-login-dark.png",
    fullPage: true,
  });
});
