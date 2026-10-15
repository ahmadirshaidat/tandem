"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Hash,
  Lock,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  Plus,
  Send,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  post,
  type User,
  type Workspace,
  type Member,
} from "@/lib/api";
import {
  mergeMessages,
  type Attachment,
  type Channel,
  type ChannelMember,
  type History,
  type LiveEvent,
  type Message,
} from "@/lib/channels";
import {
  cached,
  removeCache,
  removeWorkspaceCache,
  prepareChatShell,
  saveCache,
} from "@/lib/offline";
import { ErrorNotice, Field } from "./common";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/dialog";
import { SafeMarkdown } from "./safe-markdown";
import { ProposalCard, useChannelProposals } from "./proposals";
import {
  mergeProposals,
  type ProposalPage,
  type Proposal,
} from "@/lib/proposals";
import { AgentSteps, AgentPanel, AgentActivity } from "./agent";
import { NewTaskDialog } from "./task-dialogs";

function watchChannelSelection(callback: () => void) {
  window.addEventListener("tandem-channel-selection", callback);
  window.addEventListener("popstate", callback);
  return () => {
    window.removeEventListener("tandem-channel-selection", callback);
    window.removeEventListener("popstate", callback);
  };
}
function watchOnline(callback: () => void) {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}
export function useOnline() {
  return useSyncExternalStore(
    watchOnline,
    () => navigator.onLine,
    () => true,
  );
}
const channelsKey = (workspace: Workspace) => ["channels", workspace.id];
function channelCache(user: User, workspace: Workspace) {
  return `channels:${user.id}:${workspace.id}`;
}

export function useChannels(user: User, workspace: Workspace) {
  const online = useOnline();
  return useQuery({
    queryKey: channelsKey(workspace),
    queryFn: async () => {
      const key = channelCache(user, workspace);
      if (!navigator.onLine) {
        const stored = cached<Channel[]>(key);
        if (stored) return stored.value;
        throw new Error("No channels saved on this device yet.");
      }
      try {
        const result = await api<Channel[]>(
          `/workspaces/${workspace.id}/channels`,
        );
        saveCache(key, result);
        return result;
      } catch (error) {
        if (error instanceof ApiError && [401, 404].includes(error.status))
          removeCache(key);
        throw error;
      }
    },
    networkMode: "always",
    refetchOnWindowFocus: online,
    retry: false,
  });
}

export function ChannelNavigation({
  workspace,
  user,
  selectedId,
  choose,
}: {
  workspace: Workspace;
  user: User;
  selectedId?: string;
  choose?: (id: string) => void;
}) {
  const channels = useChannels(user, workspace);
  const selectedUrl = useSyncExternalStore(
    watchChannelSelection,
    () => new URLSearchParams(location.search).get("channel"),
    () => null,
  );
  const activeId =
    selectedId ??
    (choose ? (selectedUrl ?? channels.data?.[0]?.id) : undefined);
  const [open, setOpen] = useState(false);
  const client = useQueryClient();
  const canCreate = workspace.role !== "viewer";
  const mutation = useMutation({
    mutationFn: (form: FormData) =>
      api<Channel>(
        `/workspaces/${workspace.id}/channels`,
        post({
          name: form.get("name"),
          topic: form.get("topic"),
          is_private: form.get("private") === "on",
        }),
      ),
    onSuccess: async (c) => {
      await client.invalidateQueries({ queryKey: channelsKey(workspace) });
      setOpen(false);
      choose?.(c.id);
    },
  });
  return (
    <>
      <div className="channel-nav-heading">
        <span>Channels</span>
        {canCreate && (
          <Button
            variant="ghost"
            aria-label="Create channel"
            onClick={() => {
              mutation.reset();
              setOpen(true);
            }}
          >
            <Plus size={16} />
          </Button>
        )}
      </div>
      <nav aria-label="Channels" className="channel-navigation">
        {channels.data?.map((c) => {
          const content = (
            <>
              <span>
                {c.is_private ? <Lock size={16} /> : <Hash size={17} />}
              </span>
              <span className="channel-nav-name">
                {c.name}
                {c.archived && <span className="text-small"> · Archived</span>}
              </span>
              {c.mention_count > 0 ? (
                <span className="channel-badge">@{c.mention_count}</span>
              ) : c.unread_count > 0 ? (
                <span className="channel-badge">{c.unread_count}</span>
              ) : null}
            </>
          );
          return choose ? (
            <button
              type="button"
              key={c.id}
              className="nav-item"
              aria-current={c.id === activeId ? "page" : undefined}
              onClick={() => choose(c.id)}
            >
              {content}
            </button>
          ) : (
            <Link
              key={c.id}
              className="nav-item"
              href={`/channels?channel=${c.id}`}
            >
              {content}
            </Link>
          );
        })}
      </nav>
      <ErrorNotice error={channels.error} />
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Create a channel"
        description="Give your team a place to talk."
        actions={false}
      >
        <ErrorNotice error={mutation.error} />
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate(new FormData(event.currentTarget));
          }}
        >
          <Field
            id="channel-name"
            name="name"
            label="Channel name"
            required
            maxLength={64}
            pattern="[a-z0-9][a-z0-9-]*"
            placeholder="e.g. bug-triage"
          />
          <Field
            id="channel-topic"
            name="topic"
            label="Topic"
            maxLength={240}
            placeholder="What happens here?"
          />
          {["owner", "admin"].includes(workspace.role) && (
            <label className="row">
              <input type="checkbox" name="private" /> Private — invited members
              only
            </label>
          )}
          <div className="dialog-actions">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              Create channel
            </Button>
          </div>
        </form>
      </ConfirmDialog>
    </>
  );
}

