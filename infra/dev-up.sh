#!/bin/bash
# `make up` — start the entire PatchPilot stack with one command:
# postgres+schema, ollama+model, sandbox image, FastAPI, Next.js.
# Idempotent: already-running pieces are detected and skipped.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.patchpilot"
mkdir -p "$RUN/logs"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

step() { printf '==> %s\n' "$1"; }
ok() { printf '  [ok] %s\n' "$1"; }
die() { printf '  [FAIL] %s\n' "$1" >&2; exit 1; }

wait_for() { # url, tries, label
  for _ in $(seq 1 "$2"); do
    if curl -s -o /dev/null --max-time 2 "$1"; then return 0; fi
    sleep 1
  done
  die "$3 not reachable at $1 (logs in $RUN/logs)"
}

step "postgres (pgvector/pgvector:pg16)"
docker rm -f patchpilot-db >/dev/null 2>&1 || true
docker run -d --name patchpilot-db \
  -e POSTGRES_USER=patchpilot -e POSTGRES_PASSWORD=patchpilot \
  -e POSTGRES_DB=patchpilot -p 5432:5432 pgvector/pgvector:pg16 >/dev/null \
  || die "could not start postgres container"
for _ in $(seq 1 30); do
  if docker exec patchpilot-db pg_isready -U patchpilot >/dev/null 2>&1; then break; fi
  sleep 1
done
docker cp "$ROOT/infra/sql/001_schema.sql" patchpilot-db:/tmp/001_schema.sql
docker exec patchpilot-db psql -U patchpilot -d patchpilot -f /tmp/001_schema.sql \
  >/dev/null || die "schema apply failed"
ok "postgres on :5432 + schema applied"

step "ollama (nomic-embed-text)"
if ! curl -s --max-time 3 http://localhost:11434/api/version >/dev/null 2>&1; then
  command -v ollama >/dev/null || die "ollama not installed (https://ollama.com)"
  nohup ollama serve >"$RUN/logs/ollama.log" 2>&1 &
  echo $! >"$RUN/ollama.pid"
  wait_for http://localhost:11434/api/version 30 "ollama"
else
  rm -f "$RUN/ollama.pid" # daemon pre-existed; down must not kill it
fi
if ! ollama list 2>/dev/null | grep -q nomic-embed-text; then
  ollama pull nomic-embed-text || die "embed model pull failed"
fi
ok "ollama on :11434 + nomic-embed-text"

step "sandbox image"
if [ -z "$(docker images -q patchpilot-sandbox-py:1 2>/dev/null)" ]; then
  docker build -t patchpilot-sandbox-py:1 \
    -f "$ROOT/api/src/patchpilot/sandbox/Dockerfile.target" \
    "$ROOT/api/src/patchpilot/sandbox" || die "sandbox image build failed"
fi
ok "patchpilot-sandbox-py:1"

step "FastAPI on :$API_PORT"
if curl -s -o /dev/null --max-time 2 "http://localhost:$API_PORT/health" 2>/dev/null; then
  ok "api already running"
else
  nohup uv run --project api uvicorn patchpilot.main:app \
    --port "$API_PORT" >"$RUN/logs/api.log" 2>&1 &
  echo $! >"$RUN/api.pid"
  wait_for "http://localhost:$API_PORT/health" 60 "api"
  ok "api up"
fi

step "Next.js on :$WEB_PORT"
if curl -s -o /dev/null --max-time 2 "http://localhost:$WEB_PORT/" 2>/dev/null; then
  ok "web already running"
else
  nohup bun --cwd web dev --port "$WEB_PORT" >"$RUN/logs/web.log" 2>&1 &
  echo $! >"$RUN/web.pid"
  wait_for "http://localhost:$WEB_PORT/" 90 "web"
  ok "web up"
fi

printf '\nPatchPilot is up:\n'
printf '  UI:  http://localhost:%s\n' "$WEB_PORT"
printf '  API: http://localhost:%s  (docs at /docs)\n' "$API_PORT"
printf 'Logs: %s/logs  |  Stop everything: make down\n' "$RUN"
