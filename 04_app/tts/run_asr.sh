#!/usr/bin/env bash
# Start the Breeze-ASR-25 speech-to-text server on 127.0.0.1:8101.
#   ./run_asr.sh          -> foreground
#   ./run_asr.sh --bg     -> background, log in asr.log, pid in asr.pid
#   ./run_asr.sh stop     -> stop the background server
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HF_HOME="$DIR/hf_cache" PYTHONUTF8=1
PY="$DIR/env/bin/python"
case "${1:-}" in
  --bg)
    if [[ -f "$DIR/asr.pid" ]] && kill -0 "$(cat "$DIR/asr.pid")" 2>/dev/null; then echo "already running"; exit 0; fi
    nohup "$PY" "$DIR/asr_server.py" > "$DIR/asr.log" 2>&1 & echo $! > "$DIR/asr.pid"
    echo "started pid $(cat "$DIR/asr.pid"); log: $DIR/asr.log (model load ~20 s)";;
  stop)
    [[ -f "$DIR/asr.pid" ]] && kill "$(cat "$DIR/asr.pid")" 2>/dev/null && rm -f "$DIR/asr.pid" && echo stopped || echo "not running";;
  *) exec "$PY" "$DIR/asr_server.py";;
esac
