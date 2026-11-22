#!/usr/bin/env bash
# Keep the judges' demo alive: start whatever is not running, leave running parts alone.
# Run by cron at boot and every 5 minutes (crontab -l). Log: 04_app/keepalive.log (only when something was started).
#   TTS  (BreezyVoice, :8100)   -> tts/run_server.sh --bg
#   ASR  (Breeze-ASR-25, :8101) -> tts/run_asr.sh --bg
#   gateway (:8080), Cloudflare quick tunnel (internal URL), ngrok (fixed URL for the judges)
# Ollama (Gemma 4) is a system service and starts by itself; we only warm the model after a boot.
set -uo pipefail
APP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GW="$APP/gateway"
LOG="$APP/keepalive.log"
export PATH="/snap/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin"
NGROK_URL="${NGROK_URL:-$(cat "$GW/.ngrok_url" 2>/dev/null)}"   # private, not in git
CF="$HOME/.local/bin/cloudflared"
PY="$APP/tts/env/bin/python"

# Lock so two runs never overlap. Every child below is started with 9>&- so it does NOT inherit the lock
# (before 11/09, ngrok/cloudflared kept the old .keepalive.lock open and every later run exited here).
exec 9>"$APP/.keepalive.run.lock"
flock -n 9 || exit 0  # previous run still busy

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }
alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

# after a boot, wait for the network (ngrok / Cloudflare need it)
for _ in $(seq 1 24); do curl -s -m 5 -o /dev/null https://ngrok.com && break; sleep 5; done

if ! alive "$APP/tts/server.pid"; then
  log "starting TTS"; "$APP/tts/run_server.sh" --bg >> "$LOG" 2>&1 9>&-; sleep 40  # let it take its GPU memory first
fi
if ! alive "$APP/tts/asr.pid"; then
  log "starting ASR"; "$APP/tts/run_asr.sh" --bg >> "$LOG" 2>&1 9>&-
fi
if ! alive "$GW/gateway.pid"; then
  log "starting gateway"
  nohup "$PY" "$GW/gateway.py" > "$GW/gateway.log" 2>&1 9>&- & echo $! > "$GW/gateway.pid"
  sleep 3
  # warm Gemma 4 so the first visitor does not wait for the model load
  nohup curl -s -m 300 -o /dev/null http://127.0.0.1:11434/api/generate -d '{"model":"gemma4:26b","keep_alive":-1}' > /dev/null 2>&1 9>&- &
fi
# 11/12: Gemma 4 unloads itself after keep_alive expires (no free-text questions for a day), and the next visitor
# then waits ~22 s for the load while the gateway gives up after 12 s ("抱歉，我沒聽懂"). Every run: if it is not in
# memory, load it and keep it there (keep_alive -1 = until Ollama restarts).
if ! curl -s -m 5 http://127.0.0.1:11434/api/ps | grep -q '"gemma4:26b"'; then
  log "loading Gemma 4 into GPU memory"
  nohup curl -s -m 300 -o /dev/null http://127.0.0.1:11434/api/generate -d '{"model":"gemma4:26b","keep_alive":-1}' > /dev/null 2>&1 9>&- &
fi
if ! alive "$GW/ngrok.pid"; then
  log "starting ngrok ($NGROK_URL)"
  nohup ngrok http 8080 --url "$NGROK_URL" --log "$GW/ngrok.log" --log-format logfmt > /dev/null 2>&1 9>&- & echo $! > "$GW/ngrok.pid"
fi
if ! alive "$GW/tunnel.pid"; then
  log "starting Cloudflare tunnel (internal URL will change)"
  nohup "$CF" tunnel --no-autoupdate --url http://127.0.0.1:8080 > "$GW/tunnel.log" 2>&1 9>&- & echo $! > "$GW/tunnel.pid"
  for _ in $(seq 1 30); do
    URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$GW/tunnel.log" | head -1 || true)
    [[ -n "$URL" ]] && break; sleep 1
  done
  [[ -n "${URL:-}" ]] && echo "$URL" > "$GW/url.txt" && log "Cloudflare URL: $URL"
fi
