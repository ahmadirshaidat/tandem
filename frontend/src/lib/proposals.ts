export type ProposalItem = {
  item_id: string;
  project_id: string;
  title: string;
  description: string;
  type: "task" | "bug";
  status: string;
  priority: string;
  assignee_id: string | null;
  due_date: string | null;
  depends_on: string[];
};
export type ProposalPayload = {
  items?: ProposalItem[];
  task_id?: string;
  version?: number;
  changes?: {
    title?: string;
    description?: string;
    status?: string;
    due_date?: string | null;
  };
  assignee_id?: string | null;
  priority?: string;
  body?: string;
};
export type Proposal = {
  id: string;
  workspace_id: string;
  run_id: string;
  channel_id: string;
  trigger_message_id: string;
  kind: string;
  risk: "low" | "high";
  status: string;
  payload: ProposalPayload;
  payload_hash: string;
  sources: { type: string; id: string; label: string; url: string }[];
  requested_by: { id: string; name: string };
  decided_by: { id: string; name: string } | null;
  decided_at: string | null;
  decision_reason: string | null;
  execution_result: { task_ids: string[]; comment_ids: string[] } | null;
  expires_at: string;
  created_at: string;
  version: number;
  required_role: string;
};
export type ProposalPage = {
  proposals: Proposal[];
  next_cursor: string | null;
};
export function mergeProposals(previous: Proposal[], incoming: Proposal[]) {
  const records = new Map(previous.map((p) => [p.id, p]));
  for (const p of incoming)
    if (!records.has(p.id) || records.get(p.id)!.version <= p.version)
      records.set(p.id, p);
  return [...records.values()].sort(
    (a, b) =>
      a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id),
  );
}
export function canApprove(role: string, required: string) {
  return (
    ["owner", "admin"].includes(role) ||
    (role === "editor" && required === "editor")
  );
}
export function kindLabel(kind: string) {
  return (
    (
      {
        create_tasks: "Proposed tasks",
        update_task: "Proposed task update",
        reassign_task: "Proposed reassignment",
        change_priority: "Proposed priority change",
        delete_task: "Proposed deletion",
        add_comment: "Proposed comment",
      } as Record<string, string>
    )[kind] ?? "Proposal"
  );
}
