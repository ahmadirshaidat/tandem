"use client";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Sparkles,
  ShieldCheck,
  Lock,
  Check,
  X,
  Pencil,
  Inbox,
} from "lucide-react";
import {
  api,
  ApiError,
  post,
  type Workspace,
  type User,
  type Member,
} from "@/lib/api";
import {
  type Proposal,
  type ProposalPage,
  type ProposalPayload,
  type ProposalItem,
  canApprove,
  kindLabel,
  mergeProposals,
} from "@/lib/proposals";
import { cached, saveCache, removeCache } from "@/lib/offline";
import { useOnline } from "@/lib/online";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/dialog";
import { ErrorNotice, Field } from "./common";
import { SafeMarkdown } from "./safe-markdown";

export function useChannelProposals(
  workspace: Workspace,
  user: User,
  channelId: string,
  online: boolean,
) {
  const key = `proposals:${user.id}:${workspace.id}:${channelId}`;
  return useQuery({
    queryKey: ["proposals", workspace.id, channelId],
    queryFn: async () => {
      if (!navigator.onLine)
        return (
          cached<ProposalPage>(key)?.value ?? {
            proposals: [],
            next_cursor: null,
          }
        );
      try {
        const data = await api<ProposalPage>(
          `/workspaces/${workspace.id}/proposals?channel_id=${channelId}&limit=100`,
        );
        saveCache(key, data);
        return data;
      } catch (error) {
        if (error instanceof ApiError && [401, 403, 404].includes(error.status))
          removeCache(key);
        throw error;
      }
    },
    networkMode: "always",
    refetchInterval: online ? 5000 : false,
    retry: false,
  });
}

function useRules(workspace: Workspace, online: boolean) {
  return useQuery({
    queryKey: ["approval-rules", workspace.id],
    queryFn: () =>
      api<{ create_tasks_approver: string }>(
        `/workspaces/${workspace.id}/agent/approval-rules`,
      ),
    enabled: online,
    refetchInterval: online ? 5000 : false,
  });
}

