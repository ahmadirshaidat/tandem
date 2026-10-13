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
const supported = new Set(["--cloud", "--no-open", "--skip-install", "--help"]);
const windows = process.platform === "win32";
const url = "http://localhost:3000/login";
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
    if (!page.ok || !(await page.text()).includes("Tandem")) return false;
    return true;
  } catch {
    return false;
  }
}

async function ready() {
  if (!(await frontendReady())) return false;
  try {
    const api = await fetch("http://localhost:3000/api/auth/csrf", {
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
          "Port 3000 is occupied by an app that is not ready. Stop that app before starting Tandem.",
        ),
      ),
    );
    probe.listen(3000, "0.0.0.0", () => probe.close(resolve));
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
        `DATABASE_URL=postgresql+psycopg://tandem:${password}@localhost:5432/tandem`,
        `JWT_SECRET=${randomBytes(32).toString("hex")}`,
        "FRONTEND_URL=http://localhost:3000",
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
  if (origin && origin !== "http://localhost:3000") {
    throw new Error(
      "This localhost launcher needs FRONTEND_URL=http://localhost:3000 in your development configuration. The existing value was preserved.",
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
      "node infra/dev.mjs [--no-open] [--skip-install] [--cloud]\nRequires Node.js 24 and running Docker Desktop. Starts the API/database, installs locked frontend dependencies, starts Next.js, then opens the browser. Ctrl+C stops the frontend; database data remains. --cloud uses the existing Codex proxy/trust helper.",
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
      run("docker", [
        "compose",
        "up",
        "-d",
        "--build",
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
        "3000",
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
