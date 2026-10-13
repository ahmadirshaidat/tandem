"""Use the machine's existing proxy and public CA without printing credential values."""

import os
import shutil
import socket
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def cloud_environment():
    environment = os.environ.copy()
    proxy = urlsplit(environment.get("HTTPS_PROXY", environment.get("https_proxy", "")))
    if not proxy.hostname:
        raise SystemExit("The cloud needs its existing HTTPS proxy.")
    certificate = Path(environment.get("SSL_CERT_FILE", ""))
    if not certificate.is_file():
        raise SystemExit("The cloud needs its existing trusted CA file.")
    if b"PRIVATE KEY" in certificate.read_bytes():
        raise SystemExit(
            "Runtime trust must use a public CA bundle, not a private key."
        )
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    shutil.copyfile(certificate, local / "cloud-ca.pem")
    # Public trust anchors must be readable by the non-root backend container.
    (local / "cloud-ca.pem").chmod(0o644)
    environment["TANDEM_PROXY_HOST"] = proxy.hostname
    environment["TANDEM_PROXY_IP"] = socket.getaddrinfo(
        proxy.hostname, proxy.port or 80, socket.AF_INET
    )[0][4][0]
    environment["DOCKER_CONFIG"] = str(local / "docker")
    return environment