type LiveState = {
  messages: Message[];
  cursor: number;
  next: number | null;
  syncedAt: string;
  ready: boolean;
  denied: boolean;
};
const initialState: LiveState = {
  messages: [],
  cursor: 0,
  next: null,
  syncedAt: "",
  ready: false,
  denied: false,
};
function useRoom(user: User, workspace: Workspace, channel: Channel) {
  const client = useQueryClient();
  const online = useOnline();
  const base = `/workspaces/${workspace.id}/channels/${channel.id}`;
  const key = `history:${user.id}:${workspace.id}:${channel.id}`;
  const [live, setLive] = useState<LiveState>(initialState);
  const [error, setError] = useState<Error | null>(null);
  const [connection, setConnection] = useState("Connecting…");
  const [presence, setPresence] = useState<string[]>([]);
  const [typing, setTyping] = useState<string[]>([]);
  const socket = useRef<WebSocket | null>(null);
  const cursor = useRef(0);
  const lastTyping = useRef(0);
  useEffect(() => {
    let alive = true;
    async function load() {
      const stored = cached<LiveState>(key);
      try {
        if (!navigator.onLine) {
          if (!stored) throw new Error("No messages saved on this device yet.");
          if (alive) {
            cursor.current = stored.value.cursor;
            setLive({ ...stored.value, ready: true });
          }
          return;
        }
        const snapshot = await api<History>(base + "/messages");
        if (alive) {
          cursor.current = snapshot.last_seq;
          setLive({
            messages: snapshot.messages.sort((a, b) => a.seq - b.seq),
            cursor: snapshot.last_seq,
            next: snapshot.next_cursor,
            syncedAt: new Date().toISOString(),
            ready: true,
            denied: false,
          });
        }
      } catch (e) {
        if (!alive) return;
        const denied =
          e instanceof ApiError && [401, 403, 404].includes(e.status);
        if (denied) removeCache(key);
        setError(e as Error);
        if (!denied && stored) {
          cursor.current = stored.value.cursor;
          setLive({ ...stored.value, ready: true });
        } else setLive({ ...initialState, denied, ready: true });
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [base, key]);
  useEffect(() => {
    if (live.ready && !live.denied)
      saveCache(
        key,
        {
          ...live,
          messages: live.messages.filter((m) => !m.pending).slice(-150),
        },
        live.syncedAt,
      );
  }, [key, live]);
  useEffect(() => {
    if (!live.ready || live.denied || !online) return;
    let stopped = false,
      attempt = 0;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;
    function connect() {
      if (stopped) return;
      const ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`,
      );
      socket.current = ws;
      ws.onopen = () => {
        attempt = 0;
        setConnection("Live");
        ws.send(
          JSON.stringify({ type: "subscribe", workspace_id: workspace.id }),
        );
        ws.send(
          JSON.stringify({
            type: "subscribe",
            workspace_id: workspace.id,
            channel_id: channel.id,
            last_seq: cursor.current,
          }),
        );
        ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN)
            ws.send(JSON.stringify({ type: "ping" }));
        }, 15000);
      };
      ws.onmessage = (event) => {
        let data: LiveEvent;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        if (data.workspace_id !== workspace.id) return;
        if (data.type === "error") {
          if (
            ["access_revoked", "access_denied"].includes(data.data.code ?? "")
          ) {
            removeWorkspaceCache(
              user.id,
              workspace.id,
              data.channel_id ?? undefined,
            );
            if (data.channel_id)
              client.setQueryData<Channel[]>(
                channelsKey(workspace),
                (previous) =>
                  (previous ?? []).filter((c) => c.id !== data.channel_id),
              );
            if (!data.channel_id || data.channel_id === channel.id) {
              setLive({ ...initialState, ready: true, denied: true });
              setConnection("Access removed");
              ws.close();
            }
            void client.invalidateQueries({ queryKey: channelsKey(workspace) });
          }
          return;
        }
        if (data.data.channel && data.seq === null) {
          client.setQueryData<Channel[]>(channelsKey(workspace), (previous) => {
            const rows = (previous ?? []).filter(
              (c) => c.id !== data.data.channel!.id,
            );
            const result = [...rows, data.data.channel!];
            saveCache(channelCache(user, workspace), result);
            return result;
          });
        }
        if (data.channel_id !== channel.id) return;
        if (data.data.proposal) {
          const proposal = data.data.proposal as Proposal;
          client.setQueryData<ProposalPage>(
            ["proposals", workspace.id, channel.id],
            (old) => ({
              proposals: mergeProposals(old?.proposals ?? [], [proposal]),
              next_cursor: old?.next_cursor ?? null,
            }),
          );
          void client.invalidateQueries({
            queryKey: ["pending-proposals", workspace.id],
          });
        }
        if (data.data.run) {
          const run = data.data.run;
          client.setQueryData<import("@/lib/agent").AgentRun[]>(
            ["agent-runs", workspace.id, channel.id],
            (previous) => [
              run,
              ...(previous ?? []).filter((r) => r.id !== run.id),
            ],
          );
          void client.invalidateQueries({
            queryKey: ["agent-recent", workspace.id],
          });
        }
        if (data.seq !== null) {
          if (data.seq <= cursor.current) return;
          cursor.current = data.seq;
          setLive((previous) => {
            let messages = previous.messages;
            if (data.data.message && typeof data.data.message !== "string") {
              const incoming = data.data.message;
              messages = mergeMessages(messages, [incoming]);
              if (data.data.thread_root)
                messages = mergeMessages(messages, [data.data.thread_root]);
            }
            return {
              ...previous,
              messages,
              cursor: data.seq!,
              syncedAt: new Date().toISOString(),
            };
          });
        }
        if (data.type === "presence.update")
          setPresence(data.data.user_ids ?? []);
        if (data.type === "typing.start" && data.data.user_id !== user.id)
          setTyping((previous) => [
            ...new Set([...previous, data.data.user_id!]),
          ]);
        if (data.type === "typing.stop")
          setTyping((previous) =>
            previous.filter((id) => id !== data.data.user_id),
          );
      };
      ws.onclose = async (event) => {
        if (ping) clearInterval(ping);
        setPresence([]);
        setTyping([]);
        if (stopped) return;
        setConnection("Reconnecting…");
        if (event.code === 4001 || event.code === 1006) {
          try {
            await api<User>("/auth/me");
          } catch (e) {
            if (e instanceof ApiError && e.status === 401) {
              removeCache(key);
              setLive({ ...initialState, ready: true, denied: true });
              setConnection("Please log in again");
              return;
            }
          }
        }
        if (!stopped)
          reconnect = setTimeout(
            connect,
            Math.min(10000, 500 * 2 ** attempt++) + Math.random() * 200,
          );
      };
    }
    connect();
    return () => {
      stopped = true;
      if (reconnect) clearTimeout(reconnect);
      if (ping) clearInterval(ping);
      socket.current?.close();
    };
  }, [
    live.ready,
    live.denied,
    online,
    workspace,
    channel.id,
    user,
    client,
    key,
  ]);
  const typingEvent = useCallback(
    (active: boolean) => {
      const ws = socket.current,
        tick = Date.now();
      if (
        ws?.readyState === WebSocket.OPEN &&
        (!active || tick - lastTyping.current > 2000)
      ) {
        lastTyping.current = tick;
        ws.send(
          JSON.stringify({
            type: active ? "typing.start" : "typing.stop",
            workspace_id: workspace.id,
            channel_id: channel.id,
          }),
        );
      }
    },
    [workspace.id, channel.id],
  );
  async function loadOlder() {
    try {
      const page = await api<History>(base + `/messages?before=${live.next}`);
      setLive((previous) => ({
        ...previous,
        messages: mergeMessages(previous.messages, page.messages),
        next: page.next_cursor,
      }));
    } catch (e) {
      setError(e as Error);
    }
  }
  return {
    base,
    live,
    setLive,
    error,
    setError,
    online,
    connection,
    presence,
    typing,
    typingEvent,
    loadOlder,
  };
}

export function ChannelsPage({
  workspace,
  user,
}: {
  workspace: Workspace;
  user: User;
}) {
  const channels = useChannels(user, workspace);
  const [selected, setSelected] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const active =
    channels.data?.find((c) => c.id === selected) ??
    (selected ? undefined : channels.data?.[0]);
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("channel");
    if (id) queueMicrotask(() => setSelected(id));
    const select = (event: Event) => {
      const id = (event as CustomEvent<string>).detail;
      setSelected(id);
      setDrawer(false);
      const url = new URL(location.href);
      url.searchParams.set("channel", id);
      history.replaceState(null, "", url);
      window.dispatchEvent(new Event("tandem-channel-selection"));
    };
    window.addEventListener("tandem-channel", select);
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production")
      void prepareChatShell().catch(() => {});
    return () => window.removeEventListener("tandem-channel", select);
  }, []);
  function choose(id: string) {
    setSelected(id);
    setDrawer(false);
    const url = new URL(location.href);
    url.searchParams.set("channel", id);
    history.replaceState(null, "", url);
    window.dispatchEvent(new Event("tandem-channel-selection"));
  }
  return (
    <div className="channels-page">
      <div className="channel-picker-mobile">
        <Button variant="ghost" onClick={() => setDrawer(true)}>
          <Hash size={18} />
          Channels
        </Button>
        <span className="text-small text-muted">{workspace.name}</span>
      </div>
      <ConfirmDialog
        open={drawer}
        onOpenChange={setDrawer}
        title="Channels"
        description="Find your team's conversations."
        actions={false}
      >
        <ChannelNavigation
          workspace={workspace}
          user={user}
          selectedId={active?.id}
          choose={choose}
        />
        <Button variant="secondary" onClick={() => setDrawer(false)}>
          Done
        </Button>
      </ConfirmDialog>
      {active ? (
        <ChannelRoom
          key={workspace.id + active.id}
          workspace={workspace}
          user={user}
          channel={active}
        />
      ) : channels.isPending ? (
        <div className="loading" role="status">
          Opening channels…
        </div>
      ) : (
        <NoChannel onBack={() => setSelected(null)} />
      )}
    </div>
  );
}
function NoChannel({ onBack }: { onBack?: () => void }) {
  return (
    <div className="empty no-channel">
      <span className="icon-circle">
        <Lock />
      </span>
      <h1>You do not have access to this channel</h1>
      <p>
        It may be unavailable. Ask a workspace Admin for help. The agent only
        sees what you can see.
      </p>
      {onBack ? (
        <Button onClick={onBack}>Back to channels</Button>
      ) : (
        <Button asChild>
          <Link href="/channels">Back to channels</Link>
        </Button>
      )}
    </div>
  );
}

function ChannelRoom({
  workspace,
  user,
  channel,
}: {
  workspace: Workspace;
  user: User;
  channel: Channel;
}) {
  const router = useRouter();
  const room = useRoom(user, workspace, channel);
  const { base, live, setLive, online } = room;
  const proposals = useChannelProposals(workspace, user, channel.id, online);
  const [thread, setThread] = useState<string | null>(null);
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("proposal");
    if (!id || !live.ready || !online) return;
    const selected = proposals.data?.proposals.find((p) => p.id === id);
    if (selected) {
      const element = document.querySelector(
        `[data-proposal-id="${selected.id}"]`,
      );
      if (element) {
        element.scrollIntoView({ block: "center" });
        return;
      }
      void api<Message>(base + `/messages/${selected.trigger_message_id}`)
        .then((message) => {
          setLive((previous) => ({
            ...previous,
            messages: mergeMessages(previous.messages, [message]),
          }));
        })
        .catch(() => undefined);
    }
  }, [base, live.ready, online, proposals.data, setLive]);
  const [manage, setManage] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  useEffect(() => {
    const open = () => setAgentOpen(true);
    window.addEventListener("tandem-agent-open", open);
    if (new URLSearchParams(location.search).get("agent") === "1")
      queueMicrotask(open);
    return () => window.removeEventListener("tandem-agent-open", open);
  }, []);
  const [lightbox, setLightbox] = useState<Attachment | null>(null);
  const [edit, setEdit] = useState<Message | null>(null);
  const [remove, setRemove] = useState<Message | null>(null);
  const [taskMessage, setTaskMessage] = useState<Message | null>(null);
  const jumped = useRef(false);
  const list = useRef<HTMLDivElement>(null);
  const pin = useRef(true);
  const replyOpener = useRef<HTMLButtonElement | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const threadList = useRef<HTMLDivElement>(null);
  const [threadNext, setThreadNext] = useState<number | null>(null);
  const members = useQuery({
    queryKey: ["channel-members", channel.id],
    queryFn: () => api<ChannelMember[]>(base + "/members"),
    enabled: online && !live.denied,
  });
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: async (action: {
      kind: "edit" | "delete";
      message: Message;
      body?: string;
    }) =>
      action.kind === "delete"
        ? api(base + `/messages/${action.message.id}`, { method: "DELETE" })
        : api<Message>(base + `/messages/${action.message.id}`, {
            method: "PATCH",
            body: JSON.stringify({ body: action.body }),
          }),
    onSuccess: () => {
      setEdit(null);
      setRemove(null);
    },
  });
  useEffect(() => {
    const id = new URLSearchParams(location.search).get("message");
    if (!id || !live.ready || live.denied || !online || jumped.current) return;
    jumped.current = true;
    pin.current = false;
    let alive = true;
    void api<Message>(base + `/messages/${id}`)
      .then(async (message) => {
        let incoming = [message];
        if (message.thread_root_id) {
          const root = await api<Message>(
            base + `/messages/${message.thread_root_id}`,
          );
          incoming = [root, message];
          if (alive) setThread(root.id);
        }
        if (!alive) return;
        setLive((previous) => ({
          ...previous,
          messages: mergeMessages(previous.messages, incoming),
        }));
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            const target = document.querySelector<HTMLElement>(
              `[data-message-id="${message.id}"]`,
            );
            target?.scrollIntoView({ block: "center" });
            target?.focus({ preventScroll: true });
          }),
        );
      })
      .catch(room.setError);
    return () => {
      alive = false;
    };
  }, [base, live.ready, live.denied, online, setLive, room.setError]);
  useEffect(() => {
    if (pin.current && list.current)
      list.current.scrollTop = list.current.scrollHeight;
  }, [live.messages.length, thread]);
  useEffect(() => {
    const element = list.current;
    if (!element) return;
    const observer = new ResizeObserver(() => {
      if (pin.current) element.scrollTop = element.scrollHeight;
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (threadList.current)
      threadList.current.scrollTop = threadList.current.scrollHeight;
  }, [live.messages, thread]);
  useEffect(() => {
    if (!thread) return;
    threadRef.current?.focus();
    if (!navigator.onLine) return;
    void api<History>(base + `/threads/${thread}`)
      .then((data) => {
        setThreadNext(data.next_cursor);
        setLive((previous) => ({
          ...previous,
          messages: mergeMessages(previous.messages, [
            data.root!,
            ...data.messages,
          ]),
        }));
      })
      .catch(room.setError);
  }, [thread, base, setLive, room.setError]);
  useEffect(() => {
    if (
      !online ||
      !live.ready ||
      live.denied ||
      !live.messages.length ||
      document.visibilityState !== "visible"
    )
      return;
    // A read acknowledgement is itself an event; only acknowledge actual messages.
    const lastMessage = Math.max(
      ...live.messages.filter((m) => !m.pending).map((m) => m.seq),
      0,
    );
    if (lastMessage <= channel.last_read_seq) return;
    const timer = setTimeout(() => {
      void api(base + "/read", post({ last_read_seq: lastMessage }))
        .then(() =>
          client.invalidateQueries({ queryKey: channelsKey(workspace) }),
        )
        .catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [
    base,
    live.messages,
    live.ready,
    live.denied,
    online,
    channel.last_read_seq,
    client,
    workspace,
  ]);
  async function olderReplies() {
    try {
      const data = await api<History>(
        base + `/threads/${thread}?before=${threadNext}`,
      );
      setThreadNext(data.next_cursor);
      setLive((previous) => ({
        ...previous,
        messages: mergeMessages(previous.messages, data.messages),
      }));
    } catch (e) {
      room.setError(e as Error);
    }
  }
  function closeThread() {
    setThread(null);
    requestAnimationFrame(() => replyOpener.current?.focus());
  }
  function update(message: Message) {
    setLive((previous) => ({
      ...previous,
      messages: mergeMessages(previous.messages, [message]),
    }));
  }
  async function attempt(message: Message) {
    update({ ...message, pending: "sending" });
    try {
      const actual = await api<Message>(
        base + "/messages",
        post({
          body: message.body,
          client_message_id: message.client_message_id,
          thread_root_id: message.thread_root_id,
          attachment_ids: message.attachments.map((a) => a.id),
        }),
      );
      update(actual);
    } catch {
      setLive((previous) => {
        const acknowledged = previous.messages.some(
          (item) =>
            item.author.id === message.author.id &&
            item.client_message_id === message.client_message_id &&
            !item.pending,
        );
        return acknowledged
          ? previous
          : {
              ...previous,
              messages: mergeMessages(previous.messages, [
                { ...message, pending: "failed" },
              ]),
            };
      });
    }
  }
  function submit(
    body: string,
    attachments: Attachment[],
    root: string | null,
  ) {
    if (!navigator.onLine) return;
    const id = crypto.randomUUID();
    const message: Message = {
      id,
      workspace_id: workspace.id,
      channel_id: channel.id,
      body,
      author: { id: user.id, name: user.name },
      client_message_id: id,
      seq: Date.now() * 1000,
      thread_root_id: root,
      attachments,
      mentions: [],
      mentions_agent: false,
      created_at: new Date().toISOString(),
      edited_at: null,
      deleted_at: null,
      reply_count: 0,
      pending: "sending",
    };
    pin.current = true;
    void attempt(message);
  }
  function renderMessage(message: Message, grouped = false) {
    return (
      <article
        key={message.id}
        className={`chat-message ${grouped ? "grouped-message" : ""} ${message.pending ? "pending-message" : ""} ${message.author.type === "agent" ? "agent-message" : ""}`}
        dir="auto"
        data-message-id={message.id}
        tabIndex={-1}
      >
        {!grouped && (
          <span
            className={
              message.author.type === "agent"
                ? "agent-avatar"
                : `avatar avatar-color-${(message.author.id.charCodeAt(0) % 3) + 1}`
            }
            aria-hidden="true"
          >
            {message.author.type === "agent" ? (
              <Sparkles size={17} />
            ) : (
              message.author.name.slice(0, 1).toUpperCase()
            )}
          </span>
        )}
        <div className="chat-message-content">
          {!grouped && (
            <div className="message-meta">
              <strong>{message.author.name}</strong>
              <time dateTime={message.created_at}>
                {new Date(message.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </time>
              {message.edited_at && (
                <span className="text-small text-muted">Edited</span>
              )}
            </div>
          )}
          {message.deleted_at ? (
            <p className="text-muted">Message deleted</p>
          ) : (
            <>
              <SafeMarkdown body={message.body} />
              {proposals.data?.proposals
                .filter((p) => p.trigger_message_id === message.id)
                .map((p) => (
                  <ProposalCard
                    key={p.id}
                    proposal={p}
                    workspace={workspace}
                    user={user}
                    online={online}
                  />
                ))}
              {message.agent_run && <AgentSteps run={message.agent_run} />}
              {message.mentions_agent && (
                <span
                  className="chip chip-agent"
                  title="Ask the workspace agent to read or propose a change"
                >
                  <Sparkles size={12} />
                  Agent mentioned
                </span>
              )}
              {!!message.attachments.length && (
                <div className="message-images">
                  {message.attachments.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => setLightbox(a)}
                      aria-label="Open attached image"
                    >
                      <Image
                        unoptimized
                        src={a.url}
                        alt={`Image shared by ${message.author.name}`}
                        width={a.width}
                        height={a.height}
                      />
                      <span className="text-small">
                        Image · {Math.ceil(a.size / 1024)} KB
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {!message.thread_root_id && !message.pending && (
                <Button
                  variant="ghost"
                  className="reply-button"
                  onClick={(event) => {
                    replyOpener.current = event.currentTarget;
                    setThread(message.id);
                  }}
                >
                  <MessageSquare size={14} />
                  {message.reply_count
                    ? `${message.reply_count} ${message.reply_count === 1 ? "reply" : "replies"}`
                    : "Reply in thread"}
                </Button>
              )}
              {!message.pending &&
                (message.author.id === user.id ||
                  workspace.role !== "viewer") && (
                  <details className="message-actions">
                    <summary
                      aria-label={`Actions for message by ${message.author.name}`}
                    >
                      <MoreHorizontal size={18} />
                    </summary>
                    <div className="message-action-menu">
                      {workspace.role !== "viewer" && (
                        <Button
                          variant="ghost"
                          disabled={!online}
                          onClick={() => setTaskMessage(message)}
                        >
                          Create task from message
                        </Button>
                      )}
                      {message.author.id === user.id && (
                        <Button
                          variant="ghost"
                          onClick={() => {
                            mutation.reset();
                            setEdit(message);
                          }}
                          aria-label={`Edit message by ${message.author.name}`}
                        >
                          Edit
                        </Button>
                      )}
                      {(message.author.id === user.id ||
                        ["owner", "admin"].includes(workspace.role)) && (
                        <Button
                          variant="ghost"
                          onClick={() => {
                            mutation.reset();
                            setRemove(message);
                          }}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </details>
                )}
            </>
          )}
          {message.pending === "sending" && (
            <span className="text-small text-muted" role="status">
              Sending…
            </span>
          )}
          {message.pending === "failed" && (
            <div className="failed-send" role="status">
              Message wasn’t sent.
              <Button
                variant="ghost"
                disabled={!online}
                onClick={() => void attempt(message)}
              >
                Retry
              </Button>
            </div>
          )}
        </div>
      </article>
    );
  }
  if (live.denied) return <NoChannel />;
  const top = live.messages.filter((m) => !m.thread_root_id);
  const root = live.messages.find((m) => m.id === thread);
  const replies = live.messages.filter((m) => m.thread_root_id === thread);
  const typers = room.typing.map(
    (id) => members.data?.find((m) => m.user_id === id)?.name ?? "A teammate",
  );
  return (
    <div className={`channel-room ${thread ? "has-thread" : ""}`}>
      {taskMessage && (
        <NewTaskDialog
          workspace={workspace}
          user={user}
          projectId={channel.project_id ?? undefined}
          message={taskMessage}
          onClose={() => setTaskMessage(null)}
          onCreated={(task) => {
            router.push(`/tasks?task=${task.id}&project=${task.project_id}`);
          }}
        />
      )}
      <section className="channel-main" aria-label={`Channel ${channel.name}`}>
        <header className="channel-header">
          <div>
            <h1>
              {channel.is_private ? <Lock size={20} /> : <Hash size={22} />}{" "}
              {channel.name}
            </h1>
            <p>{channel.topic || "Your team's conversation"}</p>
          </div>
          <div className="row">
            <span className="presence-pill">
              <span className="presence-dot" />
              {room.presence.length} online
            </span>
            <Button
              variant="ghost"
              aria-label="Channel details"
              onClick={() => setManage(true)}
            >
              <MoreHorizontal size={20} />
            </Button>
          </div>
        </header>
        <div className="channel-tabs" role="tablist" aria-label="Channel views">
          <button role="tab" aria-selected="true">
            Chat
          </button>
          <button role="tab" disabled title="Coming soon">
            Board <span>Coming soon</span>
          </button>
          <button role="tab" disabled title="Coming soon">
            Docs <span>Coming soon</span>
          </button>
          <button
            className="agent-panel-tab"
            role="tab"
            aria-selected={agentOpen}
            onClick={() => setAgentOpen(!agentOpen)}
          >
            <Sparkles size={15} /> Agent
          </button>
        </div>
        <div className="connection-status" role="status">
          {!online
            ? `You are offline · Last sync ${live.syncedAt ? new Date(live.syncedAt).toLocaleString() : "unavailable"}. Drafts stay here; nothing is queued.`
            : room.connection}
          {channel.archived && " · Archived channel"}
        </div>
        <ErrorNotice error={room.error} />
        <div
          className="message-list"
          ref={list}
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label="Channel messages"
          onScroll={() => {
            if (list.current)
              pin.current =
                list.current.scrollHeight -
                  list.current.scrollTop -
                  list.current.clientHeight <
                80;
          }}
        >
          {live.next && (
            <Button
              variant="secondary"
              disabled={!online}
              onClick={() => void room.loadOlder()}
            >
              Load older messages
            </Button>
          )}
          {!live.ready ? (
            <p role="status">Loading messages…</p>
          ) : !top.length ? (
            <div className="chat-empty">
              <span className="icon-circle">
                <Hash />
              </span>
              <h2>This is the beginning of #{channel.name}</h2>
              <p>Say hello, share an update, or ask your team a question.</p>
            </div>
          ) : (
            top.map((message, index) => {
              const previous = top[index - 1];
              const date = new Date(message.created_at).toLocaleDateString();
              const sameDay =
                previous &&
                new Date(previous.created_at).toLocaleDateString() === date;
              const grouped =
                sameDay &&
                previous.author.id === message.author.id &&
                new Date(message.created_at).getTime() -
                  new Date(previous.created_at).getTime() <
                  300000;
              return (
                <div key={message.id}>
                  {!sameDay && (
                    <div className="date-divider">
                      <span>
                        {date === new Date().toLocaleDateString()
                          ? "Today"
                          : date}
                      </span>
                    </div>
                  )}
                  {renderMessage(message, !!grouped)}
                </div>
              );
            })
          )}
        </div>
        <AgentActivity
          workspace={workspace}
          channelId={channel.id}
          online={online}
        />
        <div className="typing-indicator" role="status">
          {typers.length > 0 && (
            <>
              <span className="typing-dots">•••</span>
              {typers.join(", ")} {typers.length > 1 ? "are" : "is"} typing
            </>
          )}
        </div>
        <Composer
          key={channel.id}
          id={`draft:${user.id}:${channel.id}:main`}
          label={`Message ${channel.name}`}
          disabled={!online || channel.archived}
          offline={!online}
          members={members.data ?? []}
          base={base}
          onTyping={room.typingEvent}
          onSubmit={(body, images) => submit(body, images, null)}
        />
      </section>
      {thread && root ? (
        <aside
          className="thread-panel"
          aria-label="Thread"
          ref={threadRef}
          tabIndex={-1}
          onKeyDown={(event) => {
            if (event.key === "Escape") closeThread();
          }}
        >
          <header className="thread-header">
            <Button
              className="thread-mobile-back"
              variant="ghost"
              aria-label="Back to channel"
              onClick={closeThread}
            >
              <ArrowLeft size={20} />
            </Button>
            <div>
              <h2>Thread</h2>
              <span className="text-small text-muted">#{channel.name}</span>
            </div>
            <Button
              variant="ghost"
              aria-label="Close thread"
              onClick={closeThread}
            >
              <X size={20} />
            </Button>
          </header>
          <div
            className="thread-messages"
            ref={threadList}
            role="log"
            aria-live="polite"
          >
            {threadNext && (
              <Button
                variant="secondary"
                disabled={!online}
                onClick={() => void olderReplies()}
              >
                Load older replies
              </Button>
            )}
            {renderMessage(root)}
            <div className="date-divider">
              <span>{root.reply_count} replies</span>
            </div>
            {replies.map((m) => renderMessage(m))}
          </div>
          <Composer
            key={thread}
            id={`draft:${user.id}:${channel.id}:${thread}`}
            label="Reply"
            disabled={!online || channel.archived || !!root.deleted_at}
            offline={!online}
            members={members.data ?? []}
            base={base}
            onTyping={room.typingEvent}
            onSubmit={(body, images) => submit(body, images, thread)}
          />
        </aside>
      ) : (
        !thread && (
          <aside
            className={`channel-context ${agentOpen ? "agent-panel-open" : ""}`}
            aria-label="Agent panel"
          >
            <AgentPanel
              workspace={workspace}
              channelId={channel.id}
              online={online}
              onClose={() => setAgentOpen(false)}
            />
          </aside>
        )
      )}
      <ConfirmDialog
        open={!!lightbox}
        onOpenChange={(open) => {
          if (!open) setLightbox(null);
        }}
        title="Shared image"
        description="An image from this conversation."
        actions={false}
      >
        {lightbox && (
          <Image
            unoptimized
            className="lightbox-image"
            src={lightbox.url}
            width={lightbox.width}
            height={lightbox.height}
            alt="Shared image enlarged"
          />
        )}
        <Button variant="secondary" onClick={() => setLightbox(null)}>
          Close
        </Button>
      </ConfirmDialog>
      <ConfirmDialog
        open={!!edit}
        onOpenChange={(open) => {
          if (!open) setEdit(null);
        }}
        title="Edit message"
        description="Only you can edit your message."
        actions={false}
      >
        <ErrorNotice error={mutation.error} />
        {edit && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutation.mutate({
                kind: "edit",
                message: edit,
                body: String(new FormData(e.currentTarget).get("body")),
              });
            }}
          >
            <label htmlFor="edit-body">Message</label>
            <textarea
              id="edit-body"
              className="input"
              name="body"
              defaultValue={edit.body}
              maxLength={4000}
              required
            />
            <div className="dialog-actions">
              <Button variant="secondary" onClick={() => setEdit(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                Save message
              </Button>
            </div>
          </form>
        )}
      </ConfirmDialog>
      <ConfirmDialog
        open={!!remove}
        onOpenChange={(open) => {
          if (!open) setRemove(null);
        }}
        title="Delete this message?"
        description="A deleted message placeholder stays in the conversation."
      >
        <ErrorNotice error={mutation.error} />
        <Button variant="secondary" onClick={() => setRemove(null)}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={mutation.isPending}
          onClick={() =>
            remove && mutation.mutate({ kind: "delete", message: remove })
          }
        >
          Delete message
        </Button>
      </ConfirmDialog>
      <ChannelDetails
        open={manage}
        setOpen={setManage}
        workspace={workspace}
        channel={channel}
        members={members.data ?? []}
        base={base}
      />
    </div>
  );
}

function Composer({
  id,
  label,
  disabled,
  offline,
  members,
  base,
  onTyping,
  onSubmit,
}: {
  id: string;
  label: string;
  disabled: boolean;
  offline: boolean;
  members: ChannelMember[];
  base: string;
  onTyping: (active: boolean) => void;
  onSubmit: (body: string, images: Attachment[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [images, setImages] = useState<Attachment[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [uploading, setUploading] = useState(false);
  const [mentionIndex, setMentionIndex] = useState(0);
  const [suggestions, setSuggestions] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null),
    file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    queueMicrotask(() => setDraft(cached<string>(id)?.value ?? ""));
  }, [id]);
  const query = draft.match(/@([^@\n]*)$/)?.[1];
  const options = [...members.map((m) => m.name), "Agent"]
    .filter(
      (name) =>
        query !== undefined &&
        name.toLowerCase().startsWith(query.toLowerCase()),
    )
    .slice(0, 6);
  function write(value: string) {
    setDraft(value);
    saveCache(id, value);
    setMentionIndex(0);
    setSuggestions(/@[^@\n]*$/.test(value));
    onTyping(!!value);
  }
  function mention(name: string) {
    const next = draft.replace(/@[^@\n]*$/, `@${name} `);
    write(next);
    setSuggestions(false);
    textarea.current?.focus();
  }
  function send() {
    if (
      disabled ||
      !navigator.onLine ||
      uploading ||
      (!draft.trim() && !images.length)
    )
      return;
    onSubmit(draft, images);
    setDraft("");
    saveCache(id, "");
    setImages([]);
    setSuggestions(false);
    onTyping(false);
    textarea.current?.focus();
  }
  async function upload(files: FileList | null) {
    if (!files || disabled) return;
    setError(null);
    if (images.length + files.length > 4) {
      setError(new Error("Attach up to four images per message."));
      return;
    }
    setUploading(true);
    const next: Attachment[] = [];
    try {
      for (const image of files) {
        if (image.size > 5 * 1024 * 1024)
          throw new Error("Each image must be 5 MB or smaller.");
        next.push(
          await api<Attachment>(base + "/attachments", {
            method: "POST",
            body: image,
            headers: {
              "Content-Type": image.type || "application/octet-stream",
            },
          }),
        );
      }
    } catch (e) {
      setError(e as Error);
    } finally {
      setImages((previous) => [...previous, ...next]);
      setUploading(false);
      if (file.current) file.current.value = "";
    }
  }
  return (
    <div className="composer">
      <ErrorNotice error={error} />
      {!!images.length && (
        <div className="composer-attachments">
          {images.map((a, index) => (
            <div key={a.id}>
              <Image
                unoptimized
                src={a.url}
                alt={`Pending image ${index + 1}`}
                width={a.width}
                height={a.height}
              />
              <Button
                variant="ghost"
                aria-label={`Remove image ${index + 1}`}
                onClick={() =>
                  setImages((previous) => previous.filter((i) => i.id !== a.id))
                }
              >
                <X size={16} />
              </Button>
            </div>
          ))}
        </div>
      )}
      {suggestions && !!options.length && (
        <div
          className="mention-options"
          id={`${id}-mentions`}
          role="listbox"
          aria-label="Mention suggestions"
        >
          {options.map((name, index) => (
            <button
              key={name}
              type="button"
              id={`${id}-mention-${index}`}
              role="option"
              aria-selected={index === mentionIndex}
              onMouseDown={(event) => event.preventDefault()}
              disabled={name === "Agent" && offline}
              onClick={() => mention(name)}
            >
              {name === "Agent" ? <Sparkles size={15} /> : <Users size={15} />}@
              {name}
              {name === "Agent" && (
                <span>{offline ? "Needs internet" : "Read or propose"}</span>
              )}
            </button>
          ))}
        </div>
      )}
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <textarea
        ref={textarea}
        id={id}
        value={draft}
        maxLength={4000}
        placeholder={offline ? "You are offline — keep writing a draft" : label}
        aria-label={label}
        aria-autocomplete="list"
        aria-controls={
          suggestions && options.length ? `${id}-mentions` : undefined
        }
        aria-activedescendant={
          suggestions && options.length
            ? `${id}-mention-${mentionIndex}`
            : undefined
        }
        rows={2}
        onChange={(event) => write(event.target.value)}
        onBlur={() => onTyping(false)}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing) return;
          if (suggestions && options.length) {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setMentionIndex(
                (previous) =>
                  (previous +
                    (event.key === "ArrowDown" ? 1 : options.length - 1)) %
                  options.length,
              );
              return;
            }
            if (event.key === "Enter" || event.key === "Tab") {
              event.preventDefault();
              mention(options[mentionIndex]);
              return;
            }
            if (event.key === "Escape") {
              setSuggestions(false);
              return;
            }
          }
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            send();
          }
        }}
      />
      <div className="composer-toolbar">
        <div className="row">
          <input
            ref={file}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="sr-only"
            tabIndex={-1}
            onChange={(event) => void upload(event.target.files)}
          />
          <Button
            variant="ghost"
            aria-label={`Attach image to ${label}`}
            disabled={disabled || uploading}
            onClick={() => file.current?.click()}
          >
            <Paperclip size={18} />
          </Button>
          <Button
            variant="ghost"
            aria-label={`Mention someone in ${label}`}
            onClick={() => {
              write(draft + "@");
              textarea.current?.focus();
            }}
          >
            @
          </Button>
          <span className="text-small text-muted">
            {uploading ? "Uploading…" : `${draft.length}/4000`}
          </span>
        </div>
        <div className="row">
          <button
            type="button"
            className="agent-mention-chip"
            disabled={offline}
            aria-label={
              offline ? "Agent needs an internet connection" : "Mention Agent"
            }
            title={
              offline
                ? "Agent needs an internet connection"
                : "Reads and proposes; changes need approval"
            }
            onClick={() => {
              write(draft + "@Agent ");
              textarea.current?.focus();
            }}
          >
            <Sparkles size={14} />
            Agent
          </button>
          <Button
            aria-label={`Send ${label}`}
            disabled={
              disabled || uploading || (!draft.trim() && !images.length)
            }
            onClick={send}
          >
            <Send size={16} />
          </Button>
        </div>
      </div>
      <div className="composer-help text-small text-muted">
        {offline
          ? "Agent needs an internet connection. Draft saved on this device. Press Send when you reconnect."
          : "Enter to send · Shift + Enter for a new line"}
      </div>
    </div>
  );
}

function ChannelDetails({
  open,
  setOpen,
  workspace,
  channel,
  members,
  base,
}: {
  open: boolean;
  setOpen: (value: boolean) => void;
  workspace: Workspace;
  channel: Channel;
  members: ChannelMember[];
  base: string;
}) {
  const client = useQueryClient();
  const canEdit = workspace.role !== "viewer",
    canManage = ["owner", "admin"].includes(workspace.role);
  const all = useQuery({
    queryKey: ["members", workspace.id],
    queryFn: () => api<Member[]>(`/workspaces/${workspace.id}/members`),
    enabled: open && canManage && channel.is_private,
  });
  const mutation = useMutation({
    mutationFn: (action: { url: string; method: string; body?: unknown }) =>
      api(base + action.url, {
        method: action.method,
        body: action.body ? JSON.stringify(action.body) : undefined,
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: channelsKey(workspace) });
      await client.invalidateQueries({
        queryKey: ["channel-members", channel.id],
      });
    },
  });
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={setOpen}
      title={`#${channel.name}`}
      description={
        channel.is_private
          ? "A private conversation for invited members."
          : "A public conversation for the workspace."
      }
      actions={false}
    >
      <ErrorNotice error={mutation.error} />
      {canEdit && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            mutation.mutate({
              url: "",
              method: "PATCH",
              body: { name: data.get("name"), topic: data.get("topic") },
            });
          }}
        >
          <Field
            label="Channel name"
            id="details-name"
            name="name"
            defaultValue={channel.name}
            required
            pattern="[a-z0-9][a-z0-9-]*"
            maxLength={64}
          />
          <Field
            label="Topic"
            id="details-topic"
            name="topic"
            defaultValue={channel.topic}
            maxLength={240}
          />
          <Button type="submit" disabled={mutation.isPending}>
            Save channel
          </Button>
          <Button
            variant="secondary"
            disabled={mutation.isPending}
            onClick={() =>
              mutation.mutate({
                url: "",
                method: "PATCH",
                body: { archived: !channel.archived },
              })
            }
          >
            {channel.archived ? "Unarchive" : "Archive"}
          </Button>
        </form>
      )}
      <h3>Members</h3>
      <div className="channel-members-list">
        {members.map((m) => (
          <div className="row-between" key={m.user_id}>
            <span>
              {m.name}
              <span className="text-small text-muted"> · {m.role}</span>
            </span>
            {canManage && channel.is_private && (
              <Button
                variant="ghost"
                disabled={mutation.isPending}
                onClick={() =>
                  mutation.mutate({
                    url: `/members/${m.user_id}`,
                    method: "DELETE",
                  })
                }
              >
                Remove
              </Button>
            )}
          </div>
        ))}
      </div>
      {canManage && channel.is_private && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({
              url: "/members",
              method: "POST",
              body: { user_id: new FormData(event.currentTarget).get("user") },
            });
          }}
        >
          <label htmlFor="add-channel-member">Add a workspace member</label>
          <select
            id="add-channel-member"
            name="user"
            className="input"
            required
          >
            {all.data
              ?.filter(
                (m) =>
                  !members.some((existing) => existing.user_id === m.user_id),
              )
              .map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.name}
                </option>
              ))}
          </select>
          <Button type="submit" disabled={mutation.isPending}>
            Add member
          </Button>
        </form>
      )}
      {!channel.is_private && (
        <Button
          variant="secondary"
          disabled={mutation.isPending}
          onClick={() =>
            mutation.mutate({
              url: channel.joined ? "/leave" : "/join",
              method: "POST",
            })
          }
        >
          {channel.joined ? "Leave channel" : "Join channel"}
        </Button>
      )}
      <Button variant="secondary" onClick={() => setOpen(false)}>
        Done
      </Button>
    </ConfirmDialog>
  );
}
