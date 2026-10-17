import { spawn } from "node:child_process";
import fs from "node:fs";
import WebSocket from "../../sync/node_modules/ws/wrapper.mjs";
import * as Y from "../../sync/node_modules/yjs/dist/yjs.mjs";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
for (const [name, cmd, args, port] of [
  [
    "python",
    "backend/.venv/bin/python",
    [
      "-m",
      "uvicorn",
      "infra.spike.python_server:app",
      "--port",
      "8891",
      "--no-access-log",
    ],
    8891,
  ],
  ["node", "node", ["infra/spike/node_server.mjs"], 8892],
]) {
  const p = spawn(cmd, args, { stdio: "ignore" });
  try {
    await sleep(1500);
    const connect = () =>
      new Promise((resolve, reject) => {
        const ws = new WebSocket(`ws://localhost:${port}/sync`);
        ws.once("message", (m) => resolve([ws, new Y.Doc(), JSON.parse(m)]));
        ws.on("error", reject);
      });
    const [a, b] = await Promise.all([connect(), connect()]);
    for (const c of [a, b])
      Y.applyUpdate(c[1], Buffer.from(c[2].state, "base64"));
    const exchange = (ws, msg) =>
      new Promise((r) => {
        ws.once("message", (m) => r(JSON.parse(m)));
        ws.send(JSON.stringify(msg));
      });
    const times = [];
    for (let i = 0; i < 100; i++) {
      const before = Y.encodeStateVector(a[1]);
      a[1].getText("probe").insert(0, "x");
      const t = performance.now();
      const got = new Promise((r) =>
        b[0].once("message", (m) => {
          Y.applyUpdate(b[1], Buffer.from(JSON.parse(m).state, "base64"));
          r();
        }),
      );
      await exchange(a[0], {
        role: "editor",
        update: Buffer.from(Y.encodeStateAsUpdate(a[1], before)).toString(
          "base64",
        ),
      });
      await got;
      times.push(performance.now() - t);
    }
    const av = Y.encodeStateVector(a[1]),
      bv = Y.encodeStateVector(b[1]);
    a[1].getText("probe").insert(1, "A");
    b[1].getText("probe").insert(1, "B");
    const ua = Y.encodeStateAsUpdate(a[1], av),
      ub = Y.encodeStateAsUpdate(b[1], bv);
    await exchange(a[0], {
      role: "editor",
      update: Buffer.from(ua).toString("base64"),
    });
    const merged = await exchange(b[0], {
      role: "editor",
      update: Buffer.from(ub).toString("base64"),
    });
    for (const c of [a, b])
      Y.applyUpdate(c[1], Buffer.from(merged.state, "base64"));
    const denied = await exchange(a[0], {
      role: "viewer",
      update: Buffer.from(ua).toString("base64"),
    });
    const invalid = await exchange(a[0], {
      role: "editor",
      update: "bm90LWFuLXVwZGF0ZQ==",
    });
    const rss = Number(
      fs
        .readFileSync(`/proc/${p.pid}/status`, "utf8")
        .match(/VmRSS:\s+(\d+)/)[1],
    );
    results.push({
      server: name,
      samples: 100,
      p95_sync_ms: times.sort((x, y) => x - y)[94],
      rss_kib: rss,
      concurrent_same_word_converged:
        a[1].getText("probe").toString() === b[1].getText("probe").toString(),
      viewer_denied: denied.denied,
      malformed_rejected: invalid.invalid,
      authorization:
        "synthetic guard only; production integration assessed separately",
    });
    a[0].close();
    b[0].close();
  } finally {
    p.kill();
    await sleep(200);
  }
}
fs.writeFileSync(
  "docs/slice7-server-spike.json",
  JSON.stringify(results, null, 2) + "\n",
);
console.log(JSON.stringify(results));
