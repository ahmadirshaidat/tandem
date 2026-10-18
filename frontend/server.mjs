// Hosted entry point: keep Next on loopback and guard HTTP and WebSocket traffic.
import { spawn } from "node:child_process";
import { timingSafeEqual } from "node:crypto";
import http from "node:http";
import net from "node:net";

const gatewaySecret = process.env.SITES_GATEWAY_SECRET;
if (!gatewaySecret || gatewaySecret.length < 32) {
  throw new Error("SITES_GATEWAY_SECRET must contain at least 32 characters");
}
const expected = Buffer.from(gatewaySecret);
const port = Number(process.env.PORT || 3000);
const internalPort = 3001;
if (port === internalPort)
  throw new Error("PORT 3001 is reserved for loopback");
const child = spawn(
  process.execPath,
  [
    "node_modules/next/dist/bin/next",
    "start",
    "--hostname",
    "127.0.0.1",
    "--port",
    String(internalPort),
  ],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      PORT: String(internalPort),
      SITES_GATEWAY_SECRET: "",
    },
  },
);
function allowed(req) {
  const value = req.headers["x-tandem-gateway"];
  if (typeof value !== "string" || Buffer.byteLength(value) !== expected.length)
    return false;
  return timingSafeEqual(Buffer.from(value), expected);
}
function headers(req) {
  const result = { ...req.headers };
  delete result["x-tandem-gateway"];
  return result;
}
const server = http.createServer((req, res) => {
  const health = req.method === "GET" && req.url === "/health";
  if (!health && !allowed(req)) {
    res.writeHead(403, { "Cache-Control": "no-store" });
    res.end("Forbidden");
    return;
  }
  const upstream = http.request(
    {
      hostname: "127.0.0.1",
      port: internalPort,
      path: health ? "/login" : req.url,
      method: req.method,
      headers: headers(req),
    },
    (response) => {
      if (health) {
        response.resume();
        res.writeHead(response.statusCode === 200 ? 200 : 503, {
          "Cache-Control": "no-store",
        });
        res.end(response.statusCode === 200 ? "ok" : "unavailable");
      } else {
        res.writeHead(response.statusCode, response.headers);
        response.pipe(res);
      }
    },
  );
  upstream.on("error", () => {
    if (!res.headersSent) res.writeHead(503, { "Cache-Control": "no-store" });
    res.end("Unavailable");
  });
  req.on("aborted", () => upstream.destroy());
  res.on("close", () => upstream.destroy());
  req.pipe(upstream);
});
server.on("upgrade", (req, socket, head) => {
  if (!allowed(req)) {
    socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
    return;
  }
  const upstream = net.connect(internalPort, "127.0.0.1", () => {
    upstream.write(
      `${req.method} ${req.url} HTTP/1.1\r\n` +
        Object.entries(headers(req))
          .map(([k, v]) => `${k}: ${v}\r\n`)
          .join("") +
        "\r\n",
    );
    if (head.length) upstream.write(head);
    socket.pipe(upstream);
    upstream.pipe(socket);
  });
  upstream.on("error", () => socket.destroy());
  socket.on("error", () => upstream.destroy());
  socket.on("close", () => upstream.destroy());
});
server.listen(port, "::");
child.on("error", () => process.exit(1));
child.on("exit", (code) => process.exit(code || 1));
for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => {
    child.kill(signal);
    server.close();
    setTimeout(() => process.exit(0), 5000).unref();
  });
}
