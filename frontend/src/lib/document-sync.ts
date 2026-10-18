import * as Y from "yjs";
import { api } from "./api";
import type { DocumentSyncEvent } from "./events.generated";
import {
  Awareness,
  applyAwarenessUpdate,
  encodeAwarenessUpdate,
} from "y-protocols/awareness";
import { IndexeddbPersistence } from "y-indexeddb";
export const b64 = (value: Uint8Array) =>
  btoa(Array.from(value, (x) => String.fromCharCode(x)).join(""));
const bytes = (value: string) =>
  Uint8Array.from(atob(value), (x) => x.charCodeAt(0));
export class DocumentSync {
  awareness: Awareness;
  persistence: IndexeddbPersistence;
  socket: WebSocket | null = null;
  status = "Not synced yet";
  canEdit: boolean;
  rejected = false;
  private listeners = new Set<() => void>();
  private vector: Uint8Array | null = null;
  private lastSent = "";
  private dirty = false;
  private version = 0;
  private sentVersions = new Map<string, number>();
  private firstState = true;
  private closed = false;
  private retry: ReturnType<typeof setTimeout> | null = null;
  constructor(
    public doc: Y.Doc,
    public workspaceId: string,
    public documentId: string,
    public userId: string,
    editable: boolean,
  ) {
    this.canEdit = editable;
    this.dirty = !!localStorage.getItem(this.key + ":dirty");
    this.awareness = new Awareness(doc);
    this.rejected = !!localStorage.getItem(this.rejectedKey);
    this.persistence = new IndexeddbPersistence(this.key, doc);
    doc.on("update", this.updated);
    this.awareness.on("update", this.awarenessChanged);
    this.persistence.whenSynced.then(() => {
      this.notify();
      if (!this.rejected) this.connect();
    });
    window.addEventListener("online", this.connect);
    window.addEventListener("offline", this.offline);
  }
  get key() {
    return `tandem-document:${this.userId}:${this.workspaceId}:${this.documentId}`;
  }
  get rejectedKey() {
    return this.key + ":rejected";
  }
  onChange(fn: () => void) {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }
  private notify() {
    for (const fn of this.listeners) fn();
  }
  private retain = () => {
    this.rejected = true;
    this.canEdit = false;
    this.status = "Rejected changes";
    localStorage.setItem(
      this.rejectedKey,
      b64(Y.encodeStateAsUpdate(this.doc)),
    );
    this.notify();
  };
  private offline = () => {
    this.status = "Offline — not synced yet";
    this.socket?.close();
    this.notify();
  };
  private updated = (_: Uint8Array, origin: unknown) => {
    if (origin === "server" || origin === this.persistence || !this.canEdit)
      return;
    this.dirty = true;
    this.version++;
    localStorage.setItem(this.key + ":dirty", "1");
    this.status = navigator.onLine
      ? "Not synced yet"
      : "Offline — not synced yet";
    this.send();
    const version = this.version;
    void this.persistence.set("last-local-edit", version).then(() => {
      if (!navigator.onLine && this.version === version && !this.rejected) {
        this.status = "Offline — saved locally, not synced yet";
        this.notify();
      }
    });
    this.notify();
  };
  private awarenessChanged = (
    {
      added,
      updated,
      removed,
    }: { added: number[]; updated: number[]; removed: number[] },
    origin: unknown,
  ) => {
    if (origin === "server") return;
    if (this.socket?.readyState === WebSocket.OPEN)
      this.socket.send(
        JSON.stringify({
          type: "awareness",
          data: b64(
            encodeAwarenessUpdate(this.awareness, [
              ...added,
              ...updated,
              ...removed,
            ]),
          ),
        }),
      );
  };
  private send() {
    if (
      !this.dirty ||
      !this.vector ||
      !this.canEdit ||
      this.rejected ||
      this.socket?.readyState !== WebSocket.OPEN
    )
      return;
    const update = Y.encodeStateAsUpdate(this.doc, this.vector);
    if (update.length <= 2) {
      this.status = "Saved to server";
      this.dirty = false;
      localStorage.removeItem(this.key + ":dirty");
      return;
    }
    const value = b64(update);
    if (value === this.lastSent) return;
    this.lastSent = value;
    const updateId = crypto.randomUUID();
    this.sentVersions.set(updateId, this.version);
    this.socket.send(
      JSON.stringify({
        type: "update",
        update: value,
        update_id: updateId,
      }),
    );
  }
  connect = () => {
    if (
      this.closed ||
      this.rejected ||
      !navigator.onLine ||
      (this.socket && this.socket.readyState < 2)
    )
      return;
    this.firstState = true;
    this.lastSent = "";
    this.vector = null;
    this.socket = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/document-sync/${this.workspaceId}/${this.documentId}`,
    );
    this.socket.onmessage = (event) => {
      const m = JSON.parse(event.data) as DocumentSyncEvent;
      if (m.type === "rejected") {
        this.retain();
        return;
      }
      if (m.type === "awareness") {
        applyAwarenessUpdate(this.awareness, bytes(m.data!), "server");
        return;
      }
      if (m.state) {
        const server = new Y.Doc();
        Y.applyUpdate(server, bytes(m.state));
        this.vector = Y.encodeStateVector(server);
        server.destroy();
        Y.applyUpdate(this.doc, bytes(m.state), "server");
        this.canEdit = m.can_edit ?? this.canEdit;
        if (!this.canEdit && this.dirty) {
          this.retain();
          return;
        }
        if (
          m.update_id &&
          this.sentVersions.get(m.update_id) === this.version
        ) {
          this.dirty = false;
          localStorage.removeItem(this.key + ":dirty");
          this.sentVersions.clear();
        }
        this.status = this.dirty ? "Not synced yet" : "Saved to server";
        // A reconnect sends pending changes once. ACKs and periodic states never echo
        // deletion sets back: a nonempty Yjs diff can contain only an already-known delete set.
        if (this.firstState) {
          this.firstState = false;
          this.send();
        }
        this.notify();
      }
    };
    this.socket.onclose = (event) => {
      this.socket = null;
      if (event.code === 4001) {
        void api("/auth/me")
          .then(() => {
            if (!this.closed) this.connect();
          })
          .catch(() => this.retain());
      } else if (event.code === 4003 || event.code === 4002) this.retain();
      else if (!this.closed && !this.rejected) {
        this.status = "Not synced yet";
        this.notify();
        this.retry = setTimeout(this.connect, 1000);
      }
    };
  };
  async discardRejected() {
    await this.persistence.clearData();
    localStorage.removeItem(this.rejectedKey);
    location.reload();
  }
  destroy() {
    this.closed = true;
    if (this.retry) clearTimeout(this.retry);
    window.removeEventListener("online", this.connect);
    window.removeEventListener("offline", this.offline);
    this.doc.off("update", this.updated);
    this.awareness.off("update", this.awarenessChanged);
    this.awareness.destroy();
    this.socket?.close();
    void this.persistence.destroy();
  }
}
