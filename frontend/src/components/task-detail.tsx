"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X, Link2 } from "lucide-react";
import { api, post, type User, type Workspace } from "@/lib/api";
import { useOnline } from "@/lib/online";
import { cached } from "@/lib/offline";
import {
  conflictTask,
  offlineRead,
  priorities,
  statuses,
  statusLabels,
  taskBase,
  taskCacheKey,
  useProjects,
  useTaskMembers,
  type Activity,
  type Comment,
  type ItemLink,
  type Task,
} from "@/lib/tasks";
import { SafeMarkdown } from "./safe-markdown";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/dialog";
import { Field, ErrorNotice } from "./common";
import { TaskSelect } from "./task-dialogs";
const editable = [
  "title",
  "description",
  "project_id",
  "type",
  "status",
  "priority",
  "assignee_id",
  "due_date",
] as const;
function diff(task: Task, baseline: Task) {
  return Object.fromEntries(
    editable
      .filter((key) => task[key] !== baseline[key])
      .map((key) => [key, task[key]]),
  );
}
export function TaskDetail({
  workspace,
  user,
  taskId,
  initial,
  onClose,
}: {
  workspace: Workspace;
  user: User;
  taskId: string;
  initial?: Task;
  onClose: () => void;
}) {
  const base = taskBase(workspace) + `/tasks/${taskId}`,
    online = useOnline();
  const task = useQuery({
    queryKey: ["task-detail", workspace.id, taskId, "task"],
    queryFn: () =>
      !navigator.onLine && initial
        ? Promise.resolve(initial)
        : offlineRead<Task>(
            taskCacheKey(user, workspace, `detail:${taskId}:task`),
            base,
          ),
    initialData: initial,
    networkMode: "always",
  });
  return (
    <ConfirmDialog
      open
      modal={false}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={task.data?.key ?? "Task"}
      description="Task details, conversation and activity."
      actions={false}
    >
      <div className="task-detail">
        <div className="task-detail-close">
          <span className="text-small text-muted">
            {online ? "Workspace task" : "You are offline · last sync"}
          </span>
          <Button
            variant="ghost"
            onClick={onClose}
            aria-label="Close task detail"
          >
            <X size={20} />
          </Button>
        </div>
        <ErrorNotice error={task.error} />
        {task.data?.deleted_at ? (
          <p>This task was deleted.</p>
        ) : task.data ? (
          <DetailFields
            key={taskId}
            workspace={workspace}
            user={user}
            task={task.data}
            onClose={onClose}
          />
        ) : (
          <p role="status">Opening task…</p>
        )}
      </div>
    </ConfirmDialog>
  );
}
function DetailFields({
  workspace,
  user,
  task,
  onClose,
}: {
  workspace: Workspace;
  user: User;
  task: Task;
  onClose: () => void;
}) {
  const online = useOnline(),
    client = useQueryClient(),
    projects = useProjects(workspace, user),
    members = useTaskMembers(workspace, user);
  const [draft, setDraft] = useState(task),
    [baseline, setBaseline] = useState(task),
    [dirty, setDirty] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false),
    [linkOpen, setLinkOpen] = useState(false);
  const base = taskBase(workspace) + `/tasks/${task.id}`;
  const writable =
    workspace.role !== "viewer" &&
    online &&
    !projects.data?.find((p) => p.id === task.project_id)?.archived;
  useEffect(() => {
    if (!dirty)
      queueMicrotask(() => {
        setDraft(task);
        setBaseline(task);
      });
  }, [task, dirty]);
  const update = useMutation({
    mutationFn: (action: {
      kind: "edit" | "delete";
      version: number;
      changes?: Record<string, unknown>;
    }) =>
      api<Task>(base, {
        method: action.kind === "delete" ? "DELETE" : "PATCH",
        body: JSON.stringify({ version: action.version, ...action.changes }),
      }),
    onSuccess: (result, action) => {
      if (action.kind === "delete") onClose();
      else {
        setDraft(result);
        setBaseline(result);
        setDirty(false);
        client.setQueryData(
          ["task-detail", workspace.id, task.id, "task"],
          result,
        );
      }
      void client.invalidateQueries({ queryKey: ["tasks", workspace.id] });
      void client.invalidateQueries({
        queryKey: ["task-detail", workspace.id, task.id],
      });
    },
  });
  const conflict = conflictTask(update.error);
  function change(key: (typeof editable)[number], value: string | null) {
    setDirty(true);
    setDraft((previous) => ({ ...previous, [key]: value }));
  }
  return (
    <>
      {!online && (
        <p className="offline-banner">
          You are offline. Tasks are read only. Last sync:{" "}
          {cached<Task>(taskCacheKey(user, workspace, `detail:${task.id}:task`))
            ?.syncedAt
            ? new Date(
                cached<Task>(
                  taskCacheKey(user, workspace, `detail:${task.id}:task`),
                )!.syncedAt,
              ).toLocaleString()
            : "saved board"}
        </p>
      )}
      {conflict ? (
        <section role="alert" className="task-conflict">
          <h3>This task changed</h3>
          <p>
            {conflict.key} is now version {conflict.version}. Your draft is
            still here.
          </p>
          <div className="row">
            <Button
              disabled={!online || update.isPending}
              onClick={() =>
                update.variables &&
                update.mutate({
                  ...update.variables,
                  version: conflict.version,
                })
              }
            >
              Keep mine
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setDraft(conflict);
                setBaseline(conflict);
                setDirty(false);
                setDeleteOpen(false);
                update.reset();
                client.setQueryData(
                  ["task-detail", workspace.id, task.id, "task"],
                  conflict,
                );
              }}
            >
              Take server&apos;s
            </Button>
          </div>
        </section>
      ) : (
        <ErrorNotice error={update.error} />
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          update.mutate({
            kind: "edit",
            version: baseline.version,
            changes: diff(draft, baseline),
          });
        }}
      >
        <Field
          label="Task title"
          id="task-detail-title"
          value={draft.title}
          onChange={(e) => change("title", e.target.value)}
          required
          maxLength={240}
          disabled={!writable}
        />
        {writable ? (
          <label className="field">
            Description
            <textarea
              className="input"
              aria-label="Task description"
              value={draft.description}
              onChange={(e) => change("description", e.target.value)}
              rows={4}
              maxLength={12000}
            />
          </label>
        ) : (
          <SafeMarkdown body={draft.description || "No description yet."} />
        )}
        {writable && draft.description && (
          <details className="task-markdown-preview">
            <summary>Preview description</summary>
            <SafeMarkdown body={draft.description} />
          </details>
        )}
        <div className="task-field-grid">
          <TaskSelect
            label="Status"
            name="status"
            value={draft.status}
            onChange={(value) => change("status", value)}
            disabled={!writable}
          >
            {statuses.map((s) => (
              <option key={s} value={s}>
                {statusLabels[s]}
              </option>
            ))}
          </TaskSelect>
          <TaskSelect
            label="Assignee"
            name="assignee_id"
            value={draft.assignee_id ?? ""}
            onChange={(value) => change("assignee_id", value || null)}
            disabled={!writable}
          >
            <option value="">Unassigned</option>
            {members.data?.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.name}
              </option>
            ))}
          </TaskSelect>
          <TaskSelect
            label="Priority"
            name="priority"
            value={draft.priority}
            onChange={(value) => change("priority", value)}
            disabled={!writable}
          >
            {Object.entries(priorities).map(([p, label]) => (
              <option key={p} value={p}>
                {p} {label}
              </option>
            ))}
          </TaskSelect>
          <Field
            label="Due date"
            id="task-detail-due"
            type="date"
            value={draft.due_date ?? ""}
            disabled={!writable}
            onChange={(e) => change("due_date", e.target.value || null)}
          />
          <TaskSelect
            label="Type"
            name="type"
            value={draft.type}
            onChange={(value) => change("type", value)}
            disabled={!writable}
          >
            <option value="task">Task</option>
            <option value="bug">Bug</option>
          </TaskSelect>
          <TaskSelect
            label="Project"
            name="project_id"
            value={draft.project_id}
            onChange={(value) => change("project_id", value)}
            disabled={!writable}
          >
            {projects.data
              ?.filter((p) => !p.archived || p.id === draft.project_id)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
          </TaskSelect>
        </div>
        <div className="task-reporter text-small text-muted">
          Reported by {task.reporter.name} ·{" "}
          {new Date(task.created_at).toLocaleDateString()}
          {task.created_by_agent && (
            <span className="chip chip-agent">Agent</span>
          )}
        </div>
        {writable && (
          <Button type="submit" disabled={!dirty || update.isPending}>
            {update.isPending ? "Saving…" : "Save changes"}
          </Button>
        )}
      </form>
      <LinksSection
        workspace={workspace}
        user={user}
        task={task}
        writable={writable}
        open={linkOpen}
        setOpen={setLinkOpen}
      />
      <TaskHistory
        workspace={workspace}
        user={user}
        task={task}
        writable={writable}
      />
      {["owner", "admin"].includes(workspace.role) && (
        <section className="task-detail-section">
          <Button
            variant="danger"
            disabled={!writable || update.isPending}
            onClick={() =>
              deleteOpen
                ? update.mutate({ kind: "delete", version: task.version })
                : setDeleteOpen(true)
            }
          >
            {deleteOpen ? "Confirm delete task" : "Delete task"}
          </Button>
          {deleteOpen && (
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
          )}
        </section>
      )}
    </>
  );
}
function useDetailRead<T>(
  workspace: Workspace,
  user: User,
  task: Task,
  part: string,
  suffix: string,
) {
  return useQuery({
    queryKey: ["task-detail", workspace.id, task.id, part],
    queryFn: () =>
      offlineRead<T>(
        taskCacheKey(user, workspace, `detail:${task.id}:${part}`),
        suffix,
      ),
    networkMode: "always",
  });
}
function LinksSection({
  workspace,
  user,
  task,
  writable,
  open,
  setOpen,
}: {
  workspace: Workspace;
  user: User;
  task: Task;
  writable: boolean;
  open: boolean;
  setOpen: (open: boolean) => void;
}) {
  const client = useQueryClient();
  const links = useDetailRead<ItemLink[]>(
    workspace,
    user,
    task,
    "links",
    taskBase(workspace) + `/links?object_type=task&object_id=${task.id}`,
  );
  const choices = useQuery({
    queryKey: ["task-link-choices", workspace.id],
    queryFn: () =>
      api<{ tasks: Task[] }>(taskBase(workspace) + "/tasks?limit=1000"),
    enabled: open && writable,
  });
  const link = useMutation({
    mutationFn: ({ target, version }: { target: string; version: number }) =>
      api(
        taskBase(workspace) + "/links",
        post({
          source_type: "task",
          source_id: task.id,
          target_type: "task",
          target_id: target,
          version,
        }),
      ),
    onSuccess: () => {
      setOpen(false);
      void client.invalidateQueries({
        queryKey: ["task-detail", workspace.id, task.id],
      });
    },
  });
  const conflict = conflictTask(link.error);
  return (
    <section className="task-detail-section">
      <div className="row-between">
        <h3>Linked items</h3>
        {writable && (
          <Button
            variant="ghost"
            onClick={() => setOpen(!open)}
            aria-label="Link another task"
          >
            <Link2 size={16} />
          </Button>
        )}
      </div>
      <ErrorNotice error={links.error} />
      {!links.data?.length && !links.isPending && (
        <p className="text-small text-muted">No accessible linked items.</p>
      )}
      {links.data?.map((item) => {
        const other = item.source.id === task.id ? item.target : item.source;
        return (
          <Link
            key={item.id}
            href={other.url}
            className="task-item-link"
            onClick={(event) => {
              if (other.type === "task") {
                event.preventDefault();
                history.replaceState(null, "", other.url);
                window.dispatchEvent(new Event("tandem-task-selection"));
              }
            }}
          >
            {other.label}
          </Link>
        );
      })}
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            link.mutate({
              target: String(form.get("target")),
              version: task.version,
            });
          }}
        >
          <TaskSelect label="Related task" name="target">
            {choices.data?.tasks
              .filter((t) => t.id !== task.id)
              .map((t) => (
                <option key={t.id} value={t.id}>
                  {t.key}: {t.title}
                </option>
              ))}
          </TaskSelect>
          <Button
            type="submit"
            disabled={
              link.isPending ||
              !writable ||
              !choices.data?.tasks.some((t) => t.id !== task.id)
            }
          >
            Create link
          </Button>
          <ErrorNotice error={link.error ?? choices.error} />
          {conflict && (
            <div className="task-conflict">
              <h3>This task changed</h3>
              <Button
                onClick={() =>
                  link.variables &&
                  link.mutate({ ...link.variables, version: conflict.version })
                }
              >
                Keep mine
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  link.reset();
                  void client.invalidateQueries({
                    queryKey: ["task-detail", workspace.id, task.id],
                  });
                }}
              >
                Take server&apos;s
              </Button>
            </div>
          )}
        </form>
      )}
    </section>
  );
}
function TaskHistory({
  workspace,
  user,
  task,
  writable,
}: {
  workspace: Workspace;
  user: User;
  task: Task;
  writable: boolean;
}) {
  const base = taskBase(workspace) + `/tasks/${task.id}`,
    client = useQueryClient();
  const activity = useDetailRead<{
    activity: Activity[];
    next_cursor: string | null;
  }>(workspace, user, task, "activity", base + "/activity");
  const comments = useDetailRead<{
    comments: Comment[];
    next_cursor: string | null;
  }>(workspace, user, task, "comments", base + "/comments");
  const [body, setBody] = useState(""),
    [editing, setEditing] = useState<Comment | null>(null);
  const comment = useMutation({
    mutationFn: (action: {
      kind: "create" | "edit" | "delete";
      comment?: Comment;
      body?: string;
    }) =>
      api(
        base +
          "/comments" +
          (action.comment
            ? `/${action.comment.id}${action.kind === "delete" ? `?version=${action.comment.version}` : ""}`
            : ""),
        {
          method:
            action.kind === "delete"
              ? "DELETE"
              : action.kind === "edit"
                ? "PATCH"
                : "POST",
          ...(action.kind === "delete"
            ? {}
            : {
                body: JSON.stringify({
                  body: action.body,
                  ...(action.comment
                    ? { version: action.comment.version }
                    : {}),
                }),
              }),
        },
      ),
    onSuccess: () => {
      setBody("");
      setEditing(null);
      void client.invalidateQueries({
        queryKey: ["task-detail", workspace.id, task.id],
      });
    },
  });
  const older = useMutation({
    mutationFn: async (part: "comments" | "activity") => {
      const old = part === "comments" ? comments.data : activity.data;
      const next = await api<
        Record<string, unknown[]> & { next_cursor: string | null }
      >(base + `/${part}?before=${old?.next_cursor}`);
      client.setQueryData(["task-detail", workspace.id, task.id, part], {
        ...next,
        [part]: [
          ...(old
            ? part === "comments"
              ? (old as { comments: Comment[] }).comments
              : (old as { activity: Activity[] }).activity
            : []),
          ...next[part],
        ],
      });
    },
  });
  function display(value: unknown) {
    if (value === null) return "None";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value).slice(0, 180);
  }
  return (
    <>
      <section className="task-detail-section">
        <h3>Activity</h3>
        <ErrorNotice error={activity.error} />
        <ol className="task-activity">
          {activity.data?.activity.map((item) => (
            <li key={item.id}>
              <span className="avatar">{item.actor.name.slice(0, 1)}</span>
              <div>
                <strong>{item.actor.name}</strong>{" "}
                {item.kind.replaceAll("_", " ")}
                <div className="text-small text-muted">
                  {item.field !== "task" && item.field !== "link" && (
                    <>
                      {item.field.replaceAll("_", " ")}:{" "}
                      {display(item.old_value)} → {display(item.new_value)}{" "}
                      ·{" "}
                    </>
                  )}
                  <time dateTime={item.created_at}>
                    {new Date(item.created_at).toLocaleString()}
                  </time>
                </div>
              </div>
            </li>
          ))}
        </ol>
        {activity.data?.next_cursor && (
          <Button
            variant="ghost"
            disabled={!navigator.onLine || older.isPending}
            onClick={() => older.mutate("activity")}
          >
            Older activity
          </Button>
        )}
      </section>
      <section className="task-detail-section">
        <h3>Comments</h3>
        <ErrorNotice error={comments.error ?? comment.error ?? older.error} />
        {comments.data?.comments
          .slice()
          .reverse()
          .map((item) => (
            <article key={item.id} className="task-comment">
              <div className="row-between">
                <strong>{item.author.name}</strong>
                <time
                  className="text-small text-muted"
                  dateTime={item.created_at}
                >
                  {new Date(item.created_at).toLocaleString()}
                </time>
              </div>
              {item.deleted_at ? (
                <p className="text-small text-muted">Comment deleted</p>
              ) : (
                <>
                  <SafeMarkdown body={item.body} />
                  {writable && (
                    <div className="row">
                      {item.author.id === user.id && (
                        <Button
                          variant="ghost"
                          onClick={() => {
                            setEditing(item);
                            setBody(item.body);
                          }}
                        >
                          Edit comment
                        </Button>
                      )}
                      {(item.author.id === user.id ||
                        ["owner", "admin"].includes(workspace.role)) && (
                        <Button
                          variant="ghost"
                          disabled={comment.isPending}
                          onClick={() =>
                            comment.mutate({ kind: "delete", comment: item })
                          }
                        >
                          Delete comment
                        </Button>
                      )}
                    </div>
                  )}
                </>
              )}
            </article>
          ))}
        {comments.data?.next_cursor && (
          <Button
            variant="ghost"
            disabled={!navigator.onLine || older.isPending}
            onClick={() => older.mutate("comments")}
          >
            Older comments
          </Button>
        )}
        <form
          className="task-comment-composer"
          onSubmit={(e) => {
            e.preventDefault();
            comment.mutate({
              kind: editing ? "edit" : "create",
              comment: editing ?? undefined,
              body,
            });
          }}
        >
          <label className="field">
            {editing ? "Edit your comment" : "Comment"}
            <textarea
              className="input"
              aria-label="Task comment"
              value={body}
              disabled={!writable}
              onChange={(e) => setBody(e.target.value)}
              maxLength={4000}
              rows={3}
              placeholder={
                writable ? "Add to the conversation…" : "Comments are read only"
              }
            />
          </label>
          <Button
            type="submit"
            disabled={!writable || !body.trim() || comment.isPending}
          >
            {editing ? "Save comment" : "Post comment"}
          </Button>
          {editing && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEditing(null);
                setBody("");
              }}
            >
              Cancel edit
            </Button>
          )}
        </form>
      </section>
    </>
  );
}
