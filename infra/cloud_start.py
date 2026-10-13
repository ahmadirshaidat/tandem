"""Restart cloud services with their supported proxy DNS and trusted TLS configuration."""

import subprocess
from pathlib import Path

from cloud_environment import cloud_environment

root = Path(__file__).resolve().parents[1]
raise SystemExit(
    subprocess.call(
        [
            "docker",
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "infra/compose.cloud.yaml",
            "up",
            "-d",
            "--wait",
        ],
        cwd=root,
        env=cloud_environment(),
    )
)
