"""Build through the cloud's existing proxy, preserving DNS and TLS verification."""
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

root = Path(__file__).resolve().parents[1]
environment = os.environ.copy()
proxy = urlsplit(environment.get("HTTPS_PROXY", environment.get("https_proxy", "")))
if not proxy.hostname:
    raise SystemExit("The cloud build requires its existing HTTPS proxy.")
address = socket.getaddrinfo(proxy.hostname, proxy.port or 80, socket.AF_INET)[0][4][0]
environment["TANDEM_PROXY_HOST"] = proxy.hostname
environment["TANDEM_PROXY_IP"] = address
environment["DOCKER_CONFIG"] = str(root / ".local" / "docker")
raise SystemExit(subprocess.call(
    ["docker", "compose", "-f", "compose.yaml", "-f", "infra/compose.cloud.yaml",
     "--progress", "plain", "build", "backend"], cwd=root, env=environment,
))
