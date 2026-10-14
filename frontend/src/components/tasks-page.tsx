"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Calendar,
  Check,
  ChevronDown,
  Flag,
  Folder,
  LayoutGrid,
  List,
  MessageSquare,
  MoreHorizontal,
  Plus,
  Settings,
  Sparkles,
} from "lucide-react";
import { api, post, type User, type Workspace } from "@/lib/api";
import { useOnline } from "@/lib/online";
import { cached, prepareChatShell, saveCache } from "@/lib/offline";
import {
  boardKey,
  compareRank,
  conflictTask,
  offlineRead,
  priorities,
  statuses,
  statusLabels,
  taskBase,
  taskCacheKey,
  useProjects,
  useTaskMembers,
  type Project,
  type Status,
  type Task,
  type TaskPage,
} from "@/lib/tasks";
import { useTaskLive } from "@/lib/task-live";
import { ErrorNotice } from "./common";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/dialog";
import { NewTaskDialog, ProjectDialog } from "./task-dialogs";
import { TaskDetail } from "./task-detail";
function navigateTaskParam(name: "project" | "task", value: string) {
  const url = new URL(location.href);
  if (value) url.searchParams.set(name, value);
  else url.searchParams.delete(name);
  history.replaceState(null, "", url);
  window.dispatchEvent(new Event("tandem-task-selection"));
}
export function ProjectNavigation({
  workspace,
  user,
}: {
  workspace: Workspace;
  user: User;
}) {
  const projects = useProjects(workspace, user),
    online = useOnline();
  const [create, setCreate] = useState(false);
  const canManage = ["owner", "admin"].includes(workspace.role);
  return (
    <section className="project-navigation">
      <div className="row-between">
        <span className="nav-group-label">Projects</span>
        {canManage && (
          <Button
            variant="ghost"
            disabled={!online}
            aria-label="Create project"
            onClick={() => setCreate(true)}
          >
            <Plus size={16} />
          </Button>
        )}
      </div>
      {projects.data
        ?.filter((p) => !p.deleted_at && !p.archived)
        .map((p) => (
          <Link
            key={p.id}
            className="nav-item"
            href={`/tasks?project=${p.id}`}
            onClick={(e) => {
              if (location.pathname === "/tasks") {
                e.preventDefault();
                navigateTaskParam("project", p.id);
                navigateTaskParam("task", "");
              }
            }}
          >
            <Folder size={17} className={`project-color-${p.color}`} />
            {p.name}
          </Link>
        ))}
      {projects.data?.length === 0 && (
        <p className="text-small text-muted">No projects yet.</p>
      )}
      <ErrorNotice error={projects.error} />
      {create && (
        <ProjectDialog workspace={workspace} onClose={() => setCreate(false)} />
      )}
    </section>
  );
}
export function TasksPage({
  workspace,
  user,
}: {
  workspace: Workspace;
  user: User;
}) {
  const online = useOnline(),
    client = useQueryClient(),
    projects = useProjects(workspace, user),
    members = useTaskMembers(workspace, user);
  const [projectId, setProjectId] = useState(""),
    [taskId, setTaskId] = useState("");
  const [view, setView] = useState("board"),
    [newTask, setNewTask] = useState(false),
    [projectDialog, setProjectDialog] = useState<Project | "new" | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [priority, setPriority] = useState(""),
    [assignee, setAssignee] = useState(""),
    [type, setType] = useState(""),
    [text, setText] = useState(""),
    [status, setStatus] = useState("");
  const [mobileStatus, setMobileStatus] = useState<Status>("todo"),
    [limit, setLimit] = useState(40);
  const [sort, setSort] = useState("rank"),
    [desc, setDesc] = useState(false),
    [group, setGroup] = useState(true),
    [selected, setSelected] = useState<string[]>([]);
  const [quickTask, setQuickTask] = useState<Task | null>(null);
  const drag = useRef<Task | null>(null);
  const base = taskBase(workspace),
    cacheKey = taskCacheKey(user, workspace, `board:${projectId}`);
  const board = useQuery({
    queryKey: boardKey(workspace, projectId),
    queryFn: () =>
      offlineRead<TaskPage>(
        cacheKey,
        base +
          "/tasks?limit=1000" +
          (projectId ? `&project_id=${projectId}` : ""),
      ),
    networkMode: "always",
  });
  const live = useTaskLive(workspace, user, projectId, board.data, online);
  useEffect(() => {
    const read = () => {
      const params = new URLSearchParams(location.search);
      setProjectId(params.get("project") ?? "");
      setTaskId(params.get("task") ?? "");
      setSelected([]);
      setLimit(40);
    };
    queueMicrotask(read);
    window.addEventListener("tandem-task-selection", read);
    window.addEventListener("popstate", read);
    if (process.env.NODE_ENV === "production")
      void prepareChatShell("/tasks").catch(() => {});
    return () => {
      window.removeEventListener("tandem-task-selection", read);
      window.removeEventListener("popstate", read);
    };
  }, []);
  const project = projects.data?.find((p) => p.id === projectId);
  const canEdit = online && workspace.role !== "viewer" && !project?.archived;
  const canManage = online && ["owner", "admin"].includes(workspace.role);
  const tasks = (board.data?.tasks ?? []).filter(
    (t) =>
      (!priority || t.priority === priority) &&
      (!assignee ||
        (assignee === "unassigned"
          ? !t.assignee_id
          : t.assignee_id === assignee)) &&
      (!type || t.type === type) &&
      (!status || t.status === status) &&
      (!text ||
        `${t.key} ${t.title} ${t.description}`
          .toLocaleLowerCase()
          .includes(text.toLocaleLowerCase())),
  );
  const order = (a: Task, b: Task) => {
    let result = 0;
    if (sort === "rank") result = compareRank(a, b);
    else if (sort === "number") result = a.number - b.number;
    else if (sort === "assignee")
      result = (a.assignee?.name ?? "").localeCompare(b.assignee?.name ?? "");
    else if (sort === "due_date")
      result = (a.due_date ?? "9999-12-31").localeCompare(
        b.due_date ?? "9999-12-31",
      );
    else if (sort === "status")
      result = statuses.indexOf(a.status) - statuses.indexOf(b.status);
    else
      result = String(a[sort as keyof Task]).localeCompare(
        String(b[sort as keyof Task]),
      );
    return (desc ? -1 : 1) * result || a.id.localeCompare(b.id);
  };
  const sorted = tasks.slice().sort(order);
  const move = useMutation({
    mutationFn: ({
      task,
      status,
      before,
    }: {
      task: Task;
      status: Status;
      before?: string;
    }) =>
      api<Task>(
        base + `/tasks/${task.id}/move`,
        post({ version: task.version, status, before_id: before ?? null }),
      ),
    onSuccess: () => {
      setQuickTask(null);
      void client.invalidateQueries({
        queryKey: boardKey(workspace, projectId),
      });
    },
  });
  const bulk = useMutation({
    mutationFn: (changes: Record<string, unknown>) =>
      api(
        base + "/tasks/bulk",
        post({
          tasks: selected.map((id) => {
            const task = client
              .getQueryData<TaskPage>(boardKey(workspace, projectId))
              ?.tasks.find((t) => t.id === id);
            return { id, version: task?.version };
          }),
          ...changes,
        }),
      ),
    onSuccess: () => {
      setSelected([]);
      void client.invalidateQueries({
        queryKey: boardKey(workspace, projectId),
      });
    },
  });
  const more = useMutation({
    mutationFn: async () => {
      const page = await api<TaskPage>(
        base +
          "/tasks?limit=1000" +
          (projectId ? `&project_id=${projectId}` : "") +
          `&cursor=${encodeURIComponent(board.data?.next_cursor ?? "")}`,
      );
      client.setQueryData<TaskPage>(boardKey(workspace, projectId), (old) => {
        if (!old) return page;
        const ids = new Set(old.tasks.map((t) => t.id));
        const next = {
          ...old,
          tasks: [...old.tasks, ...page.tasks.filter((t) => !ids.has(t.id))],
          next_cursor: page.next_cursor,
        };
        saveCache(cacheKey, next);
        return next;
      });
    },
  });
  const currentConflict = conflictTask(move.error ?? bulk.error);
  function openTask(id: string) {
    navigateTaskParam("task", id);
  }
  function drop(status: Status, before?: string) {
    const task = drag.current;
    drag.current = null;
    if (task && canEdit && task.id !== before)
      move.mutate({ task, status, before });
  }
  function selection(id: string) {
    setSelected((previous) =>
      previous.includes(id)
        ? previous.filter((item) => item !== id)
        : previous.length < 100
          ? [...previous, id]
          : previous,
    );
  }
  function taskCard(task: Task) {
    return (
      <article
        key={task.id}
        className="task-card"
        data-testid="task-card"
        data-task-key={task.key}
        draggable={
          canEdit &&
          !projects.data?.find((p) => p.id === task.project_id)?.archived
        }
        onDragStart={(e) => {
          drag.current = task;
          e.dataTransfer.setData("text/plain", task.id);
          e.dataTransfer.effectAllowed = "move";
        }}
        onDragEnd={() => {
          drag.current = null;
        }}
        onDragOver={(e) => {
          if (canEdit) e.preventDefault();
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          drop(task.status, task.id);
        }}
      >
        <div className="row-between">
          <span className="task-key">{task.key}</span>
          <div className="row">
            {task.created_by_agent && (
              <span className="chip chip-agent">
                <Sparkles size={12} />
                Agent
              </span>
            )}
            <Button
              variant="ghost"
              className="task-quick-button"
              disabled={!canEdit}
              aria-label={`Actions for ${task.key}`}
              onClick={() => setQuickTask(task)}
            >
              <MoreHorizontal size={18} />
            </Button>
          </div>
        </div>
        <button className="task-card-title" onClick={() => openTask(task.id)}>
          {task.title}
        </button>
        <div className="task-card-meta">
          <span className={`chip task-priority priority-${task.priority}`}>
            <Flag size={12} />
            {task.priority} {priorities[task.priority]}
          </span>
          {task.due_date && (
            <span className="task-due">
              <Calendar size={12} />
              {new Date(task.due_date + "T12:00:00").toLocaleDateString(
                undefined,
                { month: "short", day: "numeric" },
              )}
            </span>
          )}
        </div>
        <div className="row-between task-card-footer">
          <span className="text-small text-muted row">
            <MessageSquare size={14} />
            {task.comment_count}
          </span>
          {task.assignee ? (
            <span
              className="avatar"
              title={task.assignee.name}
              aria-label={`Assigned to ${task.assignee.name}`}
            >
              {task.assignee.name.slice(0, 1).toUpperCase()}
            </span>
          ) : (
            <span className="text-small text-muted">Unassigned</span>
          )}
        </div>
      </article>
    );
  }
  function column(s: Status) {
    const rows = sorted.filter((t) => t.status === s).sort(compareRank);
    return (
      <section
        key={s}
        className={`task-column ${s === mobileStatus ? "mobile-status-active" : ""}`}
        aria-label={statusLabels[s]}
        onDragOver={(e) => {
          if (canEdit) e.preventDefault();
        }}
        onDrop={(e) => {
          e.preventDefault();
          drop(s);
        }}
      >
        <div className="task-column-heading">
          <h2>
            <span className={`status-dot status-${s}`} />
            {statusLabels[s]}
            <span className="task-count">{rows.length}</span>
          </h2>
          {canEdit && (
            <Button
              variant="ghost"
              aria-label={`Add task to ${statusLabels[s]}`}
              onClick={() => setNewTask(true)}
            >
              <Plus size={16} />
            </Button>
          )}
        </div>
        <div className="task-column-cards">
          {rows.slice(0, limit).map(taskCard)}
          {!rows.length && (
            <p className="task-column-empty">No tasks here yet</p>
          )}
          {rows.length > limit && (
            <Button variant="ghost" onClick={() => setLimit((n) => n + 40)}>
              Show more {statusLabels[s].toLowerCase()} tasks
            </Button>
          )}
        </div>
      </section>
    );
  }
  function headerSort(key: string, label: string) {
    return (
      <th
        scope="col"
        aria-sort={sort === key ? (desc ? "descending" : "ascending") : "none"}
      >
        <button
          onClick={() => {
            if (sort === key) setDesc(!desc);
            else {
              setSort(key);
              setDesc(false);
            }
          }}
        >
          {label}
          {sort === key && <ChevronDown size={13} />}
        </button>
      </th>
    );
  }
  function tableRows(rows: Task[]) {
    return rows.slice(0, limit).map((task) => (
      <tr key={task.id} data-task-key={task.key}>
        <td>
          <input
            type="checkbox"
            aria-label={`Select ${task.key}`}
            checked={selected.includes(task.id)}
            disabled={!canEdit}
            onChange={() => selection(task.id)}
          />
        </td>
        <td className="task-key">
          <button onClick={() => openTask(task.id)}>{task.key}</button>
        </td>
        <td>
          <button
            className="task-table-title"
            onClick={() => openTask(task.id)}
          >
            {task.title}
          </button>
          {task.created_by_agent && (
            <span className="chip chip-agent">Agent</span>
          )}
        </td>
        <td>
          <span className={`chip status-${task.status}`}>
            {statusLabels[task.status]}
          </span>
        </td>
        <td>
          <span className={`chip priority-${task.priority}`}>
            <Flag size={12} />
            {task.priority} {priorities[task.priority]}
          </span>
        </td>
        <td>{task.assignee?.name ?? "Unassigned"}</td>
        <td>{task.due_date ?? "—"}</td>
        <td>{new Date(task.updated_at).toLocaleDateString()}</td>
      </tr>
    ));
  }
  return (
    <div className="tasks-page">
      <header className="tasks-heading">
        <div>
          <div className="row">
            <Folder
              size={23}
              className={`project-color-${project?.color ?? "brand"}`}
            />
            <h1>{project?.name ?? "Task board"}</h1>
            <span className="chip">
              {tasks.filter((t) => t.status !== "done").length} open
            </span>
          </div>
          <p>{project?.description || "Plan together. Keep work moving."}</p>
        </div>
        <div className="row">
          <span className="text-small text-muted task-connection" role="status">
            {live.connection}
          </span>
          {project && canManage && (
            <Button
              variant="ghost"
              aria-label="Project settings"
              onClick={() => setProjectDialog(project)}
            >
              <Settings size={18} />
            </Button>
          )}
          <Button
            className="desktop-new-task"
            onClick={() => setNewTask(true)}
            disabled={!canEdit || !projects.data?.some((p) => !p.archived)}
          >
            <Plus size={17} />
            New task
          </Button>
        </div>
      </header>
      {!online && (
        <p className="offline-banner">
          You are offline. Tasks are read only. Last sync:{" "}
          {cached<TaskPage>(cacheKey)?.syncedAt
            ? new Date(cached<TaskPage>(cacheKey)!.syncedAt).toLocaleString()
            : "unavailable"}
          .
        </p>
      )}
      {project?.archived && (
        <p className="offline-banner">
          This project is archived. Its tasks are read only.
        </p>
      )}
      <div className="task-toolbar">
        <div className="task-view-tabs" role="group" aria-label="Task view">
          <Button
            variant="ghost"
            aria-pressed={view === "board"}
            onClick={() => setView("board")}
          >
            <LayoutGrid size={16} />
            Board
          </Button>
          <Button
            variant="ghost"
            aria-pressed={view === "table"}
            onClick={() => setView("table")}
          >
            <List size={16} />
            Table
          </Button>
        </div>
        <label className="sr-only" htmlFor="task-project-switch">
          Project
        </label>
        <select
          id="task-project-switch"
          className="input"
          value={projectId}
          onChange={(e) => {
            if (e.target.value === "__new") {
              setProjectDialog("new");
              return;
            }
            navigateTaskParam("project", e.target.value);
            navigateTaskParam("task", "");
          }}
        >
          <option value="">All projects</option>
          {canManage && <option value="__new">New project…</option>}
          {projects.data?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.archived ? " (archived)" : ""}
            </option>
          ))}
        </select>
        {canManage && (
          <Button variant="ghost" onClick={() => setProjectDialog("new")}>
            New project
          </Button>
        )}
        {view === "table" && (
          <label className="row text-small">
            <input
              type="checkbox"
              checked={group}
              onChange={(e) => setGroup(e.target.checked)}
            />
            Group by status
          </label>
        )}
      </div>
      <Button
        variant="ghost"
        className="task-mobile-filter-button"
        aria-expanded={filtersOpen}
        onClick={() => setFiltersOpen(!filtersOpen)}
      >
        Filters
      </Button>
      <div className={`task-filters ${filtersOpen ? "filters-open" : ""}`}>
        <input
          className="input"
          aria-label="Filter tasks by text"
          placeholder="Filter tasks…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <select
          className="input"
          aria-label="Filter status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {statusLabels[s]}
            </option>
          ))}
        </select>
        <select
          className="input"
          aria-label="Filter priority"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          <option value="">All priorities</option>
          {Object.entries(priorities).map(([p, label]) => (
            <option key={p} value={p}>
              {p} {label}
            </option>
          ))}
        </select>
        <select
          className="input"
          aria-label="Filter assignee"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
        >
          <option value="">All assignees</option>
          <option value="unassigned">Unassigned</option>
          {members.data?.map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {m.name}
            </option>
          ))}
        </select>
        <select
          className="input"
          aria-label="Filter type"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="">All types</option>
          <option value="bug">Bugs</option>
          <option value="task">Tasks</option>
        </select>
      </div>
      <div className="task-mobile-chips">
        <button
          className="chip"
          onClick={() => {
            setType("");
            setPriority("");
            setAssignee("");
            setStatus("");
            setText("");
          }}
        >
          All
        </button>
        <button
          className={`chip ${assignee === user.id ? "chip-brand" : ""}`}
          onClick={() => setAssignee(assignee === user.id ? "" : user.id)}
        >
          My tasks
        </button>
        <button
          className={`chip ${type === "bug" ? "chip-brand" : ""}`}
          onClick={() => setType(type === "bug" ? "" : "bug")}
        >
          Bugs
        </button>
        <button
          className={`chip ${priority === "P1" ? "chip-brand" : ""}`}
          onClick={() => setPriority(priority === "P1" ? "" : "P1")}
        >
          P1
        </button>
      </div>
      <div
        className="task-mobile-status"
        role="group"
        aria-label="Board status"
      >
        {statuses.map((s) => (
          <button
            key={s}
            aria-pressed={s === mobileStatus}
            onClick={() => setMobileStatus(s)}
          >
            {statusLabels[s]}
            <span>{tasks.filter((t) => t.status === s).length}</span>
          </button>
        ))}
      </div>
      <ErrorNotice
        error={
          board.error ??
          projects.error ??
          (!currentConflict ? (move.error ?? bulk.error) : null) ??
          more.error
        }
      />
      <span className="sr-only" role="status" aria-live="polite">
        {live.announcement}
      </span>
      {board.isPending ? (
        <p className="loading" role="status">
          Opening tasks…
        </p>
      ) : !projects.data?.length ? (
        <section className="empty">
          <Folder size={36} />
          <h2>Make room for your next project.</h2>
          <p>Projects bring tasks and conversations together.</p>
          {canManage && (
            <Button onClick={() => setProjectDialog("new")}>
              Create project
            </Button>
          )}
        </section>
      ) : view === "board" ? (
        <div className="task-board">{statuses.map(column)}</div>
      ) : (
        <>
          {selected.length > 0 && canEdit && (
            <div className="task-bulk-bar">
              <strong>{selected.length} selected</strong>
              <select
                className="input"
                aria-label="Bulk status"
                defaultValue=""
                onChange={(e) => {
                  if (e.target.value) bulk.mutate({ status: e.target.value });
                  e.target.value = "";
                }}
                disabled={bulk.isPending}
              >
                <option value="">Change status</option>
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {statusLabels[s]}
                  </option>
                ))}
              </select>
              <select
                className="input"
                aria-label="Bulk assignee"
                defaultValue=""
                onChange={(e) => {
                  if (e.target.value)
                    bulk.mutate({
                      assignee_id:
                        e.target.value === "unassigned" ? null : e.target.value,
                    });
                  e.target.value = "";
                }}
                disabled={bulk.isPending}
              >
                <option value="">Assign to…</option>
                <option value="unassigned">Unassigned</option>
                {members.data?.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.name}
                  </option>
                ))}
              </select>
              <Button variant="ghost" onClick={() => setSelected([])}>
                Clear
              </Button>
            </div>
          )}
          <div className="task-table-scroll">
            <table className="task-table" aria-label="Tasks">
              <thead>
                <tr>
                  <th scope="col">
                    <input
                      type="checkbox"
                      aria-label="Select visible tasks (up to 100)"
                      disabled={!canEdit}
                      checked={
                        selected.length > 0 &&
                        selected.length === Math.min(sorted.length, limit, 100)
                      }
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? sorted
                                .slice(0, Math.min(limit, 100))
                                .map((t) => t.id)
                            : [],
                        )
                      }
                    />
                  </th>
                  {headerSort("number", "ID")}
                  {headerSort("title", "Title")}
                  {headerSort("status", "Status")}
                  {headerSort("priority", "Priority")}
                  {headerSort("assignee", "Assignee")}
                  {headerSort("due_date", "Due")}
                  {headerSort("updated_at", "Updated")}
                </tr>
              </thead>
              <tbody>
                {group
                  ? statuses.map((s) => {
                      const rows = sorted.filter((t) => t.status === s);
                      return rows.length ? (
                        <TableGroup
                          key={s}
                          label={statusLabels[s]}
                          count={rows.length}
                        >
                          {tableRows(rows)}
                        </TableGroup>
                      ) : null;
                    })
                  : tableRows(sorted)}
              </tbody>
            </table>
          </div>
          {sorted.length > limit && (
            <Button variant="ghost" onClick={() => setLimit((n) => n + 40)}>
              Show more rows
            </Button>
          )}
        </>
      )}
      {board.data?.next_cursor && (
        <div className="task-load-more">
          <p className="text-small text-muted">
            Showing {board.data.tasks.length} of {board.data.total} tasks. Load
            more to include them in filters.
          </p>
          <Button
            variant="secondary"
            disabled={!online || more.isPending}
            onClick={() => more.mutate()}
          >
            Load more tasks
          </Button>
        </div>
      )}
      {canEdit && projects.data?.some((p) => !p.archived) && (
        <Button className="task-fab" onClick={() => setNewTask(true)}>
          <Plus size={20} />
          New task
        </Button>
      )}
      {newTask && (
        <NewTaskDialog
          workspace={workspace}
          user={user}
          projectId={projectId}
          onClose={() => setNewTask(false)}
          onCreated={(task) => {
            if (projectId && projectId !== task.project_id)
              navigateTaskParam("project", task.project_id);
            openTask(task.id);
          }}
        />
      )}
      {projectDialog && (
        <ProjectDialog
          workspace={workspace}
          project={projectDialog === "new" ? undefined : projectDialog}
          onClose={() => setProjectDialog(null)}
        />
      )}
      {taskId && (
        <TaskDetail
          key={taskId}
          workspace={workspace}
          user={user}
          taskId={taskId}
          initial={board.data?.tasks.find((t) => t.id === taskId)}
          onClose={() => navigateTaskParam("task", "")}
        />
      )}
      {quickTask && (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) setQuickTask(null);
          }}
          title={quickTask.key}
          description="Move this task or open its details."
          actions={false}
        >
          <div className="task-quick-actions">
            <h3>{quickTask.title}</h3>
            <p className="text-small text-muted">Move to</p>
            {statuses.map((s) => (
              <Button
                key={s}
                variant={quickTask.status === s ? "secondary" : "ghost"}
                disabled={!canEdit || move.isPending || quickTask.status === s}
                onClick={() => move.mutate({ task: quickTask, status: s })}
              >
                {quickTask.status === s && <Check size={16} />}
                {statusLabels[s]}
              </Button>
            ))}
            <Button
              onClick={() => {
                openTask(quickTask.id);
                setQuickTask(null);
              }}
            >
              Open details
            </Button>
          </div>
        </ConfirmDialog>
      )}
      {currentConflict && (
        <ConfirmDialog
          open
          onOpenChange={(open) => {
            if (!open) {
              move.reset();
              bulk.reset();
            }
          }}
          title="This task changed"
          description={`${currentConflict.key} is now version ${currentConflict.version}. Choose how to continue.`}
        >
          <Button
            disabled={!online || move.isPending || bulk.isPending}
            onClick={() => {
              if (move.variables && move.error)
                move.mutate({ ...move.variables, task: currentConflict });
              else {
                client.setQueryData<TaskPage>(
                  boardKey(workspace, projectId),
                  (old) =>
                    old
                      ? {
                          ...old,
                          tasks: old.tasks.map((t) =>
                            t.id === currentConflict.id ? currentConflict : t,
                          ),
                        }
                      : old,
                );
                if (bulk.variables) bulk.mutate(bulk.variables);
                void client.invalidateQueries({
                  queryKey: boardKey(workspace, projectId),
                });
              }
            }}
          >
            Keep mine
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              move.reset();
              bulk.reset();
              setQuickTask(null);
              void client.invalidateQueries({
                queryKey: boardKey(workspace, projectId),
              });
            }}
          >
            Take server&apos;s
          </Button>
        </ConfirmDialog>
      )}
    </div>
  );
}
function TableGroup({
  label,
  count,
  children,
}: {
  label: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <>
      <tr className="task-table-group">
        <th colSpan={8} scope="rowgroup">
          {label}
          <span className="task-count">{count}</span>
        </th>
      </tr>
      {children}
    </>
  );
}
