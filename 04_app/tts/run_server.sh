#!/usr/bin/env bash
# Start the BreezyVoice TTS server on 127.0.0.1:8100 (local only; the gateway proxies it).
#   ./run_server.sh          -> foreground
#   ./run_server.sh --bg     -> background (nohup), log in tts/server.log, pid in tts/server.pid
set -euo pipefail
TTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUTF8=1
export HF_HOME="$TTS_DIR/hf_cache"
export TTS_PORT="${TTS_PORT:-8100}"
export PATH="$TTS_DIR/env/bin:$PATH"
PY="$TTS_DIR/env/bin/python"
if [[ "${1:-}" == "--bg" ]]; then
  if [[ -f "$TTS_DIR/server.pid" ]] && kill -0 "$(cat "$TTS_DIR/server.pid")" 2>/dev/null; then
    echo "already running (pid $(cat "$TTS_DIR/server.pid"))"; exit 0
  fi
  nohup "$PY" "$TTS_DIR/server.py" > "$TTS_DIR/server.log" 2>&1 &
  echo $! > "$TTS_DIR/server.pid"
  echo "started pid $(cat "$TTS_DIR/server.pid"); log: $TTS_DIR/server.log (model load ~20-40 s)"
else
  exec "$PY" "$TTS_DIR/server.py"
fi
