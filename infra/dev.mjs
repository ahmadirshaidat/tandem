#!/usr/bin/env node
// Start the real app on the computer running this command, including Windows.
import { spawn, spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const frontend = path.join(root, "frontend");
const flags = new Set(process.argv.slice(2));
const supported = new Set([
  "--cloud",
  "--no-open",
  "--skip-install",
  "--skip-build",
  "--help",
]);
const windows = process.platform === "win32";
const cloud = flags.has("--cloud");
const port = cloud ? 3000 : 3001;
const originUrl = `http://localhost:${port}`;
const url = `${originUrl}/login`;
let server;

function command(program, args) {
  // npm.cmd needs the Windows command interpreter. All arguments here are fixed.
  return windows && program === "npm"
    ? ["cmd.exe", ["/d", "/s", "/c", `npm ${args.join(" ")}`]]
    : [program, args];
}

function run(program, args, cwd = root) {
  const [executable, arguments_] = command(program, args);
  const result = spawnSync(executable, arguments_, {
    cwd,
    stdio: "inherit",
    env: process.env,
  });
  if (result.error)
    throw new Error(
      `${program} could not start. Install it and add it to PATH.`,
    );
  if (result.status !== 0)
    throw new Error(
      `${program} failed (${result.status ?? result.signal}). Check its output above.`,
    );
}

async function frontendReady() {
  try {
    const page = await fetch(url, { signal: AbortSignal.timeout(4000) });
    if (
      !page.ok ||
      page.headers.get("x-tandem-project") !== "tandem-workspace-v1"
    )
      return false;
    return true;
  } catch {
    return false;
  }
}

async function ready() {
  if (!(await frontendReady())) return false;
  try {
    const api = await fetch(`${originUrl}/api/auth/csrf`, {
      signal: AbortSignal.timeout(4000),
    });
    return api.ok && typeof (await api.json()).csrf_token === "string";
  } catch {
    return false;
  }
}

async function requireFreePort() {
  await new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once("error", () =>
      reject(
        new Error(
          `Port ${port} is occupied by another project or an older server. It was left untouched. Use a free port before starting this new Tandem project.`,
        ),
      ),
    );
    probe.listen(port, "0.0.0.0", () => probe.close(resolve));
  });
}