export function ProposalCard({
  proposal: p,
  workspace,
  user,
  online,
}: {
  proposal: Proposal;
  workspace: Workspace;
  user: User;
  online: boolean;
}) {
  const client = useQueryClient();
  const rules = useRules(workspace, online);
  const projects = useQuery({
    queryKey: ["proposal-projects", workspace.id],
    queryFn: () =>
      api<{ id: string; name: string }[]>(
        `/workspaces/${workspace.id}/projects`,
      ),
    enabled: online,
  });
  const members = useQuery({
    queryKey: ["members", workspace.id],
    queryFn: () => api<Member[]>(`/workspaces/${workspace.id}/members`),
    enabled: online,
  });
  const target = useQuery({
    queryKey: ["proposal-target", workspace.id, p.payload.task_id],
    queryFn: () =>
      api<{ title: string; key: string }>(
        `/workspaces/${workspace.id}/tasks/${p.payload.task_id}`,
      ),
    enabled: online && !!p.payload.task_id,
    retry: false,
  });
  const required =
    p.kind === "create_tasks"
      ? (rules.data?.create_tasks_approver ?? p.required_role)
      : p.required_role;
  const allowed = canApprove(workspace.role, required);
  const pending = p.status === "proposed";
  const [review, setReview] = useState<Proposal | null>(null);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: ({
      action,
      payload,
    }: {
      action: string;
      payload?: ProposalPayload;
    }) =>
      api<Proposal>(
        `/workspaces/${workspace.id}/proposals/${p.id}/${action}`,
        post({
          version: p.version,
          payload_hash: p.payload_hash,
          idempotency_key: crypto.randomUUID(),
          ...(payload ? { payload } : {}),
          ...(reason ? { reason } : {}),
        }),
      ),
    onSuccess: async (result) => {
      client.setQueryData<ProposalPage>(
        ["proposals", workspace.id, p.channel_id],
        (old) => ({
          proposals: mergeProposals(old?.proposals ?? [], [result]),
          next_cursor: old?.next_cursor ?? null,
        }),
      );
      setRejecting(false);
      setReason("");
      await client.invalidateQueries({
        queryKey: ["pending-proposals", workspace.id],
      });
    },
  });
  const busy = mutation.isPending;
  const label = kindLabel(p.kind);
  return (
    <section
      className={`proposal-card proposal-${p.status}`}
      role="region"
      aria-label={`${label}: ${p.status}`}
      data-proposal-id={p.id}
    >
      <header>
        <span className="agent-avatar">
          <Sparkles size={17} />
        </span>
        <div>
          <strong>{label}</strong>
          <div className="proposal-chips">
            <span
              className={`chip ${p.status === "completed" ? "chip-success" : "chip-agent"}`}
              aria-live="polite"
            >
              {p.status[0].toUpperCase() + p.status.slice(1)}
            </span>
            <span
              className={`chip ${p.risk === "high" ? "chip-warning" : "chip-agent"}`}
            >
              {p.risk === "high" ? "High risk" : "Low risk"}
            </span>
          </div>
        </div>
      </header>
      <div className="proposal-body">
        <p className="text-small text-muted">
          {required === "admin"
            ? "Only an Admin can approve this"
            : "Any Editor or Admin can approve"}
        </p>
        {p.payload.items?.map((item, index) => (
          <article key={item.item_id} className="proposal-item">
            <div className="proposal-item-heading">
              <span className="proposal-item-number">{index + 1}</span>
              <h3 dir="auto">{item.title}</h3>
            </div>
            <SafeMarkdown body={item.description} />
            <div className="proposal-properties">
              <span>{item.type}</span>
              <span>{item.priority}</span>
              <span>{item.status.replaceAll("_", " ")}</span>
              <span>
                {item.assignee_id
                  ? (members.data?.find((m) => m.user_id === item.assignee_id)
                      ?.name ?? item.assignee_id)
                  : "Unassigned"}
              </span>
              {item.due_date && <span>Due {item.due_date}</span>}
              <Link href={`/tasks?project=${item.project_id}`}>
                {projects.data?.find(
                  (project) => project.id === item.project_id,
                )?.name ?? item.project_id}
              </Link>
            </div>
            {!!item.depends_on.length && (
              <p className="text-small text-muted" dir="auto">
                Depends on:{" "}
                {item.depends_on
                  .map(
                    (id) =>
                      p.payload.items?.find((i) => i.item_id === id)?.title ??
                      id,
                  )
                  .join(", ")}
              </p>
            )}
          </article>
        ))}
        {!p.payload.items && (
          <div className="proposal-target">
            <Link href={`/tasks?task=${p.payload.task_id}`}>
              <span dir="auto">
                {target.data
                  ? `${target.data.key}: ${target.data.title}`
                  : `Task ${p.payload.task_id}`}
              </span>
            </Link>
            {p.payload.changes && (
              <dl>
                {Object.entries(p.payload.changes).map(([k, v]) => (
                  <div key={k}>
                    <dt>{k.replaceAll("_", " ")}</dt>
                    <dd dir="auto">{v === null ? "Clear value" : v}</dd>
                  </div>
                ))}
              </dl>
            )}
            {p.payload.priority && <p>Priority: {p.payload.priority}</p>}
            {"assignee_id" in p.payload && (
              <p>
                {p.payload.assignee_id
                  ? `Reassign to ${members.data?.find((m) => m.user_id === p.payload.assignee_id)?.name ?? p.payload.assignee_id}`
                  : "Remove assignee"}
              </p>
            )}
            {p.payload.body && <SafeMarkdown body={p.payload.body} />}
          </div>
        )}
        {!!p.sources.length && (
          <div className="proposal-sources">
            <span>Based on</span>
            {p.sources.map((s) => (
              <Link className="chip" key={s.id} href={s.url}>
                {s.label}
              </Link>
            ))}
          </div>
        )}
        <ErrorNotice error={mutation.error} />
        {p.decided_by && (
          <p className="text-small text-muted">
            {p.status === "completed" ? "Approved" : "Decided"} by{" "}
            <span dir="auto">{p.decided_by.name}</span>
          </p>
        )}
        {p.decision_reason && (
          <p dir="auto" className="text-small">
            {p.decision_reason}
          </p>
        )}
        {p.status === "failed" && (
          <p role="status">
            The change could not be executed. Nothing from this proposal was
            applied.
          </p>
        )}
        {p.status === "stale" && (
          <p role="status">
            The target changed. Review its current state and ask for a new
            proposal.
          </p>
        )}
        {p.status === "expired" && (
          <p role="status">
            This proposal expired. Mention @Agent to request a new one.
          </p>
        )}
        {p.execution_result?.task_ids.map((id) => (
          <Link className="proposal-result" href={`/tasks?task=${id}`} key={id}>
            <Check size={15} />
            Open {p.kind === "create_tasks" ? "created" : "updated"} task
          </Link>
        ))}
      </div>
      {pending && (
        <footer>
          <p className="text-small text-muted">
            {!online
              ? "Approvals require an internet connection. Nothing is queued."
              : !allowed
                ? workspace.role === "viewer"
                  ? "Viewers can read proposals; an eligible teammate must approve."
                  : "Only an Admin can approve this"
                : "Review first. Only your approval applies these changes."}
          </p>
          {allowed && (
            <div className="proposal-actions">
              <Button
                variant="ghost"
                disabled={!online || busy}
                onClick={() => setRejecting(true)}
              >
                <X size={15} />
                Reject
              </Button>
              <Button
                variant="secondary"
                disabled={!online || busy}
                onClick={() => setReview(structuredClone(p))}
              >
                <Pencil size={15} />
                Edit
              </Button>
              <Button
                disabled={!online || busy}
                onClick={() => mutation.mutate({ action: "approve" })}
              >
                <Check size={15} />
                {busy
                  ? "Deciding…"
                  : p.kind === "create_tasks"
                    ? "Approve and create"
                    : "Approve change"}
              </Button>
            </div>
          )}
          {p.requested_by.id === user.id && workspace.role !== "viewer" && (
            <Button
              variant="ghost"
              disabled={!online || busy}
              onClick={() => mutation.mutate({ action: "cancel" })}
            >
              Cancel proposal
            </Button>
          )}
        </footer>
      )}
      <ConfirmDialog
        open={rejecting}
        onOpenChange={setRejecting}
        title="Reject proposal?"
        description="No task or comment will be changed. A reason is optional."
        actions={false}
      >
        <Field
          label="Reason (optional)"
          id={`reject-${p.id}`}
          value={reason}
          maxLength={500}
          dir="auto"
          onChange={(e) => setReason(e.target.value)}
        />
        <ErrorNotice error={mutation.error} />
        <div className="dialog-actions">
          <Button variant="secondary" onClick={() => setRejecting(false)}>
            Back
          </Button>
          <Button
            disabled={!online || busy}
            onClick={() => mutation.mutate({ action: "reject" })}
          >
            Reject proposal
          </Button>
        </div>
      </ConfirmDialog>
      {review && (
        <ProposalReview
          key={review.id}
          proposal={review}
          workspace={workspace}
          online={online}
          onClose={() => setReview(null)}
        />
      )}
    </section>
  );
}

