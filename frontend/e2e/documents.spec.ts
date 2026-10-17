import * as Y from "yjs";
import { test, expect, type BrowserContext } from "@playwright/test";
async function write(
  c: BrowserContext,
  path: string,
  data: unknown,
  method = "POST",
) {
  const csrf = await (await c.request.get("/api/auth/csrf")).json();
  const r = await c.request.fetch("/api" + path, {
    method,
    data,
    headers: { "X-CSRF-Token": csrf.csrf_token },
  });
  expect(r.ok(), `${method} ${path} ${r.status()}`).toBeTruthy();
  return r.status() === 204 ? null : r.json();
}
test("documents co-edit, offline merge, suggestions, history, private revocation and mobile RTL", async ({
  browser,
}, info) => {
  test.setTimeout(180000);
  const a = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
    }),
    b = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const stamp = Date.now();
  await write(a, "/auth/register", {
    name: "Document owner",
    email: `doc-owner-${stamp}@example.com`,
    password: "synthetic-doc-password-123",
  });
  const u = await write(b, "/auth/register", {
    name: "Document editor",
    email: `doc-editor-${stamp}@example.com`,
    password: "synthetic-doc-password-123",
  });
  const w = await write(a, "/workspaces", { name: "Document Studio" });
  const base = `/workspaces/${w.id}`;
  const inv = await write(a, base + "/invitations", {
    email: u.email,
    role: "editor",
  });
  await write(
    b,
    `/invitations/${new URL(inv.invite_url).searchParams.get("token")}/accept`,
    {},
  );
  const project = await write(a, base + "/projects", {
    name: "Platform",
    key: "DOC",
  });
  const doc = await write(a, base + "/documents", {
    project_id: project.id,
    title: "Collaborative specification",
    type: "spec",
  });
  await write(
    a,
    base + "/agent/settings",
    {
      enabled: true,
      provider_chain: ["groq"],
      monthly_run_limit: 1000,
      pause_at_limit: true,
    },
    "PUT",
  );
  const pa = await a.newPage(),
    pb = await b.newPage();
  let ownerUpdateFrames = 0;
  pa.on("websocket", (ws) =>
    ws.on("framesent", (frame) => {
      try {
        if (JSON.parse(String(frame.payload)).type === "update")
          ownerUpdateFrames++;
      } catch {}
    }),
  );
  await Promise.all([
    pa.goto("/documents?document=" + doc.id),
    pb.goto("/documents?document=" + doc.id),
  ]);
  const ea = pa.getByRole("textbox", { name: "Document content", exact: true }),
    eb = pb.getByRole("textbox", { name: "Document content", exact: true });
  await expect(ea).toContainText("Describe the problem.");
  await expect(eb).toContainText("Describe the problem.");
  await Promise.all([ea.click(), eb.click()]);
  await Promise.all([
    pa.keyboard.press("Control+End"),
    pb.keyboard.press("Control+End"),
  ]);
  await Promise.all([
    pa.keyboard.type(" Shared alpha"),
    pb.keyboard.type(" Shared beta"),
  ]);
  await expect(ea).toContainText("Shared beta");
  await expect(eb).toContainText("Shared alpha");
  const content = (element: typeof ea) =>
    element.evaluate((el) => {
      const copy = el.cloneNode(true) as HTMLElement;
      copy
        .querySelectorAll(
          ".collaboration-carets__caret,.collaboration-carets__label",
        )
        .forEach((node) => node.remove());
      return copy.textContent;
    });
  await expect
    .poll(async () => (await content(ea)) === (await content(eb)))
    .toBeTruthy();
  // Edit inside the same first word on both clients, not just separate paragraphs.
  await Promise.all([ea.click(), eb.click()]);
  await Promise.all([
    pa.keyboard.press("Control+Home"),
    pb.keyboard.press("Control+Home"),
  ]);
  await Promise.all([
    pa.keyboard.press("ArrowRight"),
    pb.keyboard.press("ArrowRight"),
  ]);
  await Promise.all([pa.keyboard.type("A"), pb.keyboard.type("B")]);
  await expect
    .poll(async () => (await content(ea)) === (await content(eb)))
    .toBeTruthy();
  await pa.screenshot({
    path: info.outputPath("editor-live-cursors.png"),
    fullPage: true,
  });
  await expect
    .poll(() =>
      pb.evaluate(async () =>
        Boolean(
          await (await caches.open("tandem-chat-shell-v1")).match("/documents"),
        ),
      ),
    )
    .toBeTruthy();
  await b.setOffline(true);
  await eb.click();
  await pb.keyboard.press("Control+End");
  await pb.keyboard.type(" Offline gamma");
  await expect(
    pb.getByRole("status").filter({ hasText: "Offline — saved locally" }),
  ).toBeVisible();
  await pb.reload();
  await expect(eb).toContainText("Offline gamma");
  await ea.click();
  await pa.keyboard.press("Control+End");
  await pa.keyboard.type(" Online delta");
  await expect(ea).toContainText("Online delta");
  await b.setOffline(false);
  await expect(ea).toContainText("Offline gamma");
  await expect(eb).toContainText("Online delta");
  expect(ownerUpdateFrames).toBeLessThan(180);
  await pa
    .getByRole("textbox", { name: "Ask Agent", exact: true })
    .fill("Improve the specification with a suggestion.");
  await pa.getByRole("button", { name: "Ask Agent", exact: true }).click();
  await expect(pa.locator(".document-suggestion")).toContainText("proposed", {
    timeout: 30000,
  });
  await pa.screenshot({
    path: info.outputPath("suggestions.png"),
    fullPage: true,
  });
  await pa.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(ea).toContainText("Improved specification");
  await pa.getByRole("button", { name: "Versions", exact: true }).click();
  await pa
    .getByRole("textbox", { name: "Version name", exact: true })
    .fill("Reviewed milestone");
  await pa.getByRole("button", { name: "Save version", exact: true }).click();
  await expect(
    pa.getByText("Reviewed milestone", { exact: true }),
  ).toBeVisible();
  await pa.screenshot({
    path: info.outputPath("version-history.png"),
    fullPage: true,
  });
  const secret = await write(a, base + "/documents", {
    project_id: project.id,
    title: "Private postmortem",
    is_private: true,
    type: "bug_postmortem",
  });
  await write(a, base + `/documents/${secret.id}/members/${u.id}`, {}, "PUT");
  await Promise.all([
    pa.goto("/documents?document=" + secret.id),
    pb.goto("/documents?document=" + secret.id),
  ]);
  await expect(eb).toContainText("Bug postmortem");
  await pa.screenshot({
    path: info.outputPath("private-document.png"),
    fullPage: true,
  });
  await b.setOffline(true);
  await eb.click();
  await pb.keyboard.press("Control+End");
  await pb.keyboard.insertText(" تغييرات محلية عربية");
  await pb.setViewportSize({ width: 390, height: 844 });
  await expect(
    pb.getByRole("status").filter({ hasText: "Offline — edits stay" }),
  ).toBeVisible();
  await pb.screenshot({
    path: info.outputPath("mobile-document-offline.png"),
    fullPage: true,
  });
  await write(
    a,
    base + `/documents/${secret.id}/members/${u.id}`,
    undefined,
    "DELETE",
  );
  await b.setOffline(false);
  await expect(
    pb.getByRole("heading", { name: "Rejected changes", exact: true }),
  ).toBeVisible();
  await expect(pb.getByLabel("Rejected changes")).toContainText(
    "تغييرات محلية عربية",
  );
  expect(
    (
      await (
        await a.request.get("/api" + base + `/documents/${secret.id}`)
      ).json()
    ).text,
  ).not.toContain("تغييرات محلية عربية");
  await a.close();
  await b.close();
});

