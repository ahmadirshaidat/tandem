export type AgentRun = {
  id: string;
  channel_id: string;
  trigger_message_id: string;
  status: string;
  error_category: string | null;
  provider: string | null;
  model: string | null;
  latency_ms: number | null;
  steps: { name: string; status: string; duration_ms: number; count: number }[];
};
export type AgentSettings = {
  enabled: boolean;
  provider_chain: string[];
  monthly_run_limit: number;
  pause_at_limit: boolean;
  usage: number;
  channels: {
    id: string;
    name: string;
    is_private: boolean;
    enabled: boolean;
  }[];
  providers: Record<string, { model: string; status: string }>;
};
export type AuditEvent = {
  id: string;
  created_at: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  target_type: string;
  target_id: string | null;
  redacted_arguments: Record<string, unknown>;
  result_status: string;
  request_id: string;
};
export function stepLabel(name: string, count: number) {
  if (name.startsWith("propose_"))
    return name === "propose_create_tasks"
      ? `Proposed ${count} tasks`
      : "Drafted a proposal";
  if (name === "get_channel_context" || name === "summarize_channel")
    return `Read ${count} ${count === 1 ? "message" : "messages"}`;
  if (name === "search_memory") return "Searched memory";
  if (name === "find_similar_bugs") return "Found similar bugs";
  if (name === "analyze_bug") return "Analyzed bug evidence";
  if (name === "search_messages") return "Searched messages";
  if (name === "search_workspace") return "Searched workspace";
  return name.replaceAll("_", " ");
}
