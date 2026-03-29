#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is not installed or not on PATH" >&2
  echo "install uv first, then rerun this script" >&2
  exit 1
fi

cd "${REPO_ROOT}"
uv tool install --editable .

cat <<'EOF'

Installed the mbot CLI with uv.

If `mbot` is not found in a fresh shell, run:

  uv tool update-shell

Then restart your shell and try:

  mbot --help

EOF
