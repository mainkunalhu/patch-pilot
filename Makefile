.PHONY: dev up down db-direct db-schema lint test eval-quick eval

# One command to run everything (postgres+schema, ollama+model,
# sandbox image, FastAPI, Next.js) — and one to stop it all.
# Idempotent: already-running pieces are detected and skipped.
up:
	bash infra/dev-up.sh

down:
	bash infra/dev-down.sh

db-direct:
	docker run -d --name patchpilot-db -e POSTGRES_USER=patchpilot -e POSTGRES_PASSWORD=patchpilot -e POSTGRES_DB=patchpilot -p 5432:5432 pgvector/pgvector:pg16

db-schema:
	docker cp infra/sql/001_schema.sql patchpilot-db:/tmp/001_schema.sql
	docker exec patchpilot-db psql -U patchpilot -d patchpilot -f /tmp/001_schema.sql

dev-api:
	uv run --project api uvicorn patchpilot.main:app --reload --port 8000

dev-web:
	bun --cwd web dev

lint:
	uv run --project api ruff check api/src api/tests
	uv run --project api ruff format --check api/src api/tests
	bun --cwd web lint

test:
	uv run --project api pytest api/tests -q

eval-quick:
	uv run --project api python evals/run_evals.py --limit 5

eval:
	uv run --project api python evals/run_evals.py
