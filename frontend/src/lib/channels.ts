import type { Role } from "./api";
import type { SocketEvent } from "./events.generated";
export type Channel = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  name: string;
  topic: string;
  is_private: boolean;
  archived: boolean;
  last_seq: number;
  unread_count: number;
  mention_count: number;
  joined: boolean;
  last_read_seq: number;
};
export type ChannelMember = { user_id: string; name: string; role: Role };
export type Attachment = {
  id: string;
  url: string;
  content_type: string;
  size: number;
  width: number;
  height: number;
};
export type Message = {
  id: string;
  workspace_id: string;
  channel_id: string;
  author: { id: string; name: string };
  body: string;
  seq: number;
  client_message_id: string;
  thread_root_id: string | null;
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  mentions: { user_id: string | null; is_agent: boolean }[];
  mentions_agent: boolean;
  attachments: Attachment[];
  reply_count: number;
  pending?: "sending" | "failed";
};
export type History = {
  messages: Message[];
  last_seq: number;
  next_cursor: number | null;
  root?: Message;
};
export type LiveEvent = SocketEvent;

export function mergeMessages(
  previous: Message[],
  incoming: Message[],
): Message[] {
  const records = new Map(previous.map((message) => [message.id, message]));
  for (const message of incoming) {
    // REST responses and live events acknowledge the same optimistic send.
    for (const [id, old] of records)
      if (
        old.author.id === message.author.id &&
        old.client_message_id === message.client_message_id &&
        id !== message.id
      )
        records.delete(id);
    const existing = records.get(message.id);
    const version = (value: Message) =>
      value.deleted_at ?? value.edited_at ?? value.created_at;
    if (!existing || version(message) >= version(existing) || existing.pending)
      records.set(message.id, {
        ...message,
        reply_count: Math.max(message.reply_count, existing?.reply_count ?? 0),
      });
  }
  return [...records.values()].sort((a, b) => a.seq - b.seq);
}
