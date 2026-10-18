import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { command, servicesReady } from "./dev-runtime.mjs";

test("Windows dispatch uses cmd.exe for npm and preserves argument order", () => {
  assert.deepEqual(
    command("npm", ["run", "dev", "--", "--port", "3001"], true),
    ["cmd.exe", ["/d", "/s", "/c", "npm run dev -- --port 3001"]],
  );
  assert.deepEqual(command("docker", ["compose", "up", "-d", "--wait"], true), [
    "docker",
    ["compose", "up", "-d", "--wait"],
  ]);
});
test("native npm dispatch actually starts on this OS", () => {
  const [program, args] = command("npm", ["--version"]);
  const result = spawnSync(program, args, { encoding: "utf8", timeout: 30000 });
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0);
  assert.match(result.stdout.trim(), /^\d+\.\d+\.\d+/);
});
test("non-npm processes preserve arguments containing spaces", () => {
  const [program, args] = command(process.execPath, [
    "-e",
    "process.stdout.write(process.argv[1])",
    "synthetic path with spaces",
  ]);
  const result = spawnSync(program, args, { encoding: "utf8" });
  assert.equal(result.status, 0);
  assert.equal(result.stdout, "synthetic path with spaces");
});
test("launcher help runs without Docker or creating configuration", () => {
  const result = spawnSync(
    process.execPath,
    [fileURLToPath(new URL("./dev.mjs", import.meta.url)), "--help"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0);
  assert.match(result.stdout, /document sync 8003/);
});
const response = (ok = true) => ({
  ok,
  json: async () => ({ csrf_token: "synthetic-csrf-only" }),
});
test("desktop readiness requires both API and document-sync health", async () => {
  const urls = [];
  assert.equal(
    await servicesReady(
      "http://localhost:3001",
      "http://127.0.0.1:8003",
      async (url) => {
        urls.push(url);
        return response();
      },
    ),
    true,
  );
  assert.deepEqual(urls.sort(), [
    "http://127.0.0.1:8003/health",
    "http://localhost:3001/api/auth/csrf",
  ]);
});
test("healthy API cannot hide a failed document service", async () => {
  assert.equal(
    await servicesReady(
      "http://localhost:3001",
      "http://127.0.0.1:8003",
      async (url) => response(!url.endsWith("/health")),
    ),
    false,
  );
});
test("unreachable document service keeps launcher unready", async () => {
  assert.equal(
    await servicesReady(
      "http://localhost:3000",
      "http://127.0.0.1:8002",
      async (url) => {
        if (url.endsWith("/health"))
          throw Error("synthetic refused connection");
        return response();
      },
    ),
    false,
  );
});
test("invalid API readiness payload cannot pass", async () => {
  assert.equal(
    await servicesReady(
      "http://localhost:3001",
      "http://127.0.0.1:8003",
      async () => ({ ok: true, json: async () => ({}) }),
    ),
    false,
  );
});
