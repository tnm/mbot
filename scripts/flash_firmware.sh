#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/cu.usbserial-0001}"
shift || true

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${REPO_ROOT}/firmware/esp32/light_renderer"
IDF_EXPORT_SCRIPT="${IDF_EXPORT_SCRIPT:-/Users/tnm/esp/esp-idf/export.sh}"
if [[ "$#" -eq 0 ]]; then
  set -- flash
fi

if [[ ! -f "${IDF_EXPORT_SCRIPT}" ]]; then
  echo "error: ESP-IDF export script not found at ${IDF_EXPORT_SCRIPT}" >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}" ]]; then
  echo "error: firmware app directory not found at ${APP_DIR}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${IDF_EXPORT_SCRIPT}"
cd "${APP_DIR}"

exec idf.py -p "${PORT}" "$@"
