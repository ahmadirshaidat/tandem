"use client";
import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type User, type Workspace } from "./api";
import type { SocketEvent } from "./events.generated";
import { cached, removeWorkspaceCache, saveCache } from "./offline";
import {
  boardKey,
  mergeTaskPage,
  projectKey,
  taskCacheKey,
  type Project,
  type Task,
  type TaskPage,
} from "./tasks";
export function useTaskLive(
  workspace: Workspace,
  user: User,
  projectId: string,
  snapshot: TaskPage | undefined,
  online: boolean,
) {
  const client = useQueryClient();
  const cursor = useRef(0);
  const [connection, setConnection] = useState("Connecting…");
  const [announcement, setAnnouncement] = useState("");
  const ready = !!snapshot;
  const initial = snapshot?.last_seq ?? 0;
  useEffect(() => {
    if (!ready || !online) return;
    cursor.current = Math.max(
      initial,
      cached<TaskPage>(taskCacheKey(user, workspace, `board:${projectId}`))
        ?.value.last_seq ?? 0,
    );
    let stopped = false,
      attempt = 0;
    let ws: WebSocket;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let ping: ReturnType<typeof setInterval> | undefined;
    function connect() {
      if (stopped) return;
      ws = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`,
      );
      ws.onopen = () => {
        attempt = 0;
        setConnection("Live");
        ws.send(
          JSON.stringify({
            type: "subscribe",
            workspace_id: workspace.id,
            workspace_seq: cursor.current,
          }),
        );
        ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN)
            ws.send(JSON.stringify({ type: "ping" }));
        }, 15000);
      };
      ws.onmessage = (message) => {
        let event: SocketEvent;
        try {
          event = JSON.parse(message.data);
        } catch {
          return;
        }
        if (event.workspace_id !== workspace.id) return;
        if (
          event.type === "error" &&
          ["access_denied", "access_revoked"].includes(event.data.code ?? "")
        ) {
          removeWorkspaceCache(
            user.id,
            workspace.id,
            event.channel_id ?? undefined,
          );
          // Channel revocation also removes cached conversation links from details.
          client.removeQueries({ queryKey: ["task-detail", workspace.id] });
          if (!event.channel_id) {
            stopped = true;
            client.removeQueries({ queryKey: ["tasks", workspace.id] });
            client.removeQueries({ queryKey: projectKey(workspace) });
            void client.invalidateQueries({ queryKey: ["workspaces"] });
            setConnection("Access removed");
            ws.close();
          }
          return;
        }
        if (
          event.channel_id ||
          event.seq === null ||
          event.seq <= cursor.current
        )
          return;
        if (event.data.task) {
          const task = event.data.task;
          client.setQueryData<TaskPage>(
            boardKey(workspace, projectId),
            (old) => {
              if (!old) return old;
              const next = {
                ...mergeTaskPage(old, task, projectId),
                last_seq: event.seq!,
              };
              saveCache(
                taskCacheKey(user, workspace, `board:${projectId}`),
                next,
              );
              return next;
            },
          );
          client.setQueryData<Task>(
            ["task-detail", workspace.id, task.id, "task"],
            (old) => (old && old.version > task.version ? old : task),
          );
          if (!task.deleted_at)
            saveCache(
              taskCacheKey(user, workspace, `detail:${task.id}:task`),
              task,
            );
          void client.invalidateQueries({
            queryKey: ["task-detail", workspace.id, task.id],
            predicate: (query) => query.queryKey[3] !== "task",
          });
          setAnnouncement(
            `${task.key} ${event.type.replace("task.", "").replace("_", " ")}`,
          );
        }
        if (event.data.project) {
          const project = event.data.project;
          client.setQueryData<Project[]>(projectKey(workspace), (old) => {
            const next = (old ?? []).filter((item) => item.id !== project.id);
            if (!project.deleted_at) next.push(project);
            saveCache(taskCacheKey(user, workspace, "projects"), next);
            return next;
          });
        }
        cursor.current = event.seq;
      };
      ws.onclose = () => {
        if (ping) clearInterval(ping);
        if (stopped) return;
        setConnection("Reconnecting…");
        retry = setTimeout(
          () => {
            void api("/auth/me")
              .then(connect)
              .catch(() => {
                if (!stopped)
                  void client.invalidateQueries({ queryKey: ["me"] });
              });
          },
          Math.min(10000, 500 * 2 ** attempt++),
        );
      };
    }
    connect();
    return () => {
      stopped = true;
      if (retry) clearTimeout(retry);
      if (ping) clearInterval(ping);
      ws?.close();
    };
    // Changing the snapshot during replay must not reset its cursor or reconnect the socket.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspace.id, user.id, projectId, ready, online, client]);
  return { connection: online ? connection : "Offline", announcement };
}
