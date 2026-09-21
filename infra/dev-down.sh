#!/bin/bash
# `make down` — stop everything `make up` started (and compose leftovers).
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.patchpilot"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

stop_port() { # port, label
  pids=$(lsof -ti "tcp:$1" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    rest=$(lsof -ti "tcp:$1" 2>/dev/null || true)
    if [ -n "$rest" ]; then
      # shellcheck disable=SC2086
      kill -9 $rest 2>/dev/null || true
    fi
  fi
  printf '  [ok] %s stopped (port %s free)\n' "$2" "$1"
}

stop_port "$API_PORT" "api"
stop_port "$WEB_PORT" "web"
rm -f "$RUN/api.pid" "$RUN/web.pid"

if [ -f "$RUN/ollama.pid" ]; then
  pid=$(cat "$RUN/ollama.pid")
  if kill -0 "$pid" 2>/dev/null; then kill "$pid" 2>/dev/null || true; fi
  rm -f "$RUN/ollama.pid"
  printf '  [ok] ollama (started by up) stopped\n'
else
  printf '  [skip] ollama daemon left running (not started by up)\n'
fi

docker rm -f patchpilot-db >/dev/null 2>&1 || true
printf '  [ok] postgres container removed\n'
docker compose -f "$ROOT/infra/docker-compose.yml" down >/dev/null 2>&1 || true

printf 'PatchPilot is down.\n'
