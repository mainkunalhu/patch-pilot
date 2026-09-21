# PatchPilot — Repo-Native Bug Fixer

Point it at any Python repo, describe a bug, and it finds the faulty functions, writes a patch, runs the tests in an isolated Docker sandbox, and shows a proven diff. A tiny Groq-powered Cursor/SWE-agent.

## Stack

- Python: FastAPI, Tree-sitter AST chunking, Docker sandbox pytest runner
- TS: Next.js diff UI (Hono BFF deferred to `gateway/`)
- Groq: `openai/gpt-oss-120b` coder, `openai/gpt-oss-20b` retriever-rewrite/judge
- Retrieval: local nomic-embed (Ollama) + BM25, Postgres + pgvector
- Evals: DeepEval, SWE-style fail-to-pass / pass-to-pass

## Quickstart (Phase 0)

```bash
cp .env.example .env          # add GROQ_API_KEY
make up                       # postgres + ollama
ollama pull nomic-embed-text  # local embed model
make dev-api                  # http://localhost:8000/health
make dev-web                  # http://localhost:3000
make lint && make test
```

## Layout

```text
api/      # uv FastAPI: ingest, indexer, retrieval, agent, sandbox, routers
web/      # bun Next.js diff UI
infra/    # docker-compose (pgvector + ollama) + sql schema
fixtures/ # sample buggy targets
evals/    # 50 curated bugs + DeepEval harness
```

## Evals (measured)

```bash
make eval-quick   # 5 curated bugs vs live stack (API + pgvector + Ollama + Docker)
```

Starter set (2026-09-21): **5/5 fixed (100%), median 362 tok/s**, DeepEval GEval correctness 0.7–1.0 on all fixed diffs. Reports land in `evals/results/` (git-ignored). Dataset schema supports 50 cases; `dataset.jsonl` curates 5 so far — verbal 42%-on-50 hiring line stays a target until measured.

## Roadmap

Phases 1–7 in `phases.md` (temp). Deferred: Hono BFF, TS/vitest sandbox.
