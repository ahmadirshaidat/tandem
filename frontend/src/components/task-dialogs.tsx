"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post, type User, type Workspace } from "@/lib/api";
import { useOnline } from "@/lib/online";
import {
  priorities,
  projectKey,
  statusLabels,
  statuses,
  taskBase,
  useProjects,
  useTaskMembers,
  type Project,
  type Task,
} from "@/lib/tasks";
import type { Channel } from "@/lib/channels";
import { ConfirmDialog } from "./ui/dialog";
import { Button } from "./ui/button";
import { ErrorNotice, Field } from "./common";
export function TaskSelect({
  label,
  name,
  value,
  defaultValue,
  onChange,
  children,
  disabled = false,
}: {
  label: string;
  name: string;
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="field">
      <span className="field-label-row">{label}</span>
      <select
        aria-label={label}
        name={name}
        value={value}
        defaultValue={defaultValue}
        onChange={onChange ? (e) => onChange(e.target.value) : undefined}
        className="input"
        disabled={disabled}
      >
        {children}
      </select>
    </label>
  );
}
export function NewTaskDialog({
  workspace,
  user,
  projectId,
  message,
  onClose,
  onCreated,
}: {
  workspace: Workspace;
  user: User;
  projectId?: string;
  message?: { id: string; body: string };
  onClose: () => void;
  onCreated?: (task: Task) => void;
}) {
  const online = useOnline(),
    projects = useProjects(workspace, user),
    members = useTaskMembers(workspace, user),
    client = useQueryClient();
  const [chosen, setChosen] = useState(projectId ?? "");
  const writable = projects.data?.filter((item) => !item.archived) ?? [];
  const create = useMutation({
    mutationFn: (form: FormData) =>
      api<Task>(
        taskBase(workspace) + (message ? "/tasks/from-message" : "/tasks"),
        post({
          project_id: form.get("project_id"),
          title: form.get("title"),
          description: form.get("description"),
          type: form.get("type"),
          status: form.get("status"),
          priority: form.get("priority"),
          assignee_id: form.get("assignee_id") || null,
          due_date: form.get("due_date") || null,
          ...(message ? { message_id: message.id } : {}),
        }),
      ),
    onSuccess: (task) => {
      void client.invalidateQueries({ queryKey: ["tasks", workspace.id] });
      onCreated?.(task);
      onClose();
    },
  });
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (!open && !create.isPending) onClose();
      }}
      title={message ? "Create task from message" : "New task"}
      description={
        message
          ? "Create a workspace-visible task linked to this conversation."
          : "Give your team a clear next step."
      }
      actions={false}
    >
      <ErrorNotice error={create.error ?? projects.error} />
      {!online && (
        <p className="offline-banner">
          You are offline. Task edits are disabled.
        </p>
      )}
      {!writable.length ? (
        <p>
          Create an active project first. An Owner or Admin can create one from
          Projects.
        </p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate(new FormData(event.currentTarget));
          }}
        >
          <Field
            id="new-task-title"
            name="title"
            label="Title"
            defaultValue={message?.body.split("\n")[0].slice(0, 240)}
            maxLength={240}
            required
          />
          <label className="field">
            Description
            <textarea
              className="input"
              name="description"
              aria-label="Description"
              defaultValue={message?.body ?? ""}
              maxLength={12000}
              rows={4}
            />
          </label>
          <div className="task-field-grid">
            <TaskSelect
              label="Project"
              name="project_id"
              value={
                writable.some((p) => p.id === chosen) ? chosen : writable[0].id
              }
              onChange={setChosen}
            >
              {writable.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </TaskSelect>
            <TaskSelect label="Type" name="type">
              <option value="task">Task</option>
              <option value="bug">Bug</option>
            </TaskSelect>
            <TaskSelect label="Status" name="status">
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {statusLabels[s]}
                </option>
              ))}
            </TaskSelect>
            <TaskSelect label="Priority" name="priority" defaultValue="P2">
              {Object.entries(priorities).map(([p, label]) => (
                <option key={p} value={p}>
                  {p} {label}
                </option>
              ))}
            </TaskSelect>
            <TaskSelect label="Assignee" name="assignee_id">
              <option value="">Unassigned</option>
              {members.data?.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.name}
                </option>
              ))}
            </TaskSelect>
            <Field
              label="Due date"
              id="new-task-due"
              name="due_date"
              type="date"
            />
          </div>
          <div className="task-dialog-footer">
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                !online || create.isPending || workspace.role === "viewer"
              }
            >
              {create.isPending ? "Creating…" : "Create task"}
            </Button>
          </div>
        </form>
      )}
    </ConfirmDialog>
  );
}
export function ProjectDialog({
  workspace,
  project,
  onClose,
}: {
  workspace: Workspace;
  project?: Project;
  onClose: () => void;
}) {
  const client = useQueryClient(),
    online = useOnline();
  const mutation = useMutation({
    mutationFn: (form: FormData) =>
      api<Project>(
        taskBase(workspace) + "/projects" + (project ? `/${project.id}` : ""),
        {
          method: project ? "PATCH" : "POST",
          body: JSON.stringify({
            name: form.get("name"),
            key: form.get("key"),
            color: form.get("color"),
            description: form.get("description"),
            ...(project ? { archived: form.get("archived") === "on" } : {}),
          }),
        },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: projectKey(workspace) });
      onClose();
    },
  });
  const channels = useQuery({
    queryKey: ["channels", workspace.id],
    queryFn: () => api<Channel[]>(taskBase(workspace) + "/channels"),
    enabled: !!project && online,
  });
  const link = useMutation({
    mutationFn: ({
      channel,
      enabled,
    }: {
      channel: Channel;
      enabled: boolean;
    }) =>
      api(taskBase(workspace) + `/channels/${channel.id}/project`, {
        method: "PATCH",
        body: JSON.stringify({ project_id: enabled ? project?.id : null }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["channels", workspace.id] });
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      api(taskBase(workspace) + `/projects/${project?.id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: projectKey(workspace) });
      onClose();
    },
  });
  const [deleting, setDeleting] = useState(false);
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={project ? "Project settings" : "New project"}
      description={
        project
          ? "Manage this project and its conversations."
          : "A shared home for your team's tasks."
      }
      actions={false}
    >
      <ErrorNotice
        error={mutation.error ?? link.error ?? remove.error ?? channels.error}
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(new FormData(e.currentTarget));
        }}
      >
        <Field
          label="Project name"
          id="project-name"
          name="name"
          required
          maxLength={80}
          defaultValue={project?.name}
        />
        <div className="task-field-grid">
          <Field
            label="Project key"
            id="project-key"
            name="key"
            required
            pattern="[A-Z][A-Z0-9]*"
            maxLength={10}
            defaultValue={project?.key}
            placeholder="WEB"
          />
          <TaskSelect
            label="Color"
            name="color"
            defaultValue={project?.color ?? "brand"}
          >
            {["brand", "agent", "success", "warning", "danger"].map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </TaskSelect>
        </div>
        <label className="field">
          Description
          <textarea
            className="input"
            aria-label="Project description"
            name="description"
            rows={3}
            maxLength={4000}
            defaultValue={project?.description}
          />
        </label>
        {project && (
          <label className="row">
            <input
              type="checkbox"
              name="archived"
              defaultChecked={project.archived}
            />
            Archived (read only)
          </label>
        )}
        <div className="task-dialog-footer">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!online || mutation.isPending}>
            {project ? "Save project" : "Create project"}
          </Button>
        </div>
      </form>
      {project && (
        <section className="task-detail-section">
          <h3>Linked channels</h3>
          <p className="text-small text-muted">
            Only channels you can access are shown.
          </p>
          {channels.data?.map((channel) => (
            <label className="project-channel-link row" key={channel.id}>
              <input
                type="checkbox"
                checked={channel.project_id === project.id}
                disabled={!online || link.isPending || project.archived}
                onChange={(e) =>
                  link.mutate({ channel, enabled: e.target.checked })
                }
              />
              #{channel.name}
            </label>
          ))}
          <Button
            variant="danger"
            disabled={!online || remove.isPending}
            onClick={() => (deleting ? remove.mutate() : setDeleting(true))}
          >
            {deleting ? "Confirm delete project" : "Delete empty project"}
          </Button>
        </section>
      )}
    </ConfirmDialog>
  );
}
