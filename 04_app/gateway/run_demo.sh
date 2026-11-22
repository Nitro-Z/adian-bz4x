#!/usr/bin/env bash
# Start the password-protected demo and expose it through a Cloudflare Quick Tunnel (changes on every start)
# and ngrok on the team's fixed domain (the address given to the judges).
#   ./run_demo.sh         -> start gateway (127.0.0.1:8080) + tunnel, print the public URL
#   ./run_demo.sh stop    -> stop gateway + tunnel
# Requires the TTS server to be running (../tts/run_server.sh --bg).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/../tts/env/bin/python"
CF="${CLOUDFLARED:-$HOME/.local/bin/cloudflared}"
NGROK_URL="${NGROK_URL:-$(cat "$DIR/.ngrok_url" 2>/dev/null)}"   # private, not in git

stop() {
  for f in gateway tunnel ngrok; do
    if [[ -f "$DIR/$f.pid" ]]; then kill "$(cat "$DIR/$f.pid")" 2>/dev/null || true; rm -f "$DIR/$f.pid"; fi
  done
  echo "stopped"
}

if [[ "${1:-}" == "stop" ]]; then stop; exit 0; fi

if [[ ! -f "$DIR/.credentials" ]]; then
  echo "adian:$("$PY" -c 'import secrets; print(secrets.token_urlsafe(9))')" > "$DIR/.credentials"
  chmod 600 "$DIR/.credentials"
fi

stop >/dev/null
nohup "$PY" "$DIR/gateway.py" > "$DIR/gateway.log" 2>&1 & echo $! > "$DIR/gateway.pid"
sleep 2
nohup "$CF" tunnel --no-autoupdate --url http://127.0.0.1:8080 > "$DIR/tunnel.log" 2>&1 & echo $! > "$DIR/tunnel.pid"
nohup ngrok http 8080 --url "$NGROK_URL" --log "$DIR/ngrok.log" --log-format logfmt > /dev/null 2>&1 & echo $! > "$DIR/ngrok.pid"

for _ in $(seq 1 30); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$DIR/tunnel.log" | head -1 || true)
  [[ -n "$URL" ]] && break
  sleep 1
done
echo "${URL:-(tunnel URL not found yet, see $DIR/tunnel.log)}" > "$DIR/url.txt"
echo "Demo URL : $(cat "$DIR/url.txt")"
echo "Password : $(cut -d: -f2- "$DIR/.credentials")"
echo "Judges   : $NGROK_URL  (password: $(cat "$DIR/.judge_password" 2>/dev/null || echo none))"
KEY=$("$PY" -c 'import hmac,hashlib,sys; pw=open(sys.argv[1]).read().strip().split(":",1)[1]; print(hmac.new(pw.encode(), b"adian-link-v1", hashlib.sha256).hexdigest()[:20])' "$DIR/.credentials")
echo "$KEY" > "$DIR/.access_key"; chmod 600 "$DIR/.access_key"
echo "Link vào thẳng (không cần gõ mật khẩu): $(cat "$DIR/url.txt")/?key=$KEY"
