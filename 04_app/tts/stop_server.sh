#!/usr/bin/env bash
TTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$TTS_DIR/server.pid" ]] && kill "$(cat "$TTS_DIR/server.pid")" 2>/dev/null; then
  echo "stopped pid $(cat "$TTS_DIR/server.pid")"; rm -f "$TTS_DIR/server.pid"
else
  pkill -f "$TTS_DIR/server.py" && echo "stopped" || echo "not running"
  rm -f "$TTS_DIR/server.pid"
fi
