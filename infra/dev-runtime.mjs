// Launcher probes and Windows process dispatch; contains no private configuration.
export function command(program, args, windows = process.platform === "win32") {
  // Only fixed launcher npm arguments reach cmd.exe; other executables run directly.
  return windows && program === "npm"
    ? ["cmd.exe", ["/d", "/s", "/c", `npm ${args.join(" ")}`]]
    : [program, args];
}

export async function servicesReady(
  originUrl,
  documentSyncUrl,
  fetcher = fetch,
) {
  try {
    const [api, sync] = await Promise.all([
      fetcher(`${originUrl}/api/auth/csrf`, {
        signal: AbortSignal.timeout(4000),
      }),
      fetcher(`${documentSyncUrl}/health`, {
        signal: AbortSignal.timeout(4000),
      }),
    ]);
    return (
      api.ok && sync.ok && typeof (await api.json()).csrf_token === "string"
    );
  } catch {
    return false;
  }
}
