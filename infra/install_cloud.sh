#!/usr/bin/env bash
set -euo pipefail
cd /workspace/tandem
export UV_CACHE_DIR=/workspace/.cache/uv
export npm_config_cache=/workspace/.cache/npm
export DOCKER_CONFIG=/workspace/tandem/.local/docker
python3 infra/bootstrap.py
uv sync --project backend --frozen
(cd frontend && npm ci)
python3 infra/cloud_build.py
