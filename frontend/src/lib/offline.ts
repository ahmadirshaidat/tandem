const PREFIX = "tandem-chat:";
export type Cached<T> = { value: T; syncedAt: string };
export function cached<T>(key: string): Cached<T> | undefined {
  if (typeof window === "undefined") return;
  try {
    return (
      JSON.parse(localStorage.getItem(PREFIX + key) ?? "null") ?? undefined
    );
  } catch {
    return;
  }
}
export function saveCache<T>(
  key: string,
  value: T,
  syncedAt = new Date().toISOString(),
) {
  try {
    // Bound this app's cache, leaving other local applications and user files alone.
    const entries = Object.keys(localStorage).filter((k) =>
      k.startsWith(PREFIX),
    );
    if (entries.length >= 40 && !entries.includes(PREFIX + key))
      localStorage.removeItem(entries[0]);
    localStorage.setItem(PREFIX + key, JSON.stringify({ value, syncedAt }));
  } catch {
    /* A full/disabled browser store must not break live messaging. */
  }
}
export function removeCache(key: string) {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {}
}
export function removeWorkspaceCache(
  userId: string,
  workspaceId: string,
  channelId?: string,
) {
  const historyPrefix =
    PREFIX + `history:${userId}:${workspaceId}:` + (channelId ?? "");
  for (const key of Object.keys(localStorage))
    if (key.startsWith(historyPrefix)) localStorage.removeItem(key);
  removeCache(`channels:${userId}:${workspaceId}`);
  // Task details may contain links to this channel. Evict them on any observed revocation.
  for (const key of Object.keys(localStorage))
    if (key.startsWith(PREFIX + `tasks:${userId}:${workspaceId}:`))
      localStorage.removeItem(key);
}
export function clearChatCache() {
  for (const key of Object.keys(localStorage))
    if (key.startsWith(PREFIX)) localStorage.removeItem(key);
  if ("serviceWorker" in navigator)
    navigator.serviceWorker.controller?.postMessage({
      type: "clear-chat-shell",
    });
}

export async function prepareChatShell(path = "/channels") {
  if (!("serviceWorker" in navigator) || !navigator.onLine) return;
  await navigator.serviceWorker.register("/chat-sw.js");
  await navigator.serviceWorker.ready;
  const shell = await caches.open("tandem-chat-shell-v1");
  const assets = new Set(
    performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((name) => {
        const url = new URL(name);
        return (
          url.origin === location.origin &&
          url.pathname.startsWith("/_next/static/")
        );
      }),
  );
  assets.add(location.origin + path);
  await Promise.all(
    [...assets].map(async (url) => {
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          cache: "reload",
        });
        if (response.ok)
          await shell.put(url.endsWith(path) ? path : url, response);
      } catch {}
    }),
  );
}
