// Deploy as a private Sites Worker. All credentials are runtime secrets.
const forwardedHeaders = [
  "accept",
  "accept-language",
  "content-type",
  "origin",
  "user-agent",
  "x-csrf-token",
  "rsc",
  "next-router-state-tree",
  "next-router-prefetch",
  "next-router-segment-prefetch",
  "next-url",
  "range",
  "if-range",
  "upgrade",
  "connection",
  "sec-websocket-key",
  "sec-websocket-version",
  "sec-websocket-protocol",
  "sec-websocket-extensions",
];
const cookies = new Set(["tandem_access", "tandem_refresh", "tandem_csrf"]);
export default {
  async fetch(request, env) {
    let origin;
    try {
      origin = new URL(env.UPSTREAM_ORIGIN);
      if (
        origin.protocol !== "https:" ||
        origin.username ||
        origin.password ||
        origin.pathname !== "/" ||
        origin.search ||
        origin.hash ||
        !env.TANDEM_GATEWAY_SECRET ||
        env.TANDEM_GATEWAY_SECRET.length < 32
      )
        throw Error();
    } catch {
      return new Response("Tandem connection is unavailable", {
        status: 503,
        headers: { "Cache-Control": "private, no-store" },
      });
    }
    const incoming = new URL(request.url);
    // Assign path fields individually: a //evil.example path must never select a host.
    origin.pathname = incoming.pathname;
    origin.search = incoming.search;
    const headers = new Headers();
    for (const name of forwardedHeaders) {
      const value = request.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    const session = (request.headers.get("cookie") || "")
      .split(";")
      .map((v) => v.trim())
      .filter((v) => cookies.has(v.slice(0, v.indexOf("="))))
      .join("; ");
    if (session) headers.set("cookie", session);
    headers.set("x-tandem-gateway", env.TANDEM_GATEWAY_SECRET);
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", "https");
    let upstream;
    try {
      upstream = await fetch(origin, {
        method: request.method,
        headers,
        redirect: "manual",
        body: ["GET", "HEAD"].includes(request.method)
          ? undefined
          : request.body,
      });
    } catch {
      return new Response("Tandem connection is unavailable", {
        status: 502,
        headers: { "Cache-Control": "private, no-store" },
      });
    }
    // Cloudflare's response owns the accepted WebSocket; preserve it unchanged.
    if (upstream.status === 101) return upstream;
    const responseHeaders = new Headers(upstream.headers);
    responseHeaders.delete("x-tandem-gateway");
    responseHeaders.set("Cache-Control", "private, no-store");
    const location = responseHeaders.get("location");
    if (location) {
      const target = new URL(location, origin);
      if (target.origin === origin.origin) {
        responseHeaders.set(
          "location",
          incoming.origin + target.pathname + target.search + target.hash,
        );
      }
    }
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  },
};
