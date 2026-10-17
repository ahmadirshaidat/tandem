import {
  request,
  chromium,
} from "../frontend/node_modules/playwright/index.mjs";
import WebSocket from "../sync/node_modules/ws/wrapper.mjs";
import * as Y from "../sync/node_modules/yjs/dist/yjs.mjs";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
const origin = process.argv[2] || "http://localhost:3000";
const a = await request.newContext({ baseURL: origin }),
  b = await request.newContext({ baseURL: origin });
async function write(c, path, data, method = "POST") {
  const csrf = await (await c.get("/api/auth/csrf")).json();
  const r = await c.fetch("/api" + path, {
    method,
    data,
    headers: { "X-CSRF-Token": csrf.csrf_token },
  });
  if (!r.ok()) throw Error("Synthetic fixture HTTP " + r.status());
  return r.json();
}
const stamp = Date.now();
await write(a, "/auth/register", {
  name: "Sync measure owner",
  email: `measure-doc-a-${stamp}@example.com`,
  password: crypto.randomUUID() + "!",
});
const u = await write(b, "/auth/register", {
  name: "Sync measure editor",
  email: `measure-doc-b-${stamp}@example.com`,
  password: crypto.randomUUID() + "!",
});
const w = await write(a, "/workspaces", { name: "Synthetic sync performance" }),
  base = `/workspaces/${w.id}`;
const invite = await write(a, base + "/invitations", {
  email: u.email,
  role: "editor",
});
await write(
  b,
  `/invitations/${new URL(invite.invite_url).searchParams.get("token")}/accept`,
  {},
);
const p = await write(a, base + "/projects", {
  name: "Measured project",
  key: "PERF",
});
const d = await write(a, base + "/documents", {
  project_id: p.id,
  title: "50 KB synthetic document",
});
const projected = JSON.parse(
  execFileSync(
    "backend/.venv/bin/python",
    [
      "-c",
      "import json; from app.documents.service import transform; print(json.dumps(transform(action='template',text='# Sync probe\\n'+('Synthetic measurement paragraph. '*1600)+'\\nDOCINDEXPROBE')))",
    ],
    { env: { ...process.env, PYTHONPATH: "backend" }, maxBuffer: 300000 },
  ),
);
const indexStart = performance.now();
await write(a, base + `/documents/${d.id}/sync`, { update: projected.state });
async function connect(c) {
  const cookie = (await c.storageState()).cookies
    .map((c) => c.name + "=" + c.value)
    .join("; ");
  const ws = new WebSocket(
    origin.replace(/^http/, "ws") + `/api/document-sync/${w.id}/${d.id}`,
    { headers: { origin, cookie } },
  );
  const doc = new Y.Doc();
  await new Promise((resolve, reject) => {
    ws.once("error", reject);
    ws.once("message", (m) => {
      Y.applyUpdate(doc, Buffer.from(JSON.parse(m).state, "base64"));
      resolve();
    });
  });
  return { ws, doc };
}
const writer = await connect(a),
  reader = await connect(b);
let done = null;
reader.ws.on("message", (raw) => {
  const m = JSON.parse(raw);
  if (m.state) {
    Y.applyUpdate(reader.doc, Buffer.from(m.state, "base64"));
    done?.();
  }
});
const times = [];
for (let i = 0; i < 30; i++) {
  const text = writer.doc.getXmlFragment("default").get(1).get(0);
  const vector = Y.encodeStateVector(writer.doc);
  text.insert(text.length, "x");
  const target = text.length;
  const received = new Promise((resolve) => {
    done = () => {
      if (reader.doc.getXmlFragment("default").get(1).get(0).length >= target) {
        done = null;
        resolve();
      }
    };
  });
  const start = performance.now();
  writer.ws.send(
    JSON.stringify({
      type: "update",
      update: Buffer.from(Y.encodeStateAsUpdate(writer.doc, vector)).toString(
        "base64",
      ),
      update_id: crypto.randomUUID(),
    }),
  );
  await Promise.race([
    received,
    new Promise((_, reject) =>
      setTimeout(() => reject(Error("sync timeout")), 5000),
    ),
  ]);
  times.push(performance.now() - start);
}
let lag = null;
for (let i = 0; i < 120; i++) {
  const r = await (
    await a.get("/api" + base + "/search?query=DOCINDEXPROBE&mode=full_text")
  ).json();
  if (r.items?.some((x) => x.source_id === d.id)) {
    lag = performance.now() - indexStart;
    break;
  }
  await new Promise((r) => setTimeout(r, 250));
}
const browser = await chromium.launch({
  executablePath:
    process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/usr/bin/chromium",
});
const ctx = await browser.newContext({
  storageState: await a.storageState(),
  baseURL: origin,
});
const page = await ctx.newPage();
const opened = performance.now();
await page.goto("/documents?document=" + d.id);
await page
  .getByRole("textbox", { name: "Document content", exact: true })
  .getByText("DOCINDEXPROBE", { exact: true })
  .waitFor();
const openMs = performance.now() - opened;
const result = {
  mode: "synthetic_production_path",
  samples: 30,
  p95_sync_ms: times.sort((a, b) => a - b)[28],
  under_500_ms: times[28] < 500,
  document_utf8_bytes: Buffer.byteLength(projected.text),
  open_50kb_ms: openMs,
  indexing_lag_ms: lag,
  indexing_target_verified: lag !== null && lag < 30000,
  transport:
    "Node WS -> Python current authorization and PostgreSQL persistence -> authorized recipient",
  generation: "none",
};
fs.writeFileSync(
  "docs/slice7-document-performance.json",
  JSON.stringify(result, null, 2) + "\n",
);
console.log(JSON.stringify(result));
writer.ws.close();
reader.ws.close();
await browser.close();
await a.dispose();
await b.dispose();
