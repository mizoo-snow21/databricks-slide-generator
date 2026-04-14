#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$REPO_ROOT/frontend"
npm install
npm run build

cd "$REPO_ROOT/backend"
uv sync
uv run playwright install --with-deps chromium