function bootstrap() {
  const envFile = path.join(root, ".env");
  if (!existsSync(envFile)) {
    const password = randomBytes(24).toString("hex");
    writeFileSync(
      envFile,
      [
        `POSTGRES_PASSWORD=${password}`,
        `DATABASE_URL=postgresql+psycopg://tandem:${password}@localhost:${cloud ? 5432 : 5433}/tandem`,
        `JWT_SECRET=${randomBytes(32).toString("hex")}`,
        `FRONTEND_URL=${originUrl}`,
        ...(cloud
          ? []
          : [
              "COMPOSE_PROJECT_NAME=tandem-workspace-v1",
              "TANDEM_API_PORT=8001",
              "TANDEM_DB_PORT=5433",
            ]),
        "COOKIE_SECURE=false",
        "MAIL_MODE=outbox",
        "",
      ].join("\n"),
      { flag: "wx", mode: 0o600 },
    );
    console.log(
      "Created private development configuration. No credentials were printed.",
    );
  } else {
    console.log("Existing .env and data will be preserved.");
  }
  // Only inspect public runtime settings; never display or copy provider keys.
  const content = readFileSync(envFile, "utf8");
  const origin =
    process.env.FRONTEND_URL ??
    content
      .match(/^FRONTEND_URL=(.*)$/m)?.[1]
      ?.trim()
      .replace(/^["']|["']$/g, "");
  if (origin && origin !== originUrl) {
    throw new Error(
      `This new project's launcher needs FRONTEND_URL=${originUrl} in its own development configuration. The existing value was preserved.`,
    );
  }
  const secure =
    process.env.COOKIE_SECURE ??
    content.match(/^COOKIE_SECURE=(.*)$/m)?.[1]?.trim();
  const secureValue = secure?.replace(/^["']|["']$/g, "");
  if (/^(true|1)$/i.test(secureValue ?? "")) {
    throw new Error(
      "HTTP localhost needs COOKIE_SECURE=false. Use development configuration, preserving your production secrets.",
    );
  }
}

function openBrowser() {
  if (flags.has("--no-open")) return;
  const [program, args] = windows
    ? ["rundll32.exe", ["url.dll,FileProtocolHandler", url]]
    : process.platform === "darwin"
      ? ["open", [url]]
      : ["xdg-open", [url]];
  const browser = spawn(program, args, { stdio: "ignore", detached: true });
  browser.once("error", () => console.log(`Open ${url} in your browser.`));
  browser.unref();
}

function stopServer() {
  if (!server?.pid || server.exitCode !== null) return;
  if (windows)
    spawnSync("taskkill", ["/PID", String(server.pid), "/T", "/F"], {
      stdio: "ignore",
    });
  else {
    try {
      process.kill(-server.pid, "SIGTERM");
    } catch {
      /* Already stopped. */
    }
  }
}

try {
  for (const flag of flags)
    if (!supported.has(flag)) throw new Error(`Unknown option: ${flag}`);
  if (flags.has("--help")) {
    console.log(
      "node infra/dev.mjs [--no-open] [--skip-install] [--skip-build] [--cloud]\nRequires Node.js 24 and running Docker Desktop. This new desktop project uses localhost:3001, API 8001, database 5433, and separate tandem-workspace-v1 Docker data. Starts real services then opens the browser. Ctrl+C stops its frontend. --skip-build requires an existing backend image. --cloud preserves the existing cloud ports and proxy/trust helper.",
    );
  } else {
    if (Number(process.versions.node.split(".")[0]) < 24)
      throw new Error("Install Node.js 24 before starting Tandem.");
    const existingFrontend = await frontendReady();
    if (!existingFrontend) await requireFreePort();
    if (flags.has("--cloud")) {
      mkdirSync(path.join(root, ".local", "docker"), { recursive: true });
      process.env.DOCKER_CONFIG = path.join(root, ".local", "docker");
    }
    run("docker", ["info", "--format", "{{.ServerVersion}}"]);
    bootstrap();
    if (!existingFrontend && !flags.has("--skip-install"))
      run("npm", ["ci"], frontend);
    if (flags.has("--cloud")) {
      mkdirSync(path.join(root, ".local", "docker"), { recursive: true });
      process.env.DOCKER_CONFIG = path.join(root, ".local", "docker");
      run("python3", ["infra/cloud_start.py"]);
    } else {
      process.env.TANDEM_API_PORT = "8001";
      process.env.TANDEM_DOCUMENT_PORT = "8003";
      process.env.DOCUMENT_SYNC_URL = "http://127.0.0.1:8003";
      process.env.TANDEM_DB_PORT = "5433";
      process.env.FRONTEND_URL = originUrl;
      process.env.BACKEND_URL = "http://127.0.0.1:8001";
      run("docker", [
        "compose",
        "--ansi",
        "never",
        "--progress",
        "plain",
        "--project-name",
        "tandem-workspace-v1",
        "up",
        "-d",
        ...(flags.has("--skip-build") ? ["--no-build"] : ["--build"]),
        "--wait",
        "--wait-timeout",
        "120",
      ]);
    }
    if (existingFrontend) {
      if (!(await ready()))
        throw new Error(
          "The existing frontend cannot reach the API. Check BACKEND_URL and the startup output above.",
        );
      console.log(
        `Tandem and its API are ready at ${url}. Reusing the existing frontend.`,
      );
      openBrowser();
    } else {
      const [program, args] = command("npm", [
        "run",
        "dev",
        "--",
        "--port",
        String(port),
        "--hostname",
        flags.has("--cloud") ? "0.0.0.0" : "127.0.0.1",
      ]);
      server = spawn(program, args, {
        cwd: frontend,
        stdio: "inherit",
        env: process.env,
        detached: !windows,
      });
      let spawnError;
      server.once("error", (error) => {
        spawnError = error;
      });
      process.once("SIGINT", stopServer);
      process.once("SIGTERM", stopServer);
      let connected = false;
      const deadline = Date.now() + 120_000;
      while (Date.now() < deadline && server.exitCode === null && !spawnError) {
        if (await ready()) {
          connected = true;
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      if (!connected)
        throw new Error(
          "The frontend and API did not become ready. Check the startup output above. No existing data was removed.",
        );
      console.log(
        `\nTandem is ready at ${url}\nSign up, create a workspace, and invite your team. Keep this terminal open. Ctrl+C stops the frontend.\n`,
      );
      openBrowser();
      await new Promise((resolve) => server.once("close", resolve));
      if (server.exitCode !== null) process.exitCode = server.exitCode;
    }
  }
} catch (error) {
  console.error(error.message);
  stopServer();
  process.exitCode = 1;
}
