import { WebSocketServer } from "../../sync/node_modules/ws/wrapper.mjs";
import * as Y from "../../sync/node_modules/yjs/dist/yjs.mjs";
const wss = new WebSocketServer({ port: 8892 });
const doc = new Y.Doc();
wss.on("connection", (ws) => {
  ws.send(
    JSON.stringify({
      state: Buffer.from(Y.encodeStateAsUpdate(doc)).toString("base64"),
    }),
  );
  ws.on("message", (raw) => {
    const m = JSON.parse(raw);
    if (m.role !== "editor") return ws.send(JSON.stringify({ denied: true }));
    try {
      Y.applyUpdate(doc, Buffer.from(m.update, "base64"));
    } catch {
      return ws.send(JSON.stringify({ invalid: true }));
    }
    for (const peer of wss.clients)
      peer.send(
        JSON.stringify({
          state: Buffer.from(Y.encodeStateAsUpdate(doc)).toString("base64"),
        }),
      );
  });
});
