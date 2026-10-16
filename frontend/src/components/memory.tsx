"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Search, RefreshCw, ShieldCheck } from "lucide-react";
import { api, ApiError, post, type Workspace } from "@/lib/api";
import { useOnline } from "@/lib/online";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/dialog";
import { ErrorNotice } from "./common";

export type MemoryResult = {
  id: string;
  source_type: "message" | "task";
  source_id: string;
  title: string;
  snippet: string;
  highlights: { start: number; end: number }[];
  href: string;
  created_at: string;
  channel_id: string | null;
  project_id: string | null;
};
type SearchResult = {
  items: MemoryResult[];
  next_cursor: string | null;
  degraded: boolean;
  note: string;
};
type Source = {
  kind: "channel" | "project";
  id: string;
  name: string;
  is_private: boolean;
  enabled: boolean;
  records: number;
  status: string;
  indexed_at: string | null;
  lag_ms: number | null;
  error: string | null;
};
type Settings = {
  include_private: boolean;
  retention_days: number;
  offer_resolution_summaries: boolean;
  stats: { records: number; sources: number };
  sources: Source[];
  degraded: boolean;
  model: string | null;
  version: string | null;
};
type Selection =
  | { source_kind: "channel" | "project"; source_id: string }
  | { record_ids: string[] };
type Preview = { count: number; preview_token: string };

export function HighlightedSnippet({
  item,
}: {
  item: Pick<MemoryResult, "snippet" | "highlights">;
}) {
  const text = Array.from(item.snippet);
  let position = 0;
  const content: React.ReactNode[] = [];
  for (const [index, range] of item.highlights.entries()) {
    if (
      range.start < position ||
      range.end > text.length ||
      range.end <= range.start
    )
      continue;
    content.push(text.slice(position, range.start).join(""));
    content.push(
      <mark key={index}>{text.slice(range.start, range.end).join("")}</mark>,
    );
    position = range.end;
  }
  content.push(text.slice(position).join(""));
  return (
    <p dir="auto" className="memory-snippet">
      {content}
    </p>
  );
}
function Degraded({ active }: { active: boolean }) {
  return active ? (
    <p className="memory-degraded" role="status">
      Semantic search unavailable. Full-text search is active.
    </p>
  ) : null;
}
function Offline() {
  return (
    <div className="card card-body" role="status">
      <h2>You are offline</h2>
      <p>
        Search and memory settings need a connection. Reconnect to continue.
      </p>
    </div>
  );
}
function NoAccess() {
  return (
    <div className="card card-body">
      <h2>No access</h2>
      <p>Only an Owner or Admin can manage workspace memory.</p>
    </div>
  );
}

