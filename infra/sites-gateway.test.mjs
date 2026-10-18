import test from "node:test";
import assert from "node:assert/strict";
import gateway from "./sites-gateway.mjs";

const env = {
  UPSTREAM_ORIGIN: "https://test.up.railway.app",
  TANDEM_GATEWAY_SECRET: "synthetic-".repeat(8),
};
test("private Site identity stays at Sites while Tandem sessions, CSRF and RSC pass through", async (t) => {
  let captured;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    captured = { url: String(url), ...options };
    const headers = new Headers();
    headers.append("set-cookie", "tandem_access=new; Path=/; Secure; HttpOnly");
    headers.append(
      "set-cookie",
      "tandem_refresh=refresh; Path=/; Secure; HttpOnly",
    );
    return new Response("saved", { status: 201, headers });
  });
  const request = new Request("https://private.chatgpt.site/api/tasks?x=1", {
    method: "POST",
    body: "synthetic",
    headers: {
      Cookie:
        "platform=private; tandem_access=access; tandem_refresh=refresh; tandem_csrf=csrf; other=hidden",
      Authorization: "Bearer platform-private",
      "OAI-Sites-Authorization": "private",
      "oai-authenticated-user-email": "private@example.com",
      Origin: "https://private.chatgpt.site",
      "X-CSRF-Token": "csrf",
      "x-tandem-gateway": "attacker",
      RSC: "1",
      "Next-Router-State-Tree": "tree",
    },
  });
  const response = await gateway.fetch(request, env);
  assert.equal(captured.url, "https://test.up.railway.app/api/tasks?x=1");
  assert.equal(
    captured.headers.get("cookie"),
    "tandem_access=access; tandem_refresh=refresh; tandem_csrf=csrf",
  );
  for (const name of [
    "authorization",
    "oai-sites-authorization",
    "oai-authenticated-user-email",
  ])
    assert.equal(captured.headers.get(name), null);
  assert.equal(
    captured.headers.get("x-tandem-gateway"),
    env.TANDEM_GATEWAY_SECRET,
  );
  assert.equal(captured.headers.get("origin"), "https://private.chatgpt.site");
  assert.equal(captured.headers.get("x-csrf-token"), "csrf");
  assert.equal(captured.headers.get("rsc"), "1");
  assert.equal(captured.headers.get("next-router-state-tree"), "tree");
  assert.equal(captured.redirect, "manual");
  assert.equal(captured.body, request.body);
  assert.equal(response.status, 201);
  assert.equal(response.headers.getSetCookie().length, 2);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
});
test("WebSocket response and upgrade headers are preserved", async (t) => {
  const socketResponse = { status: 101, webSocket: {} };
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options.headers.get("upgrade"), "websocket");
    assert.equal(options.headers.get("origin"), "https://private.chatgpt.site");
    return socketResponse;
  });
  assert.equal(
    await gateway.fetch(
      new Request("https://private.chatgpt.site/api/document-sync/w/d", {
        headers: {
          Upgrade: "websocket",
          Origin: "https://private.chatgpt.site",
        },
      }),
      env,
    ),
    socketResponse,
  );
});
test("fixed upstream cannot be replaced by a request path and redirects stay on the Site", async (t) => {
  t.mock.method(globalThis, "fetch", async (url) => {
    assert.equal(url.origin, env.UPSTREAM_ORIGIN);
    assert.equal(url.pathname, "//external.example/path");
    return new Response(null, {
      status: 307,
      headers: { Location: env.UPSTREAM_ORIGIN + "/login" },
    });
  });
  const response = await gateway.fetch(
    new Request("https://private.chatgpt.site//external.example/path"),
    env,
  );
  assert.equal(
    response.headers.get("location"),
    "https://private.chatgpt.site/login",
  );
});
test("missing configuration and network errors disclose no credentials", async (t) => {
  t.mock.method(globalThis, "fetch", async () => {
    throw Error(env.TANDEM_GATEWAY_SECRET);
  });
  assert.equal(
    (await gateway.fetch(new Request("https://private.chatgpt.site"), {}))
      .status,
    503,
  );
  const response = await gateway.fetch(
    new Request("https://private.chatgpt.site"),
    env,
  );
  assert.equal(response.status, 502);
  assert.ok(!(await response.text()).includes(env.TANDEM_GATEWAY_SECRET));
});