function ProposalReview({
  proposal: p,
  workspace,
  online,
  onClose,
}: {
  proposal: Proposal;
  workspace: Workspace;
  online: boolean;
  onClose: () => void;
}) {
  const [payload, setPayload] = useState<ProposalPayload>(() =>
    structuredClone(p.payload),
  );
  const client = useQueryClient();
  const projects = useQuery({
    queryKey: ["proposal-projects", workspace.id],
    queryFn: () =>
      api<{ id: string; name: string }[]>(
        `/workspaces/${workspace.id}/projects`,
      ),
    enabled: online,
  });
  const members = useQuery({
    queryKey: ["members", workspace.id],
    queryFn: () => api<Member[]>(`/workspaces/${workspace.id}/members`),
    enabled: online,
  });
  const mutation = useMutation({
    mutationFn: () =>
      api<Proposal>(
        `/workspaces/${workspace.id}/proposals/${p.id}/edit-approve`,
        post({
          version: p.version,
          payload_hash: p.payload_hash,
          idempotency_key: crypto.randomUUID(),
          payload,
        }),
      ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["proposals", workspace.id] }),
        client.invalidateQueries({
          queryKey: ["pending-proposals", workspace.id],
        }),
      ]);
      onClose();
    },
  });
  const itemChange = (id: string, patch: Partial<ProposalItem>) =>
    setPayload((old) => ({
      ...old,
      items: old.items?.map((i) => (i.item_id === id ? { ...i, ...patch } : i)),
    }));
  const change = (patch: Partial<NonNullable<ProposalPayload["changes"]>>) =>
    setPayload((old) => ({ ...old, changes: { ...old.changes, ...patch } }));
  const assignees = (
    value: string | null | undefined,
    choose: (id: string | null) => void,
  ) => (
    <select
      className="input"
      aria-label="Assignee"
      value={value ?? ""}
      onChange={(e) => choose(e.target.value || null)}
    >
      <option value="">Unassigned</option>
      {members.data?.map((m) => (
        <option key={m.user_id} value={m.user_id}>
          {m.name}
        </option>
      ))}
    </select>
  );
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => !open && !mutation.isPending && onClose()}
      title="Review proposal"
      description="Edits are recorded. Approval executes exactly the reviewed fields and applies the whole set or none."
      actions={false}
    >
      <form
        className="proposal-review"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <ErrorNotice error={mutation.error} />
        <fieldset disabled={!online || mutation.isPending}>
          {payload.items?.map((item, index) => (
            <section className="proposal-review-item" key={item.item_id}>
              <div className="row-between">
                <h3>Task {index + 1}</h3>
                <Button
                  variant="ghost"
                  aria-label={`Remove task ${index + 1}`}
                  onClick={() =>
                    setPayload((old) => ({
                      ...old,
                      items: old.items
                        ?.filter((i) => i.item_id !== item.item_id)
                        .map((i) => ({
                          ...i,
                          depends_on: i.depends_on.filter(
                            (id) => id !== item.item_id,
                          ),
                        })),
                    }))
                  }
                >
                  Remove
                </Button>
              </div>
              <Field
                label="Title"
                id={`proposal-title-${item.item_id}`}
                value={item.title}
                dir="auto"
                required
                maxLength={240}
                onChange={(e) =>
                  itemChange(item.item_id, { title: e.target.value })
                }
              />
              <label className="field">
                Description
                <textarea
                  className="input"
                  aria-label={`Description for task ${index + 1}`}
                  dir="auto"
                  maxLength={4000}
                  value={item.description}
                  onChange={(e) =>
                    itemChange(item.item_id, { description: e.target.value })
                  }
                />
              </label>
              <div className="proposal-edit-grid">
                <label className="field">
                  Project
                  <select
                    className="input"
                    value={item.project_id}
                    onChange={(e) =>
                      itemChange(item.item_id, { project_id: e.target.value })
                    }
                  >
                    {projects.data?.map((project) => (
                      <option value={project.id} key={project.id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Priority
                  <select
                    className="input"
                    value={item.priority}
                    onChange={(e) =>
                      itemChange(item.item_id, { priority: e.target.value })
                    }
                  >
                    {["P1", "P2", "P3"].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Status
                  <select
                    className="input"
                    value={item.status}
                    onChange={(e) =>
                      itemChange(item.item_id, { status: e.target.value })
                    }
                  >
                    {["todo", "in_progress", "done"].map((v) => (
                      <option key={v} value={v}>
                        {v.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Type
                  <select
                    className="input"
                    value={item.type}
                    onChange={(e) =>
                      itemChange(item.item_id, {
                        type: e.target.value as "task" | "bug",
                      })
                    }
                  >
                    <option value="task">Task</option>
                    <option value="bug">Bug</option>
                  </select>
                </label>
                <label className="field">
                  Assignee
                  {assignees(item.assignee_id, (id) =>
                    itemChange(item.item_id, { assignee_id: id }),
                  )}
                </label>
                <Field
                  label="Due date"
                  id={`proposal-due-${item.item_id}`}
                  type="date"
                  value={item.due_date ?? ""}
                  onChange={(e) =>
                    itemChange(item.item_id, {
                      due_date: e.target.value || null,
                    })
                  }
                />
              </div>
              <fieldset className="proposal-dependencies">
                <legend>Depends on</legend>
                {payload.items
                  ?.filter((i) => i.item_id !== item.item_id)
                  .map((other) => (
                    <label key={other.item_id}>
                      <input
                        type="checkbox"
                        checked={item.depends_on.includes(other.item_id)}
                        onChange={(e) =>
                          itemChange(item.item_id, {
                            depends_on: e.target.checked
                              ? [...item.depends_on, other.item_id]
                              : item.depends_on.filter(
                                  (id) => id !== other.item_id,
                                ),
                          })
                        }
                      />
                      <span dir="auto">{other.title}</span>
                    </label>
                  ))}
              </fieldset>
            </section>
          ))}
          {p.kind === "update_task" && (
            <>
              <Field
                label="Title (leave unchanged unless edited)"
                id="review-update-title"
                dir="auto"
                value={payload.changes?.title ?? ""}
                onChange={(e) => change({ title: e.target.value })}
              />
              <label className="field">
                Description
                <textarea
                  className="input"
                  dir="auto"
                  value={payload.changes?.description ?? ""}
                  onChange={(e) => change({ description: e.target.value })}
                />
              </label>
              <label className="field">
                Status
                <select
                  className="input"
                  value={payload.changes?.status ?? ""}
                  onChange={(e) => change({ status: e.target.value })}
                >
                  <option value="" disabled>
                    Unchanged
                  </option>
                  {["todo", "in_progress", "done"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              <Field
                label="Due date"
                id="review-due"
                type="date"
                value={payload.changes?.due_date ?? ""}
                onChange={(e) => change({ due_date: e.target.value || null })}
              />
            </>
          )}
          {p.kind === "change_priority" && (
            <label className="field">
              Priority
              <select
                className="input"
                value={payload.priority}
                onChange={(e) =>
                  setPayload({ ...payload, priority: e.target.value })
                }
              >
                {["P1", "P2", "P3"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          )}
          {p.kind === "reassign_task" && (
            <label className="field">
              Assignee
              {assignees(payload.assignee_id, (id) =>
                setPayload({ ...payload, assignee_id: id }),
              )}
            </label>
          )}
          {p.kind === "add_comment" && (
            <label className="field">
              Comment
              <textarea
                className="input"
                dir="auto"
                maxLength={4000}
                required
                value={payload.body}
                onChange={(e) =>
                  setPayload({ ...payload, body: e.target.value })
                }
              />
            </label>
          )}
          {p.kind === "delete_task" && (
            <p>
              This permanently removes the task from active views. Only an Admin
              can approve.
            </p>
          )}
        </fieldset>
        {!online && (
          <p role="status">
            Approvals require an internet connection. Edits stay here; nothing
            is queued.
          </p>
        )}
        <div className="proposal-review-footer">
          <Button
            variant="secondary"
            disabled={mutation.isPending}
            onClick={onClose}
          >
            Back
          </Button>
          <Button
            type="submit"
            disabled={
              !online ||
              mutation.isPending ||
              (!!payload.items && !payload.items.length)
            }
          >
            {mutation.isPending ? "Applying…" : "Approve reviewed changes"}
          </Button>
        </div>
      </form>
    </ConfirmDialog>
  );
}

export function PendingProposals({
  workspace,
  online,
  actionable = false,
}: {
  workspace: Workspace;
  online: boolean;
  actionable?: boolean;
}) {
  const [cursor, setCursor] = useState("");
  const pending = useQuery({
    queryKey: ["pending-proposals", workspace.id, actionable, cursor],
    queryFn: () =>
      api<ProposalPage>(
        `/workspaces/${workspace.id}/proposals?pending=true${actionable ? "&actionable=true" : ""}${cursor ? `&before=${cursor}` : ""}`,
      ),
    enabled: online,
    refetchInterval: online ? 3000 : false,
  });
  if (!online)
    return (
      <p className="text-small text-muted">
        Connect to review current approvals.
      </p>
    );
  return (
    <>
      <ErrorNotice error={pending.error} />
      {pending.isPending ? (
        <p role="status">Loading approvals…</p>
      ) : !pending.data?.proposals.length ? (
        <p className="text-small text-muted">
          No pending proposals{actionable ? " you can approve" : ""}.
        </p>
      ) : (
        pending.data.proposals.map((p) => (
          <Link
            className="pending-proposal"
            key={p.id}
            href={`/channels?channel=${p.channel_id}&proposal=${p.id}`}
          >
            <span className="agent-avatar">
              <Sparkles size={15} />
            </span>
            <span>
              <strong dir="auto">
                {p.payload.items?.[0]?.title ?? kindLabel(p.kind)}
              </strong>
              <span className="text-small text-muted">
                {p.risk === "high" ? "High risk · Admin only" : "Low risk"} ·
                Review in channel
              </span>
            </span>
          </Link>
        ))
      )}
      <div className="row">
        <Button
          variant="ghost"
          disabled={!cursor}
          onClick={() => setCursor("")}
        >
          Newest
        </Button>
        <Button
          variant="ghost"
          disabled={!pending.data?.next_cursor}
          onClick={() => setCursor(pending.data!.next_cursor!)}
        >
          Older
        </Button>
      </div>
    </>
  );
}

export function ApprovalsInbox({ workspace }: { workspace: Workspace }) {
  const online = useOnline();
  return (
    <section className="approvals-inbox">
      <header className="page-heading">
        <span className="eyebrow">Your workspace</span>
        <h1>
          <Inbox size={24} />
          Inbox
        </h1>
        <p className="text-muted">Decisions that need your review.</p>
      </header>
      <div className="channel-tabs" role="tablist" aria-label="Inbox views">
        <button role="tab" aria-selected>
          Approvals
        </button>
        <button role="tab" disabled title="Coming soon">
          Mentions · Coming soon
        </button>
        <button role="tab" disabled title="Coming soon">
          Assigned · Coming soon
        </button>
      </div>
      {workspace.role === "viewer" && (
        <p className="notice">
          Viewers can read proposals in channels. Only eligible Editors and
          Admins can approve.
        </p>
      )}
      <div className="card card-body">
        <PendingProposals workspace={workspace} online={online} actionable />
      </div>
    </section>
  );
}

export function ApprovalRules({ workspace }: { workspace: Workspace }) {
  const online = useOnline();
  const rules = useRules(workspace, online);
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: (value: string) =>
      api(`/workspaces/${workspace.id}/agent/approval-rules`, {
        method: "PUT",
        body: JSON.stringify({ create_tasks_approver: value }),
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["approval-rules", workspace.id] }),
  });
  return (
    <section className="card card-body agent-settings-card">
      <h2>Approval rules</h2>
      <p className="text-small text-muted">
        The agent only proposes. A human decision is always required.
      </p>
      <ErrorNotice error={mutation.error} />
      <table className="agent-rules">
        <thead>
          <tr>
            <th>Action</th>
            <th>Who can approve</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              Create tasks and drafts
              <span className="text-small text-muted">
                {" "}
                (tasks only in this release)
              </span>
            </td>
            <td>
              <select
                aria-label="Create tasks approver"
                className="input"
                disabled={!online || mutation.isPending}
                value={rules.data?.create_tasks_approver ?? "editor"}
                onChange={(e) => mutation.mutate(e.target.value)}
              >
                <option value="editor">Editor or Admin</option>
                <option value="admin">Admin only</option>
              </select>
            </td>
          </tr>
          <tr>
            <td>Edit status, title, description, due date; add comment</td>
            <td>Editor or Admin · Read only</td>
          </tr>
          <tr>
            <td>Reassign, change priority, delete</td>
            <td>
              <Lock size={13} />
              Admin only · Locked
            </td>
          </tr>
        </tbody>
      </table>
      <p className="text-small text-muted">
        <ShieldCheck size={14} />
        High-risk rules cannot be loosened.
      </p>
    </section>
  );
}
