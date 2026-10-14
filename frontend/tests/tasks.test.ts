import { describe, expect, it } from "vitest";
import {
  compareRank,
  conflictTask,
  mergeTaskPage,
  type Task,
  type TaskPage,
} from "@/lib/tasks";
import { ApiError } from "@/lib/api";
function task(id: string, rank = "1024.000000000000000001", version = 1): Task {
  return {
    id,
    workspace_id: "w",
    project_id: "p",
    key: "TASK-1",
    number: 1,
    title: "Task",
    description: "",
    type: "task",
    status: "todo",
    priority: "P2",
    assignee_id: null,
    assignee: null,
    reporter: { id: "u", name: "User" },
    due_date: null,
    created_by_agent: false,
    version,
    rank,
    comment_count: 0,
    last_event_seq: 1,
    created_at: "2026-10-14",
    updated_at: "2026-10-14",
    deleted_at: null,
  };
}
const page = (tasks: Task[]): TaskPage => ({
  tasks,
  last_seq: 1,
  total: tasks.length,
  next_cursor: null,
  counts: { todo: tasks.length, in_progress: 0, done: 0 },
});
describe("task client state", () => {
  it("preserves fractional order below JavaScript floating point precision", () => {
    expect(
      compareRank(
        task("z", "1024.000000000000000001"),
        task("a", "1024.000000000000000002"),
      ),
    ).toBeLessThan(0);
    expect(
      compareRank(
        task("z", "-1.000000000000000002"),
        task("a", "-1.000000000000000001"),
      ),
    ).toBeLessThan(0);
  });
  it("deduplicates replay and REST acknowledgements by version, including deletion", () => {
    const initial = page([task("a")]);
    expect(mergeTaskPage(initial, task("a"), "p")).toBe(initial);
    const moved = mergeTaskPage(
      initial,
      { ...task("a", "2048", 2), status: "done" },
      "p",
    );
    expect(moved.total).toBe(1);
    expect(moved.counts).toEqual({ todo: 0, in_progress: 0, done: 1 });
    const deleted = mergeTaskPage(
      moved,
      { ...task("a", "2048", 3), status: "done", deleted_at: "2026-10-15" },
      "p",
    );
    expect(deleted.tasks).toHaveLength(0);
    expect(deleted.total).toBe(0);
  });
  it("recognizes current-state task conflicts separately from other 409 errors", () => {
    expect(conflictTask(new ApiError(409, "Archived"))).toBeNull();
    const current = task("a", "1024", 4);
    expect(
      conflictTask(
        new ApiError(409, "Changed", { kind: "task_conflict", current }),
      ),
    ).toEqual(current);
  });
});
