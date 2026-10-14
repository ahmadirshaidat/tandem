"use client";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type Member, type User, type Workspace } from "./api";
import { cached, removeCache, saveCache } from "./offline";
import type { ProjectOut, TaskOut, TaskCommentOut } from "./events.generated";
export type Project = ProjectOut;
export type Task = TaskOut;
export type Comment = TaskCommentOut;
export type Status = "todo" | "in_progress" | "done";
export const statuses: Status[] = ["todo", "in_progress", "done"];
export const statusLabels = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
};
export const priorities = { P1: "High", P2: "Medium", P3: "Low" };
export type TaskPage = {
  tasks: Task[];
  last_seq: number;
  next_cursor: string | null;
  total: number;
  counts: Record<Status, number>;
};
export type ItemLink = {
  id: string;
  source: { type: string; id: string; label: string; url: string };
  target: { type: string; id: string; label: string; url: string };
};
export type Activity = {
  id: string;
  kind: string;
  field: string;
  old_value: unknown;
  new_value: unknown;
  actor: { id: string; name: string };
  created_at: string;
};
export const taskBase = (workspace: Workspace) => `/workspaces/${workspace.id}`;
export const projectKey = (workspace: Workspace) => ["projects", workspace.id];
export const boardKey = (workspace: Workspace, projectId: string) => [
  "tasks",
  workspace.id,
  projectId,
];
export const taskCacheKey = (user: User, workspace: Workspace, part: string) =>
  `tasks:${user.id}:${workspace.id}:${part}`;
export async function offlineRead<T>(key: string, path: string): Promise<T> {
  if (!navigator.onLine) {
    const stored = cached<T>(key);
    if (stored) return stored.value;
    throw new ApiError(
      0,
      "You are offline. Open this view online once to save it.",
    );
  }
  try {
    const value = await api<T>(path);
    saveCache(key, value);
    return value;
  } catch (error) {
    if (error instanceof ApiError && [401, 403, 404].includes(error.status))
      removeCache(key);
    throw error;
  }
}
export function useProjects(workspace: Workspace, user: User) {
  return useQuery({
    queryKey: projectKey(workspace),
    queryFn: () =>
      offlineRead<Project[]>(
        taskCacheKey(user, workspace, "projects"),
        taskBase(workspace) + "/projects",
      ),
    networkMode: "always",
  });
}
export function useTaskMembers(workspace: Workspace, user: User) {
  return useQuery({
    queryKey: ["task-members", workspace.id],
    queryFn: () =>
      offlineRead<Member[]>(
        taskCacheKey(user, workspace, "members"),
        taskBase(workspace) + "/members",
      ),
    networkMode: "always",
  });
}
function fixedRank(value: string) {
  const [whole, fraction = ""] = value.split(".");
  const negative = whole.startsWith("-");
  const amount =
    BigInt(whole.replace("-", "")) * BigInt("1000000000000000000") +
    BigInt(fraction.padEnd(18, "0").slice(0, 18));
  return negative ? -amount : amount;
}
export function compareRank(a: Task, b: Task) {
  const left = fixedRank(a.rank),
    right = fixedRank(b.rank);
  return left < right ? -1 : left > right ? 1 : a.id.localeCompare(b.id);
}
export function mergeTaskPage(
  page: TaskPage,
  task: Task,
  projectId: string,
): TaskPage {
  const old = page.tasks.find((item) => item.id === task.id);
  if (old && old.version >= task.version) return page;
  const included =
    !task.deleted_at && (!projectId || task.project_id === projectId);
  const tasks = page.tasks.filter((item) => item.id !== task.id);
  if (included) tasks.push(task);
  const counts = { ...page.counts };
  if (old) counts[old.status]--;
  if (included) counts[task.status]++;
  return {
    ...page,
    tasks,
    total: page.total + Number(included) - Number(!!old),
    counts,
  };
}
export function conflictTask(error: unknown): Task | null {
  if (
    !(error instanceof ApiError) ||
    error.status !== 409 ||
    !error.details ||
    Array.isArray(error.details)
  )
    return null;
  return error.details.kind === "task_conflict"
    ? (error.details.current as Task)
    : null;
}
