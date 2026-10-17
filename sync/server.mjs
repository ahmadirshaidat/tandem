import http from "node:http";
import crypto from "node:crypto";
import { WebSocketServer, WebSocket } from "ws";
import { transform } from "./crdt.mjs";
import * as decoding from "lib0/decoding";
import * as encoding from "lib0/encoding";
const port = Number(process.env.DOCUMENT_SYNC_PORT || 8002),
  backend = process.env.DOCUMENT_BACKEND_URL || "http://127.0.0.1:8000";
const secret =
  process.env.DOCUMENT_SYNC_SECRET ||
  crypto
    .createHmac("sha256", process.env.JWT_SECRET || "")
    .update("tandem-document-sync")
    .digest("hex");
if (!process.env.DOCUMENT_SYNC_SECRET && !process.env.JWT_SECRET)
  throw Error("Document service secret configuration required");
const rooms = new Map();
const server = http.createServer(async (req, res) => {
  if (req.url === "/health") {
    res.writeHead(200);
    return res.end("ok");
  }
  if (
    req.url !== "/transform" ||
    req.method !== "POST" ||
    req.headers.authorization !== `Bearer ${secret}`
  ) {
    res.writeHead(404);
    return res.end();
  }
  let body = "",
    size = 0;
  try {
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 3000000) throw Error();
      body += chunk;
    }
    const out = transform(JSON.parse(body));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(out));
  } catch {
    res.writeHead(422);
    res.end("{}");
  }
});
const wss = new WebSocketServer({ noServer: true, maxPayload: 100000 });
server.on("upgrade", (req, socket, head) => {
  if (
    !/^\/api\/document-sync\/[a-f0-9-]{36}\/[a-f0-9-]{36}$/.test(req.url) ||
    req.headers.origin !== process.env.FRONTEND_URL
  ) {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => wss.emit("connection", ws, req));
});
wss.on("connection", (ws, req) => {
  const [, , , wid, id] = req.url.split("/");
  const key = wid + ":" + id;
  const peers = rooms.get(key) || new Set();
  rooms.set(key, peers);
  const csrf =
    (req.headers.cookie || "")
      .split("; ")
      .find((x) => x.startsWith("tandem_csrf="))
      ?.slice(12) || "";
  let live = true,
    busy = false,
    guard = null,
    last = Date.now(),
    count = 0,
    window = Date.now(),
    chain = Promise.resolve();
  async function api(
    method,
    body,
    suffix = method === "GET" ? "state" : "sync",
  ) {
    const r = await fetch(
      `${backend}/api/workspaces/${wid}/documents/${id}/${suffix}`,
      {
        method,
        headers: {
          cookie: req.headers.cookie || "",
          origin: req.headers.origin,
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(5000),
      },
    );
    if (!r.ok) {
      console.warn(
        JSON.stringify({ event: "document_authority", status: r.status }),
      );
      throw Error("access");
    }
    return r.json();
  }
  async function recheck() {
    try {
      const value = await api("GET");
      if (guard !== null && guard !== value.permission_stamp)
        throw Error("changed");
      guard = value.permission_stamp;
      ws.canEdit = value.can_edit;
      return value;
    } catch {
      live = false;
      ws.send(JSON.stringify({ type: "rejected" }));
      ws.close(4003, "Access changed");
      throw Error("access");
    }
  }
  const interval = setInterval(async () => {
    if (busy || !live) return;
    busy = true;
    try {
      if (Date.now() - last > 120000) {
        ws.close(4000, "Idle");
        return;
      }
      const s = await recheck();
      ws.send(
        JSON.stringify({
          type: "state",
          state: s.state,
          revision: s.revision,
          can_edit: s.can_edit,
        }),
      );
    } catch {
    } finally {
      busy = false;
    }
  }, 500);
  recheck()
    .then((s) => {
      if (!live) return;
      peers.add(ws);
      ws.send(
        JSON.stringify({
          type: "state",
          state: s.state,
          revision: s.revision,
          can_edit: s.can_edit,
        }),
      );
    })
    .catch(() => {});
  ws.on("message", (raw) => {
    chain = chain
      .then(async () => {
        last = Date.now();
        if (last - window > 60000) {
          count = 0;
          window = last;
        }
        if (++count > 240) {
          ws.close(4008, "Rate limit");
          return;
        }
        if (!live) return;
        const m = JSON.parse(raw);
        const s = await recheck();
        if (m.type === "ping") return;
        if (m.type === "awareness") {
          if (typeof m.data !== "string" || m.data.length > 12000)
            throw Error("awareness");
          const decoder = decoding.createDecoder(Buffer.from(m.data, "base64"));
          if (decoding.readVarUint(decoder) !== 1) throw Error("awareness");
          const clientId = decoding.readVarUint(decoder),
            clock = decoding.readVarUint(decoder),
            state = JSON.parse(decoding.readVarString(decoder));
          if (ws.awarenessId !== undefined && ws.awarenessId !== clientId)
            throw Error("awareness");
          ws.awarenessId = clientId;
          const encoder = encoding.createEncoder();
          encoding.writeVarUint(encoder, 1);
          encoding.writeVarUint(encoder, clientId);
          encoding.writeVarUint(encoder, clock);
          encoding.writeVarString(
            encoder,
            JSON.stringify(
              state
                ? {
                    cursor: state.cursor,
                    user: {
                      name: s.user_name,
                      color: ["#0e7c6b", "#3b3ab5", "#8a5200", "#b42318"][
                        parseInt(s.user_id.slice(0, 2), 16) % 4
                      ],
                    },
                  }
                : null,
            ),
          );
          const awarenessData = Buffer.from(
            encoding.toUint8Array(encoder),
          ).toString("base64");
          for (const p of peers) {
            if (p === ws || p.readyState !== WebSocket.OPEN) continue;
            await p.authorize?.();
            p.send(JSON.stringify({ type: "awareness", data: awarenessData }));
          }
          return;
        }
        if (m.type !== "update" || !s.can_edit) {
          ws.send(JSON.stringify({ type: "rejected" }));
          return;
        }
        const result = await api("POST", { update: m.update });
        for (const p of peers) {
          try {
            await p.authorize?.();
            p.send(
              JSON.stringify({
                type: "ack",
                state: result.state,
                revision: result.revision,
                update_id: p === ws ? m.update_id : null,
              }),
            );
          } catch {}
        }
      })
      .catch(() => {
        if (live) ws.close(4002, "Invalid update");
      });
  });
  ws.authorize = recheck;
  ws.on("close", () => {
    live = false;
    clearInterval(interval);
    peers.delete(ws);
    if (ws.canEdit && !Array.from(peers).some((p) => p.canEdit))
      api("POST", { name: null }, "versions").catch(() => {});
    if (!peers.size) rooms.delete(key);
  });
});
server.listen(port, process.env.DOCUMENT_SYNC_HOST || "127.0.0.1");
