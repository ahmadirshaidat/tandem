"use client";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles,
  ShieldCheck,
  Lock,
  Download,
  X,
  ChevronDown,
} from "lucide-react";
import { api, type Workspace } from "@/lib/api";
import {
  type AgentRun,
  type AgentSettings,
  type AuditEvent,
  stepLabel,
} from "@/lib/agent";
import { ErrorNotice, Field } from "./common";
import { Button } from "./ui/button";
import { ApprovalRules, PendingProposals } from "./proposals";
import { ConfirmDialog } from "./ui/dialog";

export function AgentSteps({ run }: { run: AgentRun }) {
  if (!run.steps.length) return null;
  return (
    <details className="agent-steps">
      <summary>
        <ShieldCheck size={14} />
        {run.steps.map((s) => stepLabel(s.name, s.count)).join(" · ")}
        {run.status === "completed" &&
          (run.steps.some((s) => s.name.startsWith("propose_"))
            ? " · Waiting for review"
            : " · Drafted an answer")}
        <ChevronDown size={14} />
      </summary>
      <ol>
        {run.steps.map((s, i) => (
          <li key={i}>
            <span>{stepLabel(s.name, s.count)}</span>
            <span>
              {s.status === "denied" ? "Unavailable" : `${s.duration_ms} ms`}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

export function AgentActivity({
  workspace,
  channelId,
  online,
}: {
  workspace: Workspace;
  channelId: string;
  online: boolean;
}) {
  const runs = useQuery({
    queryKey: ["agent-runs", workspace.id, channelId],
    queryFn: () =>
      api<AgentRun[]>(
        `/workspaces/${workspace.id}/agent/runs?channel_id=${channelId}`,
      ),
    enabled: online,
    refetchInterval: online ? 3000 : false,
  });
  const active =
    runs.data?.filter((r) => ["queued", "running"].includes(r.status)) ?? [];
  return (
    <div className="agent-activity" aria-live="polite">
      {active.map((r) => (
        <div key={r.id} className="agent-working" role="status">
          <Sparkles size={15} />
          Agent is working…
          <AgentSteps run={r} />
        </div>
      ))}
    </div>
  );
}

export function AgentPanel({
  workspace,
  channelId,
  online,
  onClose,
}: {
  workspace: Workspace;
  channelId?: string;
  online: boolean;
  onClose?: () => void;
}) {
  const context = useQuery({
    queryKey: ["agent-context", workspace.id, channelId],
    queryFn: () =>
      api<{
        channels: { id: string; name: string }[];
        projects: { id: string; name: string }[];
        private_notice: string;
      }>(
        `/workspaces/${workspace.id}/agent/context${channelId ? `?channel_id=${channelId}` : ""}`,
      ),
    enabled: online,
  });
  const recent = useQuery({
    queryKey: ["agent-recent", workspace.id],
    queryFn: () => api<AgentRun[]>(`/workspaces/${workspace.id}/agent/recent`),
    enabled: online,
    refetchInterval: online ? 5000 : false,
  });
  return (
    <div className="agent-panel">
      <header className="row-between">
        <div className="row">
          <span className="agent-avatar">
            <Sparkles size={18} />
          </span>
          <strong>Agent</strong>
          <span className="chip chip-agent">Reads & proposals</span>
        </div>
        {onClose && (
          <Button
            variant="ghost"
            aria-label="Close Agent panel"
            onClick={onClose}
          >
            <X size={18} />
          </Button>
        )}
      </header>
      {!online && <p role="status">Agent needs an internet connection</p>}
      <ErrorNotice error={context.error ?? recent.error} />
      <section>
        <h2>What the agent can see</h2>
        <p className="text-small text-muted">
          Only permitted context, safe for this conversation’s readers.
        </p>
        <ul className="agent-scope">
          {context.data?.channels.map((c) => (
            <li key={c.id}># {c.name}</li>
          ))}
          {context.data?.projects.map((p) => (
            <li key={p.id}>Project · {p.name}</li>
          ))}
        </ul>
        <p className="text-small text-muted">
          <Lock size={13} />{" "}
          {context.data?.private_notice ??
            "The agent cannot read what you cannot."}
        </p>
      </section>
      <section>
        <h2>Recent actions</h2>
        <p className="text-small text-muted">Your recent runs</p>
        {recent.data?.length ? (
          recent.data.map((r) => (
            <div key={r.id} className="agent-recent">
              <span>
                {r.status === "completed"
                  ? "Answered a question"
                  : (r.error_category?.replaceAll("_", " ") ?? "Working")}
              </span>
              <span className="chip">{r.status}</span>
              <AgentSteps run={r} />
            </div>
          ))
        ) : (
          <p className="text-muted">
            No agent actions yet. Mention @Agent in a channel.
          </p>
        )}
      </section>
      <section>
        <h2>Waiting for approval</h2>
        <PendingProposals workspace={workspace} online={online} />
        <Link href="/inbox" className="button button-ghost">
          Open approvals inbox
        </Link>
      </section>
      <Link href="/settings/agent" className="button button-secondary">
        Agent settings
      </Link>
    </div>
  );
}

export function AgentSettingsPage({ workspace }: { workspace: Workspace }) {
  const allowed = ["owner", "admin"].includes(workspace.role);
  const result = useQuery({
    queryKey: ["agent-settings", workspace.id],
    queryFn: () =>
      api<AgentSettings>(`/workspaces/${workspace.id}/agent/settings`),
    enabled: allowed,
  });
  if (!allowed)
    return (
      <div className="empty">
        <ShieldCheck />
        <h1>No access</h1>
        <p>Only Owners and Admins can manage the agent.</p>
      </div>
    );
  return (
    <div className="agent-settings-page">
      <header className="page-heading">
        <span className="eyebrow">Workspace settings</span>
        <h1>Agent</h1>
        <p className="text-muted">A shared teammate, with clear boundaries.</p>
      </header>
      <ErrorNotice error={result.error} />
      {result.data ? (
        <AgentSettingsForm
          key={workspace.id}
          workspace={workspace}
          initial={result.data}
        />
      ) : (
        <p role="status">Loading agent settings…</p>
      )}
    </div>
  );
}

function AgentSettingsForm({
  workspace,
  initial,
}: {
  workspace: Workspace;
  initial: AgentSettings;
}) {
  const client = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const [saved, setSaved] = useState(false);
  const mutation = useMutation({
    mutationFn: () =>
      api(`/workspaces/${workspace.id}/agent/settings`, {
        method: "PUT",
        body: JSON.stringify({
          enabled: draft.enabled,
          provider_chain: draft.provider_chain,
          monthly_run_limit: draft.monthly_run_limit,
          pause_at_limit: draft.pause_at_limit,
        }),
      }),
    onSuccess: async () => {
      setSaved(true);
      await client.invalidateQueries({
        queryKey: ["agent-settings", workspace.id],
      });
    },
  });
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api(`/workspaces/${workspace.id}/agent/channels/${id}`, {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["agent-settings", workspace.id] }),
  });
  return (
    <>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <section className="card card-body agent-settings-card">
          <div className="row-between">
            <div>
              <h2>Shared agent</h2>
              <p className="text-small text-muted">
                Every member can ask. Task changes require human approval.
              </p>
            </div>
            <label className="agent-toggle">
              <input
                type="checkbox"
                role="switch"
                aria-label="Enable workspace agent"
                aria-checked={draft.enabled}
                checked={draft.enabled}
                onChange={(e) => {
                  setSaved(false);
                  setDraft({ ...draft, enabled: e.target.checked });
                }}
              />
              <span>{draft.enabled ? "On" : "Off"}</span>
            </label>
          </div>
        </section>
        <section className="card card-body agent-settings-card">
          <h2>Models and data sharing</h2>
          <p className="text-muted text-small">
            Groq is primary; Gemini is the default fallback. Workspace content
            is sent to each selected provider.
          </p>
          <div className="agent-model-grid">
            {["groq", "gemini", "deepseek", "openai"].map((p) => (
              <label key={p} className="agent-model">
                <input
                  type="checkbox"
                  checked={draft.provider_chain.includes(p)}
                  disabled={
                    workspace.role !== "owner" &&
                    ["deepseek", "openai"].includes(p)
                  }
                  onChange={(e) => {
                    setSaved(false);
                    setDraft({
                      ...draft,
                      provider_chain: e.target.checked
                        ? [...draft.provider_chain, p]
                        : draft.provider_chain.filter((v) => v !== p),
                    });
                  }}
                />
                <strong>
                  {p === "openai" ? "OpenAI" : p[0].toUpperCase() + p.slice(1)}
                </strong>
                <small>
                  {initial.providers[p]?.model ?? "Checking model"} ·{" "}
                  {initial.providers[p]?.status.replaceAll("_", " ") ??
                    "Not verified"}
                </small>
              </label>
            ))}
          </div>
          <p className="agent-data-warning">
            <ShieldCheck size={17} />
            Owner opt-in: enabling DeepSeek or OpenAI sends workspace data to
            that provider. Review their data-use terms before enabling.
          </p>
          <label className="field">
            Primary provider
            <select
              className="input"
              aria-label="Primary provider"
              value={draft.provider_chain[0] ?? ""}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  provider_chain: [
                    e.target.value,
                    ...draft.provider_chain.filter((p) => p !== e.target.value),
                  ],
                })
              }
            >
              {draft.provider_chain.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <p className="text-small text-muted">
            Fallback order:{" "}
            {draft.provider_chain.slice(1).join(" → ") || "None"}. Models are
            configured on the backend.
          </p>
        </section>
        <section className="card card-body agent-settings-card">
          <h2>Usage and limits</h2>
          <p>
            <strong>{initial.usage}</strong> runs this month ·{" "}
            {initial.monthly_run_limit} configured limit
          </p>
          <progress
            max={initial.monthly_run_limit}
            value={Math.min(initial.usage, initial.monthly_run_limit)}
            aria-label="Monthly usage"
          />
          <Field
            label="Monthly run limit"
            id="agent-monthly-limit"
            type="number"
            min={1}
            max={1000000}
            required
            value={draft.monthly_run_limit}
            onChange={(e) => {
              setSaved(false);
              setDraft({ ...draft, monthly_run_limit: Number(e.target.value) });
            }}
          />
          <label className="agent-toggle">
            <input
              type="checkbox"
              checked={draft.pause_at_limit}
              onChange={(e) => {
                setSaved(false);
                setDraft({ ...draft, pause_at_limit: e.target.checked });
              }}
            />
            Pause at the monthly limit
          </label>
        </section>
        <ErrorNotice error={mutation.error} />
        <div className="agent-save">
          <span role="status">{saved ? "Agent settings saved." : ""}</span>
          <Button
            type="submit"
            disabled={mutation.isPending || !draft.provider_chain.length}
          >
            {mutation.isPending ? "Saving…" : "Save agent settings"}
          </Button>
        </div>
      </form>
      <section className="card card-body agent-settings-card">
        <h2>Where the agent can read</h2>
        <p className="text-small text-muted">
          Private channels start off. Only channels you can open are listed.
          Each switch saves immediately.
        </p>
        <ErrorNotice error={toggle.error} />
        {initial.channels.map((c) => (
          <label key={c.id} className="agent-channel-toggle">
            <span>
              {c.is_private ? <Lock size={15} /> : "#"} {c.name}
            </span>
            <input
              role="switch"
              aria-checked={c.enabled}
              aria-label={`Allow agent in ${c.name}`}
              type="checkbox"
              checked={c.enabled}
              disabled={toggle.isPending}
              onChange={(e) =>
                toggle.mutate({ id: c.id, enabled: e.target.checked })
              }
            />
          </label>
        ))}
      </section>
      <ApprovalRules workspace={workspace} />
    </>
  );
}

export function AuditLogPage({ workspace }: { workspace: Workspace }) {
  const allowed = ["owner", "admin"].includes(workspace.role);
  const [filters, setFilters] = useState({
    actor: "",
    action: "",
    status: "",
    after: "",
    until: "",
  });
  const [cursor, setCursor] = useState("");
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const params = new URLSearchParams(
    Object.entries(filters)
      .filter(([, v]) => v)
      .map(([k, v]) => [
        k,
        ["after", "until"].includes(k) ? new Date(v).toISOString() : v,
      ]),
  );
  if (cursor) params.set("before", cursor);
  const url = `/workspaces/${workspace.id}/audit`;
  const result = useQuery({
    queryKey: ["audit", workspace.id, params.toString()],
    queryFn: () =>
      api<{ events: AuditEvent[]; next_cursor: string | null }>(
        `${url}?${params}`,
      ),
    enabled: allowed,
  });
  const [exportError, setExportError] = useState<Error | null>(null);
  async function download() {
    try {
      const exportParams = new URLSearchParams(params);
      exportParams.delete("before");
      const response = await fetch(`/api${url}/export.csv?${exportParams}`, {
        credentials: "same-origin",
      });
      if (!response.ok)
        throw new Error("Export failed. Narrow the time filter and try again.");
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = "tandem-audit.csv";
      a.click();
      URL.revokeObjectURL(href);
      setExportError(null);
    } catch (e) {
      setExportError(e as Error);
    }
  }
  if (!allowed)
    return (
      <div className="empty">
        <ShieldCheck />
        <h1>No access</h1>
        <p>Only Owners and Admins can read or export the audit log.</p>
      </div>
    );
  return (
    <div className="audit-page">
      <header className="row-between">
        <div>
          <span className="eyebrow">Workspace settings</span>
          <h1>Audit log</h1>
          <p className="text-muted">
            A permanent record of agent activity and settings.
          </p>
        </div>
        <Button variant="secondary" onClick={() => void download()}>
          <Download size={16} />
          Export CSV
        </Button>
      </header>
      <div className="card card-body audit-filters">
        {["actor", "status"].map((key) => (
          <label className="field" key={key}>
            {key === "actor" ? "Actor" : "Status"}
            <select
              className="input"
              aria-label={key === "actor" ? "Filter actor" : "Filter status"}
              value={filters[key as "actor" | "status"]}
              onChange={(e) => {
                setCursor("");
                setFilters({ ...filters, [key]: e.target.value });
              }}
            >
              <option value="">All</option>
              {(key === "actor"
                ? ["user", "agent", "system"]
                : [
                    "ok",
                    "denied",
                    "queued",
                    "blocked",
                    "unavailable",
                    "timeout",
                    "rate_limited",
                  ]
              ).map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
        ))}
        <Field
          label="Action"
          id="audit-action"
          placeholder="agent.tool_call"
          value={filters.action}
          onChange={(e) => {
            setCursor("");
            setFilters({ ...filters, action: e.target.value });
          }}
        />
        {["after", "until"].map((k) => (
          <Field
            key={k}
            label={k === "after" ? "From" : "To"}
            id={`audit-${k}`}
            type="datetime-local"
            value={filters[k as "after" | "until"]}
            onChange={(e) => {
              setCursor("");
              setFilters({ ...filters, [k]: e.target.value });
            }}
          />
        ))}
      </div>
      <ErrorNotice error={result.error ?? exportError} />
      <div className="card table-scroll">
        <table className="audit-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Result</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {result.data?.events.map((e) => (
              <tr key={e.id}>
                <td>
                  <time dateTime={e.created_at}>
                    {new Date(e.created_at).toLocaleString()}
                  </time>
                </td>
                <td>{e.actor_type}</td>
                <td>{e.action}</td>
                <td>
                  <span className="chip">{e.result_status}</span>
                </td>
                <td>
                  <Button
                    variant="ghost"
                    aria-label={`View ${e.action} details`}
                    onClick={() => setSelected(e)}
                  >
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!result.isPending && !result.error && !result.data?.events.length && (
          <p className="card-body text-muted">
            No audit events match these filters.
          </p>
        )}
        {result.isPending && (
          <p role="status" className="card-body">
            Loading audit events…
          </p>
        )}
      </div>
      <div className="agent-save">
        <Button
          variant="secondary"
          disabled={!cursor}
          onClick={() => setCursor("")}
        >
          Newest
        </Button>
        <Button
          variant="secondary"
          disabled={!result.data?.next_cursor}
          onClick={() => setCursor(result.data!.next_cursor!)}
        >
          Older events
        </Button>
      </div>
      <ConfirmDialog
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
        title="Audit event details"
        description="Arguments are redacted. Message bodies and provider responses are never stored in audit records."
        actions={false}
      >
        <Button
          variant="secondary"
          aria-label="Close dialog"
          onClick={() => setSelected(null)}
        >
          Close
        </Button>
        {selected && (
          <dl className="audit-details">
            {Object.entries(selected).map(([k, v]) => (
              <div key={k}>
                <dt>{k.replaceAll("_", " ")}</dt>
                <dd>
                  {typeof v === "object"
                    ? JSON.stringify(v, null, 2)
                    : (v ?? "—")}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </ConfirmDialog>
    </div>
  );
}
