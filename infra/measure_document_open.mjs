// Synthetic browser timing only: never save cookies, response bodies or document text.
import {
  chromium,
  request,
} from "../frontend/node_modules/playwright/index.mjs";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
const origin = process.argv[2] || "http://localhost:3000";
const output = process.argv[3] || "docs/slice7-document-open-profile.json";
const api = await request.newContext({ baseURL: origin });
let browser;
async function write(path, data) {
  const csrf = await (await api.get("/api/auth/csrf")).json();
  const response = await api.post("/api" + path, {
    data,
    headers: { "X-CSRF-Token": csrf.csrf_token },
  });
  if (!response.ok())
    throw Error("Synthetic fixture HTTP " + response.status());
  return response.json();
}
const round = (x) => Math.round(x * 100) / 100;
try {
  await write("/auth/register", {
    name: "Open profile",
    email: `doc-open-${Date.now()}@example.com`,
    password: crypto.randomUUID() + "!",
  });
  const workspace = await write("/workspaces", {
    name: "Synthetic open profile",
  });
  const base = `/workspaces/${workspace.id}`;
  const project = await write(base + "/projects", {
    name: "Profile",
    key: "OPEN",
  });
  const document = await write(base + "/documents", {
    project_id: project.id,
    title: "Synthetic 50 KB open profile",
  });
  const fixture = JSON.parse(
    execFileSync(
      "backend/.venv/bin/python",
      [
        "-c",
        "import json; from app.documents.service import transform; print(json.dumps(transform(action='template',text='# Open probe\\n'+('Synthetic measurement paragraph. '*1600)+'\\nDOCOPENPROBE')))",
      ],
      { env: { ...process.env, PYTHONPATH: "backend" }, maxBuffer: 300000 },
    ),
  );
  await write(base + `/documents/${document.id}/sync`, {
    update: fixture.state,
  });
  browser = await chromium.launch({
    executablePath:
      process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
  });
  const samples = [];
  for (let pair = 0; pair < 3; pair++) {
    const context = await browser.newContext({
      baseURL: origin,
      storageState: await api.storageState(),
      serviceWorkers: "block",
    });
    await context.addInitScript(() => {
      const profile = {
        editor_dom_ms: null,
        content_ms: null,
        socket_created_ms: null,
        socket_open_ms: null,
        first_state_ms: null,
        first_state_utf8_bytes: null,
        indexeddb_open_ms: [],
      };
      window.__documentOpenProfile = profile;
      const nativeOpen = indexedDB.open.bind(indexedDB);
      indexedDB.open = (...args) => {
        const started = performance.now();
        const result = nativeOpen(...args);
        result.addEventListener("success", () =>
          profile.indexeddb_open_ms.push(performance.now() - started),
        );
        return result;
      };
      const NativeSocket = window.WebSocket;
      window.WebSocket = class extends NativeSocket {
        constructor(url, protocols) {
          super(url, protocols);
          if (!String(url).includes("/api/document-sync/")) return;
          profile.socket_created_ms ??= performance.now();
          this.addEventListener("open", () => {
            profile.socket_open_ms ??= performance.now();
          });
          this.addEventListener("message", (event) => {
            if (
              profile.first_state_ms !== null ||
              typeof event.data !== "string"
            )
              return;
            if (JSON.parse(event.data).type === "state") {
              profile.first_state_ms = performance.now();
              profile.first_state_utf8_bytes = new TextEncoder().encode(
                event.data,
              ).byteLength;
            }
          });
        }
      };
      const observer = new MutationObserver(() => {
        const editor = document.querySelector(
          '[role="textbox"][aria-label="Document content"]',
        );
        if (editor) profile.editor_dom_ms ??= performance.now();
        if (editor?.textContent.includes("DOCOPENPROBE"))
          profile.content_ms ??= performance.now();
      });
      observer.observe(document, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    });
    for (const temperature of ["cold_context", "warm_context"]) {
      const page = await context.newPage();
      const cdp = await context.newCDPSession(page);
      await cdp.send("Performance.enable");
      const before = Object.fromEntries(
        (await cdp.send("Performance.getMetrics")).metrics.map((x) => [
          x.name,
          x.value,
        ]),
      );
      const started = performance.now();
      await page.goto("/documents?document=" + document.id);
      await page
        .getByRole("textbox", { name: "Document content", exact: true })
        .getByText("DOCOPENPROBE", { exact: true })
        .waitFor();
      const visible = performance.now() - started;
      await page.waitForFunction(
        () => window.__documentOpenProfile.first_state_ms !== null,
      );
      const after = Object.fromEntries(
        (await cdp.send("Performance.getMetrics")).metrics.map((x) => [
          x.name,
          x.value,
        ]),
      );
      const timing = await page.evaluate(() => {
        const resources = performance.getEntriesByType("resource");
        const scripts = resources.filter((x) => x.initiatorType === "script");
        const apis = resources
          .filter((x) => new URL(x.name).pathname.startsWith("/api/"))
          .map((x) => {
            const path = new URL(x.name).pathname;
            const category = path.startsWith("/api/auth/")
              ? path
              : path
                  .replace(/\/workspaces\/[^/]+/, "/workspaces/:wid")
                  .replace(/\/documents\/[^/]+/, "/documents/:did");
            return {
              category,
              start_ms: x.startTime,
              response_end_ms: x.responseEnd,
              duration_ms: x.duration,
              encoded_bytes: x.encodedBodySize,
              decoded_bytes: x.decodedBodySize,
            };
          });
        const navigation = performance.getEntriesByType("navigation")[0];
        return {
          ...window.__documentOpenProfile,
          navigation_response_end_ms: navigation.responseEnd,
          dom_content_loaded_ms: navigation.domContentLoadedEventEnd,
          scripts: scripts.map((x) => ({
            file: new URL(x.name).pathname.split("/").at(-1),
            response_end_ms: x.responseEnd,
            duration_ms: x.duration,
            encoded_bytes: x.encodedBodySize,
            decoded_bytes: x.decodedBodySize,
            transfer_bytes: x.transferSize,
          })),
          apis,
        };
      });
      samples.push({
        pair: pair + 1,
        temperature,
        host_navigation_to_locator_ms: round(visible),
        ...timing,
        main_thread_script_ms: round(
          (after.ScriptDuration - before.ScriptDuration) * 1000,
        ),
        main_thread_task_ms: round(
          (after.TaskDuration - before.TaskDuration) * 1000,
        ),
        layout_ms: round((after.LayoutDuration - before.LayoutDuration) * 1000),
      });
      await page.close();
    }
    await context.close();
  }
  const result = {
    measured_utc: new Date().toISOString(),
    mode: "synthetic_production_browser_profile",
    document_utf8_bytes: Buffer.byteLength(fixture.text),
    generation: "none",
    conditions:
      "Production Next server; unthrottled local Chromium; three fresh contexts and one warm page per context; service workers blocked; no CPU/network throttling. Cold context is not a cold server or a cold OS cache. Timeline stages overlap and must not be added.",
    original_2627ms_run:
      "No original per-stage trace was captured; these new measurements cannot establish the exact cause of that historical total.",
    samples,
  };
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n");
  console.log(
    JSON.stringify({
      output,
      samples: samples.length,
      open_ms: samples.map((s) => ({
        condition: s.temperature,
        total: s.host_navigation_to_locator_ms,
        script: s.main_thread_script_ms,
      })),
    }),
  );
} finally {
  await browser?.close();
  await api.dispose();
}
