"""Build through the cloud's existing proxy, preserving DNS and TLS verification."""

import subprocess
from pathlib import Path

from cloud_environment import cloud_environment

root = Path(__file__).resolve().parents[1]
environment = cloud_environment()
raise SystemExit(
    subprocess.call(
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
        ],
        cwd=root,
        env=environment,
    )
)
