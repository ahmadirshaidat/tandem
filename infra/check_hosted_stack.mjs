import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import https from "node:https";
import http from "node:http";
import net from "node:net";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
process.chdir(fileURLToPath(new URL("../", import.meta.url)));
// Local-only smoke: fresh containers, synthetic data, no provider calls or SMTP sends.
const require = createRequire(new URL("../sync/package.json", import.meta.url));
const { WebSocket } = require("ws"),
  Y = require("yjs");
const stamp = "tandem-hosted-check-" + Date.now(),
  names = [],
  volumes = [];
const dir = mkdtempSync(".local/tls-check-");
const run = (...args) =>
  execFileSync("docker", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
const secret = () => randomBytes(32).toString("hex");
function start(name, image, env = {}, extra = []) {
  const full = stamp + "-" + name;
  names.push(full);
  const args = [
    "run",
    "-d",
    "--name",
    full,
    "--network",
    stamp,
    "--network-alias",
    name,
    ...Object.keys(env).flatMap((k) => ["-e", k]),
    ...extra,
    image,
  ];
  execFileSync("docker", args, {
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  return full;
}
const delay = (ms) => new Promise((r) => setTimeout(r, ms));
async function wait(fn, label) {
  const end = Date.now() + 180000;
  while (Date.now() < end) {
    try {
      if (await fn()) return;
    } catch {}
    await delay(1000);
  }
  throw Error(label + " timeout");
}
let upstream = 0,
  ws;
execFileSync(
  "openssl",
  [
    "req",
    "-x509",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-keyout",
    dir + "/key",
    "-out",
    dir + "/cert",
    "-days",
    "1",
    "-subj",
    "/CN=localhost",
    "-addext",
    "subjectAltName=DNS:localhost,IP:127.0.0.1",
  ],
  { stdio: "ignore" },
);
const cert = readFileSync(dir + "/cert");
const proxy = https.createServer(
  { key: readFileSync(dir + "/key"), cert },
  (req, res) => {
    const out = http.request(
      {
        host: "127.0.0.1",
        port: upstream,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, "x-forwarded-proto": "https" },
      },
      (r) => {
        res.writeHead(r.statusCode, r.headers);
        r.pipe(res);
      },
    );
    out.on("error", () => {
      res.writeHead(502);
      res.end();
    });
    req.pipe(out);
  },
);
proxy.on("upgrade", (req, socket, head) => {
  const target = net.connect(upstream, "127.0.0.1", () => {
    target.write(
      `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n` +
        req.rawHeaders.reduce(
          (s, h, i) => s + h + (i % 2 ? "\r\n" : ": "),
          "",
        ) +
        "\r\n",
    );
    if (head.length) target.write(head);
    socket.pipe(target);
    target.pipe(socket);
  });
  target.on("error", () => socket.destroy());
  socket.on("error", () => target.destroy());
  socket.on("close", () => target.destroy());
});
await new Promise((r) => proxy.listen(0, "127.0.0.1", r));
const origin = "https://127.0.0.1:" + proxy.address().port,
  cookies = new Map();
function request(
  path,
  { method = "GET", body, anonymous = false, headers = {} } = {},
) {
  return new Promise((resolve, reject) => {
    const req = https.request(
      origin + path,
      {
        ca: cert,

        method,
        headers: {
          Origin: origin,
          ...(!anonymous
            ? { Cookie: [...cookies].map(([k, v]) => k + "=" + v).join("; ") }
            : {}),
          ...(body ? { "Content-Type": "application/json" } : {}),
          ...headers,
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          if (!anonymous)
            for (const item of res.headers["set-cookie"] || []) {
              const first = item.split(";")[0],
                i = first.indexOf("=");
              cookies.set(first.slice(0, i), first.slice(i + 1));
            }
          const raw = Buffer.concat(chunks).toString();
          let json;
          try {
            json = JSON.parse(raw);
          } catch {}
          resolve({ status: res.statusCode, json, headers: res.headers });
        });
      },
    );
    req.on("error", reject);
    req.setTimeout(15000, () => req.destroy(Error("request timeout")));
    req.end(body ? JSON.stringify(body) : undefined);
  });
}
async function write(path, body) {
  const csrf = await request("/api/auth/csrf");
  assert.equal(csrf.status, 200);
  const r = await request("/api" + path, {
    method: "POST",
    body,
    headers: { "X-CSRF-Token": csrf.json.csrf_token },
  });
  assert.ok(r.status >= 200 && r.status < 300, "API write status " + r.status);
  return r;
}
try {
  run("network", "create", stamp);
  const password = secret(),
    syncSecret = secret();
  start("db", "pgvector/pgvector:pg17", {
    POSTGRES_USER: "tandem",
    POSTGRES_DB: "tandem",
    POSTGRES_PASSWORD: password,
  });
  await wait(
    () =>
      run(
        "exec",
        stamp + "-db",
        "pg_isready",
        "-U",
        "tandem",
        "-d",
        "tandem",
      ).includes("accepting"),
    "database",
  );
  const volume = stamp + "-data";
  run("volume", "create", volume);
  volumes.push(volume);
  const seed = start("seed", "tandem-hosted-backend:local", {}, [
    "--user",
    "0:0",
    "-v",
    volume + ":/data",
    "--entrypoint",
    "sh",
  ]);
  // The seed shell exits; copying into its volume requires no production credentials.
  run("cp", ".local/models/e5-small", seed + ":/data/");
  run(
    "run",
    "--rm",
    "--user",
    "0:0",
    "-v",
    volume + ":/data",
    "--entrypoint",
    "sh",
    "tandem-hosted-backend:local",
    "-c",
    "mkdir -p /data/models && mv /data/e5-small /data/models/e5-small && chown -R 10001:10001 /data",
  );
  const backend = start(
    "backend",
    "tandem-hosted-backend:local",
    {
      DATABASE_URL: `postgresql://tandem:${password}@db:5432/tandem`,
      JWT_SECRET: secret(),
      DOCUMENT_SYNC_SECRET: syncSecret,
      FRONTEND_URL: origin,
      COOKIE_SECURE: "true",
      MAIL_MODE: "resend",
      RESEND_API_KEY: "synthetic-local-smoke-key-never-used",
      MAIL_FROM: "synthetic@example.com",
      AGENT_FAKE_PROVIDER: "false",
      AGENT_WORKER_ENABLED: "false",
      DOCUMENT_SYNC_URL: "http://document-sync:8002",
      MEMORY_EMBEDDING_ENABLED: "true",
    },
    ["--user", "0:0", "-v", volume + ":/data"],
  );
  start("document-sync", "tandem-document-sync:latest", {
    DOCUMENT_SYNC_SECRET: syncSecret,
    DOCUMENT_BACKEND_URL: "http://backend:8000",
    FRONTEND_URL: origin,
    DOCUMENT_SYNC_HOST: "0.0.0.0",
  });
  await wait(
    () =>
      run(
        "exec",
        backend,
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')",
      ) === "",
    "backend",
  );
  const front = start("frontend", "tandem-hosted-frontend:local", {}, [
    "-p",
    "127.0.0.1::3000",
  ]);
  upstream = Number(run("port", front, "3000/tcp").split(":").at(-1));
  await wait(async () => (await request("/login")).status === 200, "frontend");
  assert.equal(
    (await request("/api/workspaces", { anonymous: true })).status,
    401,
  );
  const registered = await write("/auth/register", {
    name: "Synthetic hosted owner",
    email: "hosted-" + Date.now() + "@example.com",
    password: secret() + "!",
  });
  const authCookies = (registered.headers["set-cookie"] || []).filter(
    (c) => c.startsWith("tandem_access=") || c.startsWith("tandem_refresh="),
  );
  assert.equal(authCookies.length, 2);
  assert.ok(authCookies.every((c) => /; Secure/i.test(c)));
  const w = (await write("/workspaces", { name: "Synthetic hosted smoke" }))
      .json,
    base = "/workspaces/" + w.id;
  const p = (
    await write(base + "/projects", {
      name: "Synthetic hosted project",
      key: "HOST",
    })
  ).json;
  const doc = (
    await write(base + "/documents", {
      project_id: p.id,
      title: "Synthetic hosted document",
      type: "spec",
    })
  ).json;
  const memory = await request("/api" + base + "/memory/settings");
  assert.equal(memory.status, 200);
  assert.equal(memory.json.degraded, false);
  const uid = run("exec", backend, "cat", "/proc/1/status")
    .split("\n")
    .find((l) => l.startsWith("Uid:"))
    .split(/\s+/)
    .slice(1)
    .map(Number);
  assert.ok(uid.every((v) => v === 10001));
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error("websocket timeout")), 20000);
    ws = new WebSocket(
      origin.replace("https:", "wss:") +
        "/api/document-sync/" +
        w.id +
        "/" +
        doc.id,
      {
        ca: cert,

        headers: {
          Origin: origin,
          Cookie: [...cookies].map(([k, v]) => k + "=" + v).join("; "),
        },
      },
    );
    let sent = false;
    ws.on("error", reject);
    ws.on("message", (raw) => {
      try {
        const m = JSON.parse(raw);
        if (m.type === "state" && !sent) {
          sent = true;
          const y = new Y.Doc();
          Y.applyUpdate(y, Buffer.from(m.state, "base64"));
          const para = new Y.XmlElement("paragraph"),
            text = new Y.XmlText();
          text.insert(0, "Synthetic hosted websocket persistence.");
          para.insert(0, [text]);
          const f = y.getXmlFragment("default");
          f.insert(f.length, [para]);
          ws.send(
            JSON.stringify({
              type: "update",
              update: Buffer.from(Y.encodeStateAsUpdate(y)).toString("base64"),
              update_id: "synthetic",
            }),
          );
        }
        if (m.type === "ack" && m.update_id === "synthetic") {
          clearTimeout(timer);
          resolve();
        }
      } catch (e) {
        clearTimeout(timer);
        reject(e);
      }
    });
  });
  const saved = await request("/api" + base + "/documents/" + doc.id);
  assert.ok(
    saved.json.text.includes("Synthetic hosted websocket persistence."),
  );
  console.log(
    JSON.stringify(
      {
        status: "passed",
        https_login: true,
        secure_auth_cookies: true,
        unauthenticated_denied: true,
        e5_active: true,
        model: { name: memory.json.model, version: memory.json.version },
        backend_uid: 10001,
        websocket_ack: true,
        document_persisted: true,
        fake_provider: false,
        agent_worker: false,
        provider_calls: 0,
        email_mode: "resend",
        email_delivery: "not tested; no email requests made",
        hosting: "local containers; Railway and Sites not deployed",
      },
      null,
      2,
    ),
  );
} catch (error) {
  console.error(
    JSON.stringify({
      status: "failed",
      check: error.name,
      message: error.message,
    }),
  );
  process.exitCode = 1;
} finally {
  ws?.terminate();
  proxy.closeAllConnections();
  await new Promise((r) => proxy.close(r));
  for (const name of names.reverse()) {
    try {
      run("rm", "-f", name);
    } catch {}
  }
  for (const v of volumes) {
    try {
      run("volume", "rm", v);
    } catch {}
  }
  try {
    run("network", "rm", stamp);
  } catch {}
  rmSync(dir, { recursive: true, force: true });
}