test("Viewer updates are rejected and session revocation closes document sync", async ({
  browser,
}) => {
  const a = await browser.newContext(),
    b = await browser.newContext();
  const stamp = Date.now();
  await write(a, "/auth/register", {
    name: "Owner",
    email: `doc-role-owner-${stamp}@example.com`,
    password: "synthetic-doc-role-password",
  });
  const user = await write(b, "/auth/register", {
    name: "Viewer",
    email: `doc-role-viewer-${stamp}@example.com`,
    password: "synthetic-doc-role-password",
  });
  const w = await write(a, "/workspaces", { name: "Document role boundaries" }),
    base = `/workspaces/${w.id}`;
  const inv = await write(a, base + "/invitations", {
    email: user.email,
    role: "viewer",
  });
  await write(
    b,
    `/invitations/${new URL(inv.invite_url).searchParams.get("token")}/accept`,
    {},
  );
  const p = await write(a, base + "/projects", {
    name: "Read only",
    key: "VIEW",
  });
  const d = await write(a, base + "/documents", {
    project_id: p.id,
    title: "Viewer document",
  });
  const inert = new Y.Doc();
  const paragraph = new Y.XmlElement("paragraph");
  const literal = new Y.XmlText();
  literal.insert(
    0,
    'Mixed العربية <img src=x onerror="globalThis.docXss=true">',
  );
  paragraph.insert(0, [literal]);
  inert.getXmlFragment("default").insert(0, [paragraph]);
  await write(a, base + `/documents/${d.id}/sync`, {
    update: Buffer.from(Y.encodeStateAsUpdate(inert)).toString("base64"),
  });
  const page = await b.newPage();
  await page.goto("/documents?document=" + d.id);
  await expect(
    page.getByRole("textbox", { name: "Document content", exact: true }),
  ).toContainText("<img src=x");
  await expect(page.locator(".document-content img")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => (globalThis as unknown as { docXss?: boolean }).docXss,
    ),
  ).toBeUndefined();
  await expect(
    page.getByRole("textbox", { name: "Document content", exact: true }),
  ).toHaveAttribute("contenteditable", "false");
  const result = await page.evaluate(
    async ({ wid, did }) => {
      const socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/document-sync/${wid}/${did}`,
      );
      const holder = globalThis as unknown as {
        acceptanceSocket: WebSocket;
        acceptanceClose: number;
      };
      holder.acceptanceSocket = socket;
      socket.onclose = (e) => {
        holder.acceptanceClose = e.code;
      };
      return new Promise<boolean>((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error("Viewer denial timeout")),
          5000,
        );
        socket.onmessage = (e) => {
          const value = JSON.parse(e.data);
          if (value.type === "state")
            socket.send(
              JSON.stringify({
                type: "update",
                update: "AAA=",
                update_id: "viewer-probe",
              }),
            );
          if (value.type === "rejected") {
            clearTimeout(timer);
            resolve(true);
          }
        };
      });
    },
    { wid: w.id, did: d.id },
  );
  expect(result).toBeTruthy();
  await write(b, "/auth/logout", {});
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (globalThis as unknown as { acceptanceClose: number })
            .acceptanceClose,
      ),
    )
    .toBe(4003);
  await a.close();
  await b.close();
});
