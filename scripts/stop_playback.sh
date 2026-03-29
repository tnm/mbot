#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-/dev/cu.usbserial-0001}"

send_off() {
  python3 - "$PORT" <<'PY'
from __future__ import annotations

import sys

from mbot.board import SerialLightBoard


port = sys.argv[1]
try:
    with SerialLightBoard(port) as board:
        board.send_off()
        print(f"sent OFF to {port}")
except Exception as exc:
    print(f"warning: could not send OFF to {port}: {exc}", file=sys.stderr)
PY
}

kill_matches() {
  local pattern="$1"
  pkill -f "$pattern" || true
}

send_off
kill_matches "mbot run "
kill_matches "mbot piece-play "
kill_matches "mbot midi-play "
kill_matches "timidity .*mbot/"
sleep 0.2
send_off
echo "stopped mbot playback"
