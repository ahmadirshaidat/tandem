"""Build through the cloud's existing proxy, preserving DNS and TLS verification."""

import argparse
import subprocess
from pathlib import Path

from cloud_environment import cloud_environment

ROOT = Path(__file__).resolve().parents[1]
HOSTED = {
    "backend": ("infra/Dockerfile.hosted-backend", ".", "tandem-hosted-backend:local"),
    "document-sync": ("sync/Dockerfile.hosted", "sync", "tandem-document-sync:latest"),
    "frontend": ("frontend/Dockerfile", "frontend", "tandem-hosted-frontend:local"),
}


def build_hosted(name, environment):
    dockerfile, context, tag = HOSTED[name]
    source = (ROOT / dockerfile).read_text()
    # Railway rejects secret mounts. Add session-only trust to the Dockerfile
    # streamed to local Docker; the tracked hosted files and images retain no CA.
    for command, variable in (
        ("pip install --no-cache-dir uv==0.12.23", "PIP_CERT"),
        ("uv sync --frozen --no-dev", "SSL_CERT_FILE"),
        ("npm ci --omit=dev", "NODE_EXTRA_CA_CERTS"),
        ("npm ci --include=dev", "NODE_EXTRA_CA_CERTS"),
    ):
        source = source.replace(
            "RUN " + command,
            f"RUN --mount=type=secret,id=proxy_ca {variable}=/run/secrets/proxy_ca " + command,
        )
    command = [
        "docker",
        "build",
        "--file",
        "-",
        "--tag",
        tag,
        "--secret",
        "id=proxy_ca,src=" + environment["SSL_CERT_FILE"],
        "--add-host",
        environment["TANDEM_PROXY_HOST"] + ":" + environment["TANDEM_PROXY_IP"],
    ]
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        if key in environment:
            command += ["--build-arg", key + "=" + environment[key]]
    return subprocess.run(
        command + [context], input=source.encode(), cwd=ROOT, env=environment
    ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hosted", nargs="+", choices=HOSTED)
    args = parser.parse_args()
    environment = cloud_environment()
    if args.hosted:
        for name in args.hosted:
            code = build_hosted(name, environment)
            if code:
                return code
        return 0
    return subprocess.call(
        [
            "docker",
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "infra/compose.cloud.yaml",
            "--progress",
            "plain",
            "build",
            "backend",
            "document-sync",
        ],
        cwd=ROOT,
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
