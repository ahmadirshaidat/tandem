"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Collaboration from "@tiptap/extension-collaboration";
import CollaborationCaret from "@tiptap/extension-collaboration-caret";
import Mention from "@tiptap/extension-mention";
import Placeholder from "@tiptap/extension-placeholder";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { Plugin } from "@tiptap/pm/state";
import { Extension } from "@tiptap/core";
import * as Y from "yjs";
import {
  api,
  post as requestBody,
  type Workspace,
  type User,
  type Member,
} from "@/lib/api";
import { useOnline } from "@/lib/online";
import { cached, saveCache, prepareChatShell } from "@/lib/offline";
import { DocumentSync } from "@/lib/document-sync";
import { Button } from "./ui/button";
import { ErrorNotice } from "./common";

function post<T = unknown>(
  path: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  return api<T>(path, { ...requestBody(body), method });
}
type DocumentRow = {
  id: string;
  title: string;
  project_id: string;
  type: string;
  is_private: boolean;
  archived: boolean;
  revision: number;
};
type Proposal = {
  id: string;
  version: number;
  payload_hash: string;
  status: string;
  payload: { expected_text: string; replacement: string; reason: string };
  required_role: string;
};
type Version = {
  id: string;
  name: string | null;
  revision: number;
  created_by: string;
  actor_type: string;
  created_at: string;
};
const types = {
  spec: "Spec",
  meeting_notes: "Meeting notes",
  adr: "ADR",
  bug_postmortem: "Bug postmortem",
};
const SuggestionHighlight = Extension.create({
  name: "suggestionHighlight",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        state: {
          init: () => [] as string[],
          apply: (tr, previous) =>
            tr.getMeta("document-suggestion-highlights") ?? previous,
        },
        props: {
          decorations(state) {
            const texts = this.getState(state) as string[];
            const marks: Decoration[] = [];
            state.doc.descendants((node, pos) => {
              if (node.isText && node.text)
                for (const text of texts) {
                  const at = node.text.indexOf(text);
                  if (at >= 0)
                    marks.push(
                      Decoration.inline(pos + at, pos + at + text.length, {
                        class: "document-suggestion-highlight",
                      }),
                    );
                }
            });
            return DecorationSet.create(state.doc, marks);
          },
        },
      }),
    ];
  },
});
const Direction = Extension.create({
  name: "blockDirection",
  addGlobalAttributes() {
    return [
      {
        types: ["paragraph", "heading", "blockquote", "listItem", "codeBlock"],
        attributes: {
          dir: { default: "auto", renderHTML: () => ({ dir: "auto" }) },
        },
      },
    ];
  },
});
const EntityMention = Mention.extend({
  addAttributes() {
    return { ...this.parent?.(), entityType: { default: "document" } };
  },
}).configure({
  HTMLAttributes: { class: "document-mention" },
  renderText: ({ node }) => `@${node.attrs.label}`,
  suggestion: { char: "@", items: () => [] },
});
function download(text: string, name: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function DocumentsPage({
  workspace,
  user,
}: {
  workspace: Workspace;
  user: User;
}) {
  const router = useRouter();
  const params = useSearchParams(),
    online = useOnline(),
    client = useQueryClient();
  const selected = params.get("document");
  const [title, setTitle] = useState(""),
    [project, setProject] = useState(""),
    [type, setType] = useState("spec"),
    [privateDoc, setPrivate] = useState(false),
    [error, setError] = useState<unknown>();
  const [filterProject, setFilterProject] = useState("");
  const [filterType, setFilterType] = useState("");
  const base = `/workspaces/${workspace.id}`;
  const projects = useQuery({
    queryKey: ["doc-projects", workspace.id],
    queryFn: () =>
      api<{ projects: { id: string; name: string }[] }>(base + "/projects"),
    enabled: online,
  });
  const docs = useQuery({
    queryKey: ["documents", workspace.id, user.id, filterProject, filterType],
    networkMode: "always",
    queryFn: async () => {
      const key = `documents:${user.id}:${workspace.id}:${filterProject}:${filterType}`;
      if (!navigator.onLine)
        return (
          cached<{ documents: DocumentRow[] }>(key)?.value ?? { documents: [] }
        );
      const value = await api<{ documents: DocumentRow[] }>(
        base +
          "/documents?" +
          new URLSearchParams({
            ...(filterProject ? { project_id: filterProject } : {}),
            ...(filterType ? { type: filterType } : {}),
          }).toString(),
      );
      saveCache(key, value);
      return value;
    },
  });
  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      const d = await post<DocumentRow>(base + "/documents", {
        title,
        project_id: project || projects.data?.projects[0]?.id,
        type,
        is_private: privateDoc,
      });
      await client.invalidateQueries({ queryKey: ["documents"] });
      router.push("/documents?document=" + d.id);
    } catch (e) {
      setError(e);
    }
  }
  if (selected)
    return (
      <DocumentPage
        key={selected}
        documentId={selected}
        workspace={workspace}
        user={user}
      />
    );
  return (
    <section className="page-stack">
      <header>
        <h1>Documents</h1>
        <p>Specs, decisions and shared knowledge, written together.</p>
      </header>
      {!online && (
        <p role="status">Offline. Open a cached document to keep writing.</p>
      )}
      {error != null && <ErrorNotice error={error} />}
      {workspace.role !== "viewer" && online && (
        <form className="card card-body document-create" onSubmit={create}>
          <h2>New document</h2>
          <label>
            Title
            <input
              value={title}
              required
              maxLength={240}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            Project
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              {projects.data?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Template
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {Object.entries(types).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={privateDoc}
              onChange={(e) => setPrivate(e.target.checked)}
            />
            Private document
          </label>
          <Button type="submit">Create document</Button>
        </form>
      )}
      <div className="document-toolbar">
        <label>
          Filter by project
          <select
            value={filterProject}
            onChange={(e) => setFilterProject(e.target.value)}
          >
            <option value="">All projects</option>
            {projects.data?.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Filter by type
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="">All types</option>
            {Object.entries(types).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="document-list">
        {docs.data?.documents.map((d) => (
          <Link
            className="card card-body"
            key={d.id}
            href={"/documents?document=" + d.id}
          >
            <span className="chip">{types[d.type as keyof typeof types]}</span>
            {d.is_private && <span>Private</span>}
            <h2 dir="auto">{d.title}</h2>
          </Link>
        ))}
      </div>
      {docs.data?.documents.length === 0 && <p>No documents to show.</p>}
    </section>
  );
}

function DocumentPage({
  documentId,
  workspace,
  user,
}: {
  documentId: string;
  workspace: Workspace;
  user: User;
}) {
  const online = useOnline();
  const path = `/workspaces/${workspace.id}/documents/${documentId}`;
  const key = `document-meta:${user.id}:${workspace.id}:${documentId}`;
  const meta = useQuery({
    queryKey: ["document-meta", key],
    networkMode: "always",
    queryFn: async () => {
      if (!navigator.onLine) {
        const value = cached<DocumentRow>(key)?.value;
        if (value) return value;
        throw new Error("Open this document online before using it offline.");
      }
      const value = await api<DocumentRow>(path);
      saveCache(key, value);
      return value;
    },
  });
  if (meta.error)
    return (
      <section>
        <h1>Document unavailable</h1>
        <ErrorNotice error={meta.error} />
      </section>
    );
  if (!meta.data) return <p>Opening document…</p>;
  return (
    <DocumentEditor
      document={meta.data}
      path={path}
      user={user}
      workspace={workspace}
      online={online}
    />
  );
}
function DocumentEditor({
  document: record,
  path,
  user,
  workspace,
  online,
}: {
  document: DocumentRow;
  path: string;
  user: User;
  workspace: Workspace;
  online: boolean;
}) {
  const router = useRouter();
  const [doc] = useState(() => new Y.Doc());
  const [provider, setProvider] = useState<DocumentSync | null>(null);
  const [status, setStatus] = useState("Not synced yet");
  const [editable, setEditable] = useState(
    workspace.role !== "viewer" && !record.archived,
  );
  const [rejected, setRejected] = useState(false);
  const [error, setError] = useState<unknown>();
  const [panel, setPanel] = useState<
    "suggestions" | "versions" | "links" | "members"
  >("suggestions");
  const [versionName, setVersionName] = useState("");
  const [preview, setPreview] = useState("");
  const [question, setQuestion] = useState("");
  const [channel, setChannel] = useState("");
  const [blocks, setBlocks] = useState(false);
  const [mentionQuery, setMentionQuery] = useState("");
  const [title, setTitle] = useState(record.title);
  const [announcement, setAnnouncement] = useState("");
  useEffect(() => {
    if (process.env.NODE_ENV === "production")
      void prepareChatShell("/documents").catch(() => {});
    const p = new DocumentSync(
      doc,
      workspace.id,
      record.id,
      user.id,
      workspace.role !== "viewer" && !record.archived,
    );
    p.awareness.setLocalStateField("user", {
      name: user.name,
      color: "#0e7c6b",
    });
    void p.persistence.whenSynced.then(() => setProvider(p));
    const off = p.onChange(() => {
      setStatus(p.status);
      setEditable(p.canEdit && !p.rejected);
      setRejected(p.rejected);
    });
    return () => {
      off();
      p.destroy();
    };
  }, [
    doc,
    record.id,
    record.archived,
    user.id,
    user.name,
    workspace.id,
    workspace.role,
  ]);
  type MentionItem = { id: string; label: string; entityType: string };
  const [mentionPicker, setMentionPicker] = useState<{
    items: MentionItem[];
    command: (item: MentionItem) => void;
    index: number;
  } | null>(null);
  const editor = useEditor(
    {
      immediatelyRender: false,
      editable,
      extensions: [
        StarterKit.configure({ undoRedo: false, link: { openOnClick: false } }),
        Direction,
        SuggestionHighlight,
        EntityMention.configure({
          suggestion: {
            char: "@",
            items: async ({ query }) => {
              if (!navigator.onLine || !query) return [];
              const value = await api<{
                items: {
                  source_id: string;
                  title: string;
                  source_type: string;
                }[];
              }>(
                `/workspaces/${workspace.id}/search?query=${encodeURIComponent(query)}`,
              );
              return value.items.slice(0, 8).map((item) => ({
                id: item.source_id,
                label: item.title,
                entityType: item.source_type,
              }));
            },
            render: () => {
              let active: {
                items: MentionItem[];
                command: (item: MentionItem) => void;
                index: number;
              } | null = null;
              return {
                onStart: (props) => {
                  active = {
                    items: props.items,
                    command: props.command,
                    index: 0,
                  };
                  setMentionPicker(active);
                },
                onUpdate: (props) => {
                  active = {
                    items: props.items,
                    command: props.command,
                    index: 0,
                  };
                  setMentionPicker(active);
                },
                onKeyDown: (props) => {
                  if (props.event.key === "Escape") {
                    setMentionPicker(null);
                    return true;
                  }
                  if (!active?.items.length) return false;
                  if (props.event.key === "Enter") {
                    active.command(active.items[active.index]);
                    setMentionPicker(null);
                    return true;
                  }
                  if (["ArrowDown", "ArrowUp"].includes(props.event.key)) {
                    active = {
                      ...active,
                      index:
                        (active.index +
                          (props.event.key === "ArrowDown" ? 1 : -1) +
                          active.items.length) %
                        active.items.length,
                    };
                    setMentionPicker(active);
                    return true;
                  }
                  return false;
                },
                onExit: () => setMentionPicker(null),
              };
            },
          },
        }),
        Placeholder.configure({
          placeholder: "Write together. Use / for blocks or @ to link an item.",
        }),
        Collaboration.configure({ document: doc }),
        ...(provider
          ? [
              CollaborationCaret.configure({
                provider,
                user: { name: user.name, color: "#0e7c6b" },
              }),
            ]
          : []),
      ],
      editorProps: {
        attributes: {
          "aria-label": "Document content",
          role: "textbox",
          "aria-multiline": "true",
          dir: "auto",
          class: "document-content",
        },
      },
      onUpdate: ({ editor }) => {
        const { from } = editor.state.selection;
        setBlocks(
          editor.state.doc.textBetween(Math.max(0, from - 1), from) === "/",
        );
        setAnnouncement("Document changed");
      },
    },
    [provider],
  );
  useEffect(() => {
    editor?.setEditable(editable);
  }, [editor, editable]);
  const suggestions = useQuery({
    queryKey: ["doc-suggestions", record.id],
    queryFn: () => api<{ suggestions: Proposal[] }>(path + "/suggestions"),
    enabled: online,
    refetchInterval: 2000,
  });
  useEffect(() => {
    if (editor && suggestions.data)
      editor.view.dispatch(
        editor.state.tr.setMeta(
          "document-suggestion-highlights",
          suggestions.data.suggestions
            .filter((p) => p.status === "proposed")
            .map((p) => p.payload.expected_text),
        ),
      );
  }, [editor, suggestions.data]);
  const versions = useQuery({
    queryKey: ["doc-versions", record.id],
    queryFn: () => api<{ versions: Version[] }>(path + "/versions"),
    enabled: online,
    refetchInterval: 2000,
  });
  const backlinks = useQuery({
    queryKey: ["doc-links", record.id],
    queryFn: () =>
      api<{
        links: {
          id: string;
          source: { label: string; url: string };
          target: { label: string; url: string };
        }[];
      }>(path + "/backlinks"),
    enabled: online && panel === "links",
  });
  const channels = useQuery({
    queryKey: ["doc-channels", workspace.id],
    queryFn: () =>
      api<{ id: string; name: string }[]>(
        `/workspaces/${workspace.id}/channels`,
      ),
    enabled: online,
  });
  const members = useQuery({
    queryKey: ["doc-members", workspace.id],
    queryFn: () => api<Member[]>(`/workspaces/${workspace.id}/members`),
    enabled: online && panel === "members",
  });
  const mentions = useQuery({
    queryKey: ["doc-mentions", workspace.id, mentionQuery],
    queryFn: () =>
      api<{
        items: { source_type: string; source_id: string; title: string }[];
      }>(
        `/workspaces/${workspace.id}/search?query=${encodeURIComponent(mentionQuery)}`,
      ),
    enabled: online && mentionQuery.length > 1,
  });
  async function decide(p: Proposal, action: string) {
    try {
      await post(`/workspaces/${workspace.id}/proposals/${p.id}/${action}`, {
        version: p.version,
        payload_hash: p.payload_hash,
        idempotency_key: crypto.randomUUID(),
      });
      await suggestions.refetch();
      setAnnouncement("Suggestion " + action + " recorded");
    } catch (e) {
      setError(e);
    }
  }
  async function perform(fn: () => Promise<unknown>) {
    try {
      await fn();
      setError(undefined);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <section className="document-page">
      <header className="document-header">
        <Link href="/documents">← Documents</Link>
        <label>
          Document title
          <input
            dir="auto"
            value={title}
            disabled={!editable}
            maxLength={240}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={() => {
              if (online && title !== record.title)
                void perform(() => post(path, { title }, "PATCH"));
            }}
          />
        </label>
        <span className="chip">
          {types[record.type as keyof typeof types]}{" "}
          {record.is_private ? "· Private" : ""}
        </span>
        <p role="status">{status}</p>
        {["owner", "admin"].includes(workspace.role) && online && (
          <>
            <Button
              variant="secondary"
              onClick={() => {
                if (confirm("Archive this document?"))
                  void perform(() =>
                    post(path, { archived: true }, "PATCH").then(() => {
                      router.push("/documents");
                    }),
                  );
              }}
            >
              Archive
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                if (confirm("Delete this document?"))
                  void perform(() =>
                    post(path, undefined, "DELETE").then(() => {
                      router.push("/documents");
                    }),
                  );
              }}
            >
              Delete
            </Button>
          </>
        )}
      </header>
      {!online && (
        <p className="document-offline" role="status">
          Offline — edits stay on this device and merge when you reconnect.
          Agent unavailable offline.
        </p>
      )}
      {error != null && <ErrorNotice error={error} />}
      {rejected && (
        <section className="card card-body" aria-label="Rejected changes">
          <h2>Rejected changes</h2>
          <p>
            Your access changed. These edits were not applied to the server. A
            local copy is preserved.
          </p>
          <pre dir="auto">{editor?.getText()}</pre>
          <Button
            onClick={() =>
              download(editor?.getText() || "", "rejected-changes.md")
            }
          >
            Download local copy
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              if (confirm("Discard the rejected local edits and reload?"))
                void provider?.discardRejected();
            }}
          >
            Discard local changes
          </Button>
        </section>
      )}
      <div className="document-layout">
        <main className="card document-paper">
          <div
            className="document-toolbar"
            role="toolbar"
            aria-label="Document formatting"
          >
            <Button
              variant="ghost"
              disabled={!editable}
              onClick={() => editor?.chain().focus().toggleBold().run()}
            >
              Bold
            </Button>
            <Button
              variant="ghost"
              disabled={!editable}
              onClick={() => editor?.chain().focus().toggleItalic().run()}
            >
              Italic
            </Button>
            <Button
              variant="ghost"
              disabled={!editable}
              onClick={() =>
                editor?.chain().focus().toggleHeading({ level: 2 }).run()
              }
            >
              Heading
            </Button>
            <Button
              variant="ghost"
              disabled={!editable}
              onClick={() => editor?.chain().focus().toggleBulletList().run()}
            >
              List
            </Button>
            <Button
              variant="ghost"
              disabled={!editable}
              onClick={() => editor?.chain().focus().toggleCodeBlock().run()}
            >
              Code
            </Button>
            <Button
              variant="ghost"
              disabled={!editable}
              onClick={() => setBlocks(!blocks)}
            >
              Blocks /
            </Button>
            <Button
              variant="secondary"
              disabled={!online}
              onClick={() =>
                void perform(async () => {
                  const d = await api<{ markdown: string }>(path);
                  download(d.markdown, "document.md");
                })
              }
            >
              Export Markdown
            </Button>
          </div>
          {blocks && editable && (
            <div role="group" aria-label="Slash blocks">
              {["Paragraph", "Heading", "List", "Code"].map((label) => (
                <Button
                  key={label}
                  variant="secondary"
                  onClick={() => {
                    if (!editor) return;
                    const { from } = editor.state.selection;
                    if (
                      editor.state.doc.textBetween(
                        Math.max(0, from - 1),
                        from,
                      ) === "/"
                    )
                      editor.commands.deleteRange({ from: from - 1, to: from });
                    if (label === "Heading")
                      editor.commands.toggleHeading({ level: 2 });
                    else if (label === "List")
                      editor.commands.toggleBulletList();
                    else if (label === "Code")
                      editor.commands.toggleCodeBlock();
                    else editor.commands.setParagraph();
                    setBlocks(false);
                  }}
                >
                  {label}
                </Button>
              ))}
            </div>
          )}
          {mentionPicker && (
            <div role="listbox" aria-label="Mention choices">
              {mentionPicker.items.map((item, index) => (
                <Button
                  role="option"
                  aria-selected={index === mentionPicker.index}
                  key={item.entityType + item.id}
                  variant="ghost"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    mentionPicker.command(item);
                    setMentionPicker(null);
                  }}
                >
                  {item.label}
                </Button>
              ))}
            </div>
          )}
          <EditorContent editor={editor} />
          <div className="document-mention-control">
            <label>
              Link an item @
              <input
                value={mentionQuery}
                disabled={!online || !editable}
                onChange={(e) => setMentionQuery(e.target.value)}
              />
            </label>
            {mentions.data?.items.slice(0, 8).map((item) => (
              <Button
                key={item.source_type + item.source_id}
                variant="ghost"
                onClick={() => {
                  editor
                    ?.chain()
                    .focus()
                    .insertContent({
                      type: "mention",
                      attrs: {
                        id: item.source_id,
                        label: item.title,
                        entityType: item.source_type,
                      },
                    })
                    .run();
                  setMentionQuery("");
                }}
              >
                {item.title}
              </Button>
            ))}
          </div>
        </main>
        <aside
          className="card card-body document-panel"
          aria-label="Document details"
        >
          <nav aria-label="Document panels">
            {(["suggestions", "versions", "links", "members"] as const).map(
              (name) => (
                <Button
                  variant={panel === name ? "primary" : "ghost"}
                  key={name}
                  onClick={() => setPanel(name)}
                >
                  {name[0].toUpperCase() + name.slice(1)}
                </Button>
              ),
            )}
          </nav>
          {panel === "suggestions" && (
            <>
              <h2>Suggestions</h2>
              <p>
                The agent never edits directly. An Editor or Admin must accept
                each suggestion.
              </p>
              <label>
                Ask Agent
                <input
                  value={question}
                  disabled={!online}
                  onChange={(e) => setQuestion(e.target.value)}
                />
              </label>
              <label>
                Discussion channel
                <select
                  value={channel}
                  disabled={!online}
                  onChange={(e) => setChannel(e.target.value)}
                >
                  {channels.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      #{c.name}
                    </option>
                  ))}
                </select>
              </label>
              <Button
                disabled={!online || !question}
                onClick={() =>
                  void perform(() =>
                    post(path + "/ask", {
                      question,
                      channel_id: channel || channels.data?.[0]?.id,
                    }).then(() => {
                      setQuestion("");
                      setAnnouncement("Agent request sent");
                    }),
                  )
                }
              >
                Ask Agent
              </Button>
              {!online && <p>Agent and Suggestions require a connection.</p>}
              {suggestions.data?.suggestions.map((p) => (
                <article className="document-suggestion" key={p.id}>
                  <span className="chip">{p.status}</span>
                  <p dir="auto">
                    <del>{p.payload.expected_text}</del>
                  </p>
                  <p dir="auto">
                    <ins>{p.payload.replacement}</ins>
                  </p>
                  <p dir="auto">{p.payload.reason}</p>
                  {p.status === "proposed" && workspace.role !== "viewer" && (
                    <>
                      <Button
                        disabled={!online}
                        onClick={() => void decide(p, "approve")}
                      >
                        Accept
                      </Button>
                      <Button
                        variant="danger"
                        disabled={!online}
                        onClick={() => void decide(p, "reject")}
                      >
                        Reject
                      </Button>
                    </>
                  )}
                </article>
              ))}
            </>
          )}
          {panel === "versions" && (
            <>
              <h2>Version history</h2>
              <label>
                Version name
                <input
                  value={versionName}
                  onChange={(e) => setVersionName(e.target.value)}
                />
              </label>
              <Button
                disabled={!online || !editable}
                onClick={() =>
                  void perform(() =>
                    post(path + "/versions", {
                      name: versionName || null,
                    }).then(() => versions.refetch()),
                  )
                }
              >
                Save version
              </Button>
              {versions.data?.versions.map((v) => (
                <article key={v.id}>
                  <h3 dir="auto">{v.name || "Automatic version"}</h3>
                  <p>
                    {v.actor_type} · {new Date(v.created_at).toLocaleString()}
                  </p>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      void perform(async () => {
                        setPreview(
                          (
                            await api<{ markdown: string }>(
                              path + "/versions/" + v.id,
                            )
                          ).markdown,
                        );
                      })
                    }
                  >
                    Preview
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={!online || !editable}
                    onClick={() => {
                      if (
                        confirm(
                          "Restore this version? A new version will preserve history.",
                        )
                      )
                        void perform(() =>
                          post(
                            path + "/versions/" + v.id + "/restore",
                            {},
                          ).then(() => versions.refetch()),
                        );
                    }}
                  >
                    Restore
                  </Button>
                </article>
              ))}
              {preview && (
                <pre dir="auto" aria-label="Version preview">
                  {preview}
                </pre>
              )}
            </>
          )}
          {panel === "links" && (
            <>
              <h2>Backlinks</h2>
              {backlinks.data?.links.map((edge) => (
                <p key={edge.id}>
                  <Link href={edge.source.url}>{edge.source.label}</Link> ↔{" "}
                  <Link href={edge.target.url}>{edge.target.label}</Link>
                </p>
              ))}
            </>
          )}
          {panel === "members" && (
            <>
              <h2>Privacy and members</h2>
              {["owner", "admin"].includes(workspace.role) && (
                <>
                  <Button
                    disabled={!online}
                    variant="secondary"
                    onClick={() =>
                      void perform(() =>
                        post(
                          path,
                          { is_private: !record.is_private },
                          "PATCH",
                        ).then(() => location.reload()),
                      )
                    }
                  >
                    {record.is_private ? "Make public" : "Make private"}
                  </Button>
                  {members.data?.map((m) => (
                    <div key={m.user_id}>
                      <span>{m.name}</span>
                      <Button
                        disabled={!online}
                        variant="ghost"
                        onClick={() =>
                          void perform(() =>
                            post(path + "/members/" + m.user_id, {}, "PUT"),
                          )
                        }
                      >
                        Include
                      </Button>
                      <Button
                        disabled={!online}
                        variant="ghost"
                        onClick={() =>
                          void perform(() =>
                            post(
                              path + "/members/" + m.user_id,
                              undefined,
                              "DELETE",
                            ),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                </>
              )}
            </>
          )}
        </aside>
      </div>
      <span className="sr-only" aria-live="polite">
        {announcement}
      </span>
    </section>
  );
}

export function ConversationDocumentButton({
  workspaceId,
  messageId,
}: {
  workspaceId: string;
  messageId: string;
}) {
  const router = useRouter();
  const online = useOnline();
  const [open, setOpen] = useState(false),
    [title, setTitle] = useState("Conversation notes"),
    [project, setProject] = useState(""),
    [error, setError] = useState<unknown>();
  const projects = useQuery({
    queryKey: ["doc-conversation-projects", workspaceId],
    queryFn: () =>
      api<{ projects: { id: string; name: string }[] }>(
        `/workspaces/${workspaceId}/projects`,
      ),
    enabled: open && online,
  });
  return (
    <>
      <Button variant="ghost" disabled={!online} onClick={() => setOpen(!open)}>
        Create document from conversation
      </Button>
      {open && (
        <form
          aria-label="Convert conversation"
          onSubmit={(e) => {
            e.preventDefault();
            void post<DocumentRow>(
              `/workspaces/${workspaceId}/documents/from-conversation`,
              {
                project_id: project || projects.data?.projects[0]?.id,
                title,
                type: "meeting_notes",
                message_ids: [messageId],
              },
            )
              .then((d) => router.push("/documents?document=" + d.id))
              .catch(setError);
          }}
        >
          <label>
            Document title
            <input
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label>
            Project
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              {projects.data?.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          {error != null && <ErrorNotice error={error} />}
          <Button type="submit" disabled={!online}>
            Create linked document
          </Button>
        </form>
      )}
    </>
  );
}