export function SearchPage({
  workspace,
  settingsMode = false,
}: {
  workspace: Workspace;
  settingsMode?: boolean;
}) {
  const online = useOnline();
  const [text, setText] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [type, setType] = useState("");
  const [filters, setFilters] = useState({
    project_id: "",
    channel_id: "",
    assignee_id: "",
    after: "",
    before: "",
  });
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selected, setSelected] = useState<string[]>([]);
  const [forget, setForget] = useState<{
    selection: Selection;
    preview: Preview;
  } | null>(null);
  const client = useQueryClient();
  const options = useQuery({
    queryKey: ["memory-search-options", workspace.id],
    queryFn: async () => ({
      projects: await api<{ id: string; name: string }[]>(
        `/workspaces/${workspace.id}/projects`,
      ),
      channels: await api<{ id: string; name: string }[]>(
        `/workspaces/${workspace.id}/channels`,
      ),
      members: await api<{ user_id: string; name: string }[]>(
        `/workspaces/${workspace.id}/members`,
      ),
    }),
    enabled: online,
  });
  const params = new URLSearchParams({
    query: submitted,
    limit: "10",
    ...(type ? { source_type: type } : {}),
  });
  for (const [key, value] of Object.entries(filters))
    if (value)
      params.set(
        key,
        key === "after" || key === "before"
          ? `${value}T${key === "after" ? "00:00:00" : "23:59:59"}Z`
          : value,
      );
  const cursor = cursors[cursors.length - 1];
  if (cursor) params.set("cursor", cursor);
  const results = useQuery({
    queryKey: ["memory-search", workspace.id, params.toString()],
    queryFn: () =>
      api<SearchResult>(`/workspaces/${workspace.id}/search?${params}`),
    enabled: online && !!submitted,
    staleTime: 0,
  });
  const preview = useMutation({
    mutationFn: async () => {
      const selection = { record_ids: selected };
      return {
        selection,
        preview: await api<Preview>(
          `/workspaces/${workspace.id}/memory/forget-preview`,
          post(selection),
        ),
      };
    },
    onSuccess: setForget,
  });
  const execute = useMutation({
    mutationFn: () =>
      api(
        `/workspaces/${workspace.id}/memory/forget`,
        post({
          ...forget!.selection,
          preview_token: forget!.preview.preview_token,
        }),
      ),
    onSuccess: () => {
      setForget(null);
      setSelected([]);
      void client.invalidateQueries({
        queryKey: ["memory-search", workspace.id],
      });
      void client.invalidateQueries({
        queryKey: ["memory-settings", workspace.id],
      });
    },
  });
  if (!online) return <Offline />;
  const forbidden =
    results.error instanceof ApiError &&
    [403, 404].includes(results.error.status);
  return (
    <section
      className="memory-search"
      aria-label={settingsMode ? "Test memory recall" : "Global search"}
    >
      <header className="memory-heading">
        <Search aria-hidden="true" />
        <div>
          <h1>
            {settingsMode ? "Test what it can recall" : "Search workspace"}
          </h1>
          <p>Find messages, tasks and recorded fixes in English or Arabic.</p>
        </div>
      </header>
      <form
        className="memory-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(text.trim());
          setCursors([null]);
          setSelected([]);
        }}
      >
        <label htmlFor={settingsMode ? "memory-test-query" : "memory-query"}>
          Search query
        </label>
        <div className="memory-query-row">
          <input
            id={settingsMode ? "memory-test-query" : "memory-query"}
            className="input"
            value={text}
            maxLength={200}
            dir="auto"
            onChange={(e) => setText(e.target.value)}
            placeholder="How did we fix connection timeouts?"
          />
          <Button disabled={!text.trim()}>
            <Search size={16} />
            Search
          </Button>
        </div>
        {!settingsMode && (
          <div className="memory-filters">
            {(
              [
                ["project_id", "Project", options.data?.projects],
                ["channel_id", "Channel", options.data?.channels],
                [
                  "assignee_id",
                  "Assignee",
                  options.data?.members.map((m) => ({
                    id: m.user_id,
                    name: m.name,
                  })),
                ],
              ] as const
            ).map(([key, label, items]) => (
              <label key={key}>
                {label}
                <select
                  className="input"
                  value={filters[key]}
                  onChange={(e) => {
                    setFilters({ ...filters, [key]: e.target.value });
                    setCursors([null]);
                  }}
                >
                  <option value="">All</option>
                  {items?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            {(["after", "before"] as const).map((key) => (
              <label key={key}>
                {key === "after" ? "From date" : "Through date"}
                <input
                  className="input"
                  type="date"
                  value={filters[key]}
                  onChange={(e) => {
                    setFilters({ ...filters, [key]: e.target.value });
                    setCursors([null]);
                  }}
                />
              </label>
            ))}
          </div>
        )}
      </form>
      <div
        role="tablist"
        aria-label="Search result type"
        className="memory-type-tabs"
      >
        {[
          ["", "All"],
          ["message", "Messages"],
          ["task", "Tasks"],
        ].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={type === key}
            className={type === key ? "active" : ""}
            onClick={() => {
              setType(key);
              setCursors([null]);
              setSelected([]);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="text-small text-muted">
        <ShieldCheck size={14} aria-hidden="true" /> Results are limited to what
        you can access.
      </p>
      <ErrorNotice error={results.error ?? preview.error} />
      {forbidden ? (
        <p role="status">
          This workspace is unavailable or your access changed.
        </p>
      ) : (
        <>
          {results.isFetching && <p role="status">Searching workspace…</p>}
          {results.data && <Degraded active={results.data.degraded} />}
          {!submitted && (
            <div className="card card-body">
              <h2>What would you like to find?</h2>
              <p>Search a symptom, a decision or a previous fix.</p>
            </div>
          )}
          {submitted && results.data && results.data.items.length === 0 && (
            <div className="card card-body">
              <h2>No matching results</h2>
              <p>Try different wording or fewer filters.</p>
            </div>
          )}
          <div className="memory-results">
            {results.data?.items.map((item) => (
              <article className="card memory-result" key={item.id}>
                <div className="row-between">
                  <span className="chip">
                    {item.source_type === "task" ? "Task" : "Message"}
                  </span>
                  {settingsMode && (
                    <label className="memory-select">
                      <input
                        type="checkbox"
                        aria-label={`Select ${item.title}`}
                        checked={selected.includes(item.id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, item.id]
                              : selected.filter((id) => id !== item.id),
                          )
                        }
                      />
                      Select
                    </label>
                  )}
                </div>
                <h2 dir="auto">
                  <Link href={item.href}>{item.title}</Link>
                </h2>
                <HighlightedSnippet item={item} />
                <time
                  className="text-small text-muted"
                  dateTime={item.created_at}
                >
                  {new Date(item.created_at).toLocaleDateString()}
                </time>
              </article>
            ))}
          </div>
          {settingsMode && selected.length > 0 && (
            <Button
              variant="danger"
              disabled={preview.isPending}
              onClick={() => preview.mutate()}
            >
              Preview forgetting {selected.length} selected records
            </Button>
          )}
          <div className="memory-pagination">
            <Button
              variant="secondary"
              disabled={cursors.length === 1}
              onClick={() => setCursors(cursors.slice(0, -1))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              disabled={!results.data?.next_cursor || results.isFetching}
              onClick={() =>
                setCursors([...cursors, results.data!.next_cursor])
              }
            >
              Next
            </Button>
          </div>
        </>
      )}
      <ConfirmDialog
        open={!!forget}
        onOpenChange={(open) => {
          if (!open) setForget(null);
        }}
        title="Forget selected memory?"
        description="Underlying messages and tasks remain. These records stay excluded during reindexing."
      >
        <ErrorNotice error={execute.error} />
        <p>{forget?.preview.count ?? 0} memory records will be forgotten.</p>
        <Button variant="secondary" onClick={() => setForget(null)}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={execute.isPending}
          onClick={() => execute.mutate()}
        >
          Forget memory
        </Button>
      </ConfirmDialog>
    </section>
  );
}

export function MemorySettingsPage({ workspace }: { workspace: Workspace }) {
  const online = useOnline();
  const allowed = ["owner", "admin"].includes(workspace.role);
  const client = useQueryClient();
  const base = `/workspaces/${workspace.id}/memory`;
  const current = useQuery({
    queryKey: ["memory-settings", workspace.id],
    queryFn: () => api<Settings>(base + "/settings"),
    enabled: online && allowed,
    refetchInterval: online && allowed ? 5000 : false,
  });
  const [draft, setDraft] = useState<
    Partial<
      Pick<
        Settings,
        "include_private" | "retention_days" | "offer_resolution_summaries"
      >
    >
  >({});
  const [forget, setForget] = useState<{
    selection: Selection;
    preview: Preview;
  } | null>(null);
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["memory-settings", workspace.id],
    });
  };
  const save = useMutation({
    mutationFn: () =>
      api(base + "/settings", {
        method: "PUT",
        body: JSON.stringify({
          include_private:
            draft.include_private ?? current.data!.include_private,
          retention_days: draft.retention_days ?? current.data!.retention_days,
          offer_resolution_summaries:
            draft.offer_resolution_summaries ??
            current.data!.offer_resolution_summaries,
        }),
      }),
    onSuccess: () => {
      setDraft({});
      refresh();
    },
  });
  const toggle = useMutation({
    mutationFn: ({ source, enabled }: { source: Source; enabled: boolean }) =>
      api(`${base}/sources/${source.kind}/${source.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: refresh,
  });
  const reindex = useMutation({
    mutationFn: () => api(base + "/reindex", post({})),
    onSuccess: refresh,
  });
  const preview = useMutation({
    mutationFn: async (source: Source) => {
      const selection = { source_kind: source.kind, source_id: source.id };
      return {
        selection,
        preview: await api<Preview>(base + "/forget-preview", post(selection)),
      };
    },
    onSuccess: setForget,
  });
  const execute = useMutation({
    mutationFn: () =>
      api(
        base + "/forget",
        post({
          ...forget!.selection,
          preview_token: forget!.preview.preview_token,
        }),
      ),
    onSuccess: () => {
      setForget(null);
      refresh();
      void client.invalidateQueries({
        queryKey: ["memory-search", workspace.id],
      });
    },
  });
  if (
    !allowed ||
    (current.error instanceof ApiError &&
      [403, 404].includes(current.error.status))
  )
    return <NoAccess />;
  if (!online) return <Offline />;
  const value = current.data;
  return (
    <section className="memory-settings">
      <header className="memory-heading">
        <Database aria-hidden="true" />
        <div>
          <h1>Workspace memory</h1>
          <p>Control what the agent can recall. Indexing runs locally.</p>
        </div>
      </header>
      <ErrorNotice
        error={
          current.error ??
          save.error ??
          toggle.error ??
          reindex.error ??
          preview.error
        }
      />
      {current.isPending && <p role="status">Loading memory settings…</p>}
      {value && (
        <>
          <Degraded active={value.degraded} />
          <div className="memory-stats">
            <div className="card card-body">
              <strong>{value.stats.records}</strong>
              <span>Accessible memory records</span>
            </div>
            <div className="card card-body">
              <strong>{value.stats.sources}</strong>
              <span>Accessible sources</span>
            </div>
            <div className="card card-body">
              <strong>{value.degraded ? "Full-text" : "Hybrid"}</strong>
              <span>Retrieval status</span>
            </div>
          </div>
          <div className="card card-body memory-controls">
            <h2>Privacy and retention</h2>
            <label className="memory-switch">
              <input
                type="checkbox"
                role="switch"
                checked={draft.include_private ?? value.include_private}
                onChange={(e) =>
                  setDraft({ ...draft, include_private: e.target.checked })
                }
              />
              <span>
                Include private channels
                <small>
                  Off by default. Current channel membership is always required.
                </small>
              </span>
            </label>
            <label className="memory-switch">
              <input
                type="checkbox"
                role="switch"
                checked={
                  draft.offer_resolution_summaries ??
                  value.offer_resolution_summaries
                }
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    offer_resolution_summaries: e.target.checked,
                  })
                }
              />
              <span>
                Offer resolution summaries
                <small>
                  Completed bugs may produce a comment proposal. Human approval
                  is required.
                </small>
              </span>
            </label>
            <label>
              Memory retention
              <select
                aria-label="Memory retention"
                className="input"
                value={draft.retention_days ?? value.retention_days}
                onChange={(e) =>
                  setDraft({ ...draft, retention_days: Number(e.target.value) })
                }
              >
                <option value={0}>Forever</option>
                <option value={365}>1 year</option>
                <option value={90}>90 days</option>
              </select>
            </label>
            <p className="text-small text-muted">
              Retention and forgetting affect memory, never the underlying
              messages or tasks.
            </p>
            <div className="row">
              <Button disabled={save.isPending} onClick={() => save.mutate()}>
                Save memory settings
              </Button>
              <Button
                variant="secondary"
                disabled={reindex.isPending}
                onClick={() => reindex.mutate()}
              >
                <RefreshCw size={16} />
                Re-index memory
              </Button>
            </div>
            {save.isSuccess && <p role="status">Memory settings saved.</p>}
            {reindex.isSuccess && <p role="status">Re-index queued.</p>}
          </div>
          <div className="card card-body">
            <h2>Memory sources</h2>
            <p className="text-small text-muted">
              Only sources you can access are listed. Turning a source off
              removes its memory.
            </p>
            <div className="memory-source-list">
              {value.sources.map((source) => (
                <div
                  className="memory-source-row"
                  key={`${source.kind}:${source.id}`}
                >
                  <div dir="auto">
                    <strong>
                      {source.kind === "channel" ? "#" : ""}
                      {source.name}
                    </strong>
                    <small>
                      {source.is_private ? "Private channel" : source.kind} ·{" "}
                      {source.status} · {source.records} records
                      {source.lag_ms !== null
                        ? ` · ${Math.round(source.lag_ms)} ms lag`
                        : ""}
                    </small>
                  </div>
                  <label>
                    <input
                      type="checkbox"
                      role="switch"
                      aria-label={`Include ${source.name}`}
                      checked={source.enabled}
                      disabled={toggle.isPending}
                      onChange={(e) =>
                        toggle.mutate({ source, enabled: e.target.checked })
                      }
                    />
                    Include
                  </label>
                  <Button
                    variant="danger"
                    disabled={preview.isPending}
                    onClick={() => preview.mutate(source)}
                  >
                    Forget source
                  </Button>
                </div>
              ))}
            </div>
          </div>
          <div className="card card-body">
            <SearchPage workspace={workspace} settingsMode />
          </div>
          <p className="text-small text-muted">
            All changes and forgetting are audited. Results are limited to what
            you can access.
          </p>
        </>
      )}
      <ConfirmDialog
        open={!!forget}
        onOpenChange={(open) => {
          if (!open) setForget(null);
        }}
        title="Forget source memory?"
        description="This removes derived memory and turns this source off. Messages and tasks remain."
      >
        <ErrorNotice error={execute.error} />
        <p>{forget?.preview.count ?? 0} memory records will be forgotten.</p>
        <Button variant="secondary" onClick={() => setForget(null)}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={execute.isPending}
          onClick={() => execute.mutate()}
        >
          Forget memory
        </Button>
      </ConfirmDialog>
    </section>
  );
}

export function AgentMemorySources({
  workspaceId,
  runId,
}: {
  workspaceId: string;
  runId: string;
}) {
  const online = useOnline();
  const query = useQuery({
    queryKey: ["agent-memory-sources", workspaceId, runId],
    queryFn: () =>
      api<{ sources: { id: string; label: string; href: string }[] }>(
        `/workspaces/${workspaceId}/agent/runs/${runId}/memory-sources`,
      ),
    enabled: online,
    refetchInterval: online ? 5000 : false,
    staleTime: 0,
  });
  if (!online || query.error || !query.data?.sources.length) return null;
  return (
    <div className="memory-source-chips" aria-label="Answer sources">
      <span>Sources</span>
      {query.data.sources.map((source) => (
        <Link className="chip" key={source.id} href={source.href} dir="auto">
          {source.label}
        </Link>
      ))}
    </div>
  );
}
